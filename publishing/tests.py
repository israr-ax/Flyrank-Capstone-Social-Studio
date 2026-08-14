from django.test import TestCase, override_settings

from .encryption import decrypt_token, encrypt_token


@override_settings(TOKEN_ENCRYPTION_KEY="MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")
class TokenEncryptionTests(TestCase):
    """Definition of Done: 'OAuth tokens encrypted at rest (random IV/nonce)'"""

    def test_round_trip(self):
        plaintext = "super-secret-oauth-token-value"
        ciphertext, nonce = encrypt_token(plaintext)
        self.assertEqual(decrypt_token(ciphertext, nonce), plaintext)

    def test_ciphertext_does_not_contain_plaintext(self):
        plaintext = "super-secret-oauth-token-value"
        ciphertext, _ = encrypt_token(plaintext)
        self.assertNotIn(plaintext.encode(), ciphertext)

    def test_nonce_is_unique_per_call(self):
        _, nonce1 = encrypt_token("token-a")
        _, nonce2 = encrypt_token("token-a")  # same plaintext, called twice
        self.assertNotEqual(nonce1, nonce2)

    def test_ciphertext_differs_for_same_plaintext(self):
        # proves the nonce is actually doing its job -- same input, two
        # different outputs, because the nonce differs each call
        ciphertext1, _ = encrypt_token("token-a")
        ciphertext2, _ = encrypt_token("token-a")
        self.assertNotEqual(ciphertext1, ciphertext2)

    def test_wrong_nonce_fails_decryption(self):
        ciphertext, _ = encrypt_token("token-a")
        _, wrong_nonce = encrypt_token("token-b")
        with self.assertRaises(Exception):
            decrypt_token(ciphertext, wrong_nonce)