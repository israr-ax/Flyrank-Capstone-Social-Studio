from django.contrib import admin

from .models import PlatformAsset


@admin.register(PlatformAsset)
class PlatformAssetAdmin(admin.ModelAdmin):
    list_display = ["id", "campaign", "platform", "created_at"]
    list_filter = ["platform"]