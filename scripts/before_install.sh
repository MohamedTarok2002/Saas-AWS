#!/bin/bash
echo "=== before_install.sh ==="
sudo yum install -y httpd
sudo systemctl stop httpd || true
sudo rm -rf /var/www/html/*
echo "=== before_install.sh done ==="