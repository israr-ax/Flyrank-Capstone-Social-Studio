"""
Image variant pipeline: center-crop the source image to each platform's
required aspect ratio, then resize to exact pixel dimensions. Center-crop
is the deliberately simple v1 (subject-detection/manual focal point is a
documented refinement, not required for Definition of Done).
"""
from dataclasses import dataclass
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image


@dataclass(frozen=True)
class PlatformImageSpec:
    width: int
    height: int


PLATFORM_IMAGE_SPECS: dict[str, PlatformImageSpec] = {
    "instagram": PlatformImageSpec(width=1080, height=1080),
    "x": PlatformImageSpec(width=1600, height=900),
}


def center_crop_to_aspect(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Crop to the target aspect ratio around the center, then resize to
    the exact target dimensions."""
    target_ratio = target_w / target_h
    src_w, src_h = image.size
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # source is relatively wider than target -> crop left/right
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        # source is relatively taller than target -> crop top/bottom
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)

    cropped = image.crop(box)
    return cropped.resize((target_w, target_h), Image.LANCZOS)


def generate_variant(source_image_path: str, platform: str) -> ContentFile:
    if platform not in PLATFORM_IMAGE_SPECS:
        raise ValueError(f"unknown platform: {platform}")
    spec = PLATFORM_IMAGE_SPECS[platform]

    with Image.open(source_image_path) as img:
        img = img.convert("RGB")
        variant = center_crop_to_aspect(img, spec.width, spec.height)
        buffer = BytesIO()
        variant.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        return ContentFile(buffer.read(), name=f"{platform}_variant.jpg")