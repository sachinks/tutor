"""Production on Render."""

from .base import *  # noqa: F401,F403
from .base import env, env_bool

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Render terminates HTTPS
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN")  # e.g. ".tutor.org.in"; None = auto (OK for single-domain deploys)
CSRF_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN")
SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))  # raise to 31536000 once HTTPS is proven
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# HSTS preload only means something on the apex domain (tutor.org.in), which this API service doesn't serve.
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
SILENCED_SYSTEM_CHECKS = [] if SECURE_HSTS_PRELOAD else ["security.W021"]

# Render puts exactly one proxy in front of the app. Without this, every visitor would share one rate-limit bucket.
TUTOR_TRUSTED_PROXIES = int(env("TUTOR_TRUSTED_PROXIES", "1"))
SECURE_CONTENT_TYPE_NOSNIFF = True

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
