"""Pure ASGI middleware: request ID in and out, one access log line per request (method, path, status, duration).

Written as plain ASGI rather than BaseHTTPMiddleware so streamed (SSE) responses pass through untouched.
"""

import logging
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .request_context import HEADER, new_request_id, reset_request_id, set_request_id

logger = logging.getLogger("tutor_ai.access")
_HEADER_BYTES = HEADER.lower().encode()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == _HEADER_BYTES), None)
        request_id = new_request_id(incoming)
        token = set_request_id(request_id)
        started = time.perf_counter()
        status: dict[str, Any] = {"code": 500}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k != _HEADER_BYTES]
                headers.append((_HEADER_BYTES, request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status["code"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            reset_request_id(token)
