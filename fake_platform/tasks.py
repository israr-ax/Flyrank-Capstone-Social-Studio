import json

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import FakePost
from .signing import sign_payload


@shared_task(bind=True, max_retries=3)
def send_delivery_webhook(self, fake_post_id: str, event: str = "published"):
    try:
        fake_post = FakePost.objects.get(id=fake_post_id)
    except FakePost.DoesNotExist:
        return

    payload = {
        "platform_post_id": str(fake_post.id),
        "platform": fake_post.platform,
        "idempotency_key": fake_post.idempotency_key,
        "event": event,
        "timestamp": timezone.now().isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")
    signature = sign_payload(body, settings.WEBHOOK_SHARED_SECRET)

    try:
        response = requests.post(
            settings.OUR_WEBHOOK_URL,
            data=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        # our webhook receiver doesn't exist yet (Step 5) -- this will
        # legitimately fail and retry until then, which is expected
        raise self.retry(exc=exc, countdown=5)