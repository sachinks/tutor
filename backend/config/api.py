"""The TUTOR REST API: /api/v1 (API_CONTRACTS.md)."""
from django.db import connection
from ninja import NinjaAPI

from apps.accounts.api import auth_router, consent_router, me_router, parent_router
from apps.core.errors import install_error_handlers

api = NinjaAPI(
    title="TUTOR API",
    version="1.0.0",
    description="Django platform API used by the TUTOR web app.",
    urls_namespace="api-v1",
)
install_error_handlers(api)


@api.get("/health", tags=["system"])
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
