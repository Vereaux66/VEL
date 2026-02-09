#!/usr/bin/env python3
"""
VEL Distributed Locking & Idempotency Engine
=============================================

Production-grade distributed locking and idempotency guarantees for
multi-user trading operations.

Features:
- Redis-backed distributed locks
- Deadlock detection and prevention
- Idempotency key tracking
- Transaction deduplication
- Lock timeout and auto-release
- Crash recovery

CRITICAL: No trading operation can proceed without acquiring appropriate locks.
"""

import hashlib
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("vel.execution.locks")


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class LockConfig:
    """Distributed lock configuration."""
    # Lock timeouts
    default_lock_timeout_seconds: int = 30
    max_lock_timeout_seconds: int = 300
    lock_extension_seconds: int = 10
    
    # Retry configuration
    max_acquire_attempts: int = 10
    acquire_retry_delay_ms: int = 100
    
    # Deadlock detection
    deadlock_detection_enabled: bool = True
    deadlock_timeout_seconds: int = 60
    
    # Redis configuration
    redis_key_prefix: str = "vel:lock:"
    
    # Cleanup
    stale_lock_threshold_seconds: int = 600


# =============================================================================
# Lock Types
# =============================================================================

class LockType:
    """Lock type identifiers for different resources."""
    WALLET = "wallet"           # Per-wallet lock for balance operations
    NONCE = "nonce"             # Per-chain nonce lock
    TRANSACTION = "tx"          # Per-transaction lock
    POSITION = "position"       # Per-position lock
    USER = "user"               # Per-user lock
    GLOBAL = "global"           # System-wide lock (use sparingly)


# =============================================================================
# Distributed Lock Implementation
# =============================================================================

@dataclass
class LockInfo:
    """Information about an acquired lock."""
    lock_id: str
    lock_key: str
    owner_id: str
    acquired_at: float
    expires_at: float
    lock_type: str
    resource_id: str


class DistributedLockManager:
    """
    Redis-backed distributed lock manager.
    
    Implements:
    - Exclusive locks for critical sections
    - Lock timeouts with automatic expiration
    - Owner tracking for debugging
    - Deadlock detection
    - Lock extension (heartbeat)
    
    Thread-safe for use across multiple workers.
    """
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        config: Optional[LockConfig] = None
    ):
        self.config = config or LockConfig()
        self.redis = redis_client
        self._owner_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        
        # In-memory fallback (for testing/single-node)
        self._local_locks: Dict[str, LockInfo] = {}
        self._local_lock = threading.Lock()
        
        # Track locks held by this instance
        self._held_locks: Dict[str, LockInfo] = {}
        
        # Lock acquisition order for deadlock detection
        self._lock_order: Dict[str, List[str]] = {}
        
        logger.info(f"Lock manager initialized with owner_id: {self._owner_id}")
    
    def _get_lock_key(self, lock_type: str, resource_id: str) -> str:
        """Generate lock key for resource."""
        return f"{self.config.redis_key_prefix}{lock_type}:{resource_id}"
    
    def acquire(
        self,
        lock_type: str,
        resource_id: str,
        timeout_seconds: Optional[int] = None,
        blocking: bool = True
    ) -> Optional[LockInfo]:
        """
        Acquire a distributed lock.
        
        Args:
            lock_type: Type of lock (see LockType)
            resource_id: ID of resource to lock
            timeout_seconds: Lock timeout (auto-release after)
            blocking: If True, wait for lock; if False, return immediately
            
        Returns:
            LockInfo if acquired, None if failed
        """
        timeout = timeout_seconds or self.config.default_lock_timeout_seconds
        timeout = min(timeout, self.config.max_lock_timeout_seconds)
        
        lock_key = self._get_lock_key(lock_type, resource_id)
        lock_id = f"{self._owner_id}:{uuid.uuid4().hex[:12]}"
        
        # Check for potential deadlock
        if self.config.deadlock_detection_enabled:
            if self._would_cause_deadlock(lock_key):
                logger.error(f"Potential deadlock detected for {lock_key}")
                return None
        
        attempts = 0
        max_attempts = self.config.max_acquire_attempts if blocking else 1
        
        while attempts < max_attempts:
            if self._try_acquire_lock(lock_key, lock_id, timeout):
                now = time.time()
                lock_info = LockInfo(
                    lock_id=lock_id,
                    lock_key=lock_key,
                    owner_id=self._owner_id,
                    acquired_at=now,
                    expires_at=now + timeout,
                    lock_type=lock_type,
                    resource_id=resource_id
                )
                
                self._held_locks[lock_key] = lock_info
                self._record_lock_order(lock_key)
                
                logger.debug(f"Lock acquired: {lock_key} (id={lock_id})")
                return lock_info
            
            attempts += 1
            if blocking and attempts < max_attempts:
                time.sleep(self.config.acquire_retry_delay_ms / 1000.0)
        
        logger.warning(f"Failed to acquire lock: {lock_key} after {attempts} attempts")
        return None
    
    def _try_acquire_lock(self, lock_key: str, lock_id: str, timeout: int) -> bool:
        """Try to acquire lock once."""
        now = time.time()
        expires_at = now + timeout
        
        if self.redis:
            # Redis-based lock using SET NX with expiry
            try:
                result = self.redis.set(
                    lock_key,
                    lock_id,
                    nx=True,
                    ex=timeout
                )
                return result is True
            except Exception as e:
                logger.error(f"Redis lock error: {e}")
                # Fall through to local lock
        
        # Local lock fallback
        with self._local_lock:
            if lock_key in self._local_locks:
                existing = self._local_locks[lock_key]
                if now > existing.expires_at:
                    # Lock expired, we can take it
                    pass
                else:
                    return False
            
            self._local_locks[lock_key] = LockInfo(
                lock_id=lock_id,
                lock_key=lock_key,
                owner_id=self._owner_id,
                acquired_at=now,
                expires_at=expires_at,
                lock_type="",
                resource_id=""
            )
            return True
    
    def release(self, lock_info: LockInfo) -> bool:
        """
        Release a previously acquired lock.
        
        Args:
            lock_info: LockInfo from acquire()
            
        Returns:
            True if released successfully
        """
        lock_key = lock_info.lock_key
        lock_id = lock_info.lock_id
        
        if self.redis:
            # Use Lua script for atomic check-and-delete
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            try:
                result = self.redis.eval(lua_script, 1, lock_key, lock_id)
                success = result == 1
            except Exception as e:
                logger.error(f"Redis unlock error: {e}")
                success = False
        else:
            # Local lock fallback
            with self._local_lock:
                if lock_key in self._local_locks:
                    if self._local_locks[lock_key].lock_id == lock_id:
                        del self._local_locks[lock_key]
                        success = True
                    else:
                        success = False
                else:
                    success = False
        
        if success:
            self._held_locks.pop(lock_key, None)
            self._clear_lock_order(lock_key)
            logger.debug(f"Lock released: {lock_key}")
        else:
            logger.warning(f"Failed to release lock: {lock_key}")
        
        return success
    
    def extend(self, lock_info: LockInfo, extension_seconds: Optional[int] = None) -> bool:
        """
        Extend lock timeout (heartbeat).
        
        Use this for long-running operations to prevent timeout.
        """
        extension = extension_seconds or self.config.lock_extension_seconds
        lock_key = lock_info.lock_key
        lock_id = lock_info.lock_id
        
        if self.redis:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """
            try:
                result = self.redis.eval(lua_script, 1, lock_key, lock_id, extension)
                if result == 1:
                    lock_info.expires_at = time.time() + extension
                    return True
            except Exception as e:
                logger.error(f"Redis lock extend error: {e}")
        else:
            with self._local_lock:
                if lock_key in self._local_locks:
                    if self._local_locks[lock_key].lock_id == lock_id:
                        self._local_locks[lock_key].expires_at = time.time() + extension
                        lock_info.expires_at = self._local_locks[lock_key].expires_at
                        return True
        
        return False
    
    @contextmanager
    def lock(
        self,
        lock_type: str,
        resource_id: str,
        timeout_seconds: Optional[int] = None
    ):
        """
        Context manager for lock acquisition.
        
        Usage:
            with lock_manager.lock(LockType.WALLET, wallet_address):
                # Critical section
                pass
        """
        lock_info = self.acquire(lock_type, resource_id, timeout_seconds)
        if not lock_info:
            raise LockAcquisitionError(f"Failed to acquire lock: {lock_type}:{resource_id}")
        
        try:
            yield lock_info
        finally:
            self.release(lock_info)
    
    def _would_cause_deadlock(self, new_lock_key: str) -> bool:
        """
        Check if acquiring this lock would cause a deadlock.

        This implementation builds a simple lock dependency graph based on
        observed lock acquisition order across all owners in this process.

        - When an owner acquires lock B while already holding lock A, we record
          a dependency edge A -> B.
        - Before allowing the current owner to acquire `new_lock_key`, we
          check whether there is any path from `new_lock_key` back to any
          lock the owner already holds. If so, adding edges from those held
          locks to `new_lock_key` would introduce a cycle and we report a
          potential deadlock.

        Note: This is a best-effort, in-process detector. Full distributed
        deadlock detection would require coordination across processes and
        is beyond the scope of this module.
        """
        # Lazy initialization in case attributes were not set up in __init__
        if not hasattr(self, "_lock_order"):
            self._lock_order: Dict[str, List[str]] = {}
        if not hasattr(self, "_lock_dependency_graph"):
            # Maps from_lock_key -> set of to_lock_keys
            self._lock_dependency_graph: Dict[str, Set[str]] = {}

        # If the current owner holds no locks, acquiring a new one cannot
        # introduce a cycle.
        current_locks = self._lock_order.get(self._owner_id, [])
        if not current_locks:
            return False

        dependency_graph = self._lock_dependency_graph

        # Depth-first search to see if `start` can reach any lock in `targets`.
        def _can_reach_any(start: str, targets: Set[str]) -> bool:
            if start in targets:
                return True
            visited: Set[str] = set()
            stack = [start]
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                if node in targets:
                    return True
                for neighbor in dependency_graph.get(node, ()):
                    if neighbor not in visited:
                        stack.append(neighbor)
            return False

        # Treat each currently held lock as if it would gain an edge to
        # `new_lock_key`. If `new_lock_key` can already reach any of those
        # locks via existing dependencies, adding such an edge would create
        # a cycle.
        held_locks_set: Set[str] = set(current_locks)
        return _can_reach_any(new_lock_key, held_locks_set)
    
    def _record_lock_order(self, lock_key: str) -> None:
        """Record lock acquisition order for deadlock detection."""
        # Lazy initialization in case attributes were not set up in __init__
        if not hasattr(self, "_lock_order"):
            self._lock_order: Dict[str, List[str]] = {}
        if not hasattr(self, "_lock_dependency_graph"):
            self._lock_dependency_graph: Dict[str, Set[str]] = {}

        if self._owner_id not in self._lock_order:
            self._lock_order[self._owner_id] = []

        owner_locks = self._lock_order[self._owner_id]

        # For each lock the owner already holds, record a dependency to the
        # newly acquired lock. This is used by `_would_cause_deadlock` to
        # detect potential cycles for future acquisitions.
        for prev_lock_key in owner_locks:
            if prev_lock_key not in self._lock_dependency_graph:
                self._lock_dependency_graph[prev_lock_key] = set()
            self._lock_dependency_graph[prev_lock_key].add(lock_key)

        owner_locks.append(lock_key)
    
    def _clear_lock_order(self, lock_key: str) -> None:
        """Clear lock from acquisition order and dependency graph."""
        # If these structures do not exist yet, there is nothing to clear.
        if not hasattr(self, "_lock_order"):
            return

        if self._owner_id in self._lock_order:
            try:
                self._lock_order[self._owner_id].remove(lock_key)
            except ValueError:
                # Lock key not recorded for this owner; ignore.
                pass

        # Also clean up the dependency graph to avoid unbounded growth.
        if hasattr(self, "_lock_dependency_graph"):
            # Remove all outgoing edges from this lock.
            self._lock_dependency_graph.pop(lock_key, None)
            # Remove this lock as a target from other nodes.
            for from_key, to_set in list(self._lock_dependency_graph.items()):
                if lock_key in to_set:
                    to_set.discard(lock_key)
                    if not to_set:
                        # Remove empty adjacency lists to keep the graph small.
                        self._lock_dependency_graph.pop(from_key, None)


class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired."""
    pass


# =============================================================================
# Idempotency Engine
# =============================================================================

@dataclass
class IdempotencyRecord:
    """Record of an idempotent operation."""
    idempotency_key: str
    operation_id: str
    status: str  # "processing", "completed", "failed"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    ttl_seconds: int = 86400  # 24 hours default


class IdempotencyEngine:
    """
    Guarantees at-most-once execution for trading operations.
    
    Features:
    - Idempotency key tracking
    - Result caching
    - Automatic cleanup
    - Concurrent request handling
    
    Usage:
        with idempotency.execute(key) as ctx:
            if ctx.already_executed:
                return ctx.result
            result = perform_operation()
            ctx.complete(result)
            return result
    """
    
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        default_ttl_seconds: int = 86400,
        stale_operation_timeout_seconds: int = 600
    ):
        self.redis = redis_client
        self.default_ttl = default_ttl_seconds
        # Timeout after which a "processing" operation is considered stale
        # and can be retried. Default 10 minutes (600s) for long-running trades.
        self.stale_timeout = stale_operation_timeout_seconds
        
        # In-memory fallback
        self._records: Dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()
        
        logger.info("Idempotency engine initialized")
    
    def _get_key(self, idempotency_key: str) -> str:
        """Get storage key for idempotency record."""
        # Hash the key for consistent length
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]
        return f"vel:idempotency:{key_hash}"
    
    def check(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        """
        Check if operation was already executed.
        
        Returns:
            IdempotencyRecord if exists, None otherwise
        """
        storage_key = self._get_key(idempotency_key)
        
        if self.redis:
            try:
                data = self.redis.get(storage_key)
                if data:
                    import json
                    record_dict = json.loads(data)
                    return IdempotencyRecord(**record_dict)
            except Exception as e:
                logger.error(f"Redis idempotency check error: {e}")
        
        # Local fallback
        with self._lock:
            return self._records.get(storage_key)
    
    def start(
        self,
        idempotency_key: str,
        operation_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None
    ) -> tuple[bool, Optional[IdempotencyRecord]]:
        """
        Start an idempotent operation.
        
        Returns:
            Tuple of (is_new, existing_record)
            - (True, None) if this is a new operation
            - (False, record) if operation already exists
        """
        storage_key = self._get_key(idempotency_key)
        ttl = ttl_seconds or self.default_ttl
        op_id = operation_id or str(uuid.uuid4())
        
        existing = self.check(idempotency_key)
        if existing:
            # Already exists
            if existing.status == "completed":
                return False, existing
            elif existing.status == "processing":
                # Check if stale (processing for too long)
                if time.time() - existing.created_at > self.stale_timeout:
                    # Stale, allow retry
                    logger.warning(
                        f"Operation {idempotency_key} stale after {self.stale_timeout}s, allowing retry"
                    )
                    pass
                else:
                    # Still processing
                    return False, existing
        
        # Create new record
        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            operation_id=op_id,
            status="processing",
            ttl_seconds=ttl
        )
        
        if self.redis:
            try:
                import json
                self.redis.setex(
                    storage_key,
                    ttl,
                    json.dumps({
                        "idempotency_key": record.idempotency_key,
                        "operation_id": record.operation_id,
                        "status": record.status,
                        "created_at": record.created_at,
                        "ttl_seconds": record.ttl_seconds
                    })
                )
            except Exception as e:
                logger.error(f"Redis idempotency start error: {e}")
        
        with self._lock:
            self._records[storage_key] = record
        
        return True, None
    
    def complete(
        self,
        idempotency_key: str,
        result: Dict[str, Any]
    ) -> bool:
        """Mark operation as completed with result."""
        storage_key = self._get_key(idempotency_key)
        
        with self._lock:
            if storage_key not in self._records:
                return False
            
            record = self._records[storage_key]
            record.status = "completed"
            record.result = result
            record.completed_at = time.time()
        
        if self.redis:
            try:
                import json
                self.redis.setex(
                    storage_key,
                    record.ttl_seconds,
                    json.dumps({
                        "idempotency_key": record.idempotency_key,
                        "operation_id": record.operation_id,
                        "status": record.status,
                        "result": record.result,
                        "created_at": record.created_at,
                        "completed_at": record.completed_at,
                        "ttl_seconds": record.ttl_seconds
                    })
                )
            except Exception as e:
                logger.error(f"Redis idempotency complete error: {e}")
        
        return True
    
    def fail(
        self,
        idempotency_key: str,
        error: str
    ) -> bool:
        """Mark operation as failed."""
        storage_key = self._get_key(idempotency_key)
        
        with self._lock:
            if storage_key not in self._records:
                return False
            
            record = self._records[storage_key]
            record.status = "failed"
            record.error = error
            record.completed_at = time.time()
        
        if self.redis:
            try:
                import json
                self.redis.setex(
                    storage_key,
                    record.ttl_seconds,
                    json.dumps({
                        "idempotency_key": record.idempotency_key,
                        "operation_id": record.operation_id,
                        "status": record.status,
                        "error": record.error,
                        "created_at": record.created_at,
                        "completed_at": record.completed_at,
                        "ttl_seconds": record.ttl_seconds
                    })
                )
            except Exception as e:
                logger.error(f"Redis idempotency fail error: {e}")
        
        return True
    
    @contextmanager
    def execute(self, idempotency_key: str, ttl_seconds: Optional[int] = None):
        """
        Context manager for idempotent execution.
        
        Usage:
            with idempotency.execute("trade_123") as ctx:
                if ctx.already_executed:
                    return ctx.result
                result = do_trade()
                ctx.complete(result)
        """
        is_new, existing = self.start(idempotency_key, ttl_seconds=ttl_seconds)
        
        ctx = IdempotencyContext(
            engine=self,
            idempotency_key=idempotency_key,
            already_executed=not is_new,
            existing_record=existing
        )
        
        try:
            yield ctx
        except Exception as e:
            if is_new:
                self.fail(idempotency_key, str(e))
            raise
    
    def cleanup(self, max_age_seconds: int = 86400) -> int:
        """Remove old records. Returns count removed."""
        now = time.time()
        removed = 0
        
        with self._lock:
            expired = [
                k for k, v in self._records.items()
                if now - v.created_at > max_age_seconds
            ]
            for key in expired:
                del self._records[key]
                removed += 1
        
        return removed


@dataclass
class IdempotencyContext:
    """Context for idempotent execution."""
    engine: IdempotencyEngine
    idempotency_key: str
    already_executed: bool
    existing_record: Optional[IdempotencyRecord]
    
    @property
    def result(self) -> Optional[Dict[str, Any]]:
        """Get result from existing execution."""
        if self.existing_record:
            return self.existing_record.result
        return None
    
    def complete(self, result: Dict[str, Any]) -> None:
        """Mark this execution as complete."""
        self.engine.complete(self.idempotency_key, result)


# =============================================================================
# Transaction Queue Lock
# =============================================================================

class TransactionQueueLock:
    """
    Per-wallet transaction queue with strict ordering.
    
    Ensures transactions are processed in order and prevents
    concurrent transaction submission for the same wallet.
    """
    
    def __init__(
        self,
        lock_manager: DistributedLockManager,
        redis_client: Optional[Any] = None
    ):
        self.lock_manager = lock_manager
        self.redis = redis_client
        
        # Track queue positions
        self._queue_positions: Dict[str, int] = {}
        self._lock = threading.Lock()
    
    def enqueue(
        self,
        wallet_address: str,
        chain_id: int,
        transaction_id: str
    ) -> int:
        """
        Add transaction to queue.
        
        Returns queue position (0 = can execute immediately)
        """
        queue_key = f"txqueue:{chain_id}:{wallet_address.lower()}"
        
        if self.redis:
            try:
                position = self.redis.rpush(queue_key, transaction_id)
                return position - 1  # 0-indexed
            except Exception as e:
                logger.error(f"Redis queue error: {e}")
        
        with self._lock:
            if queue_key not in self._queue_positions:
                self._queue_positions[queue_key] = 0
            position = self._queue_positions[queue_key]
            self._queue_positions[queue_key] += 1
            return position
    
    def dequeue(
        self,
        wallet_address: str,
        chain_id: int,
        transaction_id: str
    ) -> bool:
        """Remove transaction from queue after processing."""
        queue_key = f"txqueue:{chain_id}:{wallet_address.lower()}"
        
        if self.redis:
            try:
                self.redis.lrem(queue_key, 1, transaction_id)
                return True
            except Exception as e:
                logger.error(f"Redis dequeue error: {e}")
        
        return True
    
    @contextmanager
    def transaction_slot(
        self,
        wallet_address: str,
        chain_id: int,
        transaction_id: str
    ):
        """
        Context manager for transaction execution slot.
        
        Acquires wallet lock and ensures queue ordering.
        """
        # Acquire wallet lock
        lock_info = self.lock_manager.acquire(
            LockType.WALLET,
            f"{chain_id}:{wallet_address.lower()}"
        )
        
        if not lock_info:
            raise LockAcquisitionError(
                f"Failed to acquire wallet lock for {wallet_address}"
            )
        
        # Add to queue
        position = self.enqueue(wallet_address, chain_id, transaction_id)
        logger.debug(f"Transaction {transaction_id} queued at position {position}")
        
        try:
            yield position
        finally:
            self.dequeue(wallet_address, chain_id, transaction_id)
            self.lock_manager.release(lock_info)
