#!/bin/bash
echo "=== start_application.sh ==="
sudo systemctl start httpd
sudo systemctl enable httpd
echo "=== start_application.sh done ==="