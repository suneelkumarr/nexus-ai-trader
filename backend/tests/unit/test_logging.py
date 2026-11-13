"""Unit tests for structured logging and secret redaction."""

import json
import logging

import pytest

from nexus.core.logging import configure_logging, get_logger


def test_structured_json_logging_redacts_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(
        log_level="INFO", log_format="json", service_name="nexus-test", environment="test"
    )
    logger = get_logger("nexus.tests.logging")

    logger.info(
        "auth_check",
        api_key="my-secret-api-key",
        postgres_password="super-secret-password",
        nested={"token": "bearer-xyz", "safe_field": "visible"},
    )
    logging.shutdown()

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured
    payload = json.loads(captured[-1])

    assert payload["event"] == "auth_check"
    assert payload["service"] == "nexus-test"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["postgres_password"] == "[REDACTED]"
    assert payload["nested"]["token"] == "[REDACTED]"
    assert payload["nested"]["safe_field"] == "visible"

