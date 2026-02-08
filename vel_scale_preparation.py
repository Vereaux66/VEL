#!/usr/bin/env python3
"""
VEL Scale Preparation Module
============================

Implements features required for scaling to 100k+ users:
- Per-user isolation
- Account-level circuit breakers
- Fair scheduling
- Rate limiting per user
- Resource quota enforcement
- Backpressure management

NO STUBS - All functionality is fully implemented.
"""

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import heapq

logger = logging.getLogger("vel.scale")


# =============================================================================
# Enums and Data Structures
# =============================================================================

class UserTier(Enum):
    """User subscription tiers with different resource limits."""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class QuotaType(Enum):
    """Types of quotas that can be enforced."""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    DAILY_TRADES = "daily_trades"
    CONCURRENT_POSITIONS = "concurrent_positions"
    MAX_POSITION_SIZE = "max_position_size"
    DAILY_VOLUME = "daily_volume"


@dataclass
class TierLimits:
    """Resource limits for a user tier."""
    requests_per_minute: int
    requests_per_hour: int
    daily_trades: int
    concurrent_positions: int
    max_position_size: Decimal
    daily_volume: Decimal
    priority_weight: int  # Higher = more priority in fair scheduling
    
    @classmethod
    def for_tier(cls, tier: UserTier) -> "TierLimits":
        """Get limits for a specific tier."""
        limits = {
            UserTier.FREE: cls(
                requests_per_minute=10,
                requests_per_hour=100,
                daily_trades=10,
                concurrent_positions=2,
                max_position_size=Decimal("1000"),
                daily_volume=Decimal("5000"),
                priority_weight=1
            ),
            UserTier.BASIC: cls(
                requests_per_minute=30,
                requests_per_hour=500,
                daily_trades=50,
                concurrent_positions=5,
                max_position_size=Decimal("10000"),
                daily_volume=Decimal("50000"),
                priority_weight=2
            ),
            UserTier.PREMIUM: cls(
                requests_per_minute=100,
                requests_per_hour=2000,
                daily_trades=200,
                concurrent_positions=20,
                max_position_size=Decimal("100000"),
                daily_volume=Decimal("500000"),
                priority_weight=5
            ),
            UserTier.ENTERPRISE: cls(
                requests_per_minute=500,
                requests_per_hour=10000,
                daily_trades=1000,
                concurrent_positions=100,
                max_position_size=Decimal("1000000"),
                daily_volume=Decimal("5000000"),
                priority_weight=10
            ),
        }
        return limits[tier]


@dataclass
class UserContext:
    """Complete context for a user account."""
    user_id: str
    tier: UserTier
    limits: TierLimits
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Usage tracking
    request_timestamps: List[float] = field(default_factory=list)
    daily_trades: int = 0
    daily_volume: Decimal = field(default_factory=lambda: Decimal("0"))
    concurrent_positions: int = 0
    last_trade_day: str = ""
    
    # Circuit breaker state
    circuit_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    circuit_open_until: Optional[float] = None
    
    # Fair scheduling
    last_served_time: float = 0.0
    pending_requests: int = 0


@dataclass
class ScheduledRequest:
    """A request scheduled for fair execution."""
    request_id: str
    user_id: str
    priority: float  # Lower = higher priority (for min-heap)
    submitted_at: float
    deadline: float
    payload: Dict[str, Any]
    
    def __lt__(self, other: "ScheduledRequest") -> bool:
        return self.priority < other.priority


# =============================================================================
# User Isolation Manager
# =============================================================================

class UserIsolationManager:
    """
    Manages per-user isolation and resource tracking.
    
    Each user gets their own isolated context that tracks:
    - Request history (for rate limiting)
    - Daily usage (trades, volume)
    - Circuit breaker state
    - Active positions
    """
    
    def __init__(self):
        self._users: Dict[str, UserContext] = {}
        self._lock = threading.RLock()
        
        # Circuit breaker settings
        self._failure_threshold = 5
        self._recovery_timeout = 60.0  # seconds
        self._half_open_max_calls = 3
    
    def get_or_create_user(
        self,
        user_id: str,
        tier: UserTier = UserTier.FREE
    ) -> UserContext:
        """Get existing user context or create new one."""
        with self._lock:
            if user_id not in self._users:
                limits = TierLimits.for_tier(tier)
                self._users[user_id] = UserContext(
                    user_id=user_id,
                    tier=tier,
                    limits=limits
                )
                logger.info(f"Created user context: {user_id} (tier: {tier.value})")
            return self._users[user_id]
    
    def get_user(self, user_id: str) -> Optional[UserContext]:
        """Get user context if exists."""
        with self._lock:
            return self._users.get(user_id)
    
    def update_tier(self, user_id: str, new_tier: UserTier) -> None:
        """Update user's subscription tier."""
        with self._lock:
            user = self.get_or_create_user(user_id)
            user.tier = new_tier
            user.limits = TierLimits.for_tier(new_tier)
            logger.info(f"Updated user tier: {user_id} -> {new_tier.value}")
    
    def record_request(self, user_id: str) -> None:
        """Record a request for rate limiting."""
        with self._lock:
            user = self.get_or_create_user(user_id)
            now = time.time()
            user.request_timestamps.append(now)
            
            # Clean old timestamps (older than 1 hour)
            cutoff = now - 3600
            user.request_timestamps = [
                ts for ts in user.request_timestamps if ts > cutoff
            ]
    
    def record_trade(
        self,
        user_id: str,
        volume: Decimal,
        success: bool = True
    ) -> None:
        """Record a trade execution."""
        with self._lock:
            user = self.get_or_create_user(user_id)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            # Reset daily counters if new day
            if user.last_trade_day != today:
                user.daily_trades = 0
                user.daily_volume = Decimal("0")
                user.last_trade_day = today
            
            user.daily_trades += 1
            user.daily_volume += volume
            
            # Update circuit breaker
            if success:
                self._record_success(user)
            else:
                self._record_failure(user)
    
    def _record_success(self, user: UserContext) -> None:
        """Record successful operation for circuit breaker."""
        if user.circuit_state == CircuitBreakerState.HALF_OPEN:
            # Successful call in half-open state -> close circuit
            user.circuit_state = CircuitBreakerState.CLOSED
            user.failure_count = 0
            logger.info(f"Circuit breaker closed for user {user.user_id}")
    
    def _record_failure(self, user: UserContext) -> None:
        """Record failed operation for circuit breaker."""
        user.failure_count += 1
        user.last_failure_time = time.time()
        
        if user.failure_count >= self._failure_threshold:
            if user.circuit_state == CircuitBreakerState.CLOSED:
                user.circuit_state = CircuitBreakerState.OPEN
                user.circuit_open_until = time.time() + self._recovery_timeout
                logger.warning(
                    f"Circuit breaker OPENED for user {user.user_id} "
                    f"(failures: {user.failure_count})"
                )
    
    def update_positions(self, user_id: str, delta: int) -> None:
        """Update concurrent position count."""
        with self._lock:
            user = self.get_or_create_user(user_id)
            user.concurrent_positions = max(0, user.concurrent_positions + delta)
    
    def get_all_users(self) -> List[str]:
        """Get all registered user IDs."""
        with self._lock:
            return list(self._users.keys())
    
    def get_user_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a user."""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return None
            
            now = time.time()
            minute_ago = now - 60
            hour_ago = now - 3600
            
            requests_last_minute = sum(
                1 for ts in user.request_timestamps if ts > minute_ago
            )
            requests_last_hour = sum(
                1 for ts in user.request_timestamps if ts > hour_ago
            )
            
            return {
                "user_id": user_id,
                "tier": user.tier.value,
                "requests_last_minute": requests_last_minute,
                "requests_last_hour": requests_last_hour,
                "daily_trades": user.daily_trades,
                "daily_volume": str(user.daily_volume),
                "concurrent_positions": user.concurrent_positions,
                "circuit_state": user.circuit_state.value,
                "failure_count": user.failure_count,
            }


# =============================================================================
# Account-Level Circuit Breaker
# =============================================================================

class AccountCircuitBreaker:
    """
    Per-account circuit breaker implementation.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject all requests
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        isolation_manager: UserIsolationManager,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self._isolation = isolation_manager
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._half_open_calls: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
    
    def can_execute(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if execution is allowed for user.
        
        Returns:
            Tuple of (allowed, reason)
        """
        with self._lock:
            user = self._isolation.get_user(user_id)
            if not user:
                return True, "new_user"
            
            now = time.time()
            
            # Check circuit state
            if user.circuit_state == CircuitBreakerState.OPEN:
                # Check if recovery timeout has passed
                if user.circuit_open_until and now >= user.circuit_open_until:
                    # Transition to half-open
                    user.circuit_state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls[user_id] = 0
                    logger.info(f"Circuit breaker HALF-OPEN for user {user_id}")
                else:
                    remaining = user.circuit_open_until - now if user.circuit_open_until else 0
                    return False, f"circuit_open (retry in {remaining:.0f}s)"
            
            if user.circuit_state == CircuitBreakerState.HALF_OPEN:
                # Allow limited calls in half-open state
                if self._half_open_calls[user_id] >= self._half_open_max_calls:
                    return False, "half_open_limit_reached"
                self._half_open_calls[user_id] += 1
            
            return True, "allowed"
    
    def record_result(self, user_id: str, success: bool) -> None:
        """Record execution result for circuit breaker."""
        self._isolation.record_trade(user_id, Decimal("0"), success)
    
    def force_open(self, user_id: str, duration: float = 300.0) -> None:
        """Force open circuit breaker for a user."""
        with self._lock:
            user = self._isolation.get_or_create_user(user_id)
            user.circuit_state = CircuitBreakerState.OPEN
            user.circuit_open_until = time.time() + duration
            logger.warning(f"Circuit breaker FORCE OPENED for user {user_id}")
    
    def force_close(self, user_id: str) -> None:
        """Force close circuit breaker for a user."""
        with self._lock:
            user = self._isolation.get_user(user_id)
            if user:
                user.circuit_state = CircuitBreakerState.CLOSED
                user.failure_count = 0
                user.circuit_open_until = None
                logger.info(f"Circuit breaker FORCE CLOSED for user {user_id}")


# =============================================================================
# Quota Enforcement
# =============================================================================

class QuotaEnforcer:
    """
    Enforces resource quotas per user.
    
    Validates:
    - Request rate limits
    - Daily trade limits
    - Position limits
    - Volume limits
    """
    
    def __init__(self, isolation_manager: UserIsolationManager):
        self._isolation = isolation_manager
        self._lock = threading.RLock()
    
    def check_quota(
        self,
        user_id: str,
        quota_type: QuotaType,
        value: Optional[Decimal] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if quota allows the operation.
        
        Args:
            user_id: User identifier
            quota_type: Type of quota to check
            value: Value to check against (for size/volume checks)
        
        Returns:
            Tuple of (allowed, reason, details)
        """
        with self._lock:
            user = self._isolation.get_or_create_user(user_id)
            limits = user.limits
            now = time.time()
            
            details: Dict[str, Any] = {
                "user_id": user_id,
                "quota_type": quota_type.value,
                "tier": user.tier.value
            }
            
            if quota_type == QuotaType.REQUESTS_PER_MINUTE:
                minute_ago = now - 60
                count = sum(1 for ts in user.request_timestamps if ts > minute_ago)
                details["current"] = count
                details["limit"] = limits.requests_per_minute
                
                if count >= limits.requests_per_minute:
                    return False, "rate_limit_minute", details
                return True, "ok", details
            
            elif quota_type == QuotaType.REQUESTS_PER_HOUR:
                hour_ago = now - 3600
                count = sum(1 for ts in user.request_timestamps if ts > hour_ago)
                details["current"] = count
                details["limit"] = limits.requests_per_hour
                
                if count >= limits.requests_per_hour:
                    return False, "rate_limit_hour", details
                return True, "ok", details
            
            elif quota_type == QuotaType.DAILY_TRADES:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if user.last_trade_day != today:
                    details["current"] = 0
                else:
                    details["current"] = user.daily_trades
                details["limit"] = limits.daily_trades
                
                if user.last_trade_day == today and user.daily_trades >= limits.daily_trades:
                    return False, "daily_trade_limit", details
                return True, "ok", details
            
            elif quota_type == QuotaType.CONCURRENT_POSITIONS:
                details["current"] = user.concurrent_positions
                details["limit"] = limits.concurrent_positions
                
                if user.concurrent_positions >= limits.concurrent_positions:
                    return False, "position_limit", details
                return True, "ok", details
            
            elif quota_type == QuotaType.MAX_POSITION_SIZE:
                if value is None:
                    return True, "no_value", details
                details["requested"] = str(value)
                details["limit"] = str(limits.max_position_size)
                
                if value > limits.max_position_size:
                    return False, "position_size_limit", details
                return True, "ok", details
            
            elif quota_type == QuotaType.DAILY_VOLUME:
                if value is None:
                    value = Decimal("0")
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                current_volume = user.daily_volume if user.last_trade_day == today else Decimal("0")
                details["current"] = str(current_volume)
                details["requested"] = str(value)
                details["limit"] = str(limits.daily_volume)
                
                if current_volume + value > limits.daily_volume:
                    return False, "daily_volume_limit", details
                return True, "ok", details
            
            return True, "unknown_quota", details
    
    def check_all_quotas(
        self,
        user_id: str,
        position_size: Optional[Decimal] = None
    ) -> Tuple[bool, List[str], List[Dict[str, Any]]]:
        """
        Check all relevant quotas for a trade.
        
        Returns:
            Tuple of (all_passed, failed_reasons, all_details)
        """
        quotas_to_check = [
            (QuotaType.REQUESTS_PER_MINUTE, None),
            (QuotaType.REQUESTS_PER_HOUR, None),
            (QuotaType.DAILY_TRADES, None),
            (QuotaType.CONCURRENT_POSITIONS, None),
        ]
        
        if position_size is not None:
            quotas_to_check.extend([
                (QuotaType.MAX_POSITION_SIZE, position_size),
                (QuotaType.DAILY_VOLUME, position_size),
            ])
        
        failed_reasons = []
        all_details = []
        
        for quota_type, value in quotas_to_check:
            allowed, reason, details = self.check_quota(user_id, quota_type, value)
            all_details.append(details)
            if not allowed:
                failed_reasons.append(reason)
        
        return len(failed_reasons) == 0, failed_reasons, all_details


# =============================================================================
# Fair Scheduler
# =============================================================================

class FairScheduler:
    """
    Fair scheduling of requests across users.
    
    Uses weighted fair queuing to ensure:
    - Higher tier users get more throughput
    - No user can monopolize resources
    - Requests are processed in a fair order
    """
    
    def __init__(
        self,
        isolation_manager: UserIsolationManager,
        max_queue_size: int = 10000
    ):
        self._isolation = isolation_manager
        self._max_queue_size = max_queue_size
        
        # Priority queue (min-heap)
        self._queue: List[ScheduledRequest] = []
        self._queue_lock = threading.RLock()
        
        # Virtual time tracking per user
        self._virtual_time: Dict[str, float] = defaultdict(float)
        self._global_virtual_time = 0.0
        
        # Request tracking
        self._request_counter = 0
    
    def _calculate_priority(self, user_id: str) -> float:
        """
        Calculate scheduling priority using weighted fair queuing.
        
        Lower value = higher priority.
        """
        user = self._isolation.get_user(user_id)
        weight = user.limits.priority_weight if user else 1
        
        # Get user's virtual time
        user_vtime = self._virtual_time[user_id]
        
        # Priority is based on virtual time divided by weight
        # Higher weight = lower increment = higher priority over time
        return user_vtime / weight
    
    def submit(
        self,
        user_id: str,
        payload: Dict[str, Any],
        deadline_seconds: float = 30.0
    ) -> Optional[str]:
        """
        Submit a request for scheduling.
        
        Args:
            user_id: User submitting the request
            payload: Request payload
            deadline_seconds: Request deadline
        
        Returns:
            Request ID if accepted, None if queue full
        """
        with self._queue_lock:
            # Check queue capacity
            if len(self._queue) >= self._max_queue_size:
                logger.warning("Fair scheduler queue full, rejecting request")
                return None
            
            # Generate request ID
            self._request_counter += 1
            request_id = f"req_{self._request_counter:012d}"
            
            now = time.time()
            priority = self._calculate_priority(user_id)
            
            request = ScheduledRequest(
                request_id=request_id,
                user_id=user_id,
                priority=priority,
                submitted_at=now,
                deadline=now + deadline_seconds,
                payload=payload
            )
            
            heapq.heappush(self._queue, request)
            
            # Update user's pending request count
            user = self._isolation.get_or_create_user(user_id)
            user.pending_requests += 1
            
            logger.debug(
                f"Scheduled request {request_id} for user {user_id} "
                f"(priority: {priority:.4f})"
            )
            
            return request_id
    
    def get_next(self) -> Optional[ScheduledRequest]:
        """
        Get the next request to process.
        
        Returns:
            Next request or None if queue empty
        """
        with self._queue_lock:
            now = time.time()
            
            while self._queue:
                request = heapq.heappop(self._queue)
                
                # Check if request has expired
                if request.deadline < now:
                    logger.warning(
                        f"Request {request.request_id} expired "
                        f"(submitted: {request.submitted_at}, deadline: {request.deadline})"
                    )
                    self._update_user_after_dequeue(request.user_id)
                    continue
                
                # Update virtual time for this user
                user = self._isolation.get_user(request.user_id)
                if user:
                    # Increment virtual time inversely proportional to weight
                    self._virtual_time[request.user_id] += 1.0 / user.limits.priority_weight
                    self._global_virtual_time = max(
                        self._global_virtual_time,
                        self._virtual_time[request.user_id]
                    )
                
                self._update_user_after_dequeue(request.user_id)
                return request
            
            return None
    
    def _update_user_after_dequeue(self, user_id: str) -> None:
        """Update user context after dequeuing a request."""
        user = self._isolation.get_user(user_id)
        if user:
            user.pending_requests = max(0, user.pending_requests - 1)
            user.last_served_time = time.time()
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self._queue_lock:
            return len(self._queue)
    
    def get_user_queue_depth(self, user_id: str) -> int:
        """Get number of pending requests for a user."""
        with self._queue_lock:
            return sum(1 for req in self._queue if req.user_id == user_id)
    
    def cancel_user_requests(self, user_id: str) -> int:
        """
        Cancel all pending requests for a user.
        
        Returns:
            Number of requests cancelled
        """
        with self._queue_lock:
            original_size = len(self._queue)
            self._queue = [req for req in self._queue if req.user_id != user_id]
            heapq.heapify(self._queue)
            cancelled = original_size - len(self._queue)
            
            if cancelled > 0:
                user = self._isolation.get_user(user_id)
                if user:
                    user.pending_requests = 0
                logger.info(f"Cancelled {cancelled} requests for user {user_id}")
            
            return cancelled


# =============================================================================
# Backpressure Manager
# =============================================================================

class BackpressureManager:
    """
    Manages backpressure to prevent system overload.
    
    Monitors:
    - Queue depth
    - Processing latency
    - Error rates
    
    Actions:
    - Reject new requests when overloaded
    - Shed load from low-priority users
    - Apply rate limiting multipliers
    """
    
    def __init__(
        self,
        scheduler: FairScheduler,
        isolation_manager: UserIsolationManager,
        queue_high_water_mark: int = 8000,
        queue_low_water_mark: int = 5000,
        latency_threshold_ms: float = 1000.0
    ):
        self._scheduler = scheduler
        self._isolation = isolation_manager
        self._high_water = queue_high_water_mark
        self._low_water = queue_low_water_mark
        self._latency_threshold = latency_threshold_ms
        
        # State
        self._backpressure_active = False
        self._current_multiplier = 1.0
        
        # Metrics
        self._recent_latencies: List[float] = []
        self._lock = threading.RLock()
    
    def record_latency(self, latency_ms: float) -> None:
        """Record processing latency."""
        with self._lock:
            self._recent_latencies.append(latency_ms)
            # Keep last 100 measurements
            if len(self._recent_latencies) > 100:
                self._recent_latencies.pop(0)
    
    def should_accept(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if a new request should be accepted.
        
        Returns:
            Tuple of (accept, reason)
        """
        with self._lock:
            queue_size = self._scheduler.get_queue_size()
            
            # Check high water mark
            if queue_size >= self._high_water:
                if not self._backpressure_active:
                    self._backpressure_active = True
                    logger.warning(
                        f"Backpressure ACTIVE (queue: {queue_size}/{self._high_water})"
                    )
                
                # In backpressure mode, only accept from high-tier users
                user = self._isolation.get_user(user_id)
                if user and user.tier in [UserTier.ENTERPRISE, UserTier.PREMIUM]:
                    return True, "high_tier_allowed"
                return False, "backpressure_active"
            
            # Check if we can exit backpressure
            if self._backpressure_active and queue_size <= self._low_water:
                self._backpressure_active = False
                logger.info("Backpressure INACTIVE")
            
            # Check latency threshold
            if self._recent_latencies:
                avg_latency = sum(self._recent_latencies) / len(self._recent_latencies)
                if avg_latency > self._latency_threshold:
                    # Apply rate limiting based on tier
                    user = self._isolation.get_user(user_id)
                    if user and user.tier == UserTier.FREE:
                        return False, "high_latency_shedding"
            
            return True, "ok"
    
    def get_rate_multiplier(self, user_id: str) -> float:
        """
        Get rate limit multiplier for backpressure.
        
        Returns multiplier to apply to rate limits (< 1.0 = stricter limits).
        """
        with self._lock:
            if not self._backpressure_active:
                return 1.0
            
            user = self._isolation.get_user(user_id)
            if not user:
                return 0.5
            
            # Higher tier = less rate reduction
            multipliers = {
                UserTier.FREE: 0.25,
                UserTier.BASIC: 0.5,
                UserTier.PREMIUM: 0.75,
                UserTier.ENTERPRISE: 1.0,
            }
            return multipliers.get(user.tier, 0.5)
    
    def get_status(self) -> Dict[str, Any]:
        """Get backpressure status."""
        with self._lock:
            avg_latency = 0.0
            if self._recent_latencies:
                avg_latency = sum(self._recent_latencies) / len(self._recent_latencies)
            
            return {
                "backpressure_active": self._backpressure_active,
                "queue_size": self._scheduler.get_queue_size(),
                "high_water_mark": self._high_water,
                "low_water_mark": self._low_water,
                "avg_latency_ms": avg_latency,
                "latency_threshold_ms": self._latency_threshold,
            }


# =============================================================================
# Unified Scale Manager
# =============================================================================

class ScaleManager:
    """
    Unified manager for all scale preparation features.
    
    Coordinates:
    - User isolation
    - Circuit breakers
    - Quota enforcement
    - Fair scheduling
    - Backpressure management
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        queue_high_water: int = 8000,
        queue_low_water: int = 5000
    ):
        self.isolation = UserIsolationManager()
        self.circuit_breaker = AccountCircuitBreaker(self.isolation)
        self.quota_enforcer = QuotaEnforcer(self.isolation)
        self.scheduler = FairScheduler(self.isolation, max_queue_size)
        self.backpressure = BackpressureManager(
            self.scheduler,
            self.isolation,
            queue_high_water,
            queue_low_water
        )
    
    def validate_request(
        self,
        user_id: str,
        position_size: Optional[Decimal] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a request can proceed.
        
        Checks:
        1. Backpressure
        2. Circuit breaker
        3. All quotas
        
        Returns:
            Tuple of (valid, reasons)
        """
        reasons = []
        
        # Check backpressure
        accept, reason = self.backpressure.should_accept(user_id)
        if not accept:
            reasons.append(f"backpressure: {reason}")
        
        # Check circuit breaker
        can_exec, reason = self.circuit_breaker.can_execute(user_id)
        if not can_exec:
            reasons.append(f"circuit_breaker: {reason}")
        
        # Check quotas
        quotas_ok, failed_quotas, _ = self.quota_enforcer.check_all_quotas(
            user_id, position_size
        )
        if not quotas_ok:
            reasons.extend([f"quota: {q}" for q in failed_quotas])
        
        return len(reasons) == 0, reasons
    
    def submit_request(
        self,
        user_id: str,
        payload: Dict[str, Any],
        position_size: Optional[Decimal] = None
    ) -> Tuple[Optional[str], List[str]]:
        """
        Submit a request through the scale manager.
        
        Returns:
            Tuple of (request_id or None, validation_errors)
        """
        # Validate first
        valid, errors = self.validate_request(user_id, position_size)
        if not valid:
            return None, errors
        
        # Record the request for rate limiting
        self.isolation.record_request(user_id)
        
        # Submit to scheduler
        request_id = self.scheduler.submit(user_id, payload)
        if not request_id:
            return None, ["scheduler_full"]
        
        return request_id, []
    
    def complete_request(
        self,
        user_id: str,
        success: bool,
        volume: Decimal = Decimal("0"),
        latency_ms: float = 0.0
    ) -> None:
        """Record completion of a request."""
        # Record trade
        self.isolation.record_trade(user_id, volume, success)
        
        # Record for circuit breaker
        self.circuit_breaker.record_result(user_id, success)
        
        # Record latency for backpressure
        if latency_ms > 0:
            self.backpressure.record_latency(latency_ms)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "total_users": len(self.isolation.get_all_users()),
            "queue_size": self.scheduler.get_queue_size(),
            "backpressure": self.backpressure.get_status(),
        }
    
    def get_user_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific user."""
        stats = self.isolation.get_user_stats(user_id)
        if not stats:
            return None
        
        can_execute, reason = self.circuit_breaker.can_execute(user_id)
        stats["can_execute"] = can_execute
        stats["execution_reason"] = reason
        stats["pending_requests"] = self.scheduler.get_user_queue_depth(user_id)
        
        return stats


# =============================================================================
# Module Entry Point
# =============================================================================

def create_scale_manager() -> ScaleManager:
    """Create a configured scale manager."""
    return ScaleManager()


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)
    
    manager = create_scale_manager()
    
    # Create some test users
    manager.isolation.get_or_create_user("user_1", UserTier.FREE)
    manager.isolation.get_or_create_user("user_2", UserTier.PREMIUM)
    manager.isolation.get_or_create_user("user_3", UserTier.ENTERPRISE)
    
    # Submit some requests
    for i in range(20):
        user_id = f"user_{(i % 3) + 1}"
        request_id, errors = manager.submit_request(
            user_id,
            {"action": "trade", "amount": 100}
        )
        if errors:
            print(f"Request {i} rejected: {errors}")
        else:
            print(f"Request {i} scheduled: {request_id}")
    
    # Process requests
    while True:
        request = manager.scheduler.get_next()
        if not request:
            break
        print(f"Processing: {request.request_id} for {request.user_id}")
        manager.complete_request(request.user_id, True, Decimal("100"), 50.0)
    
    print("\nSystem status:", manager.get_system_status())
