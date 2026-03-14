#!/bin/bash
# ---------------------------------------------------------------------------
# Villa Sirene — EC2 Deployment Script
# Run this ON the EC2 instance after cloning the repo.
# Usage: bash deploy.sh
# ---------------------------------------------------------------------------

set -euo pipefail

echo "==> Updating system packages..."
sudo yum update -y 2>/dev/null || sudo dnf update -y 2>/dev/null

echo "==> Installing Python 3 and pip..."
sudo yum install -y python3 python3-pip git 2>/dev/null || sudo dnf install -y python3 python3-pip git 2>/dev/null

echo "==> Installing Python dependencies (system-wide for sudo access)..."
sudo pip3 install flask python-dateutil gunicorn boto3

echo "==> Initialising database..."
python3 -c "import sys; sys.path.insert(0,'.'); from database import init_db; init_db('hotel.db')"

echo "==> Stopping any existing instance..."
sudo pkill gunicorn 2>/dev/null || true
sleep 1

echo "==> Starting gunicorn on port 80..."
sudo /usr/local/bin/gunicorn \
    --workers 1 \
    --bind 0.0.0.0:80 \
    --daemon \
    --access-logfile /tmp/villa_sirene_access.log \
    --error-logfile  /tmp/villa_sirene_error.log \
    --chdir "$(pwd)" \
    app:app

sleep 2

if curl -s -o /dev/null -w "%{http_code}" http://localhost/ | grep -q 200; then
    echo ""
    echo "==> Villa Sirene is running!"
    echo "    Public URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-hostname 2>/dev/null || echo '<your-ec2-public-dns>')"
    echo "    Logs:       /tmp/villa_sirene_access.log"
    echo "                /tmp/villa_sirene_error.log"
else
    echo ""
    echo "==> WARNING: Server may not have started correctly."
    echo "    Check: cat /tmp/villa_sirene_error.log"
fi
