from django.utils import timezone

from .idempotency import make_idempotency_key
from .models import ScheduledPost


def schedule_campaign_posts(campaign, scheduled_at=None):
    """
    Creates one ScheduledPost per PlatformAsset already generated for this
    campaign. Idempotent at the DB level via get_or_create + the
    unique_together constraint -- calling this twice for the same
    campaign does not create duplicate rows.
    """
    scheduled_at = scheduled_at or timezone.now()
    created = []
    for asset in campaign.platform_assets.all():
        key = make_idempotency_key(campaign.id, asset.platform)
        scheduled_post, _ = ScheduledPost.objects.get_or_create(
            campaign=campaign,
            platform=asset.platform,
            defaults={"scheduled_at": scheduled_at, "idempotency_key": key},
        )
        created.append(scheduled_post)
    return created