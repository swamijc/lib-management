"""UI Service — configuration."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_gateway_url: str = "http://api-gateway:8000"
    page_title: str = "SDK Management System"
    page_icon: str = "📚"
    request_timeout: float = 30.0


settings = Settings()
