import uuid
from django.db import models


class PlatformAsset(models.Model):
    PLATFORM_CHOICES = [("instagram", "Instagram"), ("x", "X")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE, related_name="platform_assets"
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    image = models.ImageField(upload_to="platform_variants/")
    caption = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "platform"], name="unique_asset_per_campaign_platform"
            )
        ]

    def __str__(self):
        return f"{self.platform} asset for {self.campaign_id}"