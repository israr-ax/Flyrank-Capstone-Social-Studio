"""
Caption composition: one shared "core" message per blog post, combined with
a per-platform spec (length limit, hashtag count, whether a link is
allowed). This is deliberately NOT two near-identical hand-written caption
templates -- the shared core is computed once and reused; only the
platform-specific fragment differs. Swapping compose_shared_core() for an
LLM-based summarizer later doesn't touch platform logic at all.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformCaptionSpec:
    max_length: int
    hashtag_count: int
    include_link: bool
    cta: str


# X: short & punchy, link allowed (X captions support clickable links).
# Instagram: longer-form, no link (Instagram captions don't render clickable
# links -- "link in bio" is the real-world convention, not a bug).
PLATFORM_SPECS: dict[str, PlatformCaptionSpec] = {
    "x": PlatformCaptionSpec(max_length=280, hashtag_count=2, include_link=True, cta="Read more:"),
    "instagram": PlatformCaptionSpec(
        max_length=2200, hashtag_count=8, include_link=False, cta="Link in bio."
    ),
}


def compose_shared_core(blog_post) -> str:
    """The one message every platform's caption is built from."""
    first_sentence = blog_post.body.strip().split(". ")[0].strip()
    if not first_sentence.endswith((".", "!", "?")):
        first_sentence += "."
    return f"{blog_post.title} — {first_sentence}"


def generate_hashtags(blog_post, count: int) -> list[str]:
    """Naive keyword extraction from the title. Swap for real topic
    extraction or an AI call later -- signature doesn't need to change."""
    words = [w.strip("#,.:;!?").lower() for w in blog_post.title.split() if len(w) > 3]
    return [f"#{w}" for w in words[:count]]


def truncate_caption(caption: str, max_length: int) -> str:
    if len(caption) <= max_length:
        return caption
    return caption[: max_length - 1].rstrip() + "…"


def compose_caption(blog_post, platform: str) -> str:
    if platform not in PLATFORM_SPECS:
        raise ValueError(f"unknown platform: {platform}")
    spec = PLATFORM_SPECS[platform]

    parts = [compose_shared_core(blog_post)]
    parts.append(f"{spec.cta} {blog_post.url}" if spec.include_link else spec.cta)

    hashtags = generate_hashtags(blog_post, spec.hashtag_count)
    if hashtags:
        parts.append(" ".join(hashtags))

    return truncate_caption("\n\n".join(parts), spec.max_length)