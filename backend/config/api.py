"""The TUTOR REST API: /api/v1 (API_CONTRACTS.md)."""

import logging

from django.conf import settings
from django.db import connection
from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import auth_router, consent_router, me_router, parent_router
from apps.assessment.api import attempts_router  # also registers /lessons/{id}/quiz/start
from apps.catalogue.api import catalogue_router, courses_router, lessons_router, programmes_router
from apps.core.errors import install_error_handlers
from apps.core.throttling import api_throttle
from apps.learning.api import student_router  # also registers /lessons/{id} and /finish
from apps.tutor.api import tutor_router

api = NinjaAPI(
    title="TUTOR API",
    version="1.0.0",
    description="Django platform API used by the TUTOR web app.",
    urls_namespace="api-v1",
    # Secure by default: every endpoint needs a logged-in session unless its router or operation says auth=None.
    # It also makes /docs send the CSRF token on logged-in requests (ninja does so for cookie auth).
    auth=django_auth,
    # A general per-user/per-IP ceiling; sensitive endpoints add stricter limits (apps/core/throttling.py).
    throttle=[api_throttle],
)
install_error_handlers(api)
logger = logging.getLogger(__name__)


@api.get("/health", tags=["system"], auth=None, response={200: dict, 503: dict})
def health(request):
    """Health check for Render: 200 when the app is up and can reach the database, 503 otherwise.

    The status code matters: Render only switches traffic to a new version whose health check succeeds.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - any failure means "not healthy"; report it, don't crash
        logger.exception("Health check: database unreachable")
        return 503, {"ok": False, "db": False}
    return 200, {"ok": True, "db": True}


api.add_router("/auth", auth_router)
api.add_router("/me", me_router)
api.add_router("/consent", consent_router)
api.add_router("/parent", parent_router)
api.add_router("/catalogue", catalogue_router)
api.add_router("/courses", courses_router)
api.add_router("/programmes", programmes_router)
api.add_router("/lessons", lessons_router)
api.add_router("/student", student_router)
api.add_router("/attempts", attempts_router)
api.add_router("/tutor", tutor_router)

# Tester tools: only when DEBUG and TUTOR_DEV_TOOLS=true (docs/testing/tester-guide.md). Never in production.
if settings.DEBUG and settings.TUTOR_DEV_TOOLS:
    from apps.core.dev_api import dev_router

    api.add_router("/dev", dev_router)
