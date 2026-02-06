#!/bin/bash
# VEL Trading Platform - Validate Service Hook
# Validates the deployed application is healthy

set -e

echo "Validating VEL service..."

# Wait for application to be ready
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:5000/health | grep -q "healthy"; then
        echo "Service is healthy!"
        exit 0
    fi
    
    attempt=$((attempt + 1))
    echo "Waiting for service... (attempt $attempt/$max_attempts)"
    sleep 2
done

echo "Service validation failed!"
exit 1
