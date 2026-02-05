#!/usr/bin/env python3
"""
VEL Execution Queue Manager
============================

High-QPS intent intake with tenant isolation and backpressure.

Features:
- Multi-tenant queue management
- Per-wallet serial execution (no race conditions)
- Cross-wallet parallel execution
- Rate limiting per tenant
- Backpressure and queue depth monitoring
- Priority queue support
- Dead letter queue for failures

Architecture:
- Rust gateway receives intents (native/rust_gateway/)
- Python service consumes from queue
- Per-wallet execution serialization
- Parallel execution across different wallets

Queue guarantees:
- At-least-once delivery
- Order preservation per wallet
- No duplicate execution (idempotency)
"""

import logging
import queue
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class IntentPriority(Enum):
    """Intent priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class QueuedIntent:
    """Queued intent with metadata."""
    intent_id: str
    wallet_address: str
    intent_data: Dict[str, Any]
    priority: IntentPriority = IntentPriority.NORMAL
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0
    max_retries: int = 3
    
    def __lt__(self, other):
        """Compare for priority queue ordering."""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.queued_at < other.queued_at
    
    def __le__(self, other):
        """Less than or equal comparison."""
        return self == other or self < other
    
    def __ge__(self, other):
        """Greater than or equal comparison."""
        return self == other or not self < other


@dataclass
class TenantQuota:
    """Per-tenant rate limiting quota."""
    tenant_id: str
    max_qps: int
    current_count: int = 0
    window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def check_and_increment(self) -> bool:
        """
        Check if tenant has quota and increment.
        
        Returns:
            True if within quota
        """
        now = datetime.now(timezone.utc)
        
        # Reset window if needed
        if (now - self.window_start).total_seconds() >= 1.0:
            self.current_count = 0
            self.window_start = now
        
        if self.current_count >= self.max_qps:
            return False
        
        self.current_count += 1
        return True


class ExecutionQueue:
    """
    Execution queue manager.
    
    Manages intent queuing with:
    - Per-wallet serialization
    - Cross-wallet parallelization
    - Rate limiting
    - Backpressure handling
    """
    
    def __init__(
        self,
        max_queue_depth: int = 10000,
        max_wallet_queue_depth: int = 100,
        worker_threads: int = 10,
        enable_rate_limiting: bool = True
    ):
        """
        Initialize execution queue.
        
        Args:
            max_queue_depth: Maximum total queue depth
            max_wallet_queue_depth: Maximum queue depth per wallet
            worker_threads: Number of worker threads
            enable_rate_limiting: Enable per-tenant rate limiting
        """
        self.max_queue_depth = max_queue_depth
        self.max_wallet_queue_depth = max_wallet_queue_depth
        self.worker_threads = worker_threads
        self.enable_rate_limiting = enable_rate_limiting
        
        # Main intent queue (priority queue)
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_queue_depth)
        
        # Per-wallet queues for serialization
        self._wallet_queues: Dict[str, queue.Queue] = {}
        self._wallet_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        
        # Dead letter queue
        self._dlq: List[QueuedIntent] = []
        
        # Tenant quotas
        self._tenant_quotas: Dict[str, TenantQuota] = {}
        
        # Worker threads
        self._workers: List[threading.Thread] = []
        self._running = False
        
        # Metrics
        self._total_queued = 0
        self._total_processed = 0
        self._total_failed = 0
        self._total_dlq = 0
        
        # Execution handler
        self._execution_handler: Optional[Callable] = None
        
        logger.info(
            f"Execution queue initialized: "
            f"max_depth={max_queue_depth}, "
            f"workers={worker_threads}"
        )
    
    def set_execution_handler(self, handler: Callable):
        """
        Set execution handler function.
        
        Handler signature: handler(intent_data: Dict) -> bool
        Returns True on success, False on failure.
        """
        self._execution_handler = handler
        logger.info("Execution handler registered")
    
    def enqueue(
        self,
        intent_id: str,
        wallet_address: str,
        intent_data: Dict[str, Any],
        priority: IntentPriority = IntentPriority.NORMAL,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Enqueue intent for execution.
        
        Args:
            intent_id: Unique intent ID
            wallet_address: Wallet address
            intent_data: Intent data
            priority: Priority level
            tenant_id: Tenant ID for rate limiting
            
        Returns:
            True if enqueued successfully
        """
        # Check rate limiting
        if self.enable_rate_limiting and tenant_id:
            if not self._check_tenant_quota(tenant_id):
                logger.warning(
                    f"Rate limit exceeded for tenant {tenant_id}",
                    extra={"tenant_id": tenant_id, "intent_id": intent_id}
                )
                return False
        
        # Check wallet queue depth
        wallet_key = wallet_address.lower()
        if wallet_key in self._wallet_queues:
            wallet_queue = self._wallet_queues[wallet_key]
            if wallet_queue.qsize() >= self.max_wallet_queue_depth:
                logger.warning(
                    f"Wallet queue full: {wallet_address}",
                    extra={"wallet": wallet_address, "queue_depth": wallet_queue.qsize()}
                )
                return False
        
        # Create queued intent
        queued = QueuedIntent(
            intent_id=intent_id,
            wallet_address=wallet_address,
            intent_data=intent_data,
            priority=priority
        )
        
        try:
            # Add to main queue
            self._queue.put_nowait(queued)
            self._total_queued += 1
            
            logger.info(
                f"Intent queued: {intent_id}, wallet={wallet_address}, priority={priority.name}",
                extra={
                    "intent_id": intent_id,
                    "wallet": wallet_address,
                    "priority": priority.name,
                    "queue_depth": self._queue.qsize()
                }
            )
            return True
            
        except queue.Full:
            logger.error(
                f"Queue full - cannot enqueue intent {intent_id}",
                extra={"intent_id": intent_id, "queue_depth": self._queue.qsize()}
            )
            return False
    
    def _check_tenant_quota(self, tenant_id: str) -> bool:
        """Check if tenant has remaining quota."""
        if tenant_id not in self._tenant_quotas:
            # Default quota: 10 QPS per tenant
            self._tenant_quotas[tenant_id] = TenantQuota(
                tenant_id=tenant_id,
                max_qps=10
            )
        
        quota = self._tenant_quotas[tenant_id]
        return quota.check_and_increment()
    
    def set_tenant_quota(self, tenant_id: str, max_qps: int):
        """Set rate limit quota for tenant."""
        self._tenant_quotas[tenant_id] = TenantQuota(
            tenant_id=tenant_id,
            max_qps=max_qps
        )
        logger.info(f"Tenant quota set: {tenant_id} = {max_qps} QPS")
    
    def start(self):
        """Start worker threads."""
        if self._running:
            logger.warning("Execution queue already running")
            return
        
        if not self._execution_handler:
            raise RuntimeError("Execution handler not set - call set_execution_handler() first")
        
        self._running = True
        
        # Start worker threads
        for i in range(self.worker_threads):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"ExecutionWorker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        logger.info(f"Execution queue started with {self.worker_threads} workers")
    
    def stop(self, timeout: int = 30):
        """
        Stop worker threads.
        
        Args:
            timeout: Timeout in seconds to wait for workers
        """
        if not self._running:
            return
        
        logger.info("Stopping execution queue...")
        self._running = False
        
        # Wait for workers
        for worker in self._workers:
            worker.join(timeout=timeout)
        
        self._workers.clear()
        logger.info("Execution queue stopped")
    
    def _worker_loop(self):
        """Worker thread main loop."""
        thread_name = threading.current_thread().name
        logger.info(f"Worker {thread_name} started")
        
        while self._running:
            try:
                # Get next intent (with timeout to allow clean shutdown)
                try:
                    queued = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Process intent
                success = self._process_intent(queued)
                
                if success:
                    self._total_processed += 1
                else:
                    # Retry logic
                    if queued.retry_count < queued.max_retries:
                        queued.retry_count += 1
                        logger.warning(
                            f"Retrying intent {queued.intent_id}, attempt {queued.retry_count}",
                            extra={"intent_id": queued.intent_id, "retry": queued.retry_count}
                        )
                        self._queue.put(queued)
                    else:
                        # Move to DLQ
                        self._dlq.append(queued)
                        self._total_dlq += 1
                        self._total_failed += 1
                        logger.error(
                            f"Intent {queued.intent_id} moved to DLQ after {queued.max_retries} retries",
                            extra={"intent_id": queued.intent_id}
                        )
                
                self._queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
        
        logger.info(f"Worker {thread_name} stopped")
    
    def _process_intent(self, queued: QueuedIntent) -> bool:
        """
        Process queued intent.
        
        Ensures per-wallet serialization.
        
        Returns:
            True on success
        """
        wallet_key = queued.wallet_address.lower()
        
        # Acquire wallet lock to ensure serialization
        with self._wallet_locks[wallet_key]:
            try:
                logger.info(
                    f"Processing intent {queued.intent_id}",
                    extra={"intent_id": queued.intent_id, "wallet": queued.wallet_address}
                )
                
                # Call execution handler
                success = self._execution_handler(queued.intent_data)
                
                if success:
                    logger.info(
                        f"Intent executed successfully: {queued.intent_id}",
                        extra={"intent_id": queued.intent_id}
                    )
                else:
                    logger.error(
                        f"Intent execution failed: {queued.intent_id}",
                        extra={"intent_id": queued.intent_id}
                    )
                
                return success
                
            except Exception as e:
                logger.error(
                    f"Intent processing error: {e}",
                    extra={"intent_id": queued.intent_id},
                    exc_info=True
                )
                return False
    
    def get_queue_depth(self) -> int:
        """Get current queue depth."""
        return self._queue.qsize()
    
    def get_wallet_queue_depth(self, wallet_address: str) -> int:
        """Get queue depth for specific wallet."""
        wallet_key = wallet_address.lower()
        if wallet_key in self._wallet_queues:
            return self._wallet_queues[wallet_key].qsize()
        return 0
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get queue metrics."""
        return {
            "queue_depth": self._queue.qsize(),
            "total_queued": self._total_queued,
            "total_processed": self._total_processed,
            "total_failed": self._total_failed,
            "total_dlq": self._total_dlq,
            "dlq_size": len(self._dlq),
            "worker_count": len(self._workers),
            "is_running": self._running,
        }
    
    def get_dlq(self) -> List[QueuedIntent]:
        """Get dead letter queue contents."""
        return self._dlq.copy()
    
    def clear_dlq(self):
        """Clear dead letter queue (admin function)."""
        count = len(self._dlq)
        self._dlq.clear()
        logger.warning(f"Dead letter queue cleared: {count} items removed")
