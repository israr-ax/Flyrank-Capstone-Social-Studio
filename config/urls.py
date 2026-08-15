from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("fake/", include("fake_platform.urls")),
    path("api/webhook/", include("webhooks.urls")),
    path("api/", include("campaigns.urls")),
]