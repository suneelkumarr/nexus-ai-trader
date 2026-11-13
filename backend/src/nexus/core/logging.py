"""Structured logging configuration using structlog with automatic secret redaction."""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "secret",
    "api_key",
    "apikey",
    "token",
    "authorization",
    "private_key",
    "database_url",
)

_REDACTED = "[REDACTED]"
_DSN_CRED_RE = re.compile(r"([a-zA-Z0-9+_-]+://[^:\s/@]+:)([^@\s]+)(@)")
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{6,}", re.IGNORECASE)
_SK_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{10,}|AIza[0-9A-Za-z\-_]{20,})\b")


def _scrub_secret_string(value: str) -> str:
    """Mask embedded DSN passwords, Bearer tokens, and API keys inside log string values."""
    scrubbed = _DSN_CRED_RE.sub(rf"\1{_REDACTED}\3", value)
    scrubbed = _BEARER_RE.sub(rf"\1{_REDACTED}", scrubbed)
    scrubbed = _SK_TOKEN_RE.sub(_REDACTED, scrubbed)
    return scrubbed


def _redact_value(key: str, value: Any) -> Any:
    """Recursively redact sensitive fields and embedded credentials in structured logs."""
    lowered = key.lower()
    if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return _REDACTED
    if isinstance(value, str):
        return _scrub_secret_string(value)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def redact_sensitive_fields(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that scrubs secrets before logs are serialized."""
    for key in list(event_dict.keys()):
        event_dict[key] = _redact_value(str(key), event_dict[key])
    return event_dict


def configure_logging(
    *,
    log_level: str = "INFO",
    log_format: str = "json",
    service_name: str = "nexus-ai-trader",
    environment: str = "development",
) -> None:
    """Configure structlog and stdlib logging with unified formatting."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_fields,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if log_format.lower() == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name, environment=environment)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound to the given module name."""
    return structlog.stdlib.get_logger(name)

