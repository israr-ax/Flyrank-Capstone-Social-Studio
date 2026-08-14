import os
import tempfile
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings

from .adapters import FakeInstagramPublisher


@override_settings(TOKEN_ENCRYPTION_KEY="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")
class FakeInstagramPublisherTests(TestCase):
    def setUp(self):
        patcher = patch("publishing.adapters.get_or_create_token", return_value="fake-token")
        self.mock_token = patcher.start()
        self.addCleanup(patcher.stop)

        fd, self.image_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        with open(self.image_path, "wb") as f:
            f.write(b"fake-image-bytes")

    def tearDown(self):
        os.remove(self.image_path)

    @patch("publishing.adapters.requests.post")
    def test_202_returns_accepted_result(self, mock_post):
        mock_response = MagicMock(status_code=202)
        mock_response.json.return_value = {"platform_post_id": "post-123"}
        mock_post.return_value = mock_response

        result = FakeInstagramPublisher().publish(
            image_path=self.image_path, caption="hello", idempotency_key="key-1"
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.platform_post_id, "post-123")

    @patch("publishing.adapters.requests.post")
    def test_429_returns_retry_after_seconds(self, mock_post):
        mock_response = MagicMock(status_code=429, headers={"Retry-After": "7"})
        mock_post.return_value = mock_response

        result = FakeInstagramPublisher().publish(
            image_path=self.image_path, caption="hello", idempotency_key="key-2"
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.retry_after_seconds, 7)
        self.assertEqual(result.error, "rate_limited")

    @patch("publishing.adapters.requests.post")
    def test_timeout_returns_error_not_exception(self, mock_post):
        mock_post.side_effect = requests.Timeout()

        result = FakeInstagramPublisher().publish(
            image_path=self.image_path, caption="hello", idempotency_key="key-3"
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.error, "timeout")

    @patch("publishing.adapters.requests.post")
    def test_idempotency_key_sent_as_header(self, mock_post):
        mock_response = MagicMock(status_code=202)
        mock_response.json.return_value = {"platform_post_id": "post-123"}
        mock_post.return_value = mock_response

        FakeInstagramPublisher().publish(
            image_path=self.image_path, caption="hello", idempotency_key="unique-key-abc"
        )

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "unique-key-abc")