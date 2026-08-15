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
STALE_CLAIM_THRESHOLD_SECONDS = 120  # claimed but publish() never even ran/finished
WEBHOOK_WAIT_TIMEOUT_SECONDS = 300  # accepted by platform, but no webhook ever arrived


@shared_task
def poll_due_scheduled_posts():
    """
    Runs on a Celery Beat schedule (every 15s, see CELERY_BEAT_SCHEDULE).

    Three jobs, in order:
    1. Reclaim TRULY stale claims -- a worker that crashed before ever
       reaching a successful publish() call (no platform_post_id yet)
       leaves a row stuck at "claimed"/"publishing" forever otherwise.
    2. Time out rows that WERE accepted by the platform (platform_post_id
       is set) but never got a webhook back within a much longer window.
       These must NOT be re-published -- fake_platform's own idempotency
       dedup means a republish with the same key returns the same
       platform_post_id WITHOUT firing a new webhook, which would loop
       this row forever instead of ever resolving. Mark failed instead.
    3. Claim newly-due rows via an atomic conditional UPDATE and dispatch
       one publish task per claimed row.

    State lives in ScheduledPost rows in the DB, not in Celery's broker,
    so a crashed worker or a restarted Beat process just means the next
    poll picks up exactly where things were left off.
    """
    now = timezone.now()

    stale_claim_cutoff = now - timedelta(seconds=STALE_CLAIM_THRESHOLD_SECONDS)
    reclaimed = ScheduledPost.objects.filter(
        status__in=["claimed", "publishing"],
        platform_post_id__isnull=True,
        claimed_at__lt=stale_claim_cutoff,
    ).update(status="queued", next_retry_at=None, claimed_by=None, claimed_at=None)
    if reclaimed:
        logger.warning("poll_due_scheduled_posts: reclaimed %d stale claim(s)", reclaimed)

    webhook_timeout_cutoff = now - timedelta(seconds=WEBHOOK_WAIT_TIMEOUT_SECONDS)
    timed_out = ScheduledPost.objects.filter(
        status="publishing",
        platform_post_id__isnull=False,
        claimed_at__lt=webhook_timeout_cutoff,
    ).update(status="failed", last_error="webhook not received within timeout")
    if timed_out:
        logger.warning(
            "poll_due_scheduled_posts: %d post(s) timed out waiting for webhook", timed_out
        )

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