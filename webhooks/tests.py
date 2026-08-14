import hashlib
import hmac
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from campaigns.models import BlogPost, Campaign
from scheduling.models import ScheduledPost

from .models import WebhookEvent


@override_settings(WEBHOOK_SHARED_SECRET=b"test-secret")
class WebhookSignatureTests(TestCase):
    """Definition of Done: 'Delivery webhooks are signature-verified;
    forged/modified -> 400' and 'Campaign status updates only after a
    verified webhook'"""

    def setUp(self):
        self.blog_post = BlogPost.objects.create(
            title="Test Post",
            body="Body text here.",
            url="https://example.com/post",
            source_image=SimpleUploadedFile("x.jpg", b"fake-image-bytes"),
        )
        self.campaign = Campaign.objects.create(blog_post=self.blog_post)
        self.scheduled_post = ScheduledPost.objects.create(
            campaign=self.campaign,
            platform="instagram",
            scheduled_at=timezone.now(),
            idempotency_key="key-abc123",
        )

    def _sign(self, body: bytes) -> str:
        digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_valid_signature_updates_status(self):
        payload = {
            "platform_post_id": "post-1",
            "platform": "instagram",
            "idempotency_key": "key-abc123",
            "event": "published",
            "timestamp": "2026-01-01T00:00:05Z",
        }
        body = json.dumps(payload).encode()
        response = self.client.post(
            "/api/webhook/social-delivery/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
        )
        self.assertEqual(response.status_code, 200)
        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.status, "published")

    def test_forged_signature_rejected_and_state_untouched(self):
        payload = {"idempotency_key": "key-abc123", "event": "published"}
        body = json.dumps(payload).encode()
        response = self.client.post(
            "/api/webhook/social-delivery/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=" + "0" * 64,
        )
        self.assertEqual(response.status_code, 400)
        self.scheduled_post.refresh_from_db()
        self.assertEqual(self.scheduled_post.status, "queued")  # never touched

    def test_missing_signature_rejected(self):
        body = json.dumps({"idempotency_key": "key-abc123"}).encode()
        response = self.client.post(
            "/api/webhook/social-delivery/", data=body, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_all_events_logged_valid_and_forged(self):
        body = json.dumps({"idempotency_key": "key-abc123", "event": "published"}).encode()
        self.client.post(
            "/api/webhook/social-delivery/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._sign(body),
        )
        self.client.post(
            "/api/webhook/social-delivery/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=" + "f" * 64,
        )
        self.assertEqual(WebhookEvent.objects.count(), 2)
        self.assertEqual(WebhookEvent.objects.filter(signature_valid=True).count(), 1)
        self.assertEqual(WebhookEvent.objects.filter(signature_valid=False).count(), 1)