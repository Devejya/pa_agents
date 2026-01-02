#!/usr/bin/env python3
"""
Inspect AWS Secrets Manager contents.

This script lists all secrets and shows which keys are present (not values).

Usage:
    # From EC2, in the yennifer_api directory:
    source venv/bin/activate
    python scripts/inspect_secrets.py
    
    # Or specify a different secret:
    python scripts/inspect_secrets.py --secret-name yennifer/yennifer-api/production
"""

import argparse
import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

# Required keys for yennifer-api
REQUIRED_KEYS = [
    'openai_api_key',
    'database_url',
    'google_client_id',
    'google_client_secret',
    'jwt_secret_key',
    'user_network_api_key',
    'allowed_emails',
    'kms_key_id',
]

OPTIONAL_KEYS = [
    'posthog_api_key',
    'posthog_host',
    'sendgrid_api_key',
    'encryption_key',
    'google_cse_api_key',
    'google_cse_id',
    'redis_url',
    'chat_archive_bucket',
]


def get_secrets_client():
    """Get boto3 Secrets Manager client."""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    endpoint_url = os.environ.get('AWS_SECRETS_ENDPOINT_URL')  # For LocalStack
    
    kwargs = {
        'service_name': 'secretsmanager',
        'region_name': region,
    }
    if endpoint_url:
        kwargs['endpoint_url'] = endpoint_url
    
    return boto3.client(**kwargs)


def list_all_secrets():
    """List all secrets in Secrets Manager."""
    client = get_secrets_client()
    
    print("\n" + "=" * 60)
    print("ALL SECRETS IN AWS SECRETS MANAGER")
    print("=" * 60)
    
    try:
        paginator = client.get_paginator('list_secrets')
        secrets = []
        
        for page in paginator.paginate():
            for secret in page['SecretList']:
                secrets.append(secret['Name'])
        
        for name in sorted(secrets):
            print(f"  - {name}")
        
        print(f"\nTotal: {len(secrets)} secrets")
        return secrets
        
    except ClientError as e:
        print(f"✗ Error listing secrets: {e}")
        return []


def inspect_secret(secret_name: str):
    """Inspect a specific secret (show keys, not values)."""
    client = get_secrets_client()
    
    print("\n" + "=" * 60)
    print(f"INSPECTING: {secret_name}")
    print("=" * 60)
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret_data = json.loads(response['SecretString'])
        
        print(f"\nKeys found ({len(secret_data)} total):")
        
        # Check for required keys (case-insensitive)
        secret_keys_lower = {k.lower(): k for k in secret_data.keys()}
        
        print("\n--- REQUIRED KEYS ---")
        for key in REQUIRED_KEYS:
            original_key = secret_keys_lower.get(key, key)
            if key in secret_keys_lower:
                value = secret_data[original_key]
                # Show presence and length, not actual value
                if isinstance(value, str):
                    preview = f"(string, {len(value)} chars)"
                    if value.startswith('phc_'):
                        preview += " [PostHog key format]"
                    elif value.startswith('sk-'):
                        preview += " [OpenAI key format]"
                    elif value.startswith('postgresql://'):
                        preview += " [PostgreSQL URL]"
                else:
                    preview = f"({type(value).__name__})"
                print(f"  ✓ {original_key}: {preview}")
            else:
                print(f"  ✗ {key}: MISSING")
        
        print("\n--- OPTIONAL KEYS ---")
        for key in OPTIONAL_KEYS:
            original_key = secret_keys_lower.get(key, key)
            if key in secret_keys_lower:
                value = secret_data[original_key]
                if isinstance(value, str):
                    preview = f"(string, {len(value)} chars)"
                else:
                    preview = f"({type(value).__name__})"
                print(f"  ✓ {original_key}: {preview}")
            else:
                print(f"  - {key}: not set")
        
        # Check for unexpected keys
        known_keys = set(REQUIRED_KEYS + OPTIONAL_KEYS)
        extra_keys = [k for k in secret_keys_lower.keys() if k not in known_keys]
        
        if extra_keys:
            print("\n--- ADDITIONAL KEYS ---")
            for key in extra_keys:
                original_key = secret_keys_lower[key]
                print(f"  + {original_key}")
        
        # Show key casing analysis
        print("\n--- KEY CASING ANALYSIS ---")
        upper_keys = [k for k in secret_data.keys() if k.isupper()]
        lower_keys = [k for k in secret_data.keys() if k.islower()]
        mixed_keys = [k for k in secret_data.keys() if not k.isupper() and not k.islower()]
        
        print(f"  UPPER_CASE keys: {len(upper_keys)}")
        print(f"  lower_case keys: {len(lower_keys)}")
        print(f"  Mixed_Case keys: {len(mixed_keys)}")
        
        if upper_keys and lower_keys:
            print("\n  ⚠️  WARNING: Mixed key casing detected!")
            print("  The config loader will normalize all keys to lowercase.")
            print("  This should work, but consistent casing is recommended.")
        
        return secret_data
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'ResourceNotFoundException':
            print(f"✗ Secret not found: {secret_name}")
        elif error_code == 'AccessDeniedException':
            print(f"✗ Access denied to secret: {secret_name}")
            print("  Check IAM permissions for secretsmanager:GetSecretValue")
        else:
            print(f"✗ Error: {error_code} - {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"✗ Secret is not valid JSON: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Inspect AWS Secrets Manager contents')
    parser.add_argument('--secret-name', default='yennifer/yennifer-api/production',
                        help='Secret name to inspect')
    parser.add_argument('--list-all', action='store_true',
                        help='List all secrets')
    args = parser.parse_args()
    
    print("=" * 60)
    print("AWS SECRETS MANAGER INSPECTOR")
    print("=" * 60)
    print(f"Region: {os.environ.get('AWS_REGION', 'us-east-1')}")
    
    if args.list_all:
        list_all_secrets()
    
    inspect_secret(args.secret_name)
    
    # Also check user-network secret if it exists
    if 'yennifer-api' in args.secret_name:
        network_secret = args.secret_name.replace('yennifer-api', 'user-network')
        inspect_secret(network_secret)
    
    print("\n" + "=" * 60)
    print("INSPECTION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

