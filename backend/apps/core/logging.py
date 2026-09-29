"""Logging configuration (quality backlog Q11, first part).

* Every line carries the request ID (see request_context).
* Console (stdout) always. That is what Render collects; hosted instances never write log files, because their disk
  is temporary and several gunicorn workers writing one rotating file corrupt it.
* Rotating files only when ``TUTOR_LOG_DIR`` is set (local development): ``tutor.log`` (INFO and up) and
  ``errors.log`` (ERROR and up, with tracebacks), each rotated at 5 MB, keeping 5 old files.
* Never log message bodies, passwords, codes, tokens or personal data. Code that handles those logs identifiers only.
"""

import logging
from pathlib import Path

from .request_context import get_request_id

FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 5


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        request_id = get_request_id()
        if request_id == "-":
            # Django logs 4xx/5xx responses after the middleware has finished; those records carry the request.
            request_id = getattr(getattr(record, "request", None), "request_id", "-")
        record.request_id = request_id
        return True


def build_logging(level="INFO", log_dir=None):
    """Return a Django LOGGING dict. ``log_dir`` None/empty → console only."""
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["request_id"],
            "level": level,
        }
    }
    active = ["console"]
    if log_dir:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        for name, file_level in (("file", level), ("errors", "ERROR")):
            handlers[name] = {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(path / ("tutor.log" if name == "file" else "errors.log")),
                "maxBytes": MAX_BYTES,
                "backupCount": BACKUPS,
                "encoding": "utf-8",
                "delay": True,
                "formatter": "standard",
                "filters": ["request_id"],
                "level": file_level,
            }
            active.append(name)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": "apps.core.logging.RequestIDFilter"}},
        "formatters": {"standard": {"format": FORMAT}},
        "handlers": handlers,
        "root": {"handlers": active, "level": level},
        "loggers": {
            # Django logs 4xx/5xx here; unhandled API errors are logged by our own handler with the traceback.
            "django.request": {"handlers": active, "level": "ERROR", "propagate": False},
            "django.db.backends": {"level": "WARNING"},  # SQL only when explicitly debugging
        },
    }
