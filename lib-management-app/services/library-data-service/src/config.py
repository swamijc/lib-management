"""
Library Data Service — configuration.
Inherits common fields from shared base and adds service-specific settings.
"""
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "library-data-service"
    service_version: str = "1.0.0"

    # Database path is set via DATABASE_URL env var (see base_settings)
    # Default inside Docker: sqlite+aiosqlite:////app/db/library_management.db

    # Export limits
    export_max_rows: int = 10_000

    # Business-rule migration toggle (backend-computed aggregates)
    use_backend_business_rules: bool = True


settings = Settings()
