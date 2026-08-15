from django.contrib import admin

from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["id", "signature_valid", "received_at", "scheduled_post", "processed_at"]
    list_filter = ["signature_valid"]