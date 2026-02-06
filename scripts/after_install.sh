#!/bin/bash
# VEL Trading Platform - After Install Hook
# Runs after the new application is installed

set -e

echo "Running after_install hook..."

cd /app/current

# Install Python dependencies
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

# Set correct permissions
chown -R vel:vel /app

echo "After install completed"
