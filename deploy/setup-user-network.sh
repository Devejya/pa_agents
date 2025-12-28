#!/bin/bash

# First-time setup script for User Network Service on EC2
# Run this ONCE after first deployment to set up the database and environment

set -e

# Configuration
EC2_HOST="ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com"
EC2_KEY="./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem"
LOCAL_DIR="$(dirname "$0")/.."

echo "🔧 Setting up User Network Service on EC2..."

# Check if key exists
if [ ! -f "$EC2_KEY" ]; then
    echo "❌ SSH key not found at $EC2_KEY"
    exit 1
fi

# Copy schema file
echo "📤 Uploading database schema..."
scp -i "$EC2_KEY" "$LOCAL_DIR/services/user_network/src/db/schema.sql" "$EC2_HOST:/tmp/user_network_schema.sql"

# Run setup on EC2
echo "🔧 Running setup on EC2..."
ssh -i "$EC2_KEY" "$EC2_HOST" << 'ENDSSH'
set -e

echo ""
echo "=========================================="
echo "User Network Service Setup"
echo "=========================================="

# Check if PostgreSQL client is installed
if ! command -v psql &> /dev/null; then
    echo "📦 Installing PostgreSQL client..."
    sudo yum install -y postgresql15 || sudo amazon-linux-extras install postgresql15 -y
fi

# Create .env file if it doesn't exist
ENV_FILE="/var/www/yennifer/user_network/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "📝 Creating environment file..."
    echo "Please enter the following values:"
    echo ""
    
    read -p "RDS Password: " -s RDS_PASSWORD
    echo ""
    
    # Generate API key
    API_KEY="un_$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)"
    
    cat > "$ENV_FILE" << EOF
# User Network Service Configuration
# Generated: $(date)

# Service
SERVICE_NAME=user-network
ENVIRONMENT=production
DEBUG=false
HOST=127.0.0.1
PORT=8001

# Database (RDS)
DATABASE_URL=postgresql://postgres:${RDS_PASSWORD}@ai-pa-agent.ckxya68q4nzj.us-east-1.rds.amazonaws.com:5432/user_network
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# API Keys
API_KEYS=${API_KEY}

# CORS
CORS_ORIGINS=https://yennifer.ai,https://www.yennifer.ai

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF
    
    echo ""
    echo "✅ Environment file created at $ENV_FILE"
    echo ""
    echo "🔑 Your API Key: $API_KEY"
    echo "   (Save this - you'll need it for the agent configuration)"
    echo ""
else
    echo "✅ Environment file already exists at $ENV_FILE"
fi

# Run database schema
echo ""
echo "🗄️  Setting up database schema..."
echo "Enter RDS password when prompted:"

# Get DATABASE_URL from .env
source "$ENV_FILE"

# Extract host from DATABASE_URL
DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

# Check if database exists, create if not
echo "Checking if database exists..."
PGPASSWORD=$(echo $DATABASE_URL | sed -n 's/.*:\([^@]*\)@.*/\1/p')
export PGPASSWORD

if psql -h "$DB_HOST" -U postgres -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
    echo "✅ Database '$DB_NAME' already exists"
else
    echo "Creating database '$DB_NAME'..."
    psql -h "$DB_HOST" -U postgres -d postgres -c "CREATE DATABASE $DB_NAME;"
    echo "✅ Database created"
fi

# Check if tables exist
TABLE_COUNT=$(psql -h "$DB_HOST" -U postgres -d "$DB_NAME" -tc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" | xargs)

if [ "$TABLE_COUNT" -gt "0" ]; then
    echo "✅ Tables already exist ($TABLE_COUNT tables)"
    read -p "Do you want to recreate the schema? This will DELETE all data. (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping schema setup"
        unset PGPASSWORD
        exit 0
    fi
fi

echo "Running schema..."
psql -h "$DB_HOST" -U postgres -d "$DB_NAME" -f /tmp/user_network_schema.sql

unset PGPASSWORD

echo ""
echo "✅ Database schema applied!"
echo ""

# Verify tables
echo "Verifying tables..."
PGPASSWORD=$(echo $DATABASE_URL | sed -n 's/.*:\([^@]*\)@.*/\1/p')
export PGPASSWORD
psql -h "$DB_HOST" -U postgres -d "$DB_NAME" -c "\dt"
unset PGPASSWORD

# Restart the service
echo ""
echo "🔄 Restarting user-network service..."
pm2 restart user-network 2>/dev/null || echo "Service not running yet - will start on next deploy"

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Test the service:"
echo "  curl http://localhost:8001/health"
echo ""
echo "From outside:"
echo "  curl https://yennifer.ai/network/health"
echo ""

# Cleanup
rm -f /tmp/user_network_schema.sql
ENDSSH

echo ""
echo "✅ User Network Service setup complete!"
echo ""
echo "Next steps:"
echo "1. Save the API key shown above"
echo "2. Update agent .env with the production API key"
echo "3. Test: curl https://yennifer.ai/network/health"

