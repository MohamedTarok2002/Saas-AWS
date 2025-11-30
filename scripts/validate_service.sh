#!/bin/bash
echo "=== validate_service.sh ==="
if sudo systemctl is-active --quiet httpd; then
    echo "Apache is running!"
    exit 0
else
    echo "Apache failed to start"
    exit 1
fi