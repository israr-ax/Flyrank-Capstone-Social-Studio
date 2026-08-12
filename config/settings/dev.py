from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}

CELERY_BROKER_URL = "filesystem://"
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "data_folder_in": str(BASE_DIR / ".celery" / "in"),
    "data_folder_out": str(BASE_DIR / ".celery" / "out"),
}
CELERY_RESULT_BACKEND = "django-db"