import uuid
from django.db import models


class ScheduledPost(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("claimed", "Claimed"),
        ("publishing", "Publishing"),
        ("published", "Published"),
        ("failed", "Failed"),
    ]
    PLATFORM_CHOICES = [("instagram", "Instagram"), ("x", "X")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE, related_name="scheduled_posts"
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    scheduled_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")

    # deterministic hash(campaign_id, platform) - same value across retries/restarts
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True)

    attempt_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    platform_post_id = models.CharField(max_length=100, null=True, blank=True)
    claimed_by = models.CharField(max_length=100, null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "platform"], name="unique_scheduled_post_per_campaign_platform"
            )
        ]

    def __str__(self):
        return f"{self.platform} for campaign {self.campaign_id} [{self.status}]"