#!/usr/bin/env python3
"""
VEL Backpressure & Capacity Management
=======================================

Production-grade capacity management and backpressure control.

Features:
- Queue backpressure behavior (reject intake when overloaded)
- Tenant-level fairness enforcement
- Wallet-level serialization under concurrency
- Rate limiting per tenant/wallet

Rules:
- Overload must slow or reject intake, not compromise execution safety
- No cross-tenant interference
- All rejections are logged with reason

NO SILENT FAILURES - System fails closed under overload.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class BackpressureState(Enum):
    """System backpressure state."""
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"
    REJECTING = "rejecting"


class RejectionReason(Enum):
    """Intent rejection reasons."""
    QUEUE_FULL = "queue_full"
    RATE_LIMITED = "rate_limited"
    TENANT_QUOTA_EXCEEDED = "tenant_quota_exceeded"
    WALLET_BUSY = "wallet_busy"
    SYSTEM_OVERLOAD = "system_overload"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class BackpressureConfig:
    """Backpressure configuration."""
    # Global queue limits
    max_pending_intents: int = 1000
    max_executing_intents: int = 100
    
    # Backpressure thresholds (percentage of max)
    elevated_threshold: float = 0.6  # 60%
    high_threshold: float = 0.8      # 80%
    critical_threshold: float = 0.95  # 95%
    
    # Rate limiting (requests per minute)
    global_rate_limit: int = 1000
    tenant_rate_limit: int = 100
    wallet_rate_limit: int = 10
    
    # Tenant quotas
    max_pending_per_tenant: int = 100
    max_executing_per_tenant: int = 10
    
    # Wallet concurrency
    max_concurrent_per_wallet: int = 1  # Serialize wallet operations
    
    # Time windows
    rate_limit_window_seconds: int = 60
    
    # Rejection history
    max_rejection_history: int = 1000
    
    # Rejection behavior
    reject_on_critical: bool = True


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""
    capacity: int
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens consumed successfully
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    def _refill(self):
        """Refill bucket based on time elapsed."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_refill).total_seconds()
        
        refill_amount = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + refill_amount)
        self.last_refill = now
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time in seconds until tokens available."""
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


@dataclass
class TenantQuota:
    """Per-tenant quota tracking."""
    tenant_id: str
    pending_count: int = 0
    executing_count: int = 0
    total_processed: int = 0
    total_rejected: int = 0
    last_request_at: Optional[datetime] = None


@dataclass
class WalletLock:
    """Per-wallet execution lock."""
    wallet_address: str
    locked: bool = False
    executing_intent_id: Optional[str] = None
    locked_at: Optional[datetime] = None
    lock_owner: Optional[str] = None  # Thread ID


@dataclass
class IntentRejection:
    """Intent rejection record."""
    intent_id: str
    tenant_id: str
    wallet_address: str
    reason: RejectionReason
    backpressure_state: BackpressureState
    rejected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[str] = None


class BackpressureManager:
    """
    Backpressure and capacity management engine.
    
    Enforces:
    - Global queue capacity limits
    - Per-tenant fairness
    - Per-wallet serialization
    - Rate limiting at multiple levels
    
    Fails closed under overload to protect execution safety.
    """
    
    def __init__(self, config: Optional[BackpressureConfig] = None):
        """
        Initialize backpressure manager.
        
        Args:
            config: Backpressure configuration
        """
        self.config = config or BackpressureConfig()
        self._lock = threading.Lock()
        
        # Queue tracking
        self._pending_intents: Set[str] = set()
        self._executing_intents: Set[str] = set()
        
        # Tenant tracking
        self._tenant_quotas: Dict[str, TenantQuota] = {}
        self._intent_to_tenant: Dict[str, str] = {}
        
        # Wallet locks
        self._wallet_locks: Dict[str, WalletLock] = {}
        self._wallet_queue: Dict[str, deque] = defaultdict(deque)
        
        # Rate limiting
        self._global_rate_bucket = RateLimitBucket(
            capacity=self.config.global_rate_limit,
            tokens=self.config.global_rate_limit,
            refill_rate=self.config.global_rate_limit / self.config.rate_limit_window_seconds
        )
        
        self._tenant_rate_buckets: Dict[str, RateLimitBucket] = {}
        self._wallet_rate_buckets: Dict[str, RateLimitBucket] = {}
        
        # Rejection tracking
        self._recent_rejections: deque = deque(maxlen=self.config.max_rejection_history)
        
        # Statistics
        self._total_accepted = 0
        self._total_rejected = 0
        
        logger.info(
            "Backpressure manager initialized",
            extra={
                "max_pending": self.config.max_pending_intents,
                "max_executing": self.config.max_executing_intents,
                "tenant_rate_limit": self.config.tenant_rate_limit,
                "wallet_rate_limit": self.config.wallet_rate_limit
            }
        )
    
    def check_can_accept_intent(
        self,
        intent_id: str,
        tenant_id: str,
        wallet_address: str
    ) -> tuple[bool, Optional[RejectionReason], Optional[str]]:
        """
        Check if intent can be accepted for processing.
        
        Performs all capacity, quota, and rate limit checks.
        
        Args:
            intent_id: Intent identifier
            tenant_id: Tenant identifier
            wallet_address: Wallet address
            
        Returns:
            (can_accept, rejection_reason, details)
        """
        with self._lock:
            # Check 1: Global rate limit
            if not self._global_rate_bucket.consume():
                wait_time = self._global_rate_bucket.get_wait_time()
                logger.warning(
                    f"Global rate limit exceeded, retry in {wait_time:.1f}s",
                    extra={
                        "intent_id": intent_id,
                        "wait_time": wait_time
                    }
                )
                return False, RejectionReason.RATE_LIMITED, f"Global rate limit, retry in {wait_time:.1f}s"
            
            # Check 2: Tenant rate limit
            if not self._check_tenant_rate_limit(tenant_id):
                bucket = self._tenant_rate_buckets.get(tenant_id)
                wait_time = bucket.get_wait_time() if bucket else 0
                logger.warning(
                    f"Tenant {tenant_id} rate limit exceeded",
                    extra={
                        "intent_id": intent_id,
                        "tenant_id": tenant_id,
                        "wait_time": wait_time
                    }
                )
                return False, RejectionReason.RATE_LIMITED, f"Tenant rate limit, retry in {wait_time:.1f}s"
            
            # Check 3: Wallet rate limit
            if not self._check_wallet_rate_limit(wallet_address):
                bucket = self._wallet_rate_buckets.get(wallet_address)
                wait_time = bucket.get_wait_time() if bucket else 0
                logger.warning(
                    f"Wallet {wallet_address} rate limit exceeded",
                    extra={
                        "intent_id": intent_id,
                        "wallet_address": wallet_address,
                        "wait_time": wait_time
                    }
                )
                return False, RejectionReason.RATE_LIMITED, f"Wallet rate limit, retry in {wait_time:.1f}s"
            
            # Check 4: Global queue capacity
            backpressure_state = self._get_backpressure_state()
            
            if backpressure_state == BackpressureState.CRITICAL and self.config.reject_on_critical:
                logger.warning(
                    "System in critical backpressure state, rejecting intent",
                    extra={
                        "intent_id": intent_id,
                        "pending": len(self._pending_intents),
                        "executing": len(self._executing_intents)
                    }
                )
                return False, RejectionReason.SYSTEM_OVERLOAD, "System overloaded"
            
            if len(self._pending_intents) >= self.config.max_pending_intents:
                logger.warning(
                    "Pending queue full, rejecting intent",
                    extra={
                        "intent_id": intent_id,
                        "pending": len(self._pending_intents),
                        "max": self.config.max_pending_intents
                    }
                )
                return False, RejectionReason.QUEUE_FULL, "Pending queue full"
            
            # Check 5: Tenant quota
            tenant_quota = self._get_or_create_tenant_quota(tenant_id)
            
            if tenant_quota.pending_count >= self.config.max_pending_per_tenant:
                logger.warning(
                    f"Tenant {tenant_id} pending quota exceeded",
                    extra={
                        "intent_id": intent_id,
                        "tenant_id": tenant_id,
                        "pending": tenant_quota.pending_count,
                        "max": self.config.max_pending_per_tenant
                    }
                )
                return False, RejectionReason.TENANT_QUOTA_EXCEEDED, "Tenant pending quota exceeded"
            
            if tenant_quota.executing_count >= self.config.max_executing_per_tenant:
                logger.warning(
                    f"Tenant {tenant_id} executing quota exceeded",
                    extra={
                        "intent_id": intent_id,
                        "tenant_id": tenant_id,
                        "executing": tenant_quota.executing_count,
                        "max": self.config.max_executing_per_tenant
                    }
                )
                return False, RejectionReason.TENANT_QUOTA_EXCEEDED, "Tenant executing quota exceeded"
            
            # Check 6: Wallet concurrency
            wallet_lock = self._wallet_locks.get(wallet_address)
            if wallet_lock and wallet_lock.locked:
                concurrent_count = len(self._wallet_queue.get(wallet_address, []))
                if concurrent_count >= self.config.max_concurrent_per_wallet:
                    logger.warning(
                        f"Wallet {wallet_address} concurrency limit exceeded",
                        extra={
                            "intent_id": intent_id,
                            "wallet_address": wallet_address,
                            "concurrent": concurrent_count
                        }
                    )
                    return False, RejectionReason.WALLET_BUSY, "Wallet concurrency limit exceeded"
            
            # All checks passed
            return True, None, None
    
    def accept_intent(
        self,
        intent_id: str,
        tenant_id: str,
        wallet_address: str
    ) -> bool:
        """
        Accept intent for processing.
        
        Args:
            intent_id: Intent identifier
            tenant_id: Tenant identifier
            wallet_address: Wallet address
            
        Returns:
            True if accepted
        """
        can_accept, reason, details = self.check_can_accept_intent(
            intent_id, tenant_id, wallet_address
        )
        
        if not can_accept:
            self._record_rejection(intent_id, tenant_id, wallet_address, reason, details)
            return False
        
        with self._lock:
            # Add to pending queue
            self._pending_intents.add(intent_id)
            self._intent_to_tenant[intent_id] = tenant_id
            
            # Update tenant quota
            tenant_quota = self._get_or_create_tenant_quota(tenant_id)
            tenant_quota.pending_count += 1
            tenant_quota.last_request_at = datetime.now(timezone.utc)
            
            # Add to wallet queue
            self._wallet_queue[wallet_address].append(intent_id)
            
            self._total_accepted += 1
        
        logger.info(
            f"Intent accepted: {intent_id}",
            extra={
                "intent_id": intent_id,
                "tenant_id": tenant_id,
                "wallet_address": wallet_address,
                "pending_queue_size": len(self._pending_intents),
                "backpressure_state": self._get_backpressure_state().value
            }
        )
        
        return True
    
    def start_execution(
        self,
        intent_id: str,
        wallet_address: str
    ) -> bool:
        """
        Mark intent as starting execution.
        
        Args:
            intent_id: Intent identifier
            wallet_address: Wallet address
            
        Returns:
            True if execution started
        """
        with self._lock:
            if intent_id not in self._pending_intents:
                logger.error(f"Intent {intent_id} not in pending queue")
                return False
            
            # Check wallet lock
            wallet_lock = self._wallet_locks.get(wallet_address)
            if wallet_lock and wallet_lock.locked:
                # Wallet busy with another intent
                logger.debug(f"Wallet {wallet_address} locked by {wallet_lock.executing_intent_id}")
                return False
            
            # Acquire wallet lock
            if wallet_address not in self._wallet_locks:
                self._wallet_locks[wallet_address] = WalletLock(wallet_address=wallet_address)
            
            lock = self._wallet_locks[wallet_address]
            lock.locked = True
            lock.executing_intent_id = intent_id
            lock.locked_at = datetime.now(timezone.utc)
            lock.lock_owner = str(threading.get_ident())
            
            # Move from pending to executing
            self._pending_intents.remove(intent_id)
            self._executing_intents.add(intent_id)
            
            # Update tenant quota
            tenant_id = self._intent_to_tenant.get(intent_id)
            if tenant_id:
                tenant_quota = self._tenant_quotas.get(tenant_id)
                if tenant_quota:
                    tenant_quota.pending_count -= 1
                    tenant_quota.executing_count += 1
            
            # Remove from wallet queue
            wallet_queue = self._wallet_queue.get(wallet_address)
            if wallet_queue and intent_id in wallet_queue:
                wallet_queue.remove(intent_id)
        
        logger.info(
            f"Intent execution started: {intent_id}",
            extra={
                "intent_id": intent_id,
                "wallet_address": wallet_address,
                "executing_count": len(self._executing_intents)
            }
        )
        
        return True
    
    def complete_execution(
        self,
        intent_id: str,
        wallet_address: str,
        success: bool
    ):
        """
        Mark intent execution as complete.
        
        Args:
            intent_id: Intent identifier
            wallet_address: Wallet address
            success: Whether execution succeeded
        """
        with self._lock:
            if intent_id not in self._executing_intents:
                logger.warning(f"Intent {intent_id} not in executing queue")
                return
            
            # Remove from executing
            self._executing_intents.remove(intent_id)
            
            # Update tenant quota
            tenant_id = self._intent_to_tenant.get(intent_id)
            if tenant_id:
                tenant_quota = self._tenant_quotas.get(tenant_id)
                if tenant_quota:
                    tenant_quota.executing_count -= 1
                    tenant_quota.total_processed += 1
                
                # Clean up mapping
                del self._intent_to_tenant[intent_id]
            
            # Release wallet lock
            wallet_lock = self._wallet_locks.get(wallet_address)
            if wallet_lock and wallet_lock.executing_intent_id == intent_id:
                wallet_lock.locked = False
                wallet_lock.executing_intent_id = None
                wallet_lock.locked_at = None
                wallet_lock.lock_owner = None
        
        logger.info(
            f"Intent execution completed: {intent_id}, success={success}",
            extra={
                "intent_id": intent_id,
                "wallet_address": wallet_address,
                "success": success,
                "executing_count": len(self._executing_intents)
            }
        )
    
    def _check_tenant_rate_limit(self, tenant_id: str) -> bool:
        """Check tenant rate limit."""
        if tenant_id not in self._tenant_rate_buckets:
            self._tenant_rate_buckets[tenant_id] = RateLimitBucket(
                capacity=self.config.tenant_rate_limit,
                tokens=self.config.tenant_rate_limit,
                refill_rate=self.config.tenant_rate_limit / self.config.rate_limit_window_seconds
            )
        
        return self._tenant_rate_buckets[tenant_id].consume()
    
    def _check_wallet_rate_limit(self, wallet_address: str) -> bool:
        """Check wallet rate limit."""
        if wallet_address not in self._wallet_rate_buckets:
            self._wallet_rate_buckets[wallet_address] = RateLimitBucket(
                capacity=self.config.wallet_rate_limit,
                tokens=self.config.wallet_rate_limit,
                refill_rate=self.config.wallet_rate_limit / self.config.rate_limit_window_seconds
            )
        
        return self._wallet_rate_buckets[wallet_address].consume()
    
    def _get_or_create_tenant_quota(self, tenant_id: str) -> TenantQuota:
        """Get or create tenant quota."""
        if tenant_id not in self._tenant_quotas:
            self._tenant_quotas[tenant_id] = TenantQuota(tenant_id=tenant_id)
        
        return self._tenant_quotas[tenant_id]
    
    def _get_backpressure_state(self) -> BackpressureState:
        """Calculate current backpressure state."""
        pending_ratio = len(self._pending_intents) / self.config.max_pending_intents
        executing_ratio = len(self._executing_intents) / self.config.max_executing_intents
        
        max_ratio = max(pending_ratio, executing_ratio)
        
        if max_ratio >= 1.0:
            return BackpressureState.REJECTING
        elif max_ratio >= self.config.critical_threshold:
            return BackpressureState.CRITICAL
        elif max_ratio >= self.config.high_threshold:
            return BackpressureState.HIGH
        elif max_ratio >= self.config.elevated_threshold:
            return BackpressureState.ELEVATED
        else:
            return BackpressureState.NORMAL
    
    def _record_rejection(
        self,
        intent_id: str,
        tenant_id: str,
        wallet_address: str,
        reason: RejectionReason,
        details: Optional[str]
    ):
        """Record intent rejection."""
        rejection = IntentRejection(
            intent_id=intent_id,
            tenant_id=tenant_id,
            wallet_address=wallet_address,
            reason=reason,
            backpressure_state=self._get_backpressure_state(),
            details=details
        )
        
        with self._lock:
            self._recent_rejections.append(rejection)
            self._total_rejected += 1
            
            # Update tenant stats
            tenant_quota = self._get_or_create_tenant_quota(tenant_id)
            tenant_quota.total_rejected += 1
        
        logger.warning(
            f"Intent rejected: {intent_id}, reason={reason.value}",
            extra={
                "intent_id": intent_id,
                "tenant_id": tenant_id,
                "wallet_address": wallet_address,
                "reason": reason.value,
                "details": details,
                "backpressure_state": rejection.backpressure_state.value
            }
        )
    
    def get_backpressure_state(self) -> BackpressureState:
        """Get current backpressure state."""
        with self._lock:
            return self._get_backpressure_state()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get backpressure statistics."""
        with self._lock:
            backpressure_state = self._get_backpressure_state()
            
            rejection_counts = defaultdict(int)
            for rejection in self._recent_rejections:
                rejection_counts[rejection.reason.value] += 1
            
            return {
                "backpressure_state": backpressure_state.value,
                "pending_intents": len(self._pending_intents),
                "executing_intents": len(self._executing_intents),
                "max_pending": self.config.max_pending_intents,
                "max_executing": self.config.max_executing_intents,
                "pending_utilization": len(self._pending_intents) / max(1, self.config.max_pending_intents),
                "executing_utilization": len(self._executing_intents) / max(1, self.config.max_executing_intents),
                "total_accepted": self._total_accepted,
                "total_rejected": self._total_rejected,
                "rejection_rate": self._total_rejected / max(1, self._total_accepted + self._total_rejected),
                "rejection_reasons": dict(rejection_counts),
                "active_tenants": len(self._tenant_quotas),
                "locked_wallets": sum(1 for lock in self._wallet_locks.values() if lock.locked)
            }
    
    def get_tenant_stats(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for specific tenant."""
        with self._lock:
            quota = self._tenant_quotas.get(tenant_id)
            if not quota:
                return None
            
            return {
                "tenant_id": tenant_id,
                "pending_count": quota.pending_count,
                "executing_count": quota.executing_count,
                "total_processed": quota.total_processed,
                "total_rejected": quota.total_rejected,
                "last_request_at": quota.last_request_at.isoformat() if quota.last_request_at else None
            }
