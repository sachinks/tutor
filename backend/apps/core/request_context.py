"""Per-request context shared with logging: the request ID.

Every request gets an ID (taken from a well-formed incoming ``X-Request-ID`` header, otherwise generated). It is
stored in a context variable so every log line written while handling the request carries it, returned in the
``X-Request-ID`` response header, and included in API error bodies, so a user's bug report can be matched to the
exact log lines. IDs never contain personal data.
"""

import contextvars
import re
import uuid

_request_id = contextvars.ContextVar("request_id", default="-")
_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")  # anything else from outside is replaced, so logs can't be forged


def get_request_id() -> str:
    return _request_id.get()


def new_request_id(incoming: str | None = None) -> str:
    return incoming if incoming and _VALID.match(incoming) else uuid.uuid4().hex


class RequestIDMiddleware:
    header = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = new_request_id(request.headers.get(self.header))
        request.request_id = request_id
        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response[self.header] = request_id
        return response
