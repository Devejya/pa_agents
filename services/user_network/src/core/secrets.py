"""
AWS Secrets Manager integration for loading configuration.

This module provides a SecretsManagerLoader class that fetches secrets
from AWS Secrets Manager and caches them for the application lifecycle.

In production, secrets are loaded from AWS Secrets Manager.
In development, you can use LocalStack by setting AWS_SECRETS_ENDPOINT_URL.
"""

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SecretsManagerLoader:
    """Load secrets from AWS Secrets Manager."""

    def __init__(
        self,
        secret_name: str,
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,  # For LocalStack
    ):
        """
        Initialize the secrets loader.

        Args:
            secret_name: Name of the secret in Secrets Manager (e.g., "yennifer/user-network/production")
            region: AWS region where the secret is stored
            endpoint_url: Optional endpoint URL for LocalStack or other compatible services
        """
        self.secret_name = secret_name
        self.region = region
        self.endpoint_url = endpoint_url
        self._client = None
        self._cache: Optional[Dict[str, Any]] = None

    @property
    def client(self):
        """Lazy-initialize the boto3 Secrets Manager client."""
        if self._client is None:
            kwargs = {
                "service_name": "secretsmanager",
                "region_name": self.region,
            }
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client = boto3.client(**kwargs)
        return self._client

    def load(self) -> Dict[str, Any]:
        """
        Fetch and parse secret from Secrets Manager.

        Returns:
            Dictionary of secret key-value pairs

        Raises:
            RuntimeError: If the secret cannot be loaded or parsed
        """
        if self._cache is not None:
            return self._cache

        try:
            logger.info(f"Loading secrets from AWS Secrets Manager: {self.secret_name}")
            response = self.client.get_secret_value(SecretId=self.secret_name)
            self._cache = json.loads(response["SecretString"])
            logger.info(f"Successfully loaded {len(self._cache)} secret keys")
            return self._cache
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                raise RuntimeError(
                    f"Secret '{self.secret_name}' not found in Secrets Manager. "
                    f"Please create it in AWS Console."
                )
            elif error_code == "AccessDeniedException":
                raise RuntimeError(
                    f"Access denied to secret '{self.secret_name}'. "
                    f"Check IAM permissions for secretsmanager:GetSecretValue."
                )
            else:
                raise RuntimeError(f"Failed to load secret {self.secret_name}: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Secret '{self.secret_name}' is not valid JSON: {e}"
            )


@lru_cache
def get_secrets(secret_name: str) -> Dict[str, Any]:
    """
    Get cached secrets for a service.

    This function is cached so secrets are only loaded once per process.
    Use clear_secrets_cache() to force a reload.

    Args:
        secret_name: Name of the secret in Secrets Manager

    Returns:
        Dictionary of secret key-value pairs
    """
    # Check for LocalStack endpoint (for local development)
    endpoint_url = os.getenv("AWS_SECRETS_ENDPOINT_URL")
    region = os.getenv("AWS_REGION", "us-east-1")

    loader = SecretsManagerLoader(
        secret_name=secret_name,
        region=region,
        endpoint_url=endpoint_url,
    )
    return loader.load()


def clear_secrets_cache():
    """Clear the secrets cache to force a reload on next access."""
    get_secrets.cache_clear()
    logger.info("Secrets cache cleared")

