"""One error format for the whole API (API_CONTRACTS.md §1):
{"error": {"code": "...", "message": "...", "fields": {...}}}
"""

import math

from ninja.errors import AuthenticationError, HttpError, Throttled, ValidationError


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def error_body(code, message, fields=None):
    return {"error": {"code": code, "message": message, "fields": fields or {}}}


def install_error_handlers(api):
    @api.exception_handler(ApiError)
    def api_error(request, exc):
        return api.create_response(request, error_body(exc.code, exc.message, exc.fields), status=exc.status)

    @api.exception_handler(ValidationError)
    def validation_error(request, exc):
        fields = {}
        for err in exc.errors:
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "payload", "query", "path")]
            fields[".".join(loc) or "non_field"] = err.get("msg", "Invalid value")
        return api.create_response(
            request, error_body("validation_error", "Some fields are invalid.", fields), status=400
        )

    @api.exception_handler(AuthenticationError)
    def not_authenticated(request, exc):
        return api.create_response(request, error_body("not_authenticated", "Please log in."), status=401)

    @api.exception_handler(Throttled)
    def throttled(request, exc):
        response = api.create_response(
            request, error_body("limit_reached", "Too many requests. Please wait a little and try again."), status=429
        )
        if exc.wait:
            response["Retry-After"] = str(math.ceil(exc.wait))
        return response

    @api.exception_handler(HttpError)
    def http_error(request, exc):
        return api.create_response(request, error_body("error", str(exc)), status=exc.status_code)
