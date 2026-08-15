from rest_framework import serializers

from content_pipeline.captions import compose_caption
from content_pipeline.images import generate_variant
from content_pipeline.models import PlatformAsset
from scheduling.models import ScheduledPost
from scheduling.services import schedule_campaign_posts

from .models import BlogPost, Campaign

PLATFORMS = ("instagram", "x")


class PlatformAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformAsset
        fields = ["platform", "image", "caption"]


class ScheduledPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledPost
        fields = [
            "platform",
            "status",
            "scheduled_at",
            "attempt_count",
            "platform_post_id",
            "last_error",
            "published_at",
        ]


class CampaignDetailSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)  # Campaign.status is the derived @property
    platform_assets = PlatformAssetSerializer(many=True, read_only=True)
    scheduled_posts = ScheduledPostSerializer(many=True, read_only=True)

    class Meta:
        model = Campaign
        fields = ["id", "blog_post", "status", "created_at", "platform_assets", "scheduled_posts"]


class CampaignCreateSerializer(serializers.Serializer):
    """
    Input-only serializer -- validates the blog post fields, then does the
    full pipeline in .create(): BlogPost -> Campaign -> PlatformAsset per
    platform (caption + image variant) -> ScheduledPost per platform.
    Any validation failure here is a 400, never a 500 -- DRF handles that
    automatically via .is_valid(raise_exception=True) in the view.
    """

    title = serializers.CharField(max_length=300)
    body = serializers.CharField()
    url = serializers.URLField()
    source_image = serializers.ImageField()
    scheduled_at = serializers.DateTimeField(required=False)

    def create(self, validated_data):
        blog_post = BlogPost.objects.create(
            title=validated_data["title"],
            body=validated_data["body"],
            url=validated_data["url"],
            source_image=validated_data["source_image"],
        )
        campaign = Campaign.objects.create(blog_post=blog_post)

        for platform in PLATFORMS:
            caption = compose_caption(blog_post, platform)
            variant_file = generate_variant(blog_post.source_image.path, platform)
            PlatformAsset.objects.create(
                campaign=campaign, platform=platform, image=variant_file, caption=caption
            )

        schedule_campaign_posts(campaign, scheduled_at=validated_data.get("scheduled_at"))

        return campaign