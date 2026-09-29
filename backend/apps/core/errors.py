"""One error format for the whole API (API_CONTRACTS.md §1):
{"error": {"code": "...", "message": "...", "fields": {...}, "request_id": "..."}}

Every failure, expected or not, leaves the API in this shape. Expected failures (ApiError, validation, auth, rate
limits) are logged briefly at INFO/WARNING; unexpected exceptions are logged once with the traceback at ERROR and
answered with a generic 500 that never reveals internals. The request ID in the body matches the log lines.
"""

import logging
import math

from django.http import Http404
from ninja.errors import AuthenticationError, HttpError, Throttled, ValidationError

from .request_context import get_request_id

logger = logging.getLogger("tutor.api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def error_body(code, message, fields=None):
    return {"error": {"code": code, "message": message, "fields": fields or {}, "request_id": get_request_id()}}


def install_error_handlers(api):
    def respond(request, code, message, status, fields=None):
        return api.create_response(request, error_body(code, message, fields), status=status)

    @api.exception_handler(ApiError)
    def api_error(request, exc):
        logger.info("%s %s → %s %s", request.method, request.path, exc.status, exc.code)
        return respond(request, exc.code, exc.message, exc.status, exc.fields)

    @api.exception_handler(ValidationError)
    def validation_error(request, exc):
        fields = {}
        for err in exc.errors:
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "payload", "query", "path")]
            fields[".".join(loc) or "non_field"] = err.get("msg", "Invalid value")
        logger.info("%s %s → 400 validation_error %s", request.method, request.path, sorted(fields))
        return respond(request, "validation_error", "Some fields are invalid.", 400, fields)

    @api.exception_handler(AuthenticationError)
    def not_authenticated(request, exc):
        return respond(request, "not_authenticated", "Please log in.", 401)

    @api.exception_handler(Throttled)
    def throttled(request, exc):
        logger.warning("%s %s → 429 limit_reached", request.method, request.path)
        response = respond(request, "limit_reached", "Too many requests. Please wait a little and try again.", 429)
        if exc.wait:
            response["Retry-After"] = str(math.ceil(exc.wait))
        return response

    @api.exception_handler(Http404)
    def not_found(request, exc):
        return respond(request, "not_found", "Not found.", 404)

    @api.exception_handler(HttpError)
    def http_error(request, exc):
        return respond(request, "error", str(exc), exc.status_code)

    @api.exception_handler(Exception)
    def unexpected(request, exc):
        # The only place an unexpected error is logged, with its traceback; the client learns nothing internal.
        logger.exception("Unhandled error on %s %s", request.method, request.path)
        return respond(
            request,
            "server_error",
            "Something went wrong on our side. Please try again; if it keeps happening, quote the request ID.",
            500,
        )


def json_404(request, exception=None):
    """Django-level 404 for URLs outside any API route: JSON under /api/, Django's page elsewhere."""
    from django.http import JsonResponse
    from django.views.defaults import page_not_found

    if request.path.startswith("/api/"):
        return JsonResponse(error_body("not_found", "Not found."), status=404)
    return page_not_found(request, exception)


def json_500(request):
    """Django-level 500 (errors outside the API handlers): JSON under /api/, Django's page elsewhere."""
    from django.http import JsonResponse
    from django.views.defaults import server_error

    if request.path.startswith("/api/"):
        return JsonResponse(error_body("server_error", "Something went wrong on our side."), status=500)
    return server_error(request)
