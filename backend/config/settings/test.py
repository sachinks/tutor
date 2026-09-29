"""Settings for the automated test suite (`manage.py test --settings=config.settings.test`)."""

from .dev import *  # noqa: F401,F403
from .dev import LOG_LEVEL, build_logging

# In-memory cache: fast, and adds no database queries to the query-count tests.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tutor-tests"}}

# Rate limits are off by default so tests don't trip over each other; throttling tests switch them on
# with override_settings. The login lockout stays on (its tests clear the cache).
TUTOR_THROTTLE_RATES = {}

# Hashing passwords slowly is a feature in production and a waste of minutes in tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tests never write log files.
TUTOR_LOG_DIR = ""
LOGGING = build_logging(LOG_LEVEL, "")
