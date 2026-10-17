"""Tests for structured logging and PII/payload sanitization."""

import json
import logging
from app.logging_config import StructuredJsonFormatter, mask_sensitive_text


def test_mask_sensitive_text():
    # Credit card PAN
    raw_card = "Customer used Visa 4111 2222 3333 4444 for payment"
    assert "[REDACTED_CARD]" in mask_sensitive_text(raw_card)
    assert "4111 2222 3333 4444" not in mask_sensitive_text(raw_card)

    # Social Security Number
    raw_ssn = "Tax ID: 000-12-3456 verified"
    assert "[REDACTED_SSN]" in mask_sensitive_text(raw_ssn)
    assert "000-12-3456" not in mask_sensitive_text(raw_ssn)

    # Bearer token
    raw_token = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    assert "[REDACTED_TOKEN]" in mask_sensitive_text(raw_token)

    # Password / secret
    raw_secret = 'api_key: "secret_1234567890abcdef"'
    assert "[REDACTED]" in mask_sensitive_text(raw_secret)


def test_structured_json_formatter():
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Processing stage for card 4111-2222-3333-4444",
        args=(),
        exc_info=None
    )
    record.agent = "TestAgent"
    record.stage = "test_stage"
    record.duration_ms = 45.2
    record.correlation_id = "corr_123"

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["agent"] == "TestAgent"
    assert data["stage"] == "test_stage"
    assert data["duration_ms"] == 45.2
    assert data["correlation_id"] == "corr_123"
    assert "[REDACTED_CARD]" in data["message"]
    assert "4111-2222-3333-4444" not in data["message"]
