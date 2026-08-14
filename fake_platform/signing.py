import hashlib
import hmac


def sign_payload(payload_bytes: bytes, secret: bytes) -> str:
    digest = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"