from django.contrib import admin

from .models import BlogPost, Campaign


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "created_at"]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["id", "blog_post", "status", "created_at"]