"""Service-to-service authentication: only the Django platform may call /v1 endpoints.

Django sends `Authorization: Bearer <TUTOR_AI_SERVICE_TOKEN>`. Tokens are compared in constant time. During a
rotation the previous token (TUTOR_AI_SERVICE_TOKEN_PREVIOUS) is also accepted, so both services can be redeployed
one after the other without downtime.
"""

import hmac
from typing import Annotated

from fastapi import Depends, Header

from .errors import AppError
from .settings import Settings, get_settings


def token_matches(presented: str, accepted: list[str]) -> bool:
    # Compare against every accepted token (no early exit), so timing doesn't reveal which one nearly matched.
    matched = False
    for token in accepted:
        matched |= hmac.compare_digest(presented.encode(), token.encode())
    return matched


async def require_service_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not presented or not token_matches(presented, settings.accepted_tokens):
        raise AppError(401, "not_authenticated", "A valid service token is required.")
