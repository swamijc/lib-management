"""API Gateway — configuration."""
from __future__ import annotations
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "api-gateway"
    service_version: str = "1.0.0"

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(..., description="Secret key for signing JWT tokens")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480   # 8 hours

    # ── Rate limiting (slowapi) ───────────────────────────────────────────────
    rate_limit_default: str = "100/minute"
    rate_limit_auth: str = "10/minute"     # stricter for login endpoint

    # ── Downstream service URLs ───────────────────────────────────────────────
    library_data_service_url: str = Field(default="http://library-data-service:8001")
    scraper_service_url: str = Field(default="http://scraper-service:8002")
    comparison_service_url: str = Field(default="http://comparison-service:8003")
    recommendation_service_url: str = Field(default="http://recommendation-service:8004")
    notification_service_url: str = Field(default="http://notification-service:8005")
    scheduler_service_url: str = Field(default="http://scheduler-service:8006")

    # ── Default admin (created on first startup if no users exist) ────────────
    default_admin_username: str = Field(default="admin")
    default_admin_password: str = Field(
        default="changeme",
        description="Initial admin password — change immediately after first login",
    )

    # Business-rule migration toggle (additive backend-computed blocks)
    use_backend_business_rules: bool = True


settings = Settings()
