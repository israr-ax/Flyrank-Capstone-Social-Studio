import hashlib


def make_idempotency_key(campaign_id, platform: str) -> str:
    """
    Deterministic, not random -- a retried request for the same
    (campaign, platform) always produces the same key, even across
    process restarts. This is both our own unique DB constraint AND what
    gets sent to fake_platform, so retries dedupe on both sides.
    """
    raw = f"{campaign_id}:{platform}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()