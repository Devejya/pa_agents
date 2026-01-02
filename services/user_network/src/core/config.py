"""
Configuration settings for User Network Service.

Uses pydantic-settings for environment variable loading.
In production, secrets are loaded from AWS Secrets Manager.
In development, secrets are loaded from .env file or LocalStack.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _normalize_secret_keys(secrets: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize secret keys to snake_case to match pydantic field names.
    
    AWS Secrets Manager JSON might have keys like:
    - DATABASE_URL (UPPER_CASE from env convention)
    - database_url (already snake_case)
    
    Pydantic fields are snake_case, so we normalize all keys.
    """
    normalized = {}
    for key, value in secrets.items():
        # Convert UPPER_CASE to snake_case (e.g., DATABASE_URL -> database_url)
        normalized_key = key.lower()
        normalized[normalized_key] = value
    return normalized


def _load_secrets_from_aws() -> Dict[str, Any]:
    """Load secrets from AWS Secrets Manager."""
    from .secrets import get_secrets

    secret_name = os.getenv(
        "AWS_SECRET_NAME",
        "yennifer/user-network/production"
    )
    secrets = get_secrets(secret_name)
    
    # Log which keys were loaded (without values for security)
    logger.info(f"Loaded secrets keys: {list(secrets.keys())}")
    
    # Normalize keys to snake_case to match pydantic field names
    return _normalize_secret_keys(secrets)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    In production (ENVIRONMENT=production), settings are loaded from
    AWS Secrets Manager. In development, settings come from .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env" if os.getenv("ENVIRONMENT") != "production" else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars from shared secrets
    )

    @model_validator(mode="before")
    @classmethod
    def load_from_secrets_manager(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Load secrets from AWS Secrets Manager in production."""
        if os.getenv("ENVIRONMENT") == "production":
            try:
                secrets_data = _load_secrets_from_aws()
                # Merge secrets (secrets take precedence over env vars)
                # This allows non-secret config to still come from env vars
                return {**values, **secrets_data}
            except Exception as e:
                logger.error(f"Failed to load secrets from AWS: {e}")
                raise
        return values

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
    # Also accepts user_network_api_key from shared secrets
    api_keys: str = ""  # e.g., "key1,key2,key3"
    user_network_api_key: str = ""  # Alternative: single key from shared secrets

    # CORS (comma-separated list of allowed origins)
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://localhost:5173"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or console

    @property
    def api_keys_list(self) -> list[str]:
        """Parse API keys into list. Accepts both api_keys and user_network_api_key."""
        keys = []
        
        # Add keys from comma-separated api_keys
        if self.api_keys:
            keys.extend([key.strip() for key in self.api_keys.split(",") if key.strip()])
        
        # Add single key from user_network_api_key (used by shared secrets)
        if self.user_network_api_key and self.user_network_api_key not in keys:
            keys.append(self.user_network_api_key)
        
        return keys

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

