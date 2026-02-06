#!/usr/bin/env python3
"""
VEL Trading Platform - Gunicorn Production Configuration
=========================================================

Production-grade WSGI server configuration for the VEL trading platform.

Features:
- Multi-worker concurrency with eventlet for WebSocket support
- Graceful shutdown with configurable timeout
- Worker recycling to prevent memory leaks
- Prometheus metrics integration
- Structured logging
- Security hardening

Usage:
    gunicorn -c gunicorn.conf.py "anvel_web_server:app"
    
Environment Variables:
    GUNICORN_WORKERS: Number of worker processes (default: CPU cores * 2 + 1)
    GUNICORN_THREADS: Threads per worker (default: 4)
    GUNICORN_BIND: Bind address (default: 0.0.0.0:8080)
    GUNICORN_TIMEOUT: Worker timeout in seconds (default: 120)
    GUNICORN_GRACEFUL_TIMEOUT: Graceful shutdown timeout (default: 30)
    GUNICORN_MAX_REQUESTS: Max requests before worker restart (default: 10000)
    GUNICORN_LOG_LEVEL: Log level (default: info)
"""

import multiprocessing
import os

# =============================================================================
# Server Socket
# =============================================================================

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8080")
backlog = 2048

# =============================================================================
# Worker Processes
# =============================================================================

# Worker class - use eventlet for WebSocket support
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "eventlet")

# Number of worker processes
# Formula: (2 * CPU cores) + 1 for CPU-bound, adjust for I/O-bound
_default_workers = (multiprocessing.cpu_count() * 2) + 1
workers = int(os.environ.get("GUNICORN_WORKERS", _default_workers))

# Threads per worker (for gthread worker class)
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# Maximum concurrent connections per worker
worker_connections = 1000

# =============================================================================
# Worker Lifecycle
# =============================================================================

# Worker timeout - kill workers that hang beyond this
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))

# Graceful timeout for worker shutdown
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Time to wait for requests on Keep-Alive connections
keepalive = 5

# Maximum number of requests a worker will process before restarting
# Helps prevent memory leaks
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 10000))

# Add jitter to max_requests to avoid all workers restarting at once
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", 1000))

# =============================================================================
# Security
# =============================================================================

# Limit the size of HTTP request headers
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Forward proxied headers (when behind nginx/ALB)
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# =============================================================================
# Server Mechanics
# =============================================================================

# Daemonize the Gunicorn process (usually False when running in container)
daemon = False

# PID file location
pidfile = os.environ.get("GUNICORN_PIDFILE", None)

# User/group to run workers as (if started as root)
user = os.environ.get("GUNICORN_USER", None)
group = os.environ.get("GUNICORN_GROUP", None)

# Temporary directory for worker heartbeat files
worker_tmp_dir = "/dev/shm"

# =============================================================================
# Logging
# =============================================================================

# Log level
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Access log - use '-' for stdout
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")

# Error log - use '-' for stderr
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")

# Access log format - JSON for structured logging
access_log_format = (
    '{"timestamp": "%(t)s", "remote_addr": "%(h)s", "method": "%(m)s", '
    '"path": "%(U)s", "query": "%(q)s", "status": "%(s)s", '
    '"response_length": %(B)s, "referer": "%(f)s", "user_agent": "%(a)s", '
    '"request_time_us": %(D)s, "pid": %(p)s}'
)

# Capture output from stdout/stderr to error log
capture_output = True

# =============================================================================
# Process Naming
# =============================================================================

proc_name = "vel-trading-api"

# =============================================================================
# Server Hooks
# =============================================================================


def on_starting(server):
    """Called just before the master process is initialized."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info("VEL Trading Platform starting...")
    logger.info(f"Workers: {workers}, Worker class: {worker_class}")
    logger.info(f"Bind: {bind}, Timeout: {timeout}s")


def on_reload(server):
    """Called when the master receives HUP signal."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info("VEL Trading Platform reloading configuration...")


def when_ready(server):
    """Called when server is ready to receive requests."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info("VEL Trading Platform ready to accept connections")
    
    # Write ready file for health checks
    ready_file = os.environ.get("GUNICORN_READY_FILE", "/tmp/vel-ready")
    try:
        with open(ready_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Could not write ready file: {e}")


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.debug(f"Worker {worker.pid} spawned")


def post_worker_init(worker):
    """Called after worker initialization."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.debug(f"Worker {worker.pid} initialized")


def worker_int(worker):
    """Called when worker receives INT or QUIT signal."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"Worker {worker.pid} received interrupt, shutting down gracefully...")


def worker_abort(worker):
    """Called when worker receives SIGABRT."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.warning(f"Worker {worker.pid} aborted!")


def pre_exec(server):
    """Called just before a new master process is forked."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info("VEL Trading Platform forking new master")


def child_exit(server, worker):
    """Called when a worker process terminates."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"Worker {worker.pid} exited")


def worker_exit(server, worker):
    """Called after a worker exits."""
    pass


def nworkers_changed(server, new_value, old_value):
    """Called when number of workers changes."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"Worker count changed: {old_value} -> {new_value}")


def on_exit(server):
    """Called just before exiting Gunicorn."""
    import logging
    logger = logging.getLogger("gunicorn.error")
    logger.info("VEL Trading Platform shutting down...")
    
    # Remove ready file
    ready_file = os.environ.get("GUNICORN_READY_FILE", "/tmp/vel-ready")
    try:
        if os.path.exists(ready_file):
            os.remove(ready_file)
    except Exception as exc:
        logger.warning("Failed to remove ready file %s: %s", ready_file, exc)
