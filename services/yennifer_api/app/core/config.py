"""
Configuration settings for Yennifer API Service.

In production, secrets are loaded from AWS Secrets Manager.
In development, secrets are loaded from .env file or LocalStack.
"""

import logging
import os
import secrets
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _normalize_secret_keys(secrets: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize secret keys to snake_case to match pydantic field names.
    
    AWS Secrets Manager JSON might have keys like:
    - POSTHOG_API_KEY (UPPER_CASE from env convention)
    - posthog_api_key (already snake_case)
    
    Pydantic fields are snake_case, so we normalize all keys.
    """
    normalized = {}
    for key, value in secrets.items():
        # Convert UPPER_CASE to snake_case (e.g., POSTHOG_API_KEY -> posthog_api_key)
        normalized_key = key.lower()
        normalized[normalized_key] = value
    return normalized


def _load_secrets_from_aws() -> Dict[str, Any]:
    """Load secrets from AWS Secrets Manager."""
    from .secrets import get_secrets

    secret_name = os.getenv(
        "AWS_SECRET_NAME",
        "yennifer/yennifer-api/production"
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
    service_name: str = "yennifer-api"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Database (PostgreSQL)
    database_url: str = "postgresql://localhost:5432/yennifer"
    database_pool_size: int = 10
    
    # Encryption key for sensitive data (Fernet key, 32 url-safe base64 chars)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # User Network Service
    user_network_api_url: str = "http://localhost:8001"
    user_network_api_key: str = ""

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Logging
    log_level: str = "INFO"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    
    # JWT Settings
    jwt_secret_key: str = secrets.token_urlsafe(32)  # Auto-generate if not set
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24 * 7  # 7 days
    
    # Allowed Users (comma-separated emails)
    allowed_emails: str = ""
    
    # Frontend URL (for redirects)
    frontend_url: str = "http://localhost:5173"
    
    # SendGrid Email Service
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "yennifer@yennifer.ai"
    sendgrid_from_name: str = "Yennifer"
    
    # Admin email for notifications
    admin_email: str = "draghuva@gmail.com"
    
    # AWS KMS for per-user encryption
    kms_key_id: str = "alias/yennifer-kek"
    aws_region: str = "us-east-1"
    
    # Redis for hot cache tier (optional)
    redis_url: str = ""  # e.g., redis://localhost:6379/0 or ElastiCache endpoint
    
    # S3 for cold storage tier (optional)
    chat_archive_bucket: str = ""  # e.g., yennifer-chat-archives
    
    # Google Custom Search API
    google_cse_api_key: str = ""  # API key from Google Cloud Console
    google_cse_id: str = ""  # Custom Search Engine ID from Programmable Search Engine
    google_cse_max_results: int = 5  # Default number of results per search
    google_cse_enabled: bool = True  # Feature flag to enable/disable web search
    
    # PostHog Analytics (same project as frontend waitlist)
    posthog_api_key: str = ""  # Same key as VITE_PUBLIC_POSTHOG_KEY
    posthog_host: str = "https://us.i.posthog.com"  # Same as VITE_PUBLIC_POSTHOG_HOST

    @property
    def web_search_available(self) -> bool:
        """Check if web search is properly configured."""
        return (
            self.google_cse_enabled
            and bool(self.google_cse_api_key)
            and bool(self.google_cse_id)
        )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into list."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_emails_list(self) -> List[str]:
        """Parse comma-separated allowed emails into list."""
        if not self.allowed_emails:
            return []
        return [email.strip().lower() for email in self.allowed_emails.split(",") if email.strip()]

    def is_email_allowed(self, email: str) -> bool:
        """Check if an email is in the allowed list."""
        allowed = self.allowed_emails_list
        if not allowed:
            # If no whitelist configured, deny all in production
            return self.environment == "development"
        return email.lower() in allowed


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
