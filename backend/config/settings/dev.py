"""Local development in WSL."""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, LOG_LEVEL, build_logging, env

DEBUG = True
TUTOR_KEEP_MESSAGES = True  # dev outbox and tests read one-time codes and links

# Rotating log files in backend/logs/ (git-ignored except .gitkeep). Set TUTOR_LOG_DIR= (empty) to switch off.
TUTOR_LOG_DIR = env("TUTOR_LOG_DIR", str(BASE_DIR / "logs"))
LOGGING = build_logging(LOG_LEVEL, TUTOR_LOG_DIR)
