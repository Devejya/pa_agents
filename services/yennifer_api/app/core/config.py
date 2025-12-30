"""
Configuration settings for Yennifer API Service.
"""

import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

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
