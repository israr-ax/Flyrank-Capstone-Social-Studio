import json
import random
import time
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import FakePost
from .tasks import send_delivery_webhook

VALID_PLATFORMS = ("instagram", "x")


@csrf_exempt
@require_http_methods(["POST"])
def oauth_token(request):
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    platform = body.get("platform")
    if platform not in VALID_PLATFORMS:
        return JsonResponse({"error": "unknown_platform"}, status=400)

    # Not real OAuth -- just enough to exercise "receive a token, encrypt
    # it, store it, decrypt it, send it back as Authorization" end to end.
    token = f"fake-{platform}-{uuid.uuid4().hex}"
    return JsonResponse({"access_token": token, "expires_in": 3600})


@csrf_exempt
@require_http_methods(["POST"])
def publish(request, platform):
    if platform not in VALID_PLATFORMS:
        return JsonResponse({"error": "unknown_platform"}, status=400)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or len(auth_header) < 15:
        return JsonResponse({"error": "invalid_token"}, status=401)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"error": "missing_idempotency_key"}, status=400)

    caption = request.POST.get("caption", "")
    image = request.FILES.get("image")
    if not caption or not image:
        return JsonResponse({"error": "missing_caption_or_image"}, status=400)

    # Deterministic failure modes for demo/testing -- see FAKE_PLATFORM_CONTRACT.md
    if request.GET.get("force_429") == "1":
        resp = JsonResponse({"error": "rate_limited"}, status=429)
        resp["Retry-After"] = "5"
        return resp

    if request.GET.get("force_timeout") == "1":
        time.sleep(30)  # your adapter's requests timeout should fire first

    # Organic ~1-in-8 429 so the retry path gets exercised without always
    # needing the explicit flag. Controllable via settings so deterministic
    # tests (e.g. the idempotency hammer) can turn it off.
    simulate_random_429 = getattr(settings, "FAKE_PLATFORM_SIMULATE_RANDOM_429", True)
    if simulate_random_429 and random.randint(1, 8) == 1:
        resp = JsonResponse({"error": "rate_limited"}, status=429)
        resp["Retry-After"] = "3"
        return resp

    existing = FakePost.objects.filter(platform=platform, idempotency_key=idempotency_key).first()
    if existing:
        # Server-side dedup on OUR side, independent of the caller's own
        # idempotency check -- same response, no new row created.
        return JsonResponse({"platform_post_id": str(existing.id), "status": "accepted"}, status=202)

    fake_post = FakePost.objects.create(
        platform=platform, idempotency_key=idempotency_key, caption=caption
    )

    delay_override = request.GET.get("force_webhook_delay")
    countdown = int(delay_override) if delay_override else random.randint(2, 10)
    send_delivery_webhook.apply_async(args=[str(fake_post.id)], countdown=countdown)

    return JsonResponse({"platform_post_id": str(fake_post.id), "status": "accepted"}, status=202)