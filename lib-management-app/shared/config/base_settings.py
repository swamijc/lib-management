"""
Shared base Pydantic settings for all services.
Each service subclasses ServiceSettings and adds its own fields.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class ServiceSettings(BaseSettings):
    """Common settings inherited by every service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ────────────────────────────────────────────────────
    service_name: str = "lib-mgmt-service"
    service_version: str = "1.0.0"
    debug: bool = False

    # ── Internal auth (service-to-service) ──────────────────────────────────
    internal_service_key: str = Field(
        ..., description="Shared secret for internal service calls (X-Internal-Service-Key header)"
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:////app/db/library_management.db",
        description="SQLAlchemy async database URL",
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"  # 'json' | 'console'

    # ── API Gateway (used by ui-service and inter-service calls) ────────────
    api_gateway_url: str = Field(
        default="http://api-gateway:8000",
        description="Internal Docker hostname of the API Gateway",
    )
