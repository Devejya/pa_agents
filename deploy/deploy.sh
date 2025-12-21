#!/bin/bash

# Deployment Script for Yennifer
# Run from your local machine to deploy to EC2

set -e

# Configuration
EC2_HOST="ec2-user@ec2-44-210-105-146.compute-1.amazonaws.com"
EC2_KEY="./SECRETS/ai_pa_agent_ec2_instance_key_pair.pem"
REMOTE_DIR="/var/www/yennifer"
LOCAL_DIR="$(dirname "$0")/.."

echo "🚀 Deploying Yennifer to EC2..."

# Check if key exists
if [ ! -f "$EC2_KEY" ]; then
    echo "❌ SSH key not found at $EC2_KEY"
    exit 1
fi

# Build frontend locally
echo "📦 Building frontend..."
cd "$LOCAL_DIR/frontend"
npm install
npm run build

# Build backend locally
echo "📦 Building backend..."
cd "$LOCAL_DIR/backend"
npm install
npm run build

cd "$LOCAL_DIR"

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf /tmp/yennifer-deploy
mkdir -p /tmp/yennifer-deploy/frontend
mkdir -p /tmp/yennifer-deploy/backend

# Copy frontend build
cp -r frontend/dist /tmp/yennifer-deploy/frontend/

# Copy backend
cp -r backend/dist /tmp/yennifer-deploy/backend/
cp backend/package.json /tmp/yennifer-deploy/backend/
cp backend/package-lock.json /tmp/yennifer-deploy/backend/ 2>/dev/null || true

# Copy nginx config
cp deploy/nginx.conf /tmp/yennifer-deploy/

# Upload to EC2
echo "📤 Uploading to EC2..."
scp -i "$EC2_KEY" -r /tmp/yennifer-deploy/* "$EC2_HOST:$REMOTE_DIR/"

# Run remote setup
echo "🔧 Setting up on EC2..."
ssh -i "$EC2_KEY" "$EC2_HOST" << 'ENDSSH'
cd /var/www/yennifer

# Install backend dependencies (production only)
cd backend
npm install --omit=dev

# Set up environment file if it doesn't exist
if [ ! -f .env ]; then
    echo "⚠️  Please create /var/www/yennifer/backend/.env with your configuration"
fi

# Restart the application with PM2
pm2 delete yennifer-api 2>/dev/null || true
pm2 start dist/server.js --name yennifer-api
pm2 save

# Update nginx config
sudo cp /var/www/yennifer/nginx.conf /etc/nginx/conf.d/yennifer.conf
sudo nginx -t && sudo systemctl reload nginx

echo "✅ Deployment complete!"
ENDSSH

# Cleanup
rm -rf /tmp/yennifer-deploy

echo ""
echo "✅ Deployment successful!"
echo ""
echo "Next steps:"
echo "1. SSH into EC2 and create backend/.env file if not already done"
echo "2. Initialize the database: cd /var/www/yennifer/backend && npm run db:init"
echo "3. Set up SSL: sudo certbot --nginx -d yennifer.ai -d www.yennifer.ai"

