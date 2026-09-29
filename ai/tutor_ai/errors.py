"""One error shape, identical to the Django platform's:
{"error": {"code": "...", "message": "...", "fields": {...}, "request_id": "..."}}

Expected failures are raised as AppError. Anything else becomes a generic 500 that reveals nothing internal and is
logged once with its traceback.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .providers.base import ProviderError, ProviderTimeout, ProviderUnavailable
from .request_context import get_request_id

logger = logging.getLogger("tutor_ai.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


def error_body(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "fields": fields or {}, "request_id": get_request_id()}}


def _response(status: int, code: str, message: str, fields: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, fields), status_code=status)


_HTTP_CODES = {401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info("request refused", extra={"path": request.url.path, "status": exc.status, "code": exc.code})
        return _response(exc.status, exc.code, exc.message, exc.fields)

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        # The detail (URLs, model names, upstream messages) goes to the log only.
        logger.warning("model provider failed", extra={"path": request.url.path, "code": exc.code, "error": str(exc)})
        if isinstance(exc, ProviderUnavailable):
            return _response(503, exc.code, "The AI model is unavailable right now.")
        if isinstance(exc, ProviderTimeout):
            return _response(504, exc.code, "The AI model took too long to answer.")
        return _response(502, exc.code, "The AI model returned an unusable answer.")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
            fields[".".join(loc) or "non_field"] = str(err.get("msg", "Invalid value"))
        return _response(400, "validation_error", "Some fields are invalid.", fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error")
        response = _response(exc.status_code, code, str(exc.detail))
        for key, value in (exc.headers or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"path": request.url.path, "method": request.method})
        return _response(500, "server_error", "Something went wrong on our side. Quote the request ID if it repeats.")
