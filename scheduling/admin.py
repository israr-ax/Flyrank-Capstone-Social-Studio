from django.contrib import admin

from .models import ScheduledPost


@admin.register(ScheduledPost)
class ScheduledPostAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "campaign",
        "platform",
        "status",
        "scheduled_at",
        "attempt_count",
        "next_retry_at",
        "published_at",
    ]
    list_filter = ["platform", "status"]
    readonly_fields = [f.name for f in ScheduledPost._meta.fields]