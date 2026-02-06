#!/bin/bash
# VEL Trading Platform - Application Start Hook
# Starts the VEL application

set -e

echo "Starting VEL application..."

cd /app/current

# Start the application
nohup python anvel_web_server.py > /app/logs/vel.log 2>&1 &
echo $! > /app/vel.pid

# Wait for startup
sleep 5

echo "Application started with PID $(cat /app/vel.pid)"
