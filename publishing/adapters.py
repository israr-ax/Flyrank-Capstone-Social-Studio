import requests
from django.conf import settings

from .base import PublishResult, SocialPublisher
from .token_store import get_or_create_token

# Shorter than fake_platform's force_timeout=1 sleep (30s) on purpose --
# this is what actually triggers our own timeout handling in a demo.
PUBLISH_TIMEOUT_SECONDS = 8


class BaseFakePublisher(SocialPublisher):
    """
    Shared HTTP mechanics for both fake-platform adapters. Only `platform`
    differs between the two concrete classes below -- this base class is
    the ONE place in the whole project that knows fake_platform's HTTP
    contract (headers, status codes, response shape).
    """

    platform: str = ""

    def get_access_token(self) -> str:
        return get_or_create_token(self.platform)

    def publish(self, *, image_path: str, caption: str, idempotency_key: str) -> PublishResult:
        url = f"{settings.FAKE_PLATFORM_BASE_URL}{self.platform}/publish/"
        token = self.get_access_token()

        try:
            with open(image_path, "rb") as image_file:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Idempotency-Key": idempotency_key,
                    },
                    data={"caption": caption},
                    files={"image": image_file},
                    timeout=PUBLISH_TIMEOUT_SECONDS,
                )
        except requests.Timeout:
            return PublishResult(
                accepted=False, platform_post_id=None, retry_after_seconds=None, error="timeout"
            )
        except requests.RequestException as exc:
            return PublishResult(
                accepted=False, platform_post_id=None, retry_after_seconds=None, error=str(exc)
            )

        if response.status_code == 202:
            body = response.json()
            return PublishResult(
                accepted=True,
                platform_post_id=body["platform_post_id"],
                retry_after_seconds=None,
                error=None,
            )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "5"))
            return PublishResult(
                accepted=False,
                platform_post_id=None,
                retry_after_seconds=retry_after,
                error="rate_limited",
            )

        return PublishResult(
            accepted=False,
            platform_post_id=None,
            retry_after_seconds=None,
            error=f"http_{response.status_code}: {response.text}",
        )


class FakeInstagramPublisher(BaseFakePublisher):
    platform = "instagram"


class FakeXPublisher(BaseFakePublisher):
    platform = "x"


def get_publisher(platform: str) -> SocialPublisher:
    """Factory -- callers ask for a platform string, never import a
    concrete class. This is the one function scheduling tasks call."""
    publishers = {"instagram": FakeInstagramPublisher, "x": FakeXPublisher}
    if platform not in publishers:
        raise ValueError(f"no publisher registered for platform: {platform}")
    return publishers[platform]()