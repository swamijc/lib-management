"""Recommendation Service — configuration."""
from __future__ import annotations
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "recommendation-service"
    service_version: str = "1.0.0"

    # ── Upstream services ────────────────────────────────────────────────────
    library_data_service_url: str = Field(
        default="http://library-data-service:8001",
    )
    comparison_service_url: str = Field(
        default="http://comparison-service:8003",
    )

    # ── LLM provider config ──────────────────────────────────────────────────
    # Provider string passed directly to litellm (e.g. "openai", "azure", "ollama/llama3")
    llm_provider: str = Field(
        default="",
        description="LLM provider key for litellm (empty = disabled → rule-based fallback)",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Model name passed to litellm",
    )
    llm_api_key: str = Field(
        default="",
        description="API key for the LLM provider",
    )
    llm_api_base: str = Field(
        default="",
        description="API base URL (required for Azure / Ollama)",
    )
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 30.0
    llm_ssl_verify: bool = True

    @property
    def llm_enabled(self) -> bool:
        """LLM is only active when provider AND api_key are both non-empty."""
        return bool(self.llm_provider and self.llm_api_key)


settings = Settings()
