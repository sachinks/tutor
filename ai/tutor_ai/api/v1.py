"""Version 1 of the internal API, called only by the Django platform (design §3). Every route needs the service
token. Endpoints arrive step by step (design §14): indexing in step 3, tutor turns in step 4."""

from fastapi import APIRouter, Depends, Request

from ..security import require_service_token

router = APIRouter(prefix="/v1", dependencies=[Depends(require_service_token)])


@router.get("/whoami", tags=["system"])
async def whoami(request: Request) -> dict[str, object]:
    """Lets Django verify its token and see which provider and models this service uses."""
    provider = request.app.state.provider
    return {
        "service": "tutor-ai",
        "provider": provider.name,
        "chat_model": provider.chat_model,
        "embedding_model": provider.embedding_model,
        "dimensions": provider.dimensions,
    }
