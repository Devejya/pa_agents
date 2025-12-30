"""
Encryption utilities for Yennifer multi-tenant data protection.

Key Hierarchy:
- KEK (Key Encryption Key): AWS KMS CMK - never leaves KMS
- DEK (Data Encryption Key): Per-user AES-256 key, encrypted by KEK, stored in users table

Usage:
    from app.core.encryption import UserEncryption
    
    encryption = UserEncryption()
    
    # Create new user DEK
    plaintext_dek, encrypted_blob = encryption.generate_user_dek()
    # Store encrypted_blob in users.encryption_key_blob
    
    # Later, decrypt user's DEK
    dek = encryption.decrypt_user_dek(encrypted_blob)
    
    # Encrypt data for user
    ciphertext = encryption.encrypt_for_user(dek, "sensitive data")
    
    # Decrypt data for user
    plaintext = encryption.decrypt_for_user(dek, ciphertext)
"""

import base64
import hashlib
import logging
import os
from functools import lru_cache
from typing import Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Base exception for encryption operations."""
    pass


class KMSError(EncryptionError):
    """Error communicating with AWS KMS."""
    pass


class DecryptionError(EncryptionError):
    """Error decrypting data."""
    pass


class UserEncryption:
    """
    Handles per-user encryption using AWS KMS for key management.
    
    Each user gets their own DEK (Data Encryption Key) which is:
    1. Generated via KMS GenerateDataKey
    2. Stored encrypted (by KMS KEK) in the users table
    3. Decrypted at runtime to encrypt/decrypt user data
    """
    
    def __init__(
        self,
        kms_key_id: Optional[str] = None,
        region_name: str = "us-east-1",
    ):
        """
        Initialize UserEncryption.
        
        Args:
            kms_key_id: KMS key ID or alias (e.g., "alias/yennifer-kek")
                       Defaults to KMS_KEY_ID environment variable
            region_name: AWS region for KMS
        """
        self.kms_key_id = kms_key_id or os.environ.get("KMS_KEY_ID", "alias/yennifer-kek")
        self.region_name = region_name
        self._kms_client = None
    
    @property
    def kms(self):
        """Lazy-load KMS client."""
        if self._kms_client is None:
            self._kms_client = boto3.client("kms", region_name=self.region_name)
        return self._kms_client
    
    def generate_user_dek(self) -> Tuple[bytes, bytes]:
        """
        Generate a new DEK for a user.
        
        Returns:
            Tuple of (plaintext_dek, encrypted_dek_blob)
            - plaintext_dek: 32-byte key for immediate use (don't store this!)
            - encrypted_dek_blob: Encrypted key to store in database
        
        Raises:
            KMSError: If KMS operation fails
        """
        try:
            response = self.kms.generate_data_key(
                KeyId=self.kms_key_id,
                KeySpec="AES_256"
            )
            
            plaintext_dek = response["Plaintext"]  # 32 bytes
            encrypted_blob = response["CiphertextBlob"]  # Encrypted by KMS
            
            logger.info("Generated new user DEK")
            return plaintext_dek, encrypted_blob
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"KMS GenerateDataKey failed: {error_code} - {e}")
            raise KMSError(f"Failed to generate data key: {error_code}") from e
    
    def decrypt_user_dek(self, encrypted_blob: bytes) -> bytes:
        """
        Decrypt a user's DEK using KMS.
        
        Args:
            encrypted_blob: The encrypted DEK from users.encryption_key_blob
        
        Returns:
            32-byte plaintext DEK for encryption/decryption operations
        
        Raises:
            KMSError: If KMS operation fails
        """
        try:
            response = self.kms.decrypt(
                KeyId=self.kms_key_id,
                CiphertextBlob=encrypted_blob
            )
            
            return response["Plaintext"]
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"KMS Decrypt failed: {error_code} - {e}")
            raise KMSError(f"Failed to decrypt data key: {error_code}") from e
    
    def encrypt_for_user(self, user_dek: bytes, plaintext: str) -> bytes:
        """
        Encrypt data using a user's DEK.
        
        Args:
            user_dek: The decrypted 32-byte DEK
            plaintext: String data to encrypt
        
        Returns:
            Encrypted bytes (Fernet token)
        """
        fernet_key = self._dek_to_fernet_key(user_dek)
        f = Fernet(fernet_key)
        return f.encrypt(plaintext.encode("utf-8"))
    
    def decrypt_for_user(self, user_dek: bytes, ciphertext: bytes) -> str:
        """
        Decrypt data using a user's DEK.
        
        Args:
            user_dek: The decrypted 32-byte DEK
            ciphertext: Encrypted bytes (Fernet token)
        
        Returns:
            Decrypted string
        
        Raises:
            DecryptionError: If decryption fails (wrong key, corrupted data, etc.)
        """
        try:
            fernet_key = self._dek_to_fernet_key(user_dek)
            f = Fernet(fernet_key)
            return f.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            logger.error("Decryption failed: invalid token (wrong key or corrupted data)")
            raise DecryptionError("Failed to decrypt data: invalid token") from e
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt data: {e}") from e
    
    def encrypt_bytes_for_user(self, user_dek: bytes, data: bytes) -> bytes:
        """
        Encrypt binary data using a user's DEK.
        
        Args:
            user_dek: The decrypted 32-byte DEK
            data: Binary data to encrypt
        
        Returns:
            Encrypted bytes (Fernet token)
        """
        fernet_key = self._dek_to_fernet_key(user_dek)
        f = Fernet(fernet_key)
        return f.encrypt(data)
    
    def decrypt_bytes_for_user(self, user_dek: bytes, ciphertext: bytes) -> bytes:
        """
        Decrypt binary data using a user's DEK.
        
        Args:
            user_dek: The decrypted 32-byte DEK
            ciphertext: Encrypted bytes (Fernet token)
        
        Returns:
            Decrypted bytes
        
        Raises:
            DecryptionError: If decryption fails
        """
        try:
            fernet_key = self._dek_to_fernet_key(user_dek)
            f = Fernet(fernet_key)
            return f.decrypt(ciphertext)
        except InvalidToken as e:
            logger.error("Decryption failed: invalid token")
            raise DecryptionError("Failed to decrypt data: invalid token") from e
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt data: {e}") from e
    
    @staticmethod
    def _dek_to_fernet_key(dek: bytes) -> bytes:
        """
        Convert a 32-byte DEK to a Fernet-compatible key.
        
        Fernet requires a 32-byte key that is base64-encoded.
        Our DEK from KMS is already 32 bytes (AES-256).
        """
        return base64.urlsafe_b64encode(dek)
    
    @staticmethod
    def hash_for_lookup(value: str) -> bytes:
        """
        Create a deterministic hash for database lookups.
        
        Use this for values that need to be searchable but shouldn't
        be stored in plaintext (e.g., provider_user_id in user_identities).
        
        Args:
            value: String to hash
        
        Returns:
            SHA-256 hash as bytes
        """
        return hashlib.sha256(value.encode("utf-8")).digest()
    
    @staticmethod
    def hash_for_lookup_hex(value: str) -> str:
        """
        Create a deterministic hash for database lookups (hex string).
        
        Same as hash_for_lookup but returns a hex string instead of bytes.
        Useful when the database column is VARCHAR instead of BYTEA.
        
        Args:
            value: String to hash
        
        Returns:
            SHA-256 hash as hex string
        """
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --- Singleton instance for app-wide use ---

_encryption_instance: Optional[UserEncryption] = None


def get_encryption() -> UserEncryption:
    """
    Get the singleton UserEncryption instance.
    
    Returns:
        UserEncryption instance configured from environment
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = UserEncryption()
    return _encryption_instance


# --- Helper functions for common operations ---

def generate_user_dek() -> Tuple[bytes, bytes]:
    """Generate a new DEK for a user. Returns (plaintext_dek, encrypted_blob)."""
    return get_encryption().generate_user_dek()


def decrypt_user_dek(encrypted_blob: bytes) -> bytes:
    """Decrypt a user's DEK from the stored encrypted blob."""
    return get_encryption().decrypt_user_dek(encrypted_blob)


def encrypt_for_user(user_dek: bytes, plaintext: str) -> bytes:
    """Encrypt a string for a user."""
    return get_encryption().encrypt_for_user(user_dek, plaintext)


def decrypt_for_user(user_dek: bytes, ciphertext: bytes) -> str:
    """Decrypt a string for a user."""
    return get_encryption().decrypt_for_user(user_dek, ciphertext)


def hash_provider_id(provider: str, provider_user_id: str) -> bytes:
    """
    Hash a provider + provider_user_id for user_identities lookup.
    
    Args:
        provider: OAuth provider (e.g., "google", "apple")
        provider_user_id: Provider's user ID (e.g., Google's "sub" claim)
    
    Returns:
        SHA-256 hash as bytes
    """
    combined = f"{provider}:{provider_user_id}"
    return UserEncryption.hash_for_lookup(combined)

