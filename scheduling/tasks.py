import logging
import os
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from publishing.adapters import get_publisher

from .models import ScheduledPost

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
CLAIM_BATCH_SIZE = 20


@shared_task
def poll_due_scheduled_posts():
    """
    Runs on a Celery Beat schedule (every 15s, see CELERY_BEAT_SCHEDULE).
    Claims due rows via an atomic conditional UPDATE (see note in
    scheduling app docs on why this replaces SELECT FOR UPDATE SKIP
    LOCKED for SQLite compatibility), then dispatches one publish task
    per claimed row. This is the piece that makes scheduling durable --
    state lives in ScheduledPost rows in the DB, not in Celery's broker,
    so a crashed worker or a restarted Beat process just means the next
    poll picks up exactly where things were left off.
    """
    now = timezone.now()
    due_ids = list(
        ScheduledPost.objects.filter(status="queued", scheduled_at__lte=now)
        .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
        .values_list("id", flat=True)[:CLAIM_BATCH_SIZE]
    )

    claimed_ids = []
    worker_id = f"worker-{os.getpid()}"
    for post_id in due_ids:
        # Atomic: only succeeds if status is STILL "queued" at the moment
        # of this UPDATE. A second process racing on the same row gets 0
        # rows affected here, not a lock wait -- this is what makes it
        # crash-safe without needing DB-specific locking syntax.
        updated = ScheduledPost.objects.filter(id=post_id, status="queued").update(
            status="claimed", claimed_at=now, claimed_by=worker_id
        )
        if updated:
            claimed_ids.append(post_id)

    for post_id in claimed_ids:
        publish_scheduled_post.delay(str(post_id))

    logger.info("poll_due_scheduled_posts: claimed %d of %d due rows", len(claimed_ids), len(due_ids))
    return {"due": len(due_ids), "claimed": len(claimed_ids)}


@shared_task
def publish_scheduled_post(scheduled_post_id: str):
    try:
        scheduled_post = ScheduledPost.objects.select_related("campaign").get(id=scheduled_post_id)
    except ScheduledPost.DoesNotExist:
        logger.warning("publish_scheduled_post: %s no longer exists", scheduled_post_id)
        return

    # Only proceed if this row is actually claimed -- guards against a
    # duplicate/late task execution (e.g. two Beat polls somehow both
    # dispatched the same id) from double-publishing.
    if scheduled_post.status != "claimed":
        logger.info(
            "publish_scheduled_post: skipping %s, status=%s (not claimed)",
            scheduled_post_id,
            scheduled_post.status,
        )
        return

    scheduled_post.status = "publishing"
    scheduled_post.attempt_count += 1
    scheduled_post.save(update_fields=["status", "attempt_count"])

    asset = scheduled_post.campaign.platform_assets.filter(platform=scheduled_post.platform).first()
    if not asset:
        scheduled_post.status = "failed"
        scheduled_post.last_error = "no PlatformAsset found for this campaign/platform"
        scheduled_post.save(update_fields=["status", "last_error"])
        return

    publisher = get_publisher(scheduled_post.platform)
    result = publisher.publish(
        image_path=asset.image.path,
        caption=asset.caption,
        idempotency_key=scheduled_post.idempotency_key,
    )

    if result.accepted:
        # Accepted != published. Status stays "publishing" until the
        # webhook receiver verifies delivery and moves it to "published".
        scheduled_post.platform_post_id = result.platform_post_id
        scheduled_post.last_error = None
        scheduled_post.save(update_fields=["platform_post_id", "last_error"])
        return

    if result.retry_after_seconds is not None:
        # 429 -- honor Retry-After exactly, don't guess a backoff value.
        scheduled_post.status = "queued"
        scheduled_post.next_retry_at = timezone.now() + timedelta(seconds=result.retry_after_seconds)
        scheduled_post.last_error = result.error
        scheduled_post.save(update_fields=["status", "next_retry_at", "last_error"])
        logger.info(
            "publish_scheduled_post: %s rate-limited, retrying in %ss",
            scheduled_post_id,
            result.retry_after_seconds,
        )
        return

    if scheduled_post.attempt_count >= MAX_ATTEMPTS:
        scheduled_post.status = "failed"
        scheduled_post.last_error = result.error
        scheduled_post.save(update_fields=["status", "last_error"])
        logger.warning(
            "publish_scheduled_post: %s failed permanently after %d attempts: %s",
            scheduled_post_id,
            scheduled_post.attempt_count,
            result.error,
        )
        return

    # Transient failure (timeout, connection error) -- exponential
    # backoff, capped at 60s, since the platform didn't tell us how long
    # to wait.
    backoff_seconds = min(60, 2**scheduled_post.attempt_count)
    scheduled_post.status = "queued"
    scheduled_post.next_retry_at = timezone.now() + timedelta(seconds=backoff_seconds)
    scheduled_post.last_error = result.error
    scheduled_post.save(update_fields=["status", "next_retry_at", "last_error"])