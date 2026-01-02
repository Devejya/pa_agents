#!/bin/bash
# Initialize LocalStack secrets for local development
# This script runs automatically when LocalStack starts

set -e

echo "🔐 Initializing LocalStack secrets..."

# Wait for LocalStack to be ready
sleep 2

# Create yennifer-api development secret
echo "Creating yennifer/yennifer-api/development secret..."
awslocal secretsmanager create-secret \
  --name yennifer/yennifer-api/development \
  --secret-string file:///etc/localstack/init/ready.d/yennifer-api-secrets.json \
  2>/dev/null || awslocal secretsmanager update-secret \
  --secret-id yennifer/yennifer-api/development \
  --secret-string file:///etc/localstack/init/ready.d/yennifer-api-secrets.json

# Create user-network development secret
echo "Creating yennifer/user-network/development secret..."
awslocal secretsmanager create-secret \
  --name yennifer/user-network/development \
  --secret-string file:///etc/localstack/init/ready.d/user-network-secrets.json \
  2>/dev/null || awslocal secretsmanager update-secret \
  --secret-id yennifer/user-network/development \
  --secret-string file:///etc/localstack/init/ready.d/user-network-secrets.json

echo "✅ LocalStack secrets initialized!"
echo ""
echo "Available secrets:"
awslocal secretsmanager list-secrets --query 'SecretList[].Name' --output table

