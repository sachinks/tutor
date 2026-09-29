"""Health check for the platform (Render) and for Django. Public: it reveals only up/down facts, no data."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import ping

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """200 when the database and the model provider are both reachable; 503 otherwise (with which part failed)."""
    state = request.app.state
    db_ok = await ping(state.engine)
    provider_ok = await state.provider.health()
    body = {"ok": db_ok and provider_ok, "db": db_ok, "provider": state.provider.name, "provider_ok": provider_ok}
    return JSONResponse(body, status_code=200 if body["ok"] else 503)
