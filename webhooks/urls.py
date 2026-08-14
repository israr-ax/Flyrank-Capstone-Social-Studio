from django.urls import path

from . import views

urlpatterns = [
    path("social-delivery/", views.social_delivery_webhook, name="social_delivery_webhook"),
]