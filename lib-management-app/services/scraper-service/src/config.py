"""
Scraper Service — configuration.
"""
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "scraper-service"
    service_version: str = "1.0.0"

    # ── HTTP client ─────────────────────────────────────────────────────────
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 3
    http_retry_wait_seconds: float = 2.0

    # ── Circuit breaker ──────────────────────────────────────────────────────
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60  # seconds

    # ── Cache freshness ──────────────────────────────────────────────────────
    # How long (hours) a cached scrape result is considered fresh (T1 gap)
    scrape_cache_ttl_hours: int = 24

    # ── GitHub API ───────────────────────────────────────────────────────────
    # Optional: avoids rate-limiting on unauthenticated calls
    github_token: str = Field(default="", description="GitHub personal access token")

    # ── Library Data Service ─────────────────────────────────────────────────
    library_data_service_url: str = Field(
        default="http://library-data-service:8001",
        description="Internal URL for library-data-service",
    )


settings = Settings()
