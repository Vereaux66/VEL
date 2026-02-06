# VEL Trading Platform - Production Dockerfile
# Multi-stage build for optimized production image

# =============================================================================
# Stage 1: Frontend Build
# =============================================================================
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies (dev deps needed for build)
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# =============================================================================
# Stage 2: Python Application
# =============================================================================
FROM python:3.11-slim AS production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Gunicorn settings
    GUNICORN_WORKERS=4 \
    GUNICORN_BIND=0.0.0.0:8080 \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_WORKER_CLASS=eventlet

# Create non-root user for security
RUN groupadd -r vel && useradd -r -g vel vel

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies including gunicorn
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn eventlet

# Copy application code
COPY --chown=vel:vel *.py ./
COPY --chown=vel:vel ai/ ./ai/
COPY --chown=vel:vel config/ ./config/
COPY --chown=vel:vel runtime/ ./runtime/
COPY --chown=vel:vel tests/ ./tests/

# Copy built frontend from previous stage
COPY --from=frontend-builder --chown=vel:vel /app/frontend/dist ./frontend/dist

# Create necessary directories
RUN mkdir -p logs data backups /dev/shm && chown -R vel:vel logs data backups

# Switch to non-root user
USER vel

# Expose port (8080 for Gunicorn)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Production command - use Gunicorn with config file
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
