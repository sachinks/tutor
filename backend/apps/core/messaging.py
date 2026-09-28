"""Outgoing SMS / email. v1 development: printed to the server log and kept in OUTBOX for tests.
A real SMS/email provider is plugged in here later (sent by the background worker)."""

import logging

logger = logging.getLogger("tutor.messaging")
OUTBOX: list[dict] = []


def send(channel: str, to: str, text: str) -> None:
    OUTBOX.append({"channel": channel, "to": to, "text": text})
    logger.info("[%s → %s] %s", channel.upper(), to, text)
