from django.contrib import admin

from .models import FakePost


@admin.register(FakePost)
class FakePostAdmin(admin.ModelAdmin):
    list_display = ["id", "platform", "idempotency_key", "status", "created_at"]
    list_filter = ["platform", "status"]