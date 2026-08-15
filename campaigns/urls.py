from django.urls import path

from . import views

urlpatterns = [
    path("campaigns/", views.CampaignListCreateView.as_view(), name="campaign-list-create"),
    path("campaigns/<uuid:campaign_id>/", views.CampaignDetailView.as_view(), name="campaign-detail"),
    path("health/", views.health, name="health"),
]