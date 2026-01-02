#!/bin/bash

# Deployment Script for Yennifer (All Services)
# Run from your local machine to deploy to EC2

set -e

# Configuration
EC2_HOST="ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com"
REMOTE_DIR="/var/www/yennifer"

# Get absolute paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EC2_KEY="$LOCAL_DIR/SECRETS/ai_pa_agent_ec2_instance_key_pair.pem"

# Parse arguments
DEPLOY_ALL=true
DEPLOY_WEBAPP=false
DEPLOY_CHAT_API=false
DEPLOY_USER_NETWORK=false
DEPLOY_AGENT=false
DEPLOY_WAITLIST=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --webapp)
            DEPLOY_ALL=false
            DEPLOY_WEBAPP=true
            shift
            ;;
        --chat-api)
            DEPLOY_ALL=false
            DEPLOY_CHAT_API=true
            shift
            ;;
        --user-network)
            DEPLOY_ALL=false
            DEPLOY_USER_NETWORK=true
            shift
            ;;
        --agent)
            DEPLOY_ALL=false
            DEPLOY_AGENT=true
            shift
            ;;
        --waitlist)
            DEPLOY_ALL=false
            DEPLOY_WAITLIST=true
            shift
            ;;
        --help)
            echo "Usage: ./deploy.sh [options]"
            echo ""
            echo "Options:"
            echo "  --webapp        Deploy React webapp (frontend)"
            echo "  --chat-api      Deploy Yennifer Chat API (FastAPI)"
            echo "  --user-network  Deploy User Network service"
            echo "  --agent         Deploy agent tools only"
            echo "  --waitlist      Deploy waitlist API (legacy Node.js)"
            echo "  (no options)    Deploy all services"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if $DEPLOY_ALL; then
    DEPLOY_WEBAPP=true
    DEPLOY_CHAT_API=true
    DEPLOY_USER_NETWORK=true
    DEPLOY_AGENT=true
fi

echo "🚀 Deploying Yennifer to EC2..."

# Check if key exists
if [ ! -f "$EC2_KEY" ]; then
    echo "❌ SSH key not found at $EC2_KEY"
    exit 1
fi

# Create deployment directory
rm -rf /tmp/yennifer-deploy
mkdir -p /tmp/yennifer-deploy

# Build and package webapp (React frontend)
if $DEPLOY_WEBAPP; then
    echo "📦 Building webapp..."
    cd "$LOCAL_DIR/webapp"
    
    # Create production .env if needed
    if [ ! -f ".env.production" ]; then
        cat > .env.production << EOF
VITE_YENNIFER_API_URL=https://yennifer.ai
VITE_USER_NETWORK_API_URL=https://yennifer.ai/network
EOF
    fi
    
    npm install
    npm run build
    cd "$LOCAL_DIR"
    
    mkdir -p /tmp/yennifer-deploy/webapp
    cp -r webapp/dist /tmp/yennifer-deploy/webapp/
fi

# Package Yennifer Chat API (FastAPI)
if $DEPLOY_CHAT_API; then
    echo "📦 Packaging Yennifer Chat API..."
    mkdir -p /tmp/yennifer-deploy/yennifer_api/app
    
    # Copy source files
    cp -r "$LOCAL_DIR/services/yennifer_api/app/"* /tmp/yennifer-deploy/yennifer_api/app/
    cp "$LOCAL_DIR/services/yennifer_api/requirements.txt" /tmp/yennifer-deploy/yennifer_api/
    
    # Copy scripts directory (diagnostic tools)
    if [ -d "$LOCAL_DIR/services/yennifer_api/scripts" ]; then
        mkdir -p /tmp/yennifer-deploy/yennifer_api/scripts/
        cp -r "$LOCAL_DIR/services/yennifer_api/scripts/"* /tmp/yennifer-deploy/yennifer_api/scripts/
    fi
    
    # Note: Secrets are loaded from AWS Secrets Manager (yennifer/yennifer-api/production)
fi

# Package agent tools (required by chat API)
if $DEPLOY_AGENT || $DEPLOY_CHAT_API; then
    echo "📦 Packaging agent tools..."
    mkdir -p /tmp/yennifer-deploy/agent/src
    
    # Copy agent source (tools, graph, etc.)
    cp -r "$LOCAL_DIR/agent/src/"* /tmp/yennifer-deploy/agent/src/
    
    # Copy requirements if exists
    if [ -f "$LOCAL_DIR/agent/requirements.txt" ]; then
        cp "$LOCAL_DIR/agent/requirements.txt" /tmp/yennifer-deploy/agent/
    fi
fi

# Package user network service
if $DEPLOY_USER_NETWORK; then
    echo "📦 Packaging user network service..."
    mkdir -p /tmp/yennifer-deploy/user_network/src
    
    # Copy source files
    cp -r "$LOCAL_DIR/services/user_network/src/"* /tmp/yennifer-deploy/user_network/src/
    cp "$LOCAL_DIR/services/user_network/requirements.txt" /tmp/yennifer-deploy/user_network/
fi

# Package waitlist API (legacy)
if $DEPLOY_WAITLIST; then
    echo "📦 Building waitlist API..."
    cd "$LOCAL_DIR/backend"
    npm install
    npm run build
    cd "$LOCAL_DIR"
    
    mkdir -p /tmp/yennifer-deploy/backend
    cp -r backend/dist /tmp/yennifer-deploy/backend/
    cp backend/package.json /tmp/yennifer-deploy/backend/
    cp backend/package-lock.json /tmp/yennifer-deploy/backend/ 2>/dev/null || true
fi

# Copy deployment configs
cp "$LOCAL_DIR/deploy/nginx.conf" /tmp/yennifer-deploy/
cp "$LOCAL_DIR/deploy/ecosystem.config.cjs" /tmp/yennifer-deploy/

# Upload to EC2
echo "📤 Uploading to EC2..."
scp -i "$EC2_KEY" -r /tmp/yennifer-deploy/* "$EC2_HOST:$REMOTE_DIR/"

# Run remote setup
echo "🔧 Setting up on EC2..."
ssh -i "$EC2_KEY" "$EC2_HOST" << 'ENDSSH'
set -e
cd /var/www/yennifer

# Create directories
sudo mkdir -p /var/log/yennifer
sudo chown ec2-user:ec2-user /var/log/yennifer

# Setup webapp if deployed
if [ -d "webapp/dist" ]; then
    echo "✓ Webapp static files deployed"
fi

# Setup Yennifer Chat API if deployed
if [ -d "yennifer_api/app" ]; then
    echo "🔧 Setting up Yennifer Chat API..."
    cd yennifer_api
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    # Activate and install dependencies
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    
    # Remove old .env file if exists (secrets now loaded from AWS Secrets Manager)
    if [ -f ".env" ]; then
        echo "⚠️  Found .env file - secrets now loaded from AWS Secrets Manager"
        echo "   Consider removing: /var/www/yennifer/yennifer_api/.env"
    fi
    
    cd ..
fi

# Setup agent tools if deployed
if [ -d "agent/src" ]; then
    echo "✓ Agent tools deployed"
    
    # Install agent requirements if exists
    if [ -f "agent/requirements.txt" ]; then
        cd agent
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        deactivate
        cd ..
    fi
fi

# Setup user network service if deployed
if [ -d "user_network/src" ]; then
    echo "🔧 Setting up user network service..."
    cd user_network
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    
    # Remove old .env file if exists (secrets now loaded from AWS Secrets Manager)
    if [ -f ".env" ]; then
        echo "⚠️  Found .env file - secrets now loaded from AWS Secrets Manager"
        echo "   Consider removing: /var/www/yennifer/user_network/.env"
    fi
    
    cd ..
fi

# Setup waitlist API if deployed
if [ -d "backend/dist" ]; then
    echo "🔧 Setting up waitlist API..."
    cd backend
    npm install --omit=dev
    cd ..
fi

# Update nginx config
echo "🔧 Updating nginx configuration..."
sudo cp /var/www/yennifer/nginx.conf /etc/nginx/conf.d/yennifer.conf

# Add rate limiting to nginx main config if not present
if ! grep -q "limit_req_zone" /etc/nginx/nginx.conf; then
    echo "Adding rate limiting zone to nginx.conf..."
    sudo sed -i '/http {/a \    limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;' /etc/nginx/nginx.conf
fi

sudo nginx -t && sudo systemctl reload nginx

# Restart services with PM2
echo "🔧 Restarting services with PM2..."
cd /var/www/yennifer

# Stop existing services
pm2 delete all 2>/dev/null || true

# Start services using ecosystem config
pm2 start ecosystem.config.cjs
pm2 save

echo ""
echo "✅ Deployment complete!"
echo ""
pm2 list
ENDSSH

# Cleanup
rm -rf /tmp/yennifer-deploy

echo ""
echo "✅ Deployment successful!"
echo ""
echo "Services deployed:"
$DEPLOY_WEBAPP && echo "  ✓ Webapp (static files at /var/www/yennifer/webapp/dist)"
$DEPLOY_CHAT_API && echo "  ✓ Yennifer Chat API (port 8000)"
$DEPLOY_USER_NETWORK && echo "  ✓ User Network Service (port 8001)"
$DEPLOY_AGENT && echo "  ✓ Agent tools"
$DEPLOY_WAITLIST && echo "  ✓ Waitlist API (port 3001)"
echo ""
echo "🔐 Secrets loaded from AWS Secrets Manager:"
echo "   - yennifer/yennifer-api/production (Chat API)"
echo "   - yennifer/user-network/production (User Network)"
echo ""
echo "Next steps:"
echo "1. SSH into EC2 and verify services: pm2 list"
echo "2. Verify AWS IAM role has secretsmanager:GetSecretValue permission"
echo "3. Update secrets in AWS Secrets Manager Console if needed"
echo "4. Test endpoints:"
echo "   - https://yennifer.ai/ (webapp)"
echo "   - https://yennifer.ai/api/v1/chat/{user_id} (chat API)"
echo "   - https://yennifer.ai/network/health (user network)"
