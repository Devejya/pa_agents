"""
Configuration settings for User Network Service.

Uses pydantic-settings for environment variable loading.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Service
    service_name: str = "user-network"
    environment: str = "development"  # development, staging, production
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8001

    # Database
    database_url: str = "postgresql://localhost:5432/user_network"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # API Keys (comma-separated list of valid keys)
    api_keys: str = ""  # e.g., "key1,key2,key3"

    # CORS (comma-separated list of allowed origins)
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://localhost:5173"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or console

    @property
    def api_keys_list(self) -> list[str]:
        """Parse comma-separated API keys into list."""
        if not self.api_keys:
            return []
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into list."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def asyncpg_url(self) -> str:
        """Convert database URL to asyncpg format."""
        # Replace postgresql:// with postgresql+asyncpg://
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

