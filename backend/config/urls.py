from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_safe

from config.api import api


@require_safe
def root(request):
    """The service has no web pages of its own (the web app is separate); say where things are instead of a 404."""
    return JsonResponse(
        {"service": "TUTOR platform API", "docs": "/api/v1/docs", "health": "/api/v1/health", "admin": "/admin/"}
    )


urlpatterns = [
    path("", root, name="root"),
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
]

# Unknown URLs and errors outside the API handlers still answer in the API's error shape under /api/.
handler404 = "apps.core.errors.json_404"
handler500 = "apps.core.errors.json_500"
