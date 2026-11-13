"""Configuration parameters for the advisory NEXUS AI market analysis module."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator

from nexus.core.exceptions import ConfigurationInvariantError


class AIAnalysisConfig(BaseModel):
    """Advisory AI analysis settings (strictly read-only, zero execution access)."""

    enabled: bool = True
    provider: Literal["openai_compatible", "deterministic"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("api_key", "AI__API_KEY", "AI_API_KEY", "NVIDIA_API_KEY"),
    )
    model: str = "gpt-4o-mini"
    timeout_s: float = Field(default=45.0, ge=1.0, le=120.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    backoff_base_s: float = Field(default=0.5, ge=0.05, le=10.0)
    cache_ttl_seconds: int = Field(default=300, ge=0, le=86400)
    cache_max_entries: int = Field(default=256, ge=1, le=5000)
    fallback_to_deterministic: bool = True
    strict_price_tolerance_pct: float = Field(default=0.5, ge=0.0, le=5.0)

    # Multi-Provider Fallback Chain
    fallback_1_name: str = "nvidia_nim"
    fallback_1_base_url: str | None = None
    fallback_1_api_key: SecretStr | None = None
    fallback_1_model: str | None = None
    fallback_1_timeout_s: float = Field(default=45.0, ge=1.0, le=120.0)

    fallback_2_name: str = "crow_llm"
    fallback_2_base_url: str | None = None
    fallback_2_api_key: SecretStr | None = None
    fallback_2_model: str | None = None
    fallback_2_timeout_s: float = Field(default=15.0, ge=1.0, le=120.0)

    fallback_3_name: str = "hcnote"
    fallback_3_base_url: str | None = None
    fallback_3_api_key: SecretStr | None = None
    fallback_3_model: str | None = None
    fallback_3_timeout_s: float = Field(default=10.0, ge=1.0, le=120.0)

    def get_fallback_endpoints(self) -> list[dict[str, object]]:
        """Return list of non-empty fallback endpoints configured for AI resilience."""
        fallbacks: list[dict[str, object]] = []
        for name, url, key, model, timeout in [
            (
                self.fallback_1_name,
                self.fallback_1_base_url,
                self.fallback_1_api_key,
                self.fallback_1_model,
                self.fallback_1_timeout_s,
            ),
            (
                self.fallback_2_name,
                self.fallback_2_base_url,
                self.fallback_2_api_key,
                self.fallback_2_model,
                self.fallback_2_timeout_s,
            ),
            (
                self.fallback_3_name,
                self.fallback_3_base_url,
                self.fallback_3_api_key,
                self.fallback_3_model,
                self.fallback_3_timeout_s,
            ),
        ]:
            if url and key and key.get_secret_value().strip():
                clean_url = url.strip().rstrip("/")
                if clean_url.startswith("http://") or clean_url.startswith("https://"):
                    fallbacks.append({
                        "name": name,
                        "base_url": clean_url,
                        "api_key": key,
                        "model": model.strip() if model else self.model,
                        "timeout_s": timeout,
                    })
        return fallbacks

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """Ensure configured AI API base URL uses HTTP(S)."""
        stripped = value.strip().rstrip("/")
        if not (stripped.startswith("https://") or stripped.startswith("http://")):
            raise ConfigurationInvariantError("AI base_url must start with http:// or https://")
        return stripped

    @field_validator("model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        """Ensure model name is non-empty."""
        stripped = value.strip()
        if not stripped:
            raise ConfigurationInvariantError("AI model name cannot be empty")
        return stripped

