"""Structured logging configuration with PII/payload sanitization and correlation ID support."""

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable to hold request correlation ID across async execution
correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Regex patterns for sensitive data masking (PANs/credit cards, SSNs, bank accounts, auth tokens)
SENSITIVE_PATTERNS = [
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"(bearer\s+)[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(password|secret|token|api_key)[\"']?\s*[:=]\s*[\"']?[^,\s\"']+", re.IGNORECASE), r"\1=[REDACTED]"),
]


def mask_sensitive_text(text: str) -> str:
    """Mask sensitive patterns such as credit cards, SSNs, and credentials."""
    if not isinstance(text, str):
        return text
    masked = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


class StructuredJsonFormatter(logging.Formatter):
    """Custom logging formatter outputting single-line JSON with context fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_sensitive_text(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None) or correlation_id_ctx.get(),
        }

        # Contextual agent attributes if present
        if hasattr(record, "agent"):
            log_entry["agent"] = record.agent
        if hasattr(record, "stage"):
            log_entry["stage"] = record.stage
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "error_category"):
            log_entry["error_category"] = record.error_category
        if hasattr(record, "client_id"):
            log_entry["client_id"] = record.client_id

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO") -> None:
    """Configures structured JSON logging for the entire application."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Utility to retrieve a named logger."""
    return logging.getLogger(name)
