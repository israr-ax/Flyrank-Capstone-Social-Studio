import os

from .base import *  # noqa

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "flyrank"),
        "USER": os.environ.get("POSTGRES_USER", "flyrank"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "flyrank"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),  # "db" = the compose service name
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = "django-db"

STATIC_ROOT = BASE_DIR / "staticfiles"

# Inside Docker Compose, containers reach each other by service name, not
# localhost -- "web" is the compose service name for this same Django app.
FAKE_PLATFORM_BASE_URL = os.environ.get("FAKE_PLATFORM_BASE_URL", "http://web:8000/fake/")
OUR_WEBHOOK_URL = os.environ.get(
    "OUR_WEBHOOK_URL", "http://web:8000/api/webhook/social-delivery/"
)