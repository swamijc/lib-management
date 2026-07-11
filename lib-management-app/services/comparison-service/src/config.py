"""Comparison Service — configuration."""
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "comparison-service"
    service_version: str = "1.0.0"

    library_data_service_url: str = Field(
        default="http://library-data-service:8001",
        description="Base URL for library-data-service",
    )
    scraper_service_url: str = Field(
        default="http://scraper-service:8002",
        description="Base URL for scraper-service",
    )

    # Max libraries fetched in one batch comparison
    batch_page_size: int = 500


settings = Settings()
