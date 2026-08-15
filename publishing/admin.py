from django.contrib import admin

from .models import PlatformToken


@admin.register(PlatformToken)
class PlatformTokenAdmin(admin.ModelAdmin):
    # Deliberately shows encrypted_token/nonce as raw ciphertext bytes in
    # the detail view -- good demo proof that it's genuinely encrypted,
    # not just hidden. Never decrypted here.
    list_display = ["id", "platform", "created_at"]
    readonly_fields = ["encrypted_token", "nonce"]