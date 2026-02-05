#!/usr/bin/env python3
"""
ANVEL Multi-User Trading Manager - API Key Management for 100k+ Users

This module implements a production-grade user management system for:
- API key generation, validation, and rotation
- User isolation for concurrent trading operations
- Scalable architecture supporting 100,000+ users
- Integration with the scalping engine and trade engine

Thread-safe, idempotent, and production-ready.
"""

import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# API Key configuration
API_KEY_PREFIX = "vel_"
API_KEY_LENGTH = 64  # Total key length including prefix
API_KEY_EXPIRY_DAYS = 365  # Keys expire after 1 year by default

# Rate limiting defaults
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_RATE_LIMIT_PER_HOUR = 1000
DEFAULT_BURST_LIMIT = 10


class UserStatus(Enum):
    """User account status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"
    DEACTIVATED = "deactivated"


class APIKeyStatus(Enum):
    """API key status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class APIKeyInfo:
    """API key metadata."""
    key_id: str
    key_hash: str
    user_id: str
    created_at: float
    expires_at: float
    last_used: Optional[float] = None
    status: APIKeyStatus = APIKeyStatus.ACTIVE
    permissions: List[str] = field(default_factory=lambda: ["trade", "read"])
    ip_whitelist: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE

    def is_valid(self) -> bool:
        """Check if key is valid and not expired."""
        if self.status != APIKeyStatus.ACTIVE:
            return False
        if time.time() > self.expires_at:
            return False
        return True

    def has_permission(self, permission: str) -> bool:
        """Check if key has a specific permission."""
        return permission in self.permissions or "admin" in self.permissions

    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP is allowed (empty whitelist = all allowed)."""
        if not self.ip_whitelist:
            return True
        return ip_address in self.ip_whitelist


@dataclass
class UserAccount:
    """User account information."""
    user_id: str
    email: str
    created_at: float
    status: UserStatus = UserStatus.ACTIVE
    subscription_tier: str = "basic"
    api_keys: Dict[str, APIKeyInfo] = field(default_factory=dict)
    trading_capital: float = 0.0
    daily_trade_limit: int = 100
    max_positions: int = 10
    max_api_keys: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE

    def can_create_api_key(self) -> bool:
        """Check if user can create more API keys."""
        active_keys = sum(1 for k in self.api_keys.values() if k.is_valid())
        return active_keys < self.max_api_keys


@dataclass
class RateLimitState:
    """Rate limiting state for a key."""
    key_id: str
    minute_window_start: float = 0.0
    minute_count: int = 0
    hour_window_start: float = 0.0
    hour_count: int = 0
    burst_tokens: float = field(default_factory=lambda: float(DEFAULT_BURST_LIMIT))
    last_burst_refill: float = field(default_factory=time.time)


# =============================================================================
# Multi-User Manager
# =============================================================================

class MultiUserManager:
    """
    Manages users, API keys, and authentication for 100k+ concurrent users.
    
    Features:
    - Secure API key generation and hashing
    - User isolation with individual trading contexts
    - Rate limiting per API key
    - IP whitelisting support
    - Thread-safe operations
    """

    def __init__(
        self,
        max_users: int = 100000,
        persistence_backend: Optional[Callable] = None,
    ):
        """
        Initialize the multi-user manager.
        
        Args:
            max_users: Maximum number of concurrent users
            persistence_backend: Optional callback for persisting data
        """
        self.max_users = max_users
        self.persistence_backend = persistence_backend

        # In-memory storage (in production, use Redis/PostgreSQL)
        self.users: Dict[str, UserAccount] = {}
        self.api_key_to_user: Dict[str, str] = {}  # key_hash -> user_id
        self.api_key_info: Dict[str, APIKeyInfo] = {}  # key_hash -> info
        self.rate_limits: Dict[str, RateLimitState] = {}

        # Locks for thread safety
        self._users_lock = threading.RLock()
        self._keys_lock = threading.RLock()
        self._rate_lock = threading.Lock()

        # Metrics
        self.total_authentications = 0
        self.failed_authentications = 0
        self.total_api_calls = 0

        log.info("MultiUserManager initialized with max_users=%d", max_users)

    # =========================================================================
    # User Management
    # =========================================================================

    def create_user(
        self,
        user_id: str,
        email: str,
        subscription_tier: str = "basic",
        trading_capital: float = 0.0,
        metadata: Dict = None,
    ) -> Tuple[bool, str]:
        """
        Create a new user account.
        
        Args:
            user_id: Unique user identifier
            email: User email address
            subscription_tier: Subscription tier
            trading_capital: Initial trading capital
            metadata: Additional user metadata
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        with self._users_lock:
            if len(self.users) >= self.max_users:
                return False, "Maximum user limit reached"

            if user_id in self.users:
                return False, "User ID already exists"

            # Set tier-specific limits
            limits = self._get_tier_limits(subscription_tier)

            user = UserAccount(
                user_id=user_id,
                email=email,
                created_at=time.time(),
                subscription_tier=subscription_tier,
                trading_capital=trading_capital,
                daily_trade_limit=limits["daily_trades"],
                max_positions=limits["max_positions"],
                max_api_keys=limits["max_api_keys"],
                metadata=metadata or {},
            )

            self.users[user_id] = user

            log.info("Created user %s with tier %s", user_id, subscription_tier)

            # Persist if backend available
            if self.persistence_backend:
                self.persistence_backend("create_user", user)

            return True, "User created successfully"

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        """Get user account by ID."""
        return self.users.get(user_id)

    def update_user(
        self,
        user_id: str,
        subscription_tier: str = None,
        trading_capital: float = None,
        status: UserStatus = None,
        metadata: Dict = None,
    ) -> bool:
        """Update user account details."""
        with self._users_lock:
            user = self.users.get(user_id)
            if not user:
                return False

            if subscription_tier:
                user.subscription_tier = subscription_tier
                limits = self._get_tier_limits(subscription_tier)
                user.daily_trade_limit = limits["daily_trades"]
                user.max_positions = limits["max_positions"]
                user.max_api_keys = limits["max_api_keys"]

            if trading_capital is not None:
                user.trading_capital = trading_capital

            if status:
                user.status = status

            if metadata:
                user.metadata.update(metadata)

            log.info("Updated user %s", user_id)
            return True

    def delete_user(self, user_id: str) -> bool:
        """Delete user and revoke all API keys."""
        with self._users_lock:
            user = self.users.get(user_id)
            if not user:
                return False

            # Revoke all API keys
            with self._keys_lock:
                for key_hash in list(user.api_keys.keys()):
                    if key_hash in self.api_key_to_user:
                        del self.api_key_to_user[key_hash]
                    if key_hash in self.api_key_info:
                        del self.api_key_info[key_hash]

            del self.users[user_id]

            log.info("Deleted user %s", user_id)
            return True

    def list_users(
        self,
        offset: int = 0,
        limit: int = 100,
        status_filter: UserStatus = None
    ) -> List[Dict[str, Any]]:
        """
        List users with pagination.
        
        Args:
            offset: Starting offset
            limit: Maximum users to return
            status_filter: Filter by status
            
        Returns:
            List of user summaries
        """
        with self._users_lock:
            users = list(self.users.values())

            if status_filter:
                users = [u for u in users if u.status == status_filter]

            users = users[offset:offset + limit]

            return [
                {
                    "user_id": u.user_id,
                    "email": u.email,
                    "status": u.status.value,
                    "tier": u.subscription_tier,
                    "created_at": u.created_at,
                    "api_keys_count": len(u.api_keys),
                    "trading_capital": u.trading_capital,
                }
                for u in users
            ]

    def _get_tier_limits(self, tier: str) -> Dict[str, int]:
        """Get limits for a subscription tier."""
        tier_limits = {
            "basic": {
                "daily_trades": 50,
                "max_positions": 5,
                "max_api_keys": 2,
            },
            "premium": {
                "daily_trades": 200,
                "max_positions": 20,
                "max_api_keys": 5,
            },
            "enterprise": {
                "daily_trades": 1000,
                "max_positions": 100,
                "max_api_keys": 20,
            },
        }
        return tier_limits.get(tier, tier_limits["basic"])

    # =========================================================================
    # API Key Management
    # =========================================================================

    def generate_api_key(
        self,
        user_id: str,
        permissions: List[str] = None,
        ip_whitelist: List[str] = None,
        expires_in_days: int = API_KEY_EXPIRY_DAYS,
    ) -> Tuple[Optional[str], str]:
        """
        Generate a new API key for a user.
        
        Args:
            user_id: User to generate key for
            permissions: List of permissions for this key
            ip_whitelist: List of allowed IP addresses
            expires_in_days: Key expiry in days
            
        Returns:
            Tuple of (api_key: Optional[str], message: str)
            The raw API key is only returned once - it cannot be retrieved later
        """
        with self._users_lock:
            user = self.users.get(user_id)
            if not user:
                return None, "User not found"

            if not user.is_active():
                return None, "User account is not active"

            if not user.can_create_api_key():
                return None, f"Maximum API keys ({user.max_api_keys}) reached"

        # Generate secure key with sufficient entropy for 100k+ users
        # 16 hex chars = 64 bits of entropy, collision probability negligible
        key_id = secrets.token_hex(16)
        raw_key = self._generate_raw_key()
        key_hash = self._hash_api_key(raw_key)

        # Create key info
        now = time.time()
        key_info = APIKeyInfo(
            key_id=key_id,
            key_hash=key_hash,
            user_id=user_id,
            created_at=now,
            expires_at=now + (expires_in_days * 86400),
            permissions=permissions or ["trade", "read"],
            ip_whitelist=ip_whitelist or [],
        )

        with self._keys_lock:
            self.api_key_to_user[key_hash] = user_id
            self.api_key_info[key_hash] = key_info
            user.api_keys[key_hash] = key_info

        log.info("Generated API key %s for user %s", key_id, user_id)

        return raw_key, "API key generated successfully"

    def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        """
        Revoke an API key.
        
        Args:
            user_id: User who owns the key
            key_id: Key ID to revoke
            
        Returns:
            True if revoked successfully
        """
        with self._users_lock:
            user = self.users.get(user_id)
            if not user:
                return False

        with self._keys_lock:
            # Find key by ID
            for key_hash, key_info in list(self.api_key_info.items()):
                if key_info.key_id == key_id and key_info.user_id == user_id:
                    key_info.status = APIKeyStatus.REVOKED

                    # Remove from mappings
                    if key_hash in self.api_key_to_user:
                        del self.api_key_to_user[key_hash]

                    log.info("Revoked API key %s for user %s", key_id, user_id)
                    return True

        return False

    def list_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """
        List all API keys for a user (without exposing key values).
        
        Args:
            user_id: User ID
            
        Returns:
            List of key metadata
        """
        user = self.users.get(user_id)
        if not user:
            return []

        return [
            {
                "key_id": info.key_id,
                "created_at": info.created_at,
                "expires_at": info.expires_at,
                "status": info.status.value,
                "permissions": info.permissions,
                "ip_whitelist": info.ip_whitelist,
                "last_used": info.last_used,
                "is_valid": info.is_valid(),
            }
            for info in user.api_keys.values()
        ]

    def _generate_raw_key(self) -> str:
        """Generate a raw API key."""
        random_part = secrets.token_hex((API_KEY_LENGTH - len(API_KEY_PREFIX)) // 2)
        return f"{API_KEY_PREFIX}{random_part}"

    def _hash_api_key(self, raw_key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    # =========================================================================
    # Authentication
    # =========================================================================

    def authenticate(
        self,
        api_key: str,
        ip_address: str = None,
        required_permission: str = None,
    ) -> Tuple[Optional[str], str]:
        """
        Authenticate an API key.
        
        Args:
            api_key: Raw API key to authenticate
            ip_address: Request IP address for whitelist check
            required_permission: Required permission for this request
            
        Returns:
            Tuple of (user_id: Optional[str], message: str)
        """
        self.total_authentications += 1

        # Hash the key
        key_hash = self._hash_api_key(api_key)

        with self._keys_lock:
            # Find key info
            key_info = self.api_key_info.get(key_hash)
            if not key_info:
                self.failed_authentications += 1
                return None, "Invalid API key"

            # Check if key is valid
            if not key_info.is_valid():
                self.failed_authentications += 1
                if key_info.status == APIKeyStatus.REVOKED:
                    return None, "API key has been revoked"
                if time.time() > key_info.expires_at:
                    key_info.status = APIKeyStatus.EXPIRED
                    return None, "API key has expired"
                return None, "API key is not valid"

            # Check IP whitelist
            if ip_address and not key_info.is_ip_allowed(ip_address):
                self.failed_authentications += 1
                return None, "IP address not allowed"

            # Check permission
            if required_permission and not key_info.has_permission(required_permission):
                self.failed_authentications += 1
                return None, f"Permission '{required_permission}' not granted"

            # Check rate limit
            if not self._check_rate_limit(key_info):
                self.failed_authentications += 1
                return None, "Rate limit exceeded"

            # Update last used
            key_info.last_used = time.time()

            self.total_api_calls += 1

            return key_info.user_id, "Authenticated successfully"

    def _check_rate_limit(self, key_info: APIKeyInfo) -> bool:
        """Check and update rate limit for a key."""
        with self._rate_lock:
            key_id = key_info.key_id
            now = time.time()

            # Get or create rate limit state
            if key_id not in self.rate_limits:
                self.rate_limits[key_id] = RateLimitState(key_id=key_id)

            state = self.rate_limits[key_id]

            # Check minute window
            if now - state.minute_window_start > 60:
                state.minute_window_start = now
                state.minute_count = 0

            if state.minute_count >= key_info.rate_limit_per_minute:
                return False

            state.minute_count += 1

            # Check hour window
            if now - state.hour_window_start > 3600:
                state.hour_window_start = now
                state.hour_count = 0

            if state.hour_count >= DEFAULT_RATE_LIMIT_PER_HOUR:
                return False

            state.hour_count += 1

            # Token bucket for burst
            elapsed = now - state.last_burst_refill
            state.burst_tokens = min(
                DEFAULT_BURST_LIMIT,
                state.burst_tokens + elapsed * (DEFAULT_BURST_LIMIT / 60)
            )
            state.last_burst_refill = now

            if state.burst_tokens < 1:
                return False

            state.burst_tokens -= 1

            return True

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        active_users = sum(1 for u in self.users.values() if u.is_active())
        active_keys = sum(1 for k in self.api_key_info.values() if k.is_valid())
        total_capital = sum(u.trading_capital for u in self.users.values())

        return {
            "total_users": len(self.users),
            "active_users": active_users,
            "max_users": self.max_users,
            "total_api_keys": len(self.api_key_info),
            "active_api_keys": active_keys,
            "total_authentications": self.total_authentications,
            "failed_authentications": self.failed_authentications,
            "auth_success_rate": (
                (self.total_authentications - self.failed_authentications)
                / self.total_authentications * 100
                if self.total_authentications > 0 else 0
            ),
            "total_api_calls": self.total_api_calls,
            "total_capital_under_management": total_capital,
        }

    def get_user_count_by_tier(self) -> Dict[str, int]:
        """Get user count breakdown by subscription tier."""
        tier_counts = defaultdict(int)
        for user in self.users.values():
            tier_counts[user.subscription_tier] += 1
        return dict(tier_counts)


# =============================================================================
# Trading Context Manager
# =============================================================================

class UserTradingContext:
    """
    Context manager for isolated user trading sessions.
    
    Ensures proper isolation between users when executing trades.
    """

    def __init__(
        self,
        user_manager: MultiUserManager,
        user_id: str,
        api_key: str,
        ip_address: str = None,
    ):
        """
        Initialize trading context.
        
        Args:
            user_manager: MultiUserManager instance
            user_id: User ID
            api_key: API key for authentication
            ip_address: Request IP address
        """
        self.user_manager = user_manager
        self.user_id = user_id
        self.api_key = api_key
        self.ip_address = ip_address
        self.authenticated = False
        self.error_message: Optional[str] = None
        self._lock = threading.Lock()

    def __enter__(self) -> "UserTradingContext":
        """Enter trading context with authentication."""
        auth_user_id, message = self.user_manager.authenticate(
            self.api_key,
            self.ip_address,
            required_permission="trade"
        )

        if auth_user_id and auth_user_id == self.user_id:
            self.authenticated = True
        else:
            self.authenticated = False
            self.error_message = message

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit trading context."""
        # Could add cleanup logic here
        pass

    def is_authenticated(self) -> bool:
        """Check if context is authenticated."""
        return self.authenticated

    def get_user(self) -> Optional[UserAccount]:
        """Get the authenticated user."""
        if not self.authenticated:
            return None
        return self.user_manager.get_user(self.user_id)

    def execute_trade(
        self,
        trade_engine: Any,
        symbol: str,
        side: str,
        quantity: float,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute a trade within the user's context.
        
        Args:
            trade_engine: Trading engine instance
            symbol: Trading symbol
            side: Buy or sell
            quantity: Trade quantity
            **kwargs: Additional trade parameters
            
        Returns:
            Trade execution result
        """
        if not self.authenticated:
            return {"success": False, "error": self.error_message or "Not authenticated"}

        with self._lock:
            try:
                result = trade_engine.submit_trade(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    strategy=f"user_{self.user_id}",
                    **kwargs
                )
                return {"success": "Queued" in result, "result": result}
            except Exception as e:
                return {"success": False, "error": str(e)}


# =============================================================================
# Factory Functions
# =============================================================================

def create_user_manager(max_users: int = 100000) -> MultiUserManager:
    """
    Create a configured multi-user manager.
    
    Args:
        max_users: Maximum concurrent users
        
    Returns:
        MultiUserManager instance
    """
    return MultiUserManager(max_users=max_users)


def create_trading_context(
    user_manager: MultiUserManager,
    user_id: str,
    api_key: str,
    ip_address: str = None,
) -> UserTradingContext:
    """
    Create a trading context for a user.
    
    Args:
        user_manager: MultiUserManager instance
        user_id: User ID
        api_key: API key
        ip_address: Request IP
        
    Returns:
        UserTradingContext instance
    """
    return UserTradingContext(
        user_manager=user_manager,
        user_id=user_id,
        api_key=api_key,
        ip_address=ip_address,
    )


if __name__ == "__main__":
    # Demonstration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=" * 60)
    print("ANVEL Multi-User Trading Manager")
    print("=" * 60)

    # Create manager
    manager = create_user_manager(max_users=100000)

    # Create test user
    success, msg = manager.create_user(
        user_id="test_user_001",
        email="test@example.com",
        subscription_tier="premium",
        trading_capital=10000.0
    )
    print(f"\nCreate user: {msg}")

    # Generate API key
    api_key, msg = manager.generate_api_key(
        user_id="test_user_001",
        permissions=["trade", "read"],
    )
    print(f"Generate API key: {msg}")
    if api_key:
        print(f"  Key (SAVE THIS - shown once): {api_key[:20]}...")

    # Test authentication
    user_id, msg = manager.authenticate(api_key)
    print(f"Authentication: {msg} (user_id={user_id})")

    # List API keys
    keys = manager.list_api_keys("test_user_001")
    print(f"User API keys: {len(keys)} key(s)")

    # Show stats
    stats = manager.get_stats()
    print("\nManager Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
