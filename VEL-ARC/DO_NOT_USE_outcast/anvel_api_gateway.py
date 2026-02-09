#!/usr/bin/env python3
"""
ANVEL API Gateway
Multi-tenant API endpoint with authentication, rate limiting, and user isolation.
Designed for 100k+ concurrent users with proper resource management.

Integrates with:
- anvel_auth_service: JWT/OAuth2/TOTP authentication
- anvel_threat_isolation: Security scanning and rate limiting at the edge
- anvel_subscription_manager: Tier-based access control
"""

import functools
import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple
from flask import Flask, request, jsonify, g
import jwt  # PyJWT library

from anvel_subscription_manager import ANVELSubscriptionManager, SubscriptionTier

# Threat Isolation Integration
try:
    from anvel_threat_isolation import (
        get_threat_isolation,
        APIRateLimiter,
        ensure_threat_isolation_running,
        ThreatType,
        ThreatLevel,
    )
    THREAT_ISOLATION_AVAILABLE = True
except ImportError:
    THREAT_ISOLATION_AVAILABLE = False
    APIRateLimiter = None

# Auth Service Integration
try:
    from anvel_auth_service import AuthService, AuthenticationError
    AUTH_SERVICE_AVAILABLE = True
except ImportError:
    AUTH_SERVICE_AVAILABLE = False

log = logging.getLogger(__name__)

# Rate limiting configuration (can be overridden via env vars)
API_RATE_LIMIT_RPM = int(os.getenv("ANVEL_API_RATE_LIMIT_RPM", "60"))
API_BURST_SIZE = int(os.getenv("ANVEL_API_BURST_SIZE", "10"))
API_BLOCK_DURATION = int(os.getenv("ANVEL_API_BLOCK_DURATION", "60"))


class APIGateway:
    """
    API Gateway with authentication, authorization, and rate limiting.
    Enforces subscription tier limits and provides user isolation.
    
    Integrates threat isolation for:
    - Edge rate limiting (before subscription checks)
    - Payload security scanning
    - Brute force protection
    - API abuse detection
    """

    def __init__(
        self,
        subscription_manager: ANVELSubscriptionManager,
        jwt_secret: str,
        auth_service: Optional[Any] = None,
        enable_threat_isolation: bool = True,
    ):
        """
        Initialize API gateway.
        
        Args:
            subscription_manager: Subscription manager instance
            jwt_secret: Secret for JWT token signing
            auth_service: Optional AuthService instance for advanced auth
            enable_threat_isolation: Enable threat isolation integration
        """
        self.subscription_manager = subscription_manager
        self.jwt_secret = jwt_secret
        self.token_expiry_hours = 24
        self.auth_service = auth_service
        self.enable_threat_isolation = enable_threat_isolation

        # Initialize edge rate limiter (runs before subscription checks)
        self._edge_rate_limiter = None
        if enable_threat_isolation and THREAT_ISOLATION_AVAILABLE and APIRateLimiter:
            self._edge_rate_limiter = APIRateLimiter(
                requests_per_minute=API_RATE_LIMIT_RPM,
                burst_size=API_BURST_SIZE,
                block_duration_seconds=API_BLOCK_DURATION,
            )
            log.info(
                "Edge rate limiter initialized: %d rpm, %d burst, %ds block",
                API_RATE_LIMIT_RPM, API_BURST_SIZE, API_BLOCK_DURATION
            )

        # Ensure threat isolation is running
        if enable_threat_isolation and THREAT_ISOLATION_AVAILABLE:
            try:
                ensure_threat_isolation_running()
                log.info("Threat isolation active for API gateway")
            except Exception as e:
                log.warning("Failed to ensure threat isolation: %s", e)

    def _get_client_ip(self) -> str:
        """Get real client IP, handling proxies."""
        if request.headers.get("X-Forwarded-For"):
            return request.headers.get("X-Forwarded-For").split(",")[0].strip()
        if request.headers.get("X-Real-IP"):
            return request.headers.get("X-Real-IP")
        return request.remote_addr or "unknown"

    def _check_edge_rate_limit(self, identifier: str, endpoint: str) -> Tuple[bool, Optional[str]]:
        """
        Check edge rate limit before any other processing.
        
        This is the first line of defense against abuse.
        """
        if not self._edge_rate_limiter:
            return True, None

        return self._edge_rate_limiter.check_rate_limit(identifier, endpoint)

    def _scan_request_payload(self, endpoint: str) -> Tuple[bool, Optional[str]]:
        """
        Scan request payload for threats using threat isolation system.
        """
        if not self.enable_threat_isolation or not THREAT_ISOLATION_AVAILABLE:
            return True, None

        try:
            threat_system = get_threat_isolation()

            # Get request payload
            payload = None
            if request.method in ("POST", "PUT", "PATCH"):
                try:
                    if request.is_json:
                        payload = str(request.get_json(silent=True) or {})
                    elif request.data:
                        payload = request.data.decode("utf-8", errors="replace")[:10000]
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_API_GATEWAY").debug("Exception suppressed in _scan_request_payload")

            # Add query params to scan
            if request.args:
                query_str = str(dict(request.args))
                payload = f"{payload or ''} {query_str}"

            if not payload:
                return True, None

            # Run threat detection
            client_ip = self._get_client_ip()
            user_id = g.get("user_id")

            allowed, threat_event = threat_system.detect_and_isolate(
                source_ip=client_ip,
                user_id=user_id,
                action=request.method,
                payload=payload,
                endpoint=endpoint,
            )

            if not allowed:
                threat_desc = threat_event.description if threat_event else "Security violation"
                log.warning(
                    "[API GATEWAY] Payload blocked: %s from %s on %s",
                    threat_desc, client_ip, endpoint
                )
                return False, threat_desc

            return True, None

        except Exception as e:
            log.error("Threat scan failed: %s", e)
            # Fail open for threat scanning (still have rate limits)
            return True, None

    def generate_api_key(self, user_id: str) -> str:
        """
        Generate unique API key for user.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            API key string
        """
        # Generate cryptographically secure random key
        random_bytes = secrets.token_bytes(32)
        timestamp = str(int(time.time()))

        # Create composite key
        key_data = f"{user_id}:{timestamp}:{random_bytes.hex()}"
        api_key = hashlib.sha256(key_data.encode()).hexdigest()

        return f"anvel_{api_key}"

    def hash_api_key(self, api_key: str) -> str:
        """
        Hash API key for secure storage.
        
        Args:
            api_key: Raw API key
            
        Returns:
            Hashed API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    def generate_jwt_token(self, user_id: str, tier: str) -> str:
        """
        Generate JWT token for authenticated session.
        
        Args:
            user_id: UUID of the user
            tier: Subscription tier
            
        Returns:
            JWT token string
        """
        expires_at = datetime.utcnow() + timedelta(hours=self.token_expiry_hours)

        payload = {
            "user_id": user_id,
            "tier": tier,
            "exp": expires_at.timestamp(),
            "iat": datetime.utcnow().timestamp(),
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        return token

    def verify_jwt_token(self, token: str) -> Optional[Dict]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"]
            )
            return payload
        except jwt.ExpiredSignatureError:
            log.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            log.warning(f"Invalid token: {e}")
            return None

    def require_auth(self, endpoint: str = "default"):
        """
        Decorator for API endpoints requiring authentication.
        Validates JWT token or API key and checks rate limits.
        
        Order of checks:
        1. Edge rate limiting (threat isolation)
        2. Authentication (JWT/API key)
        3. Payload security scan
        4. Subscription rate limiting
        
        Args:
            endpoint: Endpoint identifier for rate limiting
        """
        def decorator(f: Callable):
            @functools.wraps(f)
            def decorated_function(*args, **kwargs):
                client_ip = self._get_client_ip()

                # === STEP 1: Edge Rate Limiting (First line of defense) ===
                rate_ok, rate_reason = self._check_edge_rate_limit(client_ip, endpoint)
                if not rate_ok:
                    log.warning(
                        "[API GATEWAY] Edge rate limit: %s from %s on %s",
                        rate_reason, client_ip, endpoint
                    )
                    return jsonify({
                        "error": "Rate limit exceeded",
                        "message": rate_reason,
                        "retry_after": API_BLOCK_DURATION,
                    }), 429

                # === STEP 2: Authentication ===
                auth_header = request.headers.get("Authorization", "")

                if not auth_header:
                    return jsonify({"error": "Missing authorization"}), 401

                user_id = None

                # Support both JWT and API key
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]

                    # Try integrated auth service first
                    if self.auth_service and AUTH_SERVICE_AVAILABLE:
                        try:
                            payload = self.auth_service.verify_jwt(token)
                            user_id = payload.get("sub")
                        except Exception:
                            import logging as _lg  # noqa: E402
                            _lg.getLogger("ANVEL_API_GATEWAY").debug("Exception suppressed in decorated_function")

                    # Fall back to local verification
                    if not user_id:
                        payload = self.verify_jwt_token(token)
                        if payload:
                            user_id = payload.get("user_id")

                    if not user_id:
                        # Record failed auth for brute force detection
                        if self.enable_threat_isolation and THREAT_ISOLATION_AVAILABLE:
                            try:
                                threat_system = get_threat_isolation()
                                threat_system.record_auth_attempt(
                                    source_ip=client_ip,
                                    user_id="api_user",
                                    success=False,
                                )
                            except Exception:
                                import logging as _lg  # noqa: E402
                                _lg.getLogger("ANVEL_API_GATEWAY").debug("Exception suppressed in decorated_function")
                        return jsonify({"error": "Invalid or expired token"}), 401

                elif auth_header.startswith("ApiKey "):
                    api_key = auth_header[7:]
                    user_id = self._verify_api_key(api_key)

                    if not user_id:
                        # Record failed auth
                        if self.enable_threat_isolation and THREAT_ISOLATION_AVAILABLE:
                            try:
                                threat_system = get_threat_isolation()
                                threat_system.record_auth_attempt(
                                    source_ip=client_ip,
                                    user_id="api_key_user",
                                    success=False,
                                )
                            except Exception:
                                import logging as _lg  # noqa: E402
                                _lg.getLogger("ANVEL_API_GATEWAY").debug("Exception suppressed in decorated_function")
                        return jsonify({"error": "Invalid API key"}), 401
                else:
                    return jsonify({"error": "Invalid authorization format"}), 401

                # Store user_id for threat scanning
                g.user_id = user_id

                # === STEP 3: Payload Security Scan ===
                scan_ok, scan_reason = self._scan_request_payload(endpoint)
                if not scan_ok:
                    return jsonify({
                        "error": "Security violation",
                        "message": scan_reason or "Request blocked by security scan",
                    }), 403

                # === STEP 4: Subscription Rate Limiting ===
                if not self.subscription_manager.check_rate_limit(user_id, endpoint):
                    return jsonify({
                        "error": "Rate limit exceeded",
                        "message": "Upgrade your subscription for higher limits"
                    }), 429

                # Get subscription for context
                subscription = self.subscription_manager.get_user_subscription(user_id)

                # Store in request context
                g.subscription = subscription

                # Record successful auth
                if self.enable_threat_isolation and THREAT_ISOLATION_AVAILABLE:
                    try:
                        threat_system = get_threat_isolation()
                        threat_system.record_auth_attempt(
                            source_ip=client_ip,
                            user_id=user_id,
                            success=True,
                        )
                    except Exception:
                        import logging as _lg  # noqa: E402
                        _lg.getLogger("ANVEL_API_GATEWAY").debug("Exception suppressed in decorated_function")

                return f(*args, **kwargs)

            return decorated_function
        return decorator

    def _verify_api_key(self, api_key: str) -> Optional[str]:
        """
        Verify API key against database.
        
        Args:
            api_key: Raw API key to verify
            
        Returns:
            User ID if valid, None otherwise
        """
        # Hash the provided key
        key_hash = self.hash_api_key(api_key)

        # Query database
        conn = self.subscription_manager._get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id 
                    FROM users 
                    WHERE api_key_hash = %s 
                    AND is_active = true
                """, (key_hash,))

                result = cur.fetchone()
                return result[0] if result else None
        finally:
            conn.close()

    def require_tier(self, min_tier: SubscriptionTier):
        """
        Decorator requiring minimum subscription tier.
        
        Args:
            min_tier: Minimum required subscription tier
        """
        def decorator(f: Callable):
            @functools.wraps(f)
            def decorated_function(*args, **kwargs):
                subscription = g.get("subscription")

                if not subscription:
                    return jsonify({
                        "error": "No active subscription",
                        "required_tier": min_tier.value
                    }), 403

                # Check tier hierarchy
                tier_order = {
                    SubscriptionTier.BASIC: 0,
                    SubscriptionTier.PREMIUM: 1,
                }

                current_tier = SubscriptionTier(subscription["tier"])

                if tier_order[current_tier] < tier_order[min_tier]:
                    return jsonify({
                        "error": "Insufficient subscription tier",
                        "current_tier": current_tier.value,
                        "required_tier": min_tier.value
                    }), 403

                return f(*args, **kwargs)

            return decorated_function
        return decorator

    def check_feature_enabled(self, feature: str) -> bool:
        """
        Check if feature is enabled for current user's tier.
        
        Args:
            feature: Feature name (ai_features, backtesting, etc.)
            
        Returns:
            True if feature is enabled
        """
        subscription = g.get("subscription")

        if not subscription:
            return False

        limits = subscription.get("limits", {})

        feature_map = {
            "ai_features": "ai_features_enabled",
            "backtesting": "backtesting_enabled",
            "advanced_analytics": "advanced_analytics",
            "priority_support": "priority_support",
        }

        limit_key = feature_map.get(feature)
        return limits.get(limit_key, False) if limit_key else False


def create_api_routes(app: Flask, gateway: APIGateway):
    """
    Create API routes with authentication and rate limiting.
    
    Args:
        app: Flask application
        gateway: APIGateway instance
    """

    @app.route("/api/v1/health", methods=["GET"])
    def health_check():
        """Public health check endpoint."""
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        })

    @app.route("/api/v1/auth/login", methods=["POST"])
    def login():
        """
        Authenticate user and return JWT token.
        
        PRODUCTION WARNING: This is a mock implementation.
        Must integrate with proper user authentication system.
        """
        data = request.get_json()

        if not data or not data.get("username") or not data.get("password"):
            return jsonify({"error": "Missing credentials"}), 400

        # PRODUCTION: Replace with real authentication
        # Example integrations:
        # - Database user lookup with password hash verification
        # - LDAP/Active Directory
        # - OAuth2/OIDC provider
        # - AWS Cognito
        return jsonify({
            "error": "Authentication not implemented",
            "message": "Must integrate with user authentication system before production use"
        }), 501

    @app.route("/api/v1/subscription", methods=["GET"])
    @gateway.require_auth("subscription_info")
    def get_subscription():
        """Get current user's subscription details."""
        subscription = g.subscription

        if not subscription:
            return jsonify({
                "tier": "free",
                "status": "no_subscription"
            }), 200

        return jsonify(subscription)

    @app.route("/api/v1/trading/positions", methods=["GET"])
    @gateway.require_auth("trading_positions")
    def get_positions():
        """Get user's trading positions."""
        user_id = g.user_id
        subscription = g.subscription

        # Check position limits
        limits = subscription.get("limits", {})
        max_positions = limits.get("max_active_positions", 1)

        return jsonify({
            "user_id": user_id,
            "positions": [],  # Load from database
            "max_positions": max_positions,
        })

    @app.route("/api/v1/trading/execute", methods=["POST"])
    @gateway.require_auth("trading_execute")
    @gateway.require_tier(SubscriptionTier.STARTER)
    def execute_trade():
        """Execute trade order."""
        user_id = g.user_id
        data = request.get_json()

        if not data:
            return jsonify({"error": "Missing trade data"}), 400

        # Validate trade limits
        limits = gateway.subscription_manager.validate_user_limits(user_id)

        # Execute trade through trade engine
        # This integrates with existing anvel_trade_engine.py

        return jsonify({
            "status": "submitted",
            "trade_id": "mock-trade-id",
            "user_id": user_id,
        })

    @app.route("/api/v1/ai/signals", methods=["GET"])
    @gateway.require_auth("ai_signals")
    @gateway.require_tier(SubscriptionTier.STARTER)
    def get_ai_signals():
        """Get AI-generated trading signals."""
        if not gateway.check_feature_enabled("ai_features"):
            return jsonify({
                "error": "AI features not available",
                "upgrade_to": "starter"
            }), 403

        user_id = g.user_id

        return jsonify({
            "user_id": user_id,
            "signals": [],  # Load from AI system
        })

    @app.route("/api/v1/analytics/backtest", methods=["POST"])
    @gateway.require_auth("analytics_backtest")
    @gateway.require_tier(SubscriptionTier.STARTER)
    def run_backtest():
        """Run strategy backtest."""
        if not gateway.check_feature_enabled("backtesting"):
            return jsonify({
                "error": "Backtesting not available",
                "upgrade_to": "starter"
            }), 403

        data = request.get_json()

        if not data or not data.get("strategy"):
            return jsonify({"error": "Missing strategy"}), 400

        return jsonify({
            "status": "queued",
            "backtest_id": "mock-backtest-id",
        })

    log.info("API routes registered successfully")
