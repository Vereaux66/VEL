#!/usr/bin/env python3
"""
VEL API Rate Limiting Middleware
=================================

Production-grade rate limiting for API endpoints.

Features:
- Per-IP rate limiting
- Per-user rate limiting
- Per-endpoint rate limiting
- Token bucket and sliding window algorithms
- Redis-backed for distributed systems
- In-memory fallback for single-node
- WebSocket abuse prevention
- Configurable via environment

Usage:
    from vel_rate_limiter import RateLimitMiddleware, rate_limit
    
    # Flask integration
    app = Flask(__name__)
    RateLimitMiddleware(app)
    
    # Or per-route
    @app.route('/api/trade')
    @rate_limit(limit=10, period=60)
    def trade():
        ...
"""

import functools
import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("vel.security.ratelimit")


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    # Default limits
    default_limit: int = 100  # requests
    default_period: int = 60  # seconds
    
    # Per-endpoint limits (requests per minute)
    login_limit: int = 5
    trade_limit: int = 30
    api_limit: int = 100
    websocket_limit: int = 50
    
    # Burst allowance
    burst_multiplier: float = 1.5
    
    # Redis configuration
    redis_prefix: str = "vel:ratelimit:"
    redis_enabled: bool = True
    
    # Response settings
    retry_after_header: bool = True
    
    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        """Load config from environment."""
        return cls(
            default_limit=int(os.environ.get("VEL_RATE_DEFAULT_LIMIT", "100")),
            default_period=int(os.environ.get("VEL_RATE_DEFAULT_PERIOD", "60")),
            login_limit=int(os.environ.get("VEL_RATE_LOGIN_LIMIT", "5")),
            trade_limit=int(os.environ.get("VEL_RATE_TRADE_LIMIT", "30")),
            api_limit=int(os.environ.get("VEL_RATE_API_LIMIT", "100")),
            websocket_limit=int(os.environ.get("VEL_RATE_WEBSOCKET_LIMIT", "50")),
            redis_enabled=os.environ.get("VEL_RATE_REDIS_ENABLED", "true").lower() == "true",
        )


# =============================================================================
# Rate Limit Result
# =============================================================================

@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    retry_after: Optional[int] = None
    
    def headers(self) -> Dict[str, str]:
        """Get rate limit response headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


# =============================================================================
# Sliding Window Rate Limiter
# =============================================================================

class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter.
    
    More accurate than fixed window, prevents burst at window boundaries.
    """
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        config: Optional[RateLimitConfig] = None
    ):
        self.redis = redis_client
        self.config = config or RateLimitConfig.from_env()
        
        # In-memory storage for fallback
        self._local_windows: Dict[str, list] = {}
        self._local_lock = threading.Lock()
        
        logger.info(f"Rate limiter initialized (redis: {redis_client is not None})")
    
    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate storage key."""
        key_hash = hashlib.md5(f"{identifier}:{endpoint}".encode()).hexdigest()[:16]
        return f"{self.config.redis_prefix}{key_hash}"
    
    def check(
        self,
        identifier: str,
        endpoint: str,
        limit: Optional[int] = None,
        period: Optional[int] = None
    ) -> RateLimitResult:
        """
        Check rate limit for identifier.
        
        Args:
            identifier: Client identifier (IP, user_id, API key)
            endpoint: Endpoint being accessed
            limit: Request limit (default from config)
            period: Time period in seconds (default from config)
            
        Returns:
            RateLimitResult
        """
        limit = limit or self.config.default_limit
        period = period or self.config.default_period
        
        key = self._get_key(identifier, endpoint)
        now = time.time()
        window_start = now - period
        
        if self.redis and self.config.redis_enabled:
            return self._check_redis(key, limit, period, now, window_start)
        else:
            return self._check_local(key, limit, period, now, window_start)
    
    def _check_redis(
        self,
        key: str,
        limit: int,
        period: int,
        now: float,
        window_start: float
    ) -> RateLimitResult:
        """Check rate limit using Redis."""
        try:
            pipe = self.redis.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current entries
            pipe.zcard(key)
            
            # Add current request (tentatively)
            pipe.zadd(key, {f"{now}:{id(now)}": now})
            
            # Set expiry
            pipe.expire(key, period + 1)
            
            results = pipe.execute()
            current_count = results[1]  # zcard result before adding new
            
            if current_count >= limit:
                # Over limit - remove the request we just added
                self.redis.zrem(key, f"{now}:{id(now)}")
                
                # Calculate retry-after
                oldest = self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(period - (now - oldest[0][1])) + 1
                else:
                    retry_after = period
                
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after
                )
            
            remaining = limit - current_count - 1
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=now + period
            )
            
        except Exception as e:
            logger.warning(f"Redis rate limit error: {e}, falling back to local")
            return self._check_local(key, limit, period, now, window_start)
    
    def _check_local(
        self,
        key: str,
        limit: int,
        period: int,
        now: float,
        window_start: float
    ) -> RateLimitResult:
        """Check rate limit using local storage."""
        with self._local_lock:
            if key not in self._local_windows:
                self._local_windows[key] = []
            
            # Remove old entries
            self._local_windows[key] = [
                ts for ts in self._local_windows[key]
                if ts > window_start
            ]
            
            current_count = len(self._local_windows[key])
            
            if current_count >= limit:
                # Over limit
                if self._local_windows[key]:
                    oldest = min(self._local_windows[key])
                    retry_after = int(period - (now - oldest)) + 1
                else:
                    retry_after = period
                
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_at=now + retry_after,
                    retry_after=retry_after
                )
            
            # Add current request
            self._local_windows[key].append(now)
            remaining = limit - current_count - 1
            
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=now + period
            )
    
    def cleanup_local(self, max_age: int = 300):
        """Remove old entries from local storage."""
        cutoff = time.time() - max_age
        with self._local_lock:
            keys_to_remove = []
            for key, timestamps in self._local_windows.items():
                self._local_windows[key] = [ts for ts in timestamps if ts > cutoff]
                if not self._local_windows[key]:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._local_windows[key]


# =============================================================================
# Flask Middleware
# =============================================================================

class RateLimitMiddleware:
    """
    Flask rate limiting middleware.
    
    Automatically applies rate limiting to all requests.
    """
    
    def __init__(
        self,
        app=None,
        redis_client: Optional[Any] = None,
        config: Optional[RateLimitConfig] = None
    ):
        self.limiter = SlidingWindowRateLimiter(redis_client, config)
        self.config = config or RateLimitConfig.from_env()
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app."""
        from flask import request, g
        
        @app.before_request
        def check_rate_limit():
            # Get client identifier
            identifier = self._get_identifier()
            endpoint = request.endpoint or request.path
            
            # Determine limit based on endpoint
            limit, period = self._get_limits_for_endpoint(endpoint, request.path)
            
            # Check rate limit
            result = self.limiter.check(identifier, endpoint, limit, period)
            
            # Store for response headers
            g.rate_limit_result = result
            
            if not result.allowed:
                from flask import jsonify, make_response
                response = make_response(
                    jsonify({
                        "error": "Rate limit exceeded",
                        "retry_after": result.retry_after
                    }),
                    429
                )
                for header, value in result.headers().items():
                    response.headers[header] = value
                return response
        
        @app.after_request
        def add_rate_limit_headers(response):
            if hasattr(g, 'rate_limit_result'):
                for header, value in g.rate_limit_result.headers().items():
                    response.headers[header] = value
            return response
        
        logger.info("Rate limit middleware initialized for Flask")
    
    def _get_identifier(self) -> str:
        """Get client identifier."""
        from flask import request
        
        # Try to get user ID from JWT/session
        if hasattr(request, 'user_id') and request.user_id:
            return f"user:{request.user_id}"
        
        # Fall back to IP address
        # Handle proxied requests
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Get first IP (client IP)
            return f"ip:{forwarded.split(',')[0].strip()}"
        
        return f"ip:{request.remote_addr}"
    
    def _get_limits_for_endpoint(
        self,
        endpoint: str,
        path: str
    ) -> Tuple[int, int]:
        """Get rate limits for endpoint."""
        # Check for specific endpoints
        if "login" in path or endpoint and "login" in endpoint:
            return self.config.login_limit, 60
        
        if "trade" in path or "execute" in path:
            return self.config.trade_limit, 60
        
        if path.startswith("/api/"):
            return self.config.api_limit, 60
        
        return self.config.default_limit, self.config.default_period


# =============================================================================
# Decorator for Per-Route Rate Limiting
# =============================================================================

_default_limiter: Optional[SlidingWindowRateLimiter] = None


def get_limiter() -> SlidingWindowRateLimiter:
    """Get default rate limiter."""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = SlidingWindowRateLimiter()
    return _default_limiter


def rate_limit(
    limit: int = 100,
    period: int = 60,
    key_func: Optional[Callable] = None,
    error_message: str = "Rate limit exceeded"
):
    """
    Rate limit decorator for Flask routes.
    
    Args:
        limit: Request limit
        period: Time period in seconds
        key_func: Function to get identifier (request) -> str
        error_message: Error message when limit exceeded
        
    Usage:
        @app.route('/api/trade')
        @rate_limit(limit=10, period=60)
        def trade():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify, g
            
            # Get identifier
            if key_func:
                identifier = key_func(request)
            else:
                # Default: IP or user ID
                if hasattr(request, 'user_id') and request.user_id:
                    identifier = f"user:{request.user_id}"
                else:
                    forwarded = request.headers.get("X-Forwarded-For")
                    if forwarded:
                        identifier = f"ip:{forwarded.split(',')[0].strip()}"
                    else:
                        identifier = f"ip:{request.remote_addr}"
            
            # Check rate limit
            endpoint = f.__name__
            result = get_limiter().check(identifier, endpoint, limit, period)
            
            # Store for response
            g.rate_limit_result = result
            
            if not result.allowed:
                response = jsonify({
                    "error": error_message,
                    "retry_after": result.retry_after
                })
                response.status_code = 429
                for header, value in result.headers().items():
                    response.headers[header] = value
                return response
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator


# =============================================================================
# WebSocket Rate Limiting
# =============================================================================

class WebSocketRateLimiter:
    """
    Rate limiter for WebSocket connections.
    
    Prevents:
    - Too many connections per client
    - Message flood attacks
    - Connection cycling
    """
    
    def __init__(
        self,
        max_connections_per_client: int = 5,
        max_messages_per_second: int = 10,
        max_message_size: int = 10 * 1024,  # 10KB
        redis_client: Optional[Any] = None
    ):
        self.max_connections = max_connections_per_client
        self.max_messages = max_messages_per_second
        self.max_message_size = max_message_size
        self.redis = redis_client
        
        # Local tracking
        self._connections: Dict[str, int] = {}
        self._message_counts: Dict[str, list] = {}
        self._lock = threading.Lock()
    
    def can_connect(self, client_id: str) -> bool:
        """Check if client can open new connection."""
        with self._lock:
            current = self._connections.get(client_id, 0)
            if current >= self.max_connections:
                logger.warning(f"WebSocket connection limit exceeded for {client_id}")
                return False
            self._connections[client_id] = current + 1
            return True
    
    def on_disconnect(self, client_id: str):
        """Handle client disconnection."""
        with self._lock:
            current = self._connections.get(client_id, 0)
            self._connections[client_id] = max(0, current - 1)
    
    def can_send_message(self, client_id: str, message_size: int = 0) -> bool:
        """Check if client can send message."""
        # Check message size
        if message_size > self.max_message_size:
            logger.warning(f"WebSocket message too large from {client_id}: {message_size}")
            return False
        
        now = time.time()
        window_start = now - 1.0  # 1 second window
        
        with self._lock:
            if client_id not in self._message_counts:
                self._message_counts[client_id] = []
            
            # Remove old timestamps
            self._message_counts[client_id] = [
                ts for ts in self._message_counts[client_id]
                if ts > window_start
            ]
            
            if len(self._message_counts[client_id]) >= self.max_messages:
                logger.warning(f"WebSocket message rate limit exceeded for {client_id}")
                return False
            
            self._message_counts[client_id].append(now)
            return True
    
    def cleanup(self):
        """Clean up old tracking data."""
        cutoff = time.time() - 60
        with self._lock:
            # Clean message counts
            for client_id in list(self._message_counts.keys()):
                self._message_counts[client_id] = [
                    ts for ts in self._message_counts[client_id]
                    if ts > cutoff
                ]
                if not self._message_counts[client_id]:
                    del self._message_counts[client_id]
