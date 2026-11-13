"""HTTP adapter for OpenAI-compatible JSON chat completions (advisory-only)."""

import asyncio
import json
import re
from typing import Any

import httpx
from pydantic import SecretStr

from nexus.core.exceptions import AIProviderError
from nexus.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL | re.IGNORECASE
)


class OpenAICompatibleAIClient:
    """Async HTTP client for structured JSON completions with multi-provider fallback resilience."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str = "gpt-4o-mini",
        timeout_s: float = 15.0,
        max_retries: int = 2,
        backoff_base_s: float = 0.5,
        http_client: httpx.AsyncClient | None = None,
        fallback_endpoints: list[dict[str, Any]] | None = None,
    ) -> None:
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = backoff_base_s
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))
        self._fallback_endpoints: list[dict[str, Any]] = fallback_endpoints or []

    @property
    def model_name(self) -> str:
        """Return configured primary LLM model name."""
        return self._model

    async def generate_market_analysis(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        """Request strict JSON completion across resilient multi-provider fallback chain."""
        endpoints: list[dict[str, Any]] = [
            {
                "name": "primary",
                "base_url": self._base_url,
                "api_key": self._api_key,
                "model": self._model,
                "timeout_s": self._timeout_s,
            },
            *self._fallback_endpoints,
        ]

        primary_key = self._api_key.get_secret_value().strip()
        if not primary_key and len(endpoints) == 1:
            raise AIProviderError(
                "AI__API_KEY is not configured; refusing unauthenticated external AI request."
            )

        last_error: Exception | None = None
        for ep in endpoints:
            raw_key = ep["api_key"]
            ep_key = (
                raw_key.get_secret_value().strip()
                if isinstance(raw_key, SecretStr)
                else str(raw_key).strip()
            )
            if not ep_key:
                continue

            try:
                return await self._execute_endpoint_with_retry(
                    endpoint=ep,
                    system_prompt=system_prompt,
                    user_payload=user_payload,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "ai_provider_endpoint_failed_trying_fallback",
                    provider=ep.get("name", "unknown"),
                    base_url=ep.get("base_url"),
                    model=ep.get("model"),
                    error=str(exc),
                )
                continue

        if last_error is not None:
            raise AIProviderError(
                f"All AI providers in fallback chain failed: {last_error}"
            )
        raise AIProviderError(
            "AI__API_KEY is not configured; refusing unauthenticated external AI request."
        )

    async def _execute_endpoint_with_retry(
        self,
        *,
        endpoint: dict[str, Any],
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        """Execute request against a specific provider endpoint with retries."""
        base_url = endpoint["base_url"].strip().rstrip("/")
        secret_value = (
            endpoint["api_key"].get_secret_value().strip()
            if isinstance(endpoint["api_key"], SecretStr)
            else str(endpoint["api_key"]).strip()
        )
        model = endpoint["model"]
        timeout_s = float(endpoint.get("timeout_s", self._timeout_s))
        name = endpoint.get("name", "provider")

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {secret_value}",
            "Content-Type": "application/json",
        }
        request_body: dict[str, Any] = {
            "model": model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, sort_keys=True, separators=(",", ":")),
                },
            ],
        }

        # Provider-specific parameter optimizations
        if "mistral" in model.lower() or "nvidia" in base_url.lower():
            request_body["reasoning_effort"] = "low"
            request_body["max_tokens"] = 2048
        else:
            request_body["response_format"] = {"type": "json_object"}

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    url,
                    headers=headers,
                    json=request_body,
                    timeout=httpx.Timeout(timeout_s),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning(
                    "ai_provider_transport_error",
                    provider=name,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                    error_type=type(exc).__name__,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_base_s * (2**attempt))
                    continue
                raise AIProviderError(
                    f"AI provider {name} transport failure after {attempt + 1} attempts: "
                    f"{type(exc).__name__}"
                ) from exc

            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_exc = AIProviderError(f"HTTP {response.status_code}")
                logger.warning(
                    "ai_provider_retryable_status",
                    provider=name,
                    status_code=response.status_code,
                    attempt=attempt + 1,
                    max_attempts=self._max_retries + 1,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_base_s * (2**attempt))
                    continue
                raise AIProviderError(
                    f"AI provider {name} returned HTTP {response.status_code} "
                    f"after {attempt + 1} attempts."
                )

            if response.status_code >= 400:
                raise AIProviderError(
                    f"AI provider {name} rejected request with HTTP {response.status_code}."
                )

            try:
                data = response.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content")
                if not content and msg.get("reasoning_content"):
                    content = msg.get("reasoning_content")
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AIProviderError(
                    f"AI provider {name} returned unexpected response envelope."
                ) from exc

            if not isinstance(content, str) or not content.strip():
                raise AIProviderError(f"AI provider {name} returned empty completion content.")

            text = content.strip()
            fence_match = _CODE_FENCE_RE.match(text)
            if fence_match is not None:
                text = fence_match.group(1).strip()

            return text

        raise AIProviderError(f"AI provider {name} call failed: {last_exc}")

    async def close(self) -> None:
        """Close owned httpx.AsyncClient."""
        if self._owns_client:
            await self._client.aclose()

