"""Rate limits for the API (quality backlog Q3), built on django-ninja's throttle hook.

Rates live in ``settings.TUTOR_THROTTLE_RATES`` and are read on every request, so they can be tuned per
environment (and switched on in tests) without touching code. State is kept in the shared cache as a
sliding window of request timestamps. The throttle object is shared between threads, so no per-request
state is stored on it except in a thread-local.
"""

import threading
import time

from django.conf import settings
from django.core.cache import cache
from ninja.throttling import BaseThrottle

from .http import client_ip

PERIOD_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_rate(rate: str) -> tuple[int, int]:
    """Parse a rate: "30/m" -> (30, 60), "5/10m" -> (5, 600). Raises ValueError for anything else."""
    try:
        count, period = rate.split("/")
        unit = period[-1]
        multiplier = int(period[:-1]) if period[:-1] else 1
        limit, seconds = int(count), multiplier * PERIOD_SECONDS[unit]
    except (ValueError, KeyError, IndexError):
        raise ValueError(f"Invalid rate {rate!r}; use e.g. '30/m', '10/h' or '5/10m'.") from None
    if limit < 1 or seconds < 1:
        raise ValueError(f"Invalid rate {rate!r}; count and period must be positive.")
    return limit, seconds


class ScopedRateThrottle(BaseThrottle):
    """Limit requests per client IP, or per user with ``per_user=True`` (falling back to IP when logged out)."""

    cache_format = "throttle:%(scope)s:%(ident)s"

    def __init__(self, scope: str, per_user: bool = False):
        self.scope = scope
        self.per_user = per_user
        self._state = threading.local()

    def rate(self):
        return settings.TUTOR_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request):
        user = getattr(request, "user", None)
        if self.per_user and user is not None and user.is_authenticated:
            ident = f"user-{user.pk}"
        else:
            ident = f"ip-{client_ip(request)}"
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def allow_request(self, request) -> bool:
        self._state.wait = None
        rate = self.rate()
        if not rate:
            return True
        limit, duration = parse_rate(rate)
        key = self.get_cache_key(request)
        now = time.time()
        history = [t for t in cache.get(key, []) if t > now - duration]  # newest first
        if len(history) >= limit:
            self._state.wait = max(duration - (now - history[-1]), 1)
            return False
        history.insert(0, now)
        cache.set(key, history, duration)
        return True

    def wait(self):
        return getattr(self._state, "wait", None)


api_throttle = ScopedRateThrottle("api", per_user=True)
login_throttle = ScopedRateThrottle("login")
signup_throttle = ScopedRateThrottle("signup")
otp_throttle = ScopedRateThrottle("otp")
consent_link_throttle = ScopedRateThrottle("consent_link")
consent_send_throttle = ScopedRateThrottle("consent_send", per_user=True)
tutor_throttle = ScopedRateThrottle("tutor", per_user=True)
