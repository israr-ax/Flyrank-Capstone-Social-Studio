from django.urls import path

from . import views

urlpatterns = [
    path("oauth/token/", views.oauth_token, name="fake_oauth_token"),
    path("<str:platform>/publish/", views.publish, name="fake_publish"),
]