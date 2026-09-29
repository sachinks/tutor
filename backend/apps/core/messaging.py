"""Outgoing SMS / email. v1 development: messages are kept in OUTBOX (tests, dev outbox) and logged.
A real SMS/email provider is plugged in here later (sent by the background worker).

One-time codes and approval links are secrets. With TUTOR_KEEP_MESSAGES on (local development and tests only) the full
text is logged and kept so testers can read it; otherwise only the channel, a masked recipient and the length are
logged, and nothing is kept.
"""

import logging
from collections import deque

from django.conf import settings

logger = logging.getLogger("tutor.messaging")
OUTBOX: deque = deque(maxlen=500)  # bounded, so a long-running dev server can't grow without limit


def mask(contact: str) -> str:
    """+919812345678 → +91******5678; asha@test.tutor → a***@test.tutor."""
    if "@" in contact:
        name, _, domain = contact.partition("@")
        return f"{name[:1]}***@{domain}"
    return contact[:3] + "*" * max(len(contact) - 7, 0) + contact[-4:]


def send(channel: str, to: str, text: str) -> None:
    if settings.TUTOR_KEEP_MESSAGES:
        OUTBOX.append({"channel": channel, "to": to, "text": text})
        logger.info("[%s → %s] %s", channel.upper(), to, text)
    else:
        logger.info("[%s → %s] message queued (%d characters, content withheld)", channel.upper(), mask(to), len(text))
