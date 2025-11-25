#!/bin/bash
# start_application.sh
# This runs to START the application
# Purpose: Launch the web server/application

set -e

echo "=========================================="
echo "Running start_application.sh"
echo "=========================================="

# Define deployment directory
DEPLOY_DIR="/var/www/html"
cd $DEPLOY_DIR

echo "Starting application from: $(pwd)"

# Detect project type and start accordingly
if [ -f "package.json" ]; then
    echo "🚀 Starting Node.js application..."
    
    # Check if there's a start script in package.json
    if grep -q '"start"' package.json; then
        echo "Using npm start..."
        nohup npm start > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    else
        # Try common entry points
        if [ -f "index.js" ]; then
            echo "Starting with node index.js..."
            nohup node index.js > /var/log/app.log 2>&1 &
            echo $! > /tmp/app.pid
        elif [ -f "server.js" ]; then
            echo "Starting with node server.js..."
            nohup node server.js > /var/log/app.log 2>&1 &
            echo $! > /tmp/app.pid
        elif [ -f "app.js" ]; then
            echo "Starting with node app.js..."
            nohup node app.js > /var/log/app.log 2>&1 &
            echo $! > /tmp/app.pid
        else
            echo "⚠️  No entry point found, assuming static site"
            # For static sites, we'll use nginx (installed below)
        fi
    fi

elif [ -f "requirements.txt" ]; then
    echo "🚀 Starting Python application..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Check for common Python web frameworks
    if [ -f "app.py" ]; then
        echo "Starting Flask/FastAPI app.py..."
        nohup python app.py > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    elif [ -f "main.py" ]; then
        echo "Starting main.py..."
        nohup python main.py > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    elif [ -f "manage.py" ]; then
        echo "Starting Django application..."
        nohup python manage.py runserver 0.0.0.0:8000 > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    else
        echo "⚠️  No Python entry point found"
    fi

elif [ -f "pom.xml" ]; then
    echo "🚀 Starting Java application..."
    
    # Find the JAR file
    JAR_FILE=$(find target -name "*.jar" -type f | head -n 1)
    
    if [ -n "$JAR_FILE" ]; then
        echo "Starting JAR: $JAR_FILE"
        nohup java -jar $JAR_FILE > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    else
        echo "⚠️  No JAR file found in target/"
    fi

elif [ -f "Gemfile" ]; then
    echo "🚀 Starting Ruby application..."
    
    if [ -f "config.ru" ]; then
        echo "Starting with rackup..."
        nohup bundle exec rackup -o 0.0.0.0 -p 8080 > /var/log/app.log 2>&1 &
        echo $! > /tmp/app.pid
    else
        echo "⚠️  No config.ru found"
    fi

else
    echo "📄 Static website detected"
    echo "Setting up nginx for static content..."
    
    # Install nginx if not present
    if ! command -v nginx &> /dev/null; then
        echo "Installing nginx..."
        sudo yum install -y nginx
    fi
    
    # Configure nginx to serve this directory
    sudo tee /etc/nginx/conf.d/app.conf > /dev/null <<EOF
server {
    listen 80;
    server_name _;
    root $DEPLOY_DIR;
    index index.html index.htm;
    
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
    
    # Start nginx
    sudo systemctl enable nginx
    sudo systemctl restart nginx
    echo "nginx" > /tmp/app.pid
fi

# Wait a moment for the app to start
sleep 5

echo "Application started successfully!"

# Show the PID if saved
if [ -f /tmp/app.pid ]; then
    PID=$(cat /tmp/app.pid)
    echo "Application PID: $PID"
fi

echo "=========================================="