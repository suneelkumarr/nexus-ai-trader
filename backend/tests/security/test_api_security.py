"""Security tests for authentication, authorization, rate limiting, and payload size bounds."""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from nexus.core.config import Settings
from nexus.main import create_app


@pytest.mark.asyncio
async def test_protected_routes_enforce_authentication() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        api_auth_token=SecretStr("super-secret-admin-token"),
        database_url_override="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings=settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Unauthenticated request to protected settings endpoint is rejected with 401
        resp_unauth = await client.get("/api/v1/terminal/settings")
        assert resp_unauth.status_code == 401
        assert "Unauthorized" in resp_unauth.text

        # Invalid token is rejected with 401
        resp_invalid = await client.get(
            "/api/v1/terminal/settings",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp_invalid.status_code == 401

        # Valid Bearer token succeeds
        resp_auth = await client.get(
            "/api/v1/terminal/settings",
            headers={"Authorization": "Bearer super-secret-admin-token"},
        )
        assert resp_auth.status_code == 200

        # Valid X-Nexus-API-Key header succeeds
        resp_key = await client.get(
            "/api/v1/terminal/settings",
            headers={"X-Nexus-API-Key": "super-secret-admin-token"},
        )
        assert resp_key.status_code == 200


@pytest.mark.asyncio
async def test_oversized_payload_rejected_with_413() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        max_body_bytes=1024,
        database_url_override="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings=settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        large_body = "x" * 2048
        resp = await client.post(
            "/api/v1/terminal/emergency-stop",
            content=large_body,
            headers={"Content-Length": str(len(large_body)), "Content-Type": "application/json"},
        )
        assert resp.status_code == 413
        assert "413 Payload Too Large" in resp.text
