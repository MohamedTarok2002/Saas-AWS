#!/bin/bash
# before_install.sh
# This runs BEFORE the application is installed
# Purpose: Clean up old deployments and prepare the environment

set -e

echo "=========================================="
echo "Running before_install.sh"
echo "=========================================="

# Define deployment directory
DEPLOY_DIR="/var/www/html"

# Stop any running applications (if they exist)
echo "Stopping any running applications..."
if [ -f /tmp/app.pid ]; then
    PID=$(cat /tmp/app.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Killing process $PID"
        kill -9 $PID || true
    fi
    rm -f /tmp/app.pid
fi

# Kill any processes on port 3000, 8080, or 5000 (common app ports)
echo "Freeing up application ports..."
fuser -k 3000/tcp || true
fuser -k 8080/tcp || true
fuser -k 5000/tcp || true

# Create deployment directory if it doesn't exist
echo "Creating deployment directory: $DEPLOY_DIR"
sudo mkdir -p $DEPLOY_DIR

# Clean up old deployment files
echo "Cleaning up old deployment files..."
sudo rm -rf $DEPLOY_DIR/*

# Ensure proper permissions
echo "Setting directory permissions..."
sudo chown -R ec2-user:ec2-user $DEPLOY_DIR
sudo chmod -R 755 $DEPLOY_DIR

echo "before_install.sh completed successfully!"
echo "=========================================="