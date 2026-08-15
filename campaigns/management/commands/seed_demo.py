from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from PIL import Image

from campaigns.serializers import CampaignCreateSerializer


class Command(BaseCommand):
    help = "Creates one demo campaign end to end (blog post -> assets -> scheduled posts)."

    def handle(self, *args, **options):
        buffer = BytesIO()
        Image.new("RGB", (2000, 1000), color=(80, 130, 180)).save(buffer, format="JPEG")
        buffer.seek(0)

        serializer = CampaignCreateSerializer(
            data={
                "title": "Seeded Demo Post",
                "body": "This is a seeded demo post for evaluation. It has enough "
                "body text to compose a real caption from.",
                "url": "https://example.com/seeded-demo-post",
                "source_image": SimpleUploadedFile(
                    "demo.jpg", buffer.read(), content_type="image/jpeg"
                ),
            }
        )
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()

        self.stdout.write(self.style.SUCCESS(f"Seeded campaign {campaign.id}"))
        self.stdout.write(f"View it at: GET /api/campaigns/{campaign.id}/")