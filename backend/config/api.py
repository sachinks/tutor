"""The TUTOR REST API: /api/v1 (API_CONTRACTS.md)."""

from django.conf import settings
from django.db import connection
from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import auth_router, consent_router, me_router, parent_router
from apps.assessment.api import attempts_router  # also registers /lessons/{id}/quiz/start
from apps.catalogue.api import catalogue_router, courses_router, lessons_router, programmes_router
from apps.core.errors import install_error_handlers
from apps.learning.api import student_router  # also registers /lessons/{id} and /finish

api = NinjaAPI(
    title="TUTOR API",
    version="1.0.0",
    description="Django platform API used by the TUTOR web app.",
    urls_namespace="api-v1",
    # Secure by default: every endpoint needs a logged-in session unless its router or operation says auth=None.
    # It also makes /docs send the CSRF token on logged-in requests (ninja does so for cookie auth).
    auth=django_auth,
)
install_error_handlers(api)


@api.get("/health", tags=["system"], auth=None)
def health(request):
    """Liveness check for Render: the app is up and can reach the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - report, don't crash
        db_ok = False
    return {"ok": db_ok, "db": db_ok}


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

# Tester tools: only when DEBUG and TUTOR_DEV_TOOLS=true (docs/testing/tester-guide.md). Never in production.
if settings.DEBUG and settings.TUTOR_DEV_TOOLS:
    from apps.core.dev_api import dev_router

    api.add_router("/dev", dev_router)
