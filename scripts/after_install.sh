#!/bin/bash
echo "=== after_install.sh ==="
cd /var/www/html
if [ -d "build" ]; then
    cp -r build/* .
fi
if [ -d "dist" ]; then
    cp -r dist/* .
fi
sudo chown -R apache:apache /var/www/html
sudo chmod -R 755 /var/www/html
echo "=== after_install.sh done ==="