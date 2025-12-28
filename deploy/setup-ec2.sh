#!/bin/bash

# EC2 Initial Setup Script for Yennifer
# Run this once when setting up a new EC2 instance

set -e

echo "🚀 Setting up EC2 instance for Yennifer..."

# Update system
echo "📦 Updating system packages..."
sudo dnf update -y

# Install Node.js 20.x
echo "📦 Installing Node.js..."
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs

# Install nginx
echo "📦 Installing Nginx..."
sudo dnf install -y nginx

# Install certbot for SSL
echo "📦 Installing Certbot..."
sudo dnf install -y certbot python3-certbot-nginx

# Create app directory
echo "📁 Creating application directory..."
sudo mkdir -p /var/www/yennifer
sudo chown -R ec2-user:ec2-user /var/www/yennifer

# Enable and start nginx
echo "🔧 Configuring Nginx..."
sudo systemctl enable nginx
sudo systemctl start nginx

# Install PM2 globally for process management
echo "📦 Installing PM2..."
sudo npm install -g pm2

# Configure firewall (if firewalld is installed)
if command -v firewall-cmd &> /dev/null; then
    echo "🔥 Configuring firewall..."
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
fi

echo "✅ EC2 setup complete!"
echo ""
echo "Next steps:"
echo "1. Deploy the application using deploy.sh"
echo "2. Set up SSL with: sudo certbot --nginx -d yennifer.ai -d www.yennifer.ai"

