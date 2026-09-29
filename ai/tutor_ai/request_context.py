"""Request ID shared with logging (same contract as the Django platform: X-Request-ID, validated when incoming)."""

import contextvars
import re
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
HEADER = "X-Request-ID"


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> contextvars.Token[str]:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id.reset(token)


def new_request_id(incoming: str | None = None) -> str:
    """Keep a well-formed incoming ID (Django sends one, so both services log the same ID); otherwise make one."""
    return incoming if incoming and _VALID.match(incoming) else uuid.uuid4().hex
