"""Development-only helpers for testers. Mounted ONLY when DEBUG=True and TUTOR_DEV_TOOLS=true (never in production).

GET /api/v1/dev/outbox?to=<contact>  → the latest SMS/email messages the server "sent" (links and one-time codes),
so testers don't have to read the server log.
"""

from typing import Optional

from ninja import Router

from apps.core import messaging

dev_router = Router(tags=["dev tools (local only)"], auth=None)


@dev_router.get("/outbox", response=list[dict])
def outbox(request, to: Optional[str] = None, limit: int = 10):
    messages = [m for m in messaging.OUTBOX if not to or m["to"] == to]
    return list(reversed(messages))[: max(1, min(limit, 50))]
