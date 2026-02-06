#!/bin/bash
# VEL Trading Platform - Before Install Hook
# Runs before the new application is installed

set -e

echo "Running before_install hook..."

# Stop existing application if running
if [ -f /app/vel.pid ]; then
    kill $(cat /app/vel.pid) 2>/dev/null || true
    rm -f /app/vel.pid
fi

# Clean up old deployment artifacts
rm -rf /app/old_deployment 2>/dev/null || true
mv /app/current /app/old_deployment 2>/dev/null || true

# Create application directory
mkdir -p /app/current
mkdir -p /app/logs
mkdir -p /app/data

echo "Before install completed"
