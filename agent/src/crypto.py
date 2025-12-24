"""
Encryption Utilities

Handles secure storage of style profiles using AES-256 encryption.
Key is auto-generated on first run and stored locally.
"""

import os
import json
from pathlib import Path
from cryptography.fernet import Fernet


# Storage paths - in user's home directory (hidden folder)
AGENT_DIR = Path.home() / ".gmail_agent"
KEY_PATH = AGENT_DIR / "secret.key"
PROFILE_PATH = AGENT_DIR / "style_profile.enc"


def _ensure_directory():
    """Create the agent directory if it doesn't exist."""
    AGENT_DIR.mkdir(mode=0o700, exist_ok=True)


def get_or_create_key() -> bytes:
    """
    Get existing encryption key or generate a new one.
    
    The key is stored locally with restricted permissions (owner-only).
    This happens once on first run.
    
    Returns:
        256-bit encryption key
    """
    _ensure_directory()
    
    if KEY_PATH.exists():
        with open(KEY_PATH, "rb") as f:
            return f.read()
    
    # First run: generate new key
    key = Fernet.generate_key()
    
    with open(KEY_PATH, "wb") as f:
        f.write(key)
    
    # Set restrictive permissions (owner read/write only)
    os.chmod(KEY_PATH, 0o600)
    
    return key


def encrypt_data(data: dict) -> bytes:
    """
    Encrypt a dictionary using the local key.
    
    Args:
        data: Dictionary to encrypt
        
    Returns:
        Encrypted bytes
    """
    key = get_or_create_key()
    fernet = Fernet(key)
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    return fernet.encrypt(json_bytes)


def decrypt_data(encrypted: bytes) -> dict:
    """
    Decrypt bytes using the local key.
    
    Args:
        encrypted: Encrypted bytes
        
    Returns:
        Decrypted dictionary
    """
    key = get_or_create_key()
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted)
    return json.loads(decrypted.decode("utf-8"))


def save_style_profile(profile: dict) -> Path:
    """
    Encrypt and save style profile to disk.
    
    Args:
        profile: Style profile dictionary
        
    Returns:
        Path where profile was saved
    """
    _ensure_directory()
    encrypted = encrypt_data(profile)
    
    with open(PROFILE_PATH, "wb") as f:
        f.write(encrypted)
    
    os.chmod(PROFILE_PATH, 0o600)
    return PROFILE_PATH


def load_style_profile() -> dict | None:
    """
    Load and decrypt style profile from disk.
    
    Returns:
        Style profile dictionary, or None if not found
    """
    if not PROFILE_PATH.exists():
        return None
    
    try:
        with open(PROFILE_PATH, "rb") as f:
            encrypted = f.read()
        return decrypt_data(encrypted)
    except Exception:
        return None


def profile_exists() -> bool:
    """Check if a style profile exists."""
    return PROFILE_PATH.exists()


def delete_profile() -> bool:
    """
    Delete the style profile (but keep the key).
    
    Returns:
        True if deleted, False if didn't exist
    """
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
        return True
    return False


def get_profile_info() -> dict:
    """
    Get information about the stored profile.
    
    Returns:
        Dict with profile metadata
    """
    info = {
        "profile_exists": PROFILE_PATH.exists(),
        "key_exists": KEY_PATH.exists(),
        "storage_path": str(AGENT_DIR),
    }
    
    if PROFILE_PATH.exists():
        stat = PROFILE_PATH.stat()
        info["profile_size_bytes"] = stat.st_size
        info["profile_modified"] = stat.st_mtime
    
    return info

