import os
import tempfile

from django.test import TestCase
from PIL import Image

from .captions import compose_caption
from .images import generate_variant
from campaigns.models import BlogPost


class ImageVariantTests(TestCase):
    """Definition of Done: 'Image variants correct ... test asserts dimensions'"""

    def setUp(self):
        # Deliberately non-square, non-16:9 source (2000x1000) so a passing
        # test proves actual cropping happened, not a lucky no-op.
        img = Image.new("RGB", (2000, 1000), color=(120, 120, 200))
        fd, self.tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        img.save(self.tmp_path)

    def tearDown(self):
        os.remove(self.tmp_path)

    def test_instagram_variant_is_1080x1080(self):
        variant = generate_variant(self.tmp_path, "instagram")
        with Image.open(variant) as out:
            self.assertEqual(out.size, (1080, 1080))

    def test_x_variant_is_1600x900(self):
        variant = generate_variant(self.tmp_path, "x")
        with Image.open(variant) as out:
            self.assertEqual(out.size, (1600, 900))

    def test_unknown_platform_raises(self):
        with self.assertRaises(ValueError):
            generate_variant(self.tmp_path, "linkedin")


class CaptionComposerTests(TestCase):
    """Definition of Done: 'Captions are platform-aware ... no duplicated
    near-identical prompts'"""

    def setUp(self):
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        Image.new("RGB", (100, 100)).save(tmp_path)
        with open(tmp_path, "rb") as f:
            from django.core.files.uploadedfile import SimpleUploadedFile

            self.post = BlogPost.objects.create(
                title="Great Django Tips",
                body="This is the first sentence. This is more body text that follows.",
                url="https://example.com/blog/great-django-tips",
                source_image=SimpleUploadedFile("src.jpg", f.read()),
            )
        os.remove(tmp_path)

    def test_captions_differ_by_platform(self):
        x_caption = compose_caption(self.post, "x")
        ig_caption = compose_caption(self.post, "instagram")
        self.assertNotEqual(x_caption, ig_caption)

    def test_x_caption_respects_length_limit(self):
        caption = compose_caption(self.post, "x")
        self.assertLessEqual(len(caption), 280)

    def test_x_caption_includes_link_instagram_does_not(self):
        x_caption = compose_caption(self.post, "x")
        ig_caption = compose_caption(self.post, "instagram")
        self.assertIn(self.post.url, x_caption)
        self.assertNotIn(self.post.url, ig_caption)

    def test_unknown_platform_raises(self):
        with self.assertRaises(ValueError):
            compose_caption(self.post, "linkedin")