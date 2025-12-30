"""
Encryption utilities for sensitive data.

Uses Fernet symmetric encryption from the cryptography library.
"""

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Cache the Fernet instance
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """
    Get or create the Fernet encryption instance.
    
    Returns:
        Fernet instance for encryption/decryption.
        
    Raises:
        ValueError: If encryption key is not configured.
    """
    global _fernet
    
    if _fernet is not None:
        return _fernet
    
    settings = get_settings()
    
    if not settings.encryption_key:
        raise ValueError(
            "ENCRYPTION_KEY not configured. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    
    try:
        # Ensure key is bytes
        key = settings.encryption_key
        if isinstance(key, str):
            key = key.encode()
        
        _fernet = Fernet(key)
        return _fernet
        
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {e}")
        raise ValueError(f"Invalid encryption key: {e}")


def encrypt_token(data: str) -> str:
    """
    Encrypt sensitive data (like OAuth tokens).
    
    Args:
        data: Plain text data to encrypt.
        
    Returns:
        Base64-encoded encrypted data.
        
    Raises:
        ValueError: If encryption fails.
    """
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError(f"Failed to encrypt data: {e}")


def decrypt_token(encrypted_data: str) -> str:
    """
    Decrypt encrypted data.
    
    Args:
        encrypted_data: Base64-encoded encrypted data.
        
    Returns:
        Decrypted plain text data.
        
    Raises:
        ValueError: If decryption fails (e.g., wrong key, corrupted data).
    """
    try:
        fernet = _get_fernet()
        decoded = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    except InvalidToken:
        logger.error("Decryption failed: Invalid token (wrong key or corrupted data)")
        raise ValueError("Failed to decrypt data: Invalid token")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise ValueError(f"Failed to decrypt data: {e}")


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Returns:
        A new base64-encoded encryption key.
    """
    return Fernet.generate_key().decode()

