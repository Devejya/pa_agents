#!/usr/bin/env python3
"""
Diagnostic script to investigate encryption issues.

This script helps diagnose:
1. Whether AWS Secrets Manager is loading correctly
2. Whether KMS DEK decryption is working
3. Whether user data decryption is working
4. Find records encrypted with different keys

Usage:
    # From EC2, in the yennifer_api directory:
    source venv/bin/activate
    ENVIRONMENT=production python scripts/diagnose_encryption.py
    
    # Or with specific user:
    ENVIRONMENT=production python scripts/diagnose_encryption.py --user-id 9da8ee2a-3c05-42fc-a07f-d3bce0f08969
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from uuid import UUID

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def check_secrets_manager():
    """Check if AWS Secrets Manager is loading correctly."""
    print("\n" + "=" * 60)
    print("1. CHECKING AWS SECRETS MANAGER")
    print("=" * 60)
    
    try:
        from app.core.config import get_settings
        settings = get_settings()
        
        print(f"✓ Settings loaded successfully")
        print(f"  Environment: {settings.environment}")
        print(f"  KMS Key ID: {settings.kms_key_id}")
        print(f"  Database URL: {settings.database_url[:50]}..." if settings.database_url else "  Database URL: NOT SET")
        print(f"  PostHog API Key: {'SET' if settings.posthog_api_key else 'NOT SET'}")
        print(f"  OpenAI API Key: {'SET' if settings.openai_api_key else 'NOT SET'}")
        print(f"  Google Client ID: {'SET' if settings.google_client_id else 'NOT SET'}")
        print(f"  Encryption Key: {'SET' if settings.encryption_key else 'NOT SET'}")
        
        return True
    except Exception as e:
        print(f"✗ Failed to load settings: {e}")
        return False


async def check_kms():
    """Check if KMS is accessible."""
    print("\n" + "=" * 60)
    print("2. CHECKING AWS KMS")
    print("=" * 60)
    
    try:
        from app.core.encryption import get_encryption
        encryption = get_encryption()
        
        print(f"  KMS Key ID: {encryption.kms_key_id}")
        print(f"  Region: {encryption.region_name}")
        
        # Try to generate a test data key
        try:
            plaintext, encrypted = encryption.generate_user_dek()
            print(f"✓ KMS GenerateDataKey: OK (generated {len(plaintext)} byte key)")
            
            # Try to decrypt it back
            decrypted = encryption.decrypt_user_dek(encrypted)
            if decrypted == plaintext:
                print(f"✓ KMS Decrypt: OK (round-trip successful)")
            else:
                print(f"✗ KMS Decrypt: MISMATCH")
            
            return True
        except Exception as e:
            print(f"✗ KMS operation failed: {e}")
            return False
            
    except Exception as e:
        print(f"✗ Failed to initialize encryption: {e}")
        return False


async def check_database():
    """Check database connectivity."""
    print("\n" + "=" * 60)
    print("3. CHECKING DATABASE")
    print("=" * 60)
    
    try:
        import asyncpg
        from app.core.config import get_settings
        settings = get_settings()
        
        conn = await asyncpg.connect(settings.database_url)
        
        # Count users
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        print(f"✓ Database connected: {user_count} users")
        
        # Count interests
        interest_count = await conn.fetchval("SELECT COUNT(*) FROM interests")
        print(f"  Total interests: {interest_count}")
        
        # Count users with DEKs
        dek_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE encryption_key_blob IS NOT NULL")
        print(f"  Users with DEKs: {dek_count}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False


async def diagnose_user(user_id: str):
    """Diagnose encryption for a specific user."""
    print("\n" + "=" * 60)
    print(f"4. DIAGNOSING USER: {user_id}")
    print("=" * 60)
    
    try:
        import asyncpg
        from app.core.config import get_settings
        from app.core.encryption import get_encryption
        
        settings = get_settings()
        encryption = get_encryption()
        
        conn = await asyncpg.connect(settings.database_url)
        
        # Get user
        user = await conn.fetchrow(
            "SELECT id, email, encryption_key_blob, created_at FROM users WHERE id = $1",
            UUID(user_id)
        )
        
        if not user:
            print(f"✗ User not found: {user_id}")
            await conn.close()
            return
        
        print(f"✓ User found: {user['email']}")
        print(f"  Created: {user['created_at']}")
        print(f"  Has DEK blob: {user['encryption_key_blob'] is not None}")
        
        # Try to decrypt DEK
        if user['encryption_key_blob']:
            try:
                user_dek = encryption.decrypt_user_dek(bytes(user['encryption_key_blob']))
                print(f"✓ DEK decrypted: {len(user_dek)} bytes")
            except Exception as e:
                print(f"✗ DEK decryption failed: {e}")
                await conn.close()
                return
        else:
            print(f"✗ No DEK blob stored for user")
            await conn.close()
            return
        
        # Check interests
        interests = await conn.fetch(
            "SELECT id, category, details_encrypted, created_at FROM interests WHERE user_id = $1",
            UUID(user_id)
        )
        
        print(f"\n  Interests: {len(interests)} records")
        
        success_count = 0
        fail_count = 0
        
        for interest in interests:
            try:
                decrypted = encryption.decrypt_for_user(user_dek, bytes(interest['details_encrypted']))
                details = json.loads(decrypted)
                success_count += 1
                print(f"    ✓ {interest['id']}: {details.get('name', 'unnamed')[:30]}")
            except Exception as e:
                fail_count += 1
                print(f"    ✗ {interest['id']}: DECRYPT FAILED - {e}")
                
                # Try to detect the encryption format
                ciphertext = bytes(interest['details_encrypted'])
                print(f"      Ciphertext preview: {ciphertext[:50]}...")
                print(f"      Ciphertext length: {len(ciphertext)} bytes")
        
        print(f"\n  Summary: {success_count} succeeded, {fail_count} failed")
        
        # Check memories too
        memories = await conn.fetch(
            "SELECT id, fact_key, fact_value_encrypted, created_at FROM memories WHERE user_id = $1 AND is_active = true",
            UUID(user_id)
        )
        
        print(f"\n  Memories: {len(memories)} records")
        
        mem_success = 0
        mem_fail = 0
        
        for memory in memories:
            try:
                decrypted = encryption.decrypt_for_user(user_dek, bytes(memory['fact_value_encrypted']))
                mem_success += 1
                print(f"    ✓ {memory['fact_key']}: {decrypted[:30]}...")
            except Exception as e:
                mem_fail += 1
                print(f"    ✗ {memory['fact_key']}: DECRYPT FAILED")
        
        print(f"\n  Memory Summary: {mem_success} succeeded, {mem_fail} failed")
        
        await conn.close()
        
    except Exception as e:
        print(f"✗ Error diagnosing user: {e}")
        import traceback
        traceback.print_exc()


async def find_corrupted_records():
    """Find all records that fail decryption."""
    print("\n" + "=" * 60)
    print("5. SCANNING FOR CORRUPTED RECORDS")
    print("=" * 60)
    
    try:
        import asyncpg
        from app.core.config import get_settings
        from app.core.encryption import get_encryption
        
        settings = get_settings()
        encryption = get_encryption()
        
        conn = await asyncpg.connect(settings.database_url)
        
        # Get all users with interests
        users = await conn.fetch("""
            SELECT DISTINCT u.id, u.email, u.encryption_key_blob
            FROM users u
            JOIN interests i ON u.id = i.user_id
            WHERE u.encryption_key_blob IS NOT NULL
        """)
        
        corrupted_by_user = {}
        
        for user in users:
            try:
                user_dek = encryption.decrypt_user_dek(bytes(user['encryption_key_blob']))
            except Exception as e:
                print(f"✗ User {user['email']}: DEK decrypt failed")
                continue
            
            interests = await conn.fetch(
                "SELECT id, details_encrypted FROM interests WHERE user_id = $1",
                user['id']
            )
            
            failed = []
            for interest in interests:
                try:
                    encryption.decrypt_for_user(user_dek, bytes(interest['details_encrypted']))
                except:
                    failed.append(str(interest['id']))
            
            if failed:
                corrupted_by_user[str(user['id'])] = {
                    'email': user['email'],
                    'failed_interests': failed,
                    'total': len(interests),
                }
        
        await conn.close()
        
        if corrupted_by_user:
            print(f"\nFound {len(corrupted_by_user)} users with corrupted records:")
            for user_id, info in corrupted_by_user.items():
                print(f"  {info['email']}: {len(info['failed_interests'])}/{info['total']} interests failed")
        else:
            print("\n✓ No corrupted records found!")
            
    except Exception as e:
        print(f"✗ Error scanning: {e}")
        import traceback
        traceback.print_exc()


async def main():
    parser = argparse.ArgumentParser(description='Diagnose encryption issues')
    parser.add_argument('--user-id', help='Specific user ID to diagnose')
    parser.add_argument('--scan-all', action='store_true', help='Scan all records for corruption')
    args = parser.parse_args()
    
    print("=" * 60)
    print("YENNIFER ENCRYPTION DIAGNOSTICS")
    print("=" * 60)
    
    # Always run basic checks
    await check_secrets_manager()
    await check_kms()
    await check_database()
    
    if args.user_id:
        await diagnose_user(args.user_id)
    
    if args.scan_all:
        await find_corrupted_records()
    
    print("\n" + "=" * 60)
    print("DIAGNOSTICS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

