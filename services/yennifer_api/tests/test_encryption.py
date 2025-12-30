"""
Test script for encryption module.

Run with: 
    cd services/yennifer_api
    python -m pytest tests/test_encryption.py -v

Or for manual testing:
    cd services/yennifer_api
    python tests/test_encryption.py
"""

import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_encryption_imports():
    """Test that encryption module can be imported."""
    from app.core.encryption import (
        UserEncryption,
        get_encryption,
        hash_provider_id,
        EncryptionError,
        KMSError,
        DecryptionError,
    )
    print("✅ All imports successful")


def test_hash_functions():
    """Test hashing functions (no KMS required)."""
    from app.core.encryption import UserEncryption, hash_provider_id
    
    # Test hash_for_lookup
    hash1 = UserEncryption.hash_for_lookup("test@example.com")
    hash2 = UserEncryption.hash_for_lookup("test@example.com")
    hash3 = UserEncryption.hash_for_lookup("other@example.com")
    
    assert hash1 == hash2, "Same input should produce same hash"
    assert hash1 != hash3, "Different input should produce different hash"
    assert len(hash1) == 32, "SHA-256 should be 32 bytes"
    print("✅ hash_for_lookup works correctly")
    
    # Test hash_for_lookup_hex
    hex_hash = UserEncryption.hash_for_lookup_hex("test@example.com")
    assert len(hex_hash) == 64, "SHA-256 hex should be 64 chars"
    print("✅ hash_for_lookup_hex works correctly")
    
    # Test hash_provider_id
    provider_hash = hash_provider_id("google", "12345")
    provider_hash2 = hash_provider_id("google", "12345")
    provider_hash3 = hash_provider_id("apple", "12345")
    
    assert provider_hash == provider_hash2, "Same provider+id should produce same hash"
    assert provider_hash != provider_hash3, "Different provider should produce different hash"
    print("✅ hash_provider_id works correctly")


def test_kms_operations():
    """
    Test KMS operations (requires AWS credentials and KMS key).
    
    This test will only pass if:
    1. AWS credentials are configured (via env vars, ~/.aws/credentials, or IAM role)
    2. KMS_KEY_ID environment variable is set (or defaults to alias/yennifer-kek)
    3. The credentials have permission to use the KMS key
    """
    from app.core.encryption import UserEncryption, get_encryption
    
    print("\n--- Testing KMS Operations ---")
    print(f"KMS Key ID: {os.environ.get('KMS_KEY_ID', 'alias/yennifer-kek')}")
    print(f"AWS Region: {os.environ.get('AWS_REGION', 'us-east-1')}")
    
    try:
        encryption = get_encryption()
        
        # Test 1: Generate DEK
        print("\n1. Generating user DEK...")
        plaintext_dek, encrypted_blob = encryption.generate_user_dek()
        assert len(plaintext_dek) == 32, "DEK should be 32 bytes (AES-256)"
        assert len(encrypted_blob) > 0, "Encrypted blob should not be empty"
        print(f"   ✅ DEK generated: {len(plaintext_dek)} bytes plaintext, {len(encrypted_blob)} bytes encrypted")
        
        # Test 2: Decrypt DEK
        print("\n2. Decrypting DEK...")
        decrypted_dek = encryption.decrypt_user_dek(encrypted_blob)
        assert decrypted_dek == plaintext_dek, "Decrypted DEK should match original"
        print("   ✅ DEK decrypted successfully, matches original")
        
        # Test 3: Encrypt/decrypt string data
        print("\n3. Testing string encryption...")
        test_data = "Hello, this is sensitive user data! 🔐"
        encrypted_data = encryption.encrypt_for_user(plaintext_dek, test_data)
        decrypted_data = encryption.decrypt_for_user(plaintext_dek, encrypted_data)
        assert decrypted_data == test_data, "Decrypted data should match original"
        print(f"   ✅ String encryption works: '{test_data[:20]}...' → {len(encrypted_data)} bytes → decrypted OK")
        
        # Test 4: Encrypt/decrypt binary data
        print("\n4. Testing binary encryption...")
        binary_data = b"\x00\x01\x02\x03\xff\xfe\xfd"
        encrypted_binary = encryption.encrypt_bytes_for_user(plaintext_dek, binary_data)
        decrypted_binary = encryption.decrypt_bytes_for_user(plaintext_dek, encrypted_binary)
        assert decrypted_binary == binary_data, "Decrypted binary should match original"
        print(f"   ✅ Binary encryption works: {len(binary_data)} bytes → {len(encrypted_binary)} bytes → decrypted OK")
        
        # Test 5: Verify different DEKs produce different ciphertext
        print("\n5. Testing key isolation...")
        plaintext_dek2, _ = encryption.generate_user_dek()
        encrypted_with_key1 = encryption.encrypt_for_user(plaintext_dek, "same data")
        encrypted_with_key2 = encryption.encrypt_for_user(plaintext_dek2, "same data")
        assert encrypted_with_key1 != encrypted_with_key2, "Different keys should produce different ciphertext"
        print("   ✅ Different DEKs produce different ciphertext (key isolation works)")
        
        # Test 6: Verify wrong key fails decryption
        print("\n6. Testing decryption with wrong key...")
        try:
            encryption.decrypt_for_user(plaintext_dek2, encrypted_with_key1)
            print("   ❌ Should have raised DecryptionError!")
            assert False, "Decryption with wrong key should fail"
        except Exception as e:
            print(f"   ✅ Correctly rejected wrong key: {type(e).__name__}")
        
        print("\n" + "=" * 50)
        print("🎉 All KMS encryption tests passed!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ KMS test failed: {type(e).__name__}: {e}")
        print("\nMake sure:")
        print("1. AWS credentials are configured")
        print("2. KMS key 'alias/yennifer-kek' exists in us-east-1")
        print("3. Your credentials have permission to use the key")
        raise


def main():
    """Run all tests."""
    print("=" * 50)
    print("Yennifer Encryption Module Tests")
    print("=" * 50)
    
    # Tests that don't require AWS
    print("\n--- Non-AWS Tests ---")
    test_encryption_imports()
    test_hash_functions()
    
    # Tests that require AWS
    print("\n--- AWS KMS Tests ---")
    test_kms_operations()


if __name__ == "__main__":
    main()

