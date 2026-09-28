"""Production on Render."""
from .base import *  # noqa: F401,F403
from .base import env, env_bool

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Render terminates HTTPS
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN")  # e.g. ".tutor.org.in"
CSRF_COOKIE_DOMAIN = env("DJANGO_COOKIE_DOMAIN")
SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))  # raise once HTTPS is proven
SECURE_CONTENT_TYPE_NOSNIFF = True

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
