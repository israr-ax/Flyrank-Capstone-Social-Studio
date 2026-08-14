import requests
from django.conf import settings

from .encryption import decrypt_token, encrypt_token
from .models import PlatformToken


def get_or_create_token(platform: str) -> str:
    """Returns a decrypted, ready-to-use token. Never logs the plaintext."""
    try:
        token_row = PlatformToken.objects.get(platform=platform)
        return decrypt_token(bytes(token_row.encrypted_token), bytes(token_row.nonce))
    except PlatformToken.DoesNotExist:
        response = requests.post(
            f"{settings.FAKE_PLATFORM_BASE_URL}oauth/token/",
            json={"platform": platform},
            timeout=10,
        )
        response.raise_for_status()
        plaintext_token = response.json()["access_token"]

        ciphertext, nonce = encrypt_token(plaintext_token)
        PlatformToken.objects.create(platform=platform, encrypted_token=ciphertext, nonce=nonce)

        return plaintext_token