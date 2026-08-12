import uuid
from django.db import models


class WebhookEvent(models.Model):
    """
    Every webhook we receive gets a row here, valid signature or not.
    This is the audit trail for the forged-webhook Definition of Done item
    -- you need to be able to show a rejected forged webhook AND a valid
    one side by side.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    received_at = models.DateTimeField(auto_now_add=True)
    signature_valid = models.BooleanField()
    raw_payload = models.JSONField()
    scheduled_post = models.ForeignKey(
        "scheduling.ScheduledPost",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"webhook {self.id} valid={self.signature_valid}"