from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from content_pipeline.models import PlatformAsset
from scheduling.models import ScheduledPost

from .models import Campaign


def _fake_source_image():
    buf = BytesIO()
    Image.new("RGB", (2000, 1000), color=(100, 150, 200)).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile("src.jpg", buf.read(), content_type="image/jpeg")


class CampaignCreateAPITests(TestCase):
    def test_create_campaign_generates_assets_and_schedules_both_platforms(self):
        response = self.client.post(
            "/api/campaigns/",
            data={
                "title": "My Great Post",
                "body": "This is the first sentence. More text follows.",
                "url": "https://example.com/my-post",
                "source_image": _fake_source_image(),
            },
        )

        self.assertEqual(response.status_code, 201)
        campaign = Campaign.objects.get(id=response.json()["id"])

        self.assertEqual(PlatformAsset.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(ScheduledPost.objects.filter(campaign=campaign).count(), 2)

        ig_asset = PlatformAsset.objects.get(campaign=campaign, platform="instagram")
        x_asset = PlatformAsset.objects.get(campaign=campaign, platform="x")
        self.assertNotEqual(ig_asset.caption, x_asset.caption)

        with Image.open(ig_asset.image.path) as img:
            self.assertEqual(img.size, (1080, 1080))
        with Image.open(x_asset.image.path) as img:
            self.assertEqual(img.size, (1600, 900))

    def test_missing_required_field_returns_400_not_500(self):
        response = self.client.post("/api/campaigns/", data={"title": "Missing stuff"})
        self.assertEqual(response.status_code, 400)

    def test_campaign_status_starts_queued(self):
        response = self.client.post(
            "/api/campaigns/",
            data={
                "title": "Another Post",
                "body": "First sentence here.",
                "url": "https://example.com/another-post",
                "source_image": _fake_source_image(),
            },
        )
        self.assertEqual(response.json()["status"], "queued")

    def test_health_endpoint(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")