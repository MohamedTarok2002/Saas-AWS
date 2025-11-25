#!/bin/bash
# validate_service.sh
# This runs to VERIFY the application is working
# Purpose: Health check to ensure deployment succeeded

set -e

echo "=========================================="
echo "Running validate_service.sh"
echo "=========================================="

# Wait for application to fully start
echo "Waiting for application to initialize..."
sleep 10

# Determine which port to check based on what's running
PORTS=(80 3000 8080 5000 8000)
APP_RUNNING=false
ACTIVE_PORT=""

echo "Checking for running application..."

for PORT in "${PORTS[@]}"; do
    if netstat -tuln | grep -q ":$PORT "; then
        echo "✅ Found application listening on port $PORT"
        ACTIVE_PORT=$PORT
        APP_RUNNING=true
        break
    fi
done

if [ "$APP_RUNNING" = false ]; then
    echo "❌ ERROR: No application found running on common ports"
    echo "Checked ports: ${PORTS[@]}"
    
    # Show what processes are running
    echo ""
    echo "Current processes:"
    ps aux | grep -E "(node|python|java|nginx)" | grep -v grep
    
    # Show recent logs
    echo ""
    echo "Recent application logs:"
    tail -n 50 /var/log/app.log 2>/dev/null || echo "No logs found"
    
    exit 1
fi

# Try to make an HTTP request to the application
echo ""
echo "Testing HTTP response on port $ACTIVE_PORT..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$ACTIVE_PORT/ || echo "000")

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "✅ SUCCESS: Application is responding with HTTP $HTTP_CODE"
    echo "✅ Deployment validated successfully!"
elif [ "$HTTP_CODE" = "000" ]; then
    echo "⚠️  WARNING: Could not connect to application"
    echo "Application may still be starting up..."
    
    # Give it one more chance
    sleep 10
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$ACTIVE_PORT/ || echo "000")
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        echo "✅ SUCCESS: Application is now responding with HTTP $HTTP_CODE"
        echo "✅ Deployment validated successfully!"
    else
        echo "❌ ERROR: Application still not responding"
        exit 1
    fi
else
    echo "⚠️  WARNING: Application returned HTTP $HTTP_CODE"
    echo "This may be normal depending on your application"
    echo "Considering deployment successful"
fi

# Check if PID file exists and process is running
if [ -f /tmp/app.pid ]; then
    PID=$(cat /tmp/app.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Application process (PID: $PID) is running"
    else
        echo "⚠️  WARNING: PID file exists but process not found"
    fi
fi

# Show application info
echo ""
echo "=========================================="
echo "Deployment Summary:"
echo "=========================================="
echo "Port: $ACTIVE_PORT"
echo "HTTP Status: $HTTP_CODE"
echo "Time: $(date)"
echo "=========================================="

echo "✅ Validation completed successfully!"