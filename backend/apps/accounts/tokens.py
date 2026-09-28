"""Secrets sent by link or SMS are stored only as hashes (DATA_MODEL.md §4)."""
import hashlib
import secrets


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def make_link_token() -> tuple[str, str]:
    """Return (raw token for the link, hash to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_secret(raw)


def make_otp() -> tuple[str, str]:
    """Return (6-digit code to send, hash to store)."""
    raw = f"{secrets.randbelow(10**6):06d}"
    return raw, hash_secret(raw)
