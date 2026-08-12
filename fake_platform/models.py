import uuid
from django.db import models


class FakePost(models.Model):
    """
    This represents state on the *external* (simulated) platform - deliberately
    separate from scheduling.ScheduledPost. The fake platform does its own
    idempotency-key dedup here, independent of our own dedup logic, because
    that's what a real platform's API would do too. Two independent dedup
    layers is the point, not redundancy to remove.
    """

    PLATFORM_CHOICES = [("instagram", "Instagram"), ("x", "X")]
    STATUS_CHOICES = [("accepted", "Accepted"), ("published", "Published"), ("failed", "Failed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    idempotency_key = models.CharField(max_length=64, db_index=True)
    caption = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="accepted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "idempotency_key"], name="unique_fake_post_per_platform_key"
            )
        ]

    def __str__(self):
        return f"FakePost({self.platform}, {self.idempotency_key[:8]}...)"