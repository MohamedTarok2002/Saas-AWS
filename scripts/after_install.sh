#!/bin/bash
# after_install.sh
# This runs AFTER files are copied to the server
# Purpose: Install dependencies and prepare the application

set -e

echo "=========================================="
echo "Running after_install.sh"
echo "=========================================="

# Define deployment directory
DEPLOY_DIR="/var/www/html"
cd $DEPLOY_DIR

echo "Current directory: $(pwd)"
echo "Files in directory:"
ls -la

# Detect project type and install dependencies
echo "Detecting project type..."

if [ -f "package.json" ]; then
    echo "📦 Node.js project detected"
    
    # Install Node.js if not present
    if ! command -v node &> /dev/null; then
        echo "Installing Node.js..."
        curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
        sudo yum install -y nodejs
    fi
    
    echo "Node version: $(node --version)"
    echo "NPM version: $(npm --version)"
    
    # Install dependencies
    echo "Installing Node.js dependencies..."
    npm install --production
    
    # Build if build script exists
    if grep -q '"build"' package.json; then
        echo "Running build script..."
        npm run build || echo "Build failed, continuing..."
    fi

elif [ -f "requirements.txt" ]; then
    echo "🐍 Python project detected"
    
    # Install Python 3 if not present
    if ! command -v python3 &> /dev/null; then
        echo "Installing Python 3..."
        sudo yum install -y python3 python3-pip
    fi
    
    echo "Python version: $(python3 --version)"
    
    # Create virtual environment
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    # Install dependencies
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

elif [ -f "pom.xml" ]; then
    echo "☕ Java project detected"
    
    # Install Java if not present
    if ! command -v java &> /dev/null; then
        echo "Installing Java..."
        sudo yum install -y java-11-amazon-corretto
    fi
    
    echo "Java version: $(java -version 2>&1 | head -n 1)"
    
    # Note: Maven build should happen in CodeBuild, not here
    echo "Java dependencies should be built in CodeBuild phase"

elif [ -f "Gemfile" ]; then
    echo "💎 Ruby project detected"
    
    # Install Ruby if not present
    if ! command -v ruby &> /dev/null; then
        echo "Installing Ruby..."
        sudo yum install -y ruby ruby-devel
    fi
    
    echo "Ruby version: $(ruby --version)"
    
    # Install Bundler and dependencies
    echo "Installing Ruby dependencies..."
    gem install bundler
    bundle install

else
    echo "📄 Static website detected (HTML/CSS/JS)"
    echo "No dependencies to install"
fi

# Set proper permissions
echo "Setting file permissions..."
sudo chown -R ec2-user:ec2-user $DEPLOY_DIR
find $DEPLOY_DIR -type f -exec chmod 644 {} \;
find $DEPLOY_DIR -type d -exec chmod 755 {} \;

# Make any shell scripts executable
find $DEPLOY_DIR -name "*.sh" -exec chmod +x {} \;

echo "after_install.sh completed successfully!"
echo "=========================================="