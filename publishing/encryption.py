"""
Token encryption at rest. AESGCM with a fresh random 12-byte nonce EVERY
call -- reusing a nonce with the same key breaks AESGCM's confidentiality
guarantee, so this is non-negotiable, not a style choice.

Never log plaintext_token anywhere, including in exceptions -- if you add
error handling here later, make sure tracebacks can't leak it.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _get_key() -> bytes:
    return base64.b64decode(settings.TOKEN_ENCRYPTION_KEY)


def encrypt_token(plaintext_token: str) -> tuple[bytes, bytes]:
    """Returns (ciphertext, nonce). Caller stores both -- nonce is not
    secret, it just must never repeat for the same key."""
    key = _get_key()
    nonce = os.urandom(12)  # AESGCM standard nonce size
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_token.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_token(ciphertext: bytes, nonce: bytes) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, bytes(ciphertext), None)
    return plaintext.decode("utf-8")