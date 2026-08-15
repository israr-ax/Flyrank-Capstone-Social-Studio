from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from campaigns.models import BlogPost, Campaign
from content_pipeline.models import PlatformAsset
from fake_platform.models import FakePost
from publishing.base import PublishResult

from .idempotency import make_idempotency_key
from .models import ScheduledPost
from .services import schedule_campaign_posts
from .tasks import publish_scheduled_post


def _make_campaign():
    blog_post = BlogPost.objects.create(
        title="Test Post",
        body="Body text.",
        url="https://example.com/post",
        source_image=SimpleUploadedFile("src.jpg", b"fake-source-bytes"),
    )
    campaign = Campaign.objects.create(blog_post=blog_post)
    PlatformAsset.objects.create(
        campaign=campaign,
        platform="instagram",
        image=SimpleUploadedFile("variant.jpg", b"fake-variant-bytes"),
        caption="hello world",
    )
    return campaign


class ScheduleCampaignPostsTests(TestCase):
    """Covers ScheduledPost creation + get_or_create idempotency."""

    def test_creates_one_scheduled_post_per_asset(self):
        campaign = _make_campaign()
        created = schedule_campaign_posts(campaign)
        self.assertEqual(len(created), 1)
        self.assertEqual(ScheduledPost.objects.filter(campaign=campaign).count(), 1)

    def test_calling_twice_does_not_duplicate(self):
        campaign = _make_campaign()
        schedule_campaign_posts(campaign)
        schedule_campaign_posts(campaign)  # simulates a retried request
        self.assertEqual(ScheduledPost.objects.filter(campaign=campaign).count(), 1)

    def test_idempotency_key_is_deterministic(self):
        campaign = _make_campaign()
        key_1 = make_idempotency_key(campaign.id, "instagram")
        key_2 = make_idempotency_key(campaign.id, "instagram")
        self.assertEqual(key_1, key_2)


class AtomicClaimTests(TestCase):
    """Definition of Done: durable scheduling -- the claim itself must be
    race-safe without DB-specific locking."""

    def setUp(self):
        campaign = _make_campaign()
        self.scheduled_post = ScheduledPost.objects.create(
            campaign=campaign,
            platform="instagram",
            scheduled_at=timezone.now(),
            status="queued",
            idempotency_key=make_idempotency_key(campaign.id, "instagram"),
        )

    def test_second_claim_of_same_row_affects_zero_rows(self):
        first_claim = ScheduledPost.objects.filter(id=self.scheduled_post.id, status="queued").update(
            status="claimed"
        )
        second_claim = ScheduledPost.objects.filter(id=self.scheduled_post.id, status="queued").update(
            status="claimed"
        )
        self.assertEqual(first_claim, 1)
        self.assertEqual(second_claim, 0)


class StaleClaimReclaimTests(TestCase):
    """
    Definition of Done: 'Scheduling is durable: survives crash mid-batch,
    restarted worker doesn't double-post.'

    Simulates a worker that claimed a row and then crashed before
    finishing -- status stuck at "claimed", claimed_at in the past. The
    poller must reclaim it (reset to "queued") so it actually gets
    published, not left stuck forever.
    """

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone as tz

        campaign = _make_campaign()
        self.scheduled_post = ScheduledPost.objects.create(
            campaign=campaign,
            platform="instagram",
            scheduled_at=tz.now() - timedelta(minutes=5),
            status="claimed",  # simulates: worker claimed it, then crashed
            claimed_at=tz.now() - timedelta(minutes=5),  # 5 min ago = stale
            claimed_by="worker-that-crashed",
            idempotency_key=make_idempotency_key(campaign.id, "instagram"),
        )

    def test_stale_claim_gets_reclaimed_and_republished(self):
        from scheduling.tasks import poll_due_scheduled_posts

        with patch("scheduling.tasks.publish_scheduled_post.delay") as mock_delay:
            poll_due_scheduled_posts()

        self.scheduled_post.refresh_from_db()
        # after one poll cycle: reclaimed to "queued" then immediately
        # re-claimed and dispatched in the same cycle, since it's now due
        self.assertEqual(self.scheduled_post.status, "claimed")
        mock_delay.assert_called_once_with(str(self.scheduled_post.id))

    def test_fresh_claim_is_not_reclaimed(self):
        from django.utils import timezone as tz

        self.scheduled_post.claimed_at = tz.now()  # just claimed, not stale
        self.scheduled_post.save(update_fields=["claimed_at"])

        from scheduling.tasks import poll_due_scheduled_posts

        with patch("scheduling.tasks.publish_scheduled_post.delay"):
            poll_due_scheduled_posts()

        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.claimed_by, "worker-that-crashed")  # untouched


@override_settings(TOKEN_ENCRYPTION_KEY="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")
class PublishScheduledPostTaskTests(TestCase):
    """Retry-with-backoff logic, mocked at the publisher level."""

    def setUp(self):
        campaign = _make_campaign()
        self.scheduled_post = ScheduledPost.objects.create(
            campaign=campaign,
            platform="instagram",
            scheduled_at=timezone.now(),
            status="claimed",
            idempotency_key=make_idempotency_key(campaign.id, "instagram"),
        )

    @patch("scheduling.tasks.get_publisher")
    def test_accepted_result_sets_platform_post_id(self, mock_get_publisher):
        mock_publisher = MagicMock()
        mock_publisher.publish.return_value = PublishResult(
            accepted=True, platform_post_id="post-abc", retry_after_seconds=None, error=None
        )
        mock_get_publisher.return_value = mock_publisher

        publish_scheduled_post(str(self.scheduled_post.id))

        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.platform_post_id, "post-abc")
        self.assertEqual(self.scheduled_post.status, "publishing")  # webhook finalizes to "published"

    @patch("scheduling.tasks.get_publisher")
    def test_429_sets_next_retry_at_from_retry_after(self, mock_get_publisher):
        mock_publisher = MagicMock()
        mock_publisher.publish.return_value = PublishResult(
            accepted=False, platform_post_id=None, retry_after_seconds=9, error="rate_limited"
        )
        mock_get_publisher.return_value = mock_publisher

        before = timezone.now()
        publish_scheduled_post(str(self.scheduled_post.id))

        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.status, "queued")
        self.assertIsNotNone(self.scheduled_post.next_retry_at)
        expected_min = before + timezone.timedelta(seconds=8)  # small slack
        self.assertGreaterEqual(self.scheduled_post.next_retry_at, expected_min)

    @patch("scheduling.tasks.get_publisher")
    def test_non_claimed_row_is_skipped_not_republished(self, mock_get_publisher):
        self.scheduled_post.status = "published"
        self.scheduled_post.save(update_fields=["status"])

        publish_scheduled_post(str(self.scheduled_post.id))

        mock_get_publisher.assert_not_called()

    @patch("scheduling.tasks.get_publisher")
    def test_exhausting_max_attempts_marks_failed(self, mock_get_publisher):
        mock_publisher = MagicMock()
        mock_publisher.publish.return_value = PublishResult(
            accepted=False, platform_post_id=None, retry_after_seconds=None, error="timeout"
        )
        mock_get_publisher.return_value = mock_publisher

        self.scheduled_post.attempt_count = 4  # one more attempt = 5 = MAX_ATTEMPTS
        self.scheduled_post.save(update_fields=["attempt_count"])

        publish_scheduled_post(str(self.scheduled_post.id))

        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.status, "failed")
        self.assertEqual(self.scheduled_post.last_error, "timeout")


@override_settings(FAKE_PLATFORM_SIMULATE_RANDOM_429=False)
class IdempotencyHammerIntegrationTests(TestCase):
    """
    Definition of Done: 'Idempotent publishing: same (post, platform)
    published twice or retried after timeout -> exactly one post.'

    This hits the REAL fake_platform view (same Django project, no
    mocking) twice with the same Idempotency-Key -- true end-to-end proof,
    not a mocked approximation.

    Random 429s are deliberately disabled here (see class decorator) --
    this test proves idempotency dedup, not rate-limit handling, and a
    random 429 mid-test would make it flaky rather than actually testing
    the wrong thing.
    """

    @patch("fake_platform.views.send_delivery_webhook.apply_async")
    def test_duplicate_publish_requests_create_exactly_one_fake_post(self, mock_webhook_dispatch):
        headers = {
            "HTTP_AUTHORIZATION": "Bearer fake-instagram-hammer-test",
            "HTTP_IDEMPOTENCY_KEY": "hammer-key-001",
        }
        response_1 = self.client.post(
            "/fake/instagram/publish/",
            data={"caption": "hi", "image": SimpleUploadedFile("x.jpg", b"fake-bytes")},
            **headers,
        )
        response_2 = self.client.post(
            "/fake/instagram/publish/",
            data={"caption": "hi", "image": SimpleUploadedFile("x.jpg", b"fake-bytes")},
            **headers,
        )

        self.assertEqual(response_1.status_code, 202)
        self.assertEqual(response_2.status_code, 202)
        self.assertEqual(
            response_1.json()["platform_post_id"], response_2.json()["platform_post_id"]
        )
        self.assertEqual(
            FakePost.objects.filter(platform="instagram", idempotency_key="hammer-key-001").count(),
            1,
        )
        # webhook dispatch fires only once too -- second request never
        # created a second FakePost, so it never re-dispatched a webhook
        self.assertEqual(mock_webhook_dispatch.call_count, 1)

    @patch("fake_platform.views.send_delivery_webhook.apply_async")
    def test_ten_duplicate_requests_still_create_exactly_one_fake_post(self, mock_webhook_dispatch):
        headers = {
            "HTTP_AUTHORIZATION": "Bearer fake-instagram-hammer-test",
            "HTTP_IDEMPOTENCY_KEY": "hammer-key-002",
        }
        for _ in range(10):
            self.client.post(
                "/fake/instagram/publish/",
                data={"caption": "hi", "image": SimpleUploadedFile("x.jpg", b"fake-bytes")},
                **headers,
            )

        self.assertEqual(
            FakePost.objects.filter(platform="instagram", idempotency_key="hammer-key-002").count(),
            1,
        )