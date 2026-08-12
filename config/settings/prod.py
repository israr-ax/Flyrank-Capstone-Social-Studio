from .base import *  # noqa

DEBUG = False
DATABASES = {"default": {...}}   # Postgres via env vars, fill in later
CELERY_BROKER_URL = os.environ["CELERY_BROKER_URL"]  # redis://... via Docker