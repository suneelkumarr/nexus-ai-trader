"""Authentication, authorization dependencies, and rate-limiting middleware."""

import hmac
import time
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from nexus.core.config import Settings
from nexus.core.logging import get_logger

logger = get_logger(__name__)

_bearer_security = HTTPBearer(auto_error=False)


def verify_auth_token(provided_token: str, expected_token: str) -> bool:
    """Constant-time token comparison preventing timing attacks."""
    if not provided_token or not expected_token:
        return False
    return hmac.compare_digest(provided_token.strip(), expected_token.strip())


async def require_admin_auth(
    request: Request,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_security)] = None,
    x_nexus_api_key: Annotated[str | None, Header(alias="X-Nexus-API-Key")] = None,
) -> str:
    """Enforce token authentication on protected mutating, settings, and compute endpoints."""
    settings: Settings = getattr(request.app.state, "settings", None) or Settings(_env_file=None)
    expected_token = settings.api_auth_token.get_secret_value().strip()

    # If no auth token is configured in the environment, bypass check in dev/test mode
    if not expected_token:
        return "unauthenticated-dev"

    token: str | None = None
    if bearer is not None and bearer.credentials:
        token = bearer.credentials
    elif x_nexus_api_key:
        token = x_nexus_api_key

    if not token or not verify_auth_token(token, expected_token):
        logger.warning(
            "unauthorized_api_access_attempt",
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def authenticate_websocket(websocket: WebSocket, settings: Settings) -> bool:
    """Validate query token or Authorization header for incoming WebSocket connection."""
    expected_token = settings.api_auth_token.get_secret_value().strip()
    if not expected_token:
        return True

    # 1. Check query parameter `?token=...`
    token = websocket.query_params.get("token")
    if token and verify_auth_token(token, expected_token):
        return True

    # 2. Check header `X-Nexus-API-Key` or `Authorization: Bearer ...`
    header_key = websocket.headers.get("x-nexus-api-key")
    if header_key and verify_auth_token(header_key, expected_token):
        return True

    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
        if verify_auth_token(bearer_token, expected_token):
            return True

    return False


class SecurityRateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window IP rate limiter and body size protector."""

    def __init__(
        self,
        app: object,
        *,
        rate_limit_per_minute: int = 120,
        max_body_bytes: int = 2 * 1024 * 1024,
        trust_proxy_headers: bool = False,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._rate_limit = rate_limit_per_minute
        self._max_body_bytes = max_body_bytes
        self._trust_proxy_headers = trust_proxy_headers
        self._ip_history: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        """Resolve client IP, optionally honoring a trusted proxy's X-Forwarded-For."""
        client_ip = request.client.host if request.client else "127.0.0.1"
        if self._trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                candidate = forwarded.split(",")[0].strip()
                if candidate:
                    return candidate
        return client_ip

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check payload size
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > self._max_body_bytes
        ):
            return Response(
                content='{"detail":"Request payload exceeds size limit (413 Payload Too Large)"}',
                status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
                media_type="application/json",
            )

        # Skip rate-limiting WebSocket upgrade requests (handled per connection)
        if request.scope.get("type") == "websocket" or request.url.path.startswith("/api/v1/ws/"):
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.time()
        window_start = now - 60.0

        # Purge timestamps older than 60s and drop idle buckets to bound memory.
        timestamps = [t for t in self._ip_history.get(client_ip, []) if t > window_start]
        if not timestamps and client_ip in self._ip_history:
            self._ip_history.pop(client_ip, None)
        if len(self._ip_history) > 10_000:
            for ip in [ip for ip, hist in self._ip_history.items() if not hist]:
                self._ip_history.pop(ip, None)

        if len(timestamps) >= self._rate_limit:
            return Response(
                content='{"detail":"Rate limit exceeded (429 Too Many Requests)."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": "60"},
                media_type="application/json",
            )

        timestamps.append(now)
        self._ip_history[client_ip] = timestamps
        return await call_next(request)
