import hashlib
import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from scheduling.models import ScheduledPost

from .models import WebhookEvent


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.WEBHOOK_SHARED_SECRET, raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    # constant-time comparison -- a plain == here would leak timing info
    # an attacker could use to guess the signature byte by byte
    return hmac.compare_digest(expected, provided)


@csrf_exempt
@require_http_methods(["POST"])
def social_delivery_webhook(request):
    raw_body = request.body
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    valid = _verify_signature(raw_body, signature_header)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        payload = {"_raw": raw_body.decode("utf-8", errors="replace")}

    if not valid:
        # Logged for the audit trail, but NEVER touches ScheduledPost --
        # a forged webhook must not be able to move any status forward.
        WebhookEvent.objects.create(signature_valid=False, raw_payload=payload)
        return JsonResponse({"error": "invalid_signature"}, status=400)

    idempotency_key = payload.get("idempotency_key")
    scheduled_post = ScheduledPost.objects.filter(idempotency_key=idempotency_key).first()

    event = WebhookEvent.objects.create(
        signature_valid=True, raw_payload=payload, scheduled_post=scheduled_post
    )

    if scheduled_post:
        if payload.get("event") == "published":
            scheduled_post.status = "published"
            scheduled_post.platform_post_id = payload.get("platform_post_id")
            scheduled_post.published_at = timezone.now()
        elif payload.get("event") == "failed":
            scheduled_post.status = "failed"
            scheduled_post.last_error = "platform reported failed delivery"
        scheduled_post.save()

    event.processed_at = timezone.now()
    event.save(update_fields=["processed_at"])

    return JsonResponse({"status": "ok"}, status=200)