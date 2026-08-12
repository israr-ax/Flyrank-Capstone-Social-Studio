import uuid
from django.db import models


class PlatformToken(models.Model):
    """
    encrypted_token + nonce are raw AESGCM ciphertext/IV bytes, produced by
    publishing/encryption.py (next step). This model never sees or stores
    plaintext — encryption happens before .save(), decryption happens only
    inside SocialPublisher.get_access_token(), never logged.
    """

    PLATFORM_CHOICES = [("instagram", "Instagram"), ("x", "X")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, unique=True)
    encrypted_token = models.BinaryField()
    nonce = models.BinaryField()  # random 12 bytes, unique per encryption call
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"token for {self.platform}"