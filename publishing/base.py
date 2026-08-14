from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PublishResult:
    accepted: bool
    platform_post_id: Optional[str]
    retry_after_seconds: Optional[int]  # set only when accepted=False due to a 429
    error: Optional[str]


class SocialPublisher(ABC):
    """
    App-facing contract. Business logic (scheduling tasks, services)
    depends ONLY on this interface -- never imports FakeInstagramPublisher
    or FakeXPublisher directly. Adding a third platform later means adding
    one more subclass here, touching nothing upstream.
    """

    platform: str

    @abstractmethod
    def publish(self, *, image_path: str, caption: str, idempotency_key: str) -> PublishResult:
        """Must be safe to call twice with the same idempotency_key."""

    @abstractmethod
    def get_access_token(self) -> str:
        """Returns the decrypted token. Never logs it."""