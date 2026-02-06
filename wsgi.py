#!/usr/bin/env python3
"""
WSGI Entry Point for VEL Trading Platform
==========================================

This module provides the WSGI application entry point for production
deployment with Gunicorn.

Usage:
    gunicorn -c gunicorn.conf.py wsgi:app

The module initializes the ANVELWebServer at import time, ensuring
all routes, middleware, and security validation are properly configured
before handling requests.
"""

import logging
import os

# Configure logging before importing the app
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("wsgi")

# Import and initialize the server
# This calls get_anvel_server() which triggers password validation
# and registers all routes and middleware
from anvel_web_server import get_anvel_server, app, socketio

# Initialize the server - this triggers all security validation
logger.info("Initializing VEL Trading Platform for WSGI...")

try:
    server = get_anvel_server()
    logger.info("VEL Trading Platform initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize VEL Trading Platform: {e}")
    raise

# Export the WSGI application
# For standard WSGI servers (without WebSocket support)
application = app

# Note: For WebSocket support with eventlet, Gunicorn will use
# the eventlet worker class which patches the app appropriately.
# The socketio object handles WebSocket connections.

__all__ = ['app', 'application', 'socketio']
