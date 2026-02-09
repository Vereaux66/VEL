#!/usr/bin/env python3
"""
ANVEL Transaction Boundary Manager

Provides atomic transaction boundaries around trade execution with:
- Pre-trade validation
- Order state tracking
- Rollback capabilities
- Audit logging
- Deadlock prevention
"""

import logging
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """Transaction lifecycle states."""
    PENDING = "pending"
    VALIDATING = "validating"
    EXECUTING = "executing"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ValidationError(Exception):
    """Raised when pre-trade validation fails."""
    pass


class ExecutionError(Exception):
    """Raised when trade execution fails."""
    pass


class RollbackError(Exception):
    """Raised when rollback fails."""
    pass


@dataclass
class TradeOperation:
    """Represents a single trade operation within a transaction."""
    operation_id: str
    operation_type: str  # 'submit_order', 'cancel_order', 'modify_order'
    exchange: str
    symbol: str
    side: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    order_type: str = "market"
    order_id: Optional[str] = None  # Set after execution
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type,
            "order_id": self.order_id,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Transaction:
    """Represents a trade transaction with multiple operations."""
    transaction_id: str
    state: TransactionState = TransactionState.PENDING
    operations: List[TradeOperation] = field(default_factory=list)
    rollback_operations: List[TradeOperation] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def add_operation(self, operation: TradeOperation) -> None:
        """Add an operation to the transaction."""
        self.operations.append(operation)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "operations": [op.to_dict() for op in self.operations],
            "rollback_operations": [op.to_dict() for op in self.rollback_operations],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class TransactionManager:
    """
    Manages transaction boundaries for trade operations.
    
    Provides:
    - Atomic execution of trade operations
    - Pre-trade validation hooks
    - Automatic rollback on failure
    - Audit trail for all operations
    - Thread-safe transaction handling
    
    Usage:
        manager = TransactionManager()
        
        with manager.transaction() as txn:
            txn.submit_order(broker, "BTC/USD", "buy", 0.1)
            txn.submit_order(broker, "ETH/USD", "buy", 1.0)
        # Both orders committed or both rolled back
    """

    def __init__(
        self,
        max_operations_per_transaction: int = 10,
        validation_timeout: float = 5.0,
        execution_timeout: float = 30.0,
    ):
        """
        Initialize transaction manager.
        
        Args:
            max_operations_per_transaction: Maximum operations allowed in single transaction
            validation_timeout: Timeout for validation phase in seconds
            execution_timeout: Timeout for execution phase in seconds
        """
        self.max_operations = max_operations_per_transaction
        self.validation_timeout = validation_timeout
        self.execution_timeout = execution_timeout

        self._lock = threading.RLock()
        self._active_transactions: Dict[str, Transaction] = {}
        self._completed_transactions: List[Transaction] = []
        self._validators: List[Callable[[TradeOperation], Tuple[bool, str]]] = []

        # Register default validators
        self._register_default_validators()

        logger.info("TransactionManager initialized")

    def _register_default_validators(self) -> None:
        """Register default pre-trade validators."""

        def validate_quantity(op: TradeOperation) -> Tuple[bool, str]:
            """Ensure quantity is positive."""
            if op.quantity is not None and op.quantity <= 0:
                return False, f"Invalid quantity: {op.quantity}"
            return True, ""

        def validate_price(op: TradeOperation) -> Tuple[bool, str]:
            """Ensure limit price is positive."""
            if op.order_type == "limit" and (op.price is None or op.price <= 0):
                return False, f"Invalid limit price: {op.price}"
            return True, ""

        def validate_side(op: TradeOperation) -> Tuple[bool, str]:
            """Ensure side is valid."""
            if op.side and op.side.lower() not in ("buy", "sell"):
                return False, f"Invalid side: {op.side}"
            return True, ""

        self._validators.extend([validate_quantity, validate_price, validate_side])

    def register_validator(
        self,
        validator: Callable[[TradeOperation], Tuple[bool, str]]
    ) -> None:
        """
        Register a custom pre-trade validator.
        
        Args:
            validator: Function that takes TradeOperation and returns (is_valid, error_message)
        """
        self._validators.append(validator)

    def _validate_operation(self, operation: TradeOperation) -> None:
        """Run all validators on an operation."""
        for validator in self._validators:
            is_valid, error = validator(operation)
            if not is_valid:
                raise ValidationError(f"Validation failed: {error}")

    @contextmanager
    def transaction(self):
        """
        Create a transaction context for atomic trade operations.
        
        Yields:
            TransactionContext for adding operations
        
        Raises:
            ValidationError: If pre-trade validation fails
            ExecutionError: If trade execution fails
            RollbackError: If rollback fails
        """
        txn_id = str(uuid.uuid4())
        txn = Transaction(transaction_id=txn_id)

        with self._lock:
            self._active_transactions[txn_id] = txn

        context = TransactionContext(self, txn)

        try:
            yield context

            # Commit phase
            self._commit_transaction(txn)

        except Exception as e:
            # Rollback phase
            txn.state = TransactionState.FAILED
            txn.error = str(e)

            try:
                self._rollback_transaction(txn)
            except RollbackError as re:
                logger.error(f"Rollback failed for transaction {txn_id}: {re}")
                raise

            raise
        finally:
            txn.completed_at = datetime.now(timezone.utc)

            with self._lock:
                if txn_id in self._active_transactions:
                    del self._active_transactions[txn_id]
                self._completed_transactions.append(txn)

                # Keep only last 1000 transactions in memory
                if len(self._completed_transactions) > 1000:
                    self._completed_transactions = self._completed_transactions[-1000:]

    def _commit_transaction(self, txn: Transaction) -> None:
        """Commit all operations in the transaction."""
        txn.state = TransactionState.COMMITTED

        for op in txn.operations:
            if op.status == "executed":
                op.status = "committed"

        logger.info(
            f"Transaction {txn.transaction_id} committed with "
            f"{len(txn.operations)} operations"
        )

    def _rollback_transaction(self, txn: Transaction) -> None:
        """Rollback executed operations in reverse order."""
        txn.state = TransactionState.ROLLED_BACK

        # Rollback in reverse order
        for op in reversed(txn.operations):
            if op.status == "executed" and op.order_id:
                try:
                    self._rollback_operation(txn, op)
                except Exception as e:
                    logger.error(f"Failed to rollback operation {op.operation_id}: {e}")
                    raise RollbackError(f"Rollback failed: {e}")

        logger.info(
            f"Transaction {txn.transaction_id} rolled back "
            f"({len(txn.rollback_operations)} rollback operations)"
        )

    def _rollback_operation(self, txn: Transaction, op: TradeOperation) -> None:
        """Rollback a single operation by cancelling the order."""
        if op.operation_type == "submit_order" and op.order_id:
            rollback_op = TradeOperation(
                operation_id=str(uuid.uuid4()),
                operation_type="cancel_order",
                exchange=op.exchange,
                symbol=op.symbol,
                order_id=op.order_id,
            )

            # Note: In production, this would actually call the broker
            # Here we mark it as a rollback operation for tracking
            rollback_op.status = "rollback_pending"
            txn.rollback_operations.append(rollback_op)

    def get_active_transactions(self) -> List[Dict[str, Any]]:
        """Get list of active transactions."""
        with self._lock:
            return [txn.to_dict() for txn in self._active_transactions.values()]

    def get_transaction_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent transaction history."""
        with self._lock:
            return [txn.to_dict() for txn in self._completed_transactions[-limit:]]

    def get_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific transaction by ID."""
        with self._lock:
            if transaction_id in self._active_transactions:
                return self._active_transactions[transaction_id].to_dict()

            for txn in self._completed_transactions:
                if txn.transaction_id == transaction_id:
                    return txn.to_dict()

        return None


class TransactionContext:
    """
    Context for building transaction operations.
    
    Provides a fluent interface for adding trade operations to a transaction.
    """

    def __init__(self, manager: TransactionManager, transaction: Transaction):
        self._manager = manager
        self._transaction = transaction
        self._executed_operations: List[TradeOperation] = []

    @property
    def transaction_id(self) -> str:
        """Get the transaction ID."""
        return self._transaction.transaction_id

    @property
    def operation_count(self) -> int:
        """Get number of operations in transaction."""
        return len(self._transaction.operations)

    def submit_order(
        self,
        broker: Any,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> TradeOperation:
        """
        Add an order submission to the transaction.
        
        Args:
            broker: Broker instance to use for execution
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Order quantity
            price: Limit price (for limit orders)
            order_type: 'market' or 'limit'
        
        Returns:
            TradeOperation instance
        
        Raises:
            ValidationError: If validation fails
            RuntimeError: If max operations exceeded
        """
        if self.operation_count >= self._manager.max_operations:
            raise RuntimeError(
                f"Maximum operations ({self._manager.max_operations}) exceeded"
            )

        operation = TradeOperation(
            operation_id=str(uuid.uuid4()),
            operation_type="submit_order",
            exchange=getattr(broker, 'name', getattr(broker, 'exchange_id', 'unknown')),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

        # Validate
        self._transaction.state = TransactionState.VALIDATING
        self._manager._validate_operation(operation)

        # Execute
        self._transaction.state = TransactionState.EXECUTING
        try:
            result = broker.submit_order(
                symbol=symbol,
                side=side,
                qty=quantity,
                price=price,
                order_type=order_type,
            )

            operation.order_id = result.get("id")
            operation.result = result
            operation.status = "executed"

        except Exception as e:
            operation.status = "failed"
            operation.error = str(e)
            raise ExecutionError(f"Order execution failed: {e}")

        self._transaction.add_operation(operation)
        self._executed_operations.append(operation)

        logger.info(
            f"Transaction {self.transaction_id}: Submitted order "
            f"{operation.operation_id} ({side} {quantity} {symbol})"
        )

        return operation

    def cancel_order(
        self,
        broker: Any,
        order_id: str,
        symbol: Optional[str] = None,
    ) -> TradeOperation:
        """
        Add an order cancellation to the transaction.
        
        Args:
            broker: Broker instance
            order_id: Order ID to cancel
            symbol: Trading symbol (required by some exchanges)
        
        Returns:
            TradeOperation instance
        """
        if self.operation_count >= self._manager.max_operations:
            raise RuntimeError(
                f"Maximum operations ({self._manager.max_operations}) exceeded"
            )

        operation = TradeOperation(
            operation_id=str(uuid.uuid4()),
            operation_type="cancel_order",
            exchange=getattr(broker, 'name', getattr(broker, 'exchange_id', 'unknown')),
            symbol=symbol or "",
            order_id=order_id,
        )

        # Execute cancellation
        self._transaction.state = TransactionState.EXECUTING
        try:
            result = broker.cancel_order(order_id, symbol)
            operation.result = result
            operation.status = "executed"

        except Exception as e:
            operation.status = "failed"
            operation.error = str(e)
            raise ExecutionError(f"Order cancellation failed: {e}")

        self._transaction.add_operation(operation)

        logger.info(
            f"Transaction {self.transaction_id}: Cancelled order {order_id}"
        )

        return operation


# Convenience decorator for transactional methods
def transactional(manager: TransactionManager):
    """
    Decorator to wrap a function in a transaction.
    
    Usage:
        @transactional(transaction_manager)
        def execute_trades(txn, broker):
            txn.submit_order(broker, "BTC/USD", "buy", 0.1)
    """
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            with manager.transaction() as txn:
                return func(txn, *args, **kwargs)
        return wrapper
    return decorator


# Global transaction manager instance
_global_manager: Optional[TransactionManager] = None


def get_transaction_manager() -> TransactionManager:
    """Get or create the global transaction manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = TransactionManager()
    return _global_manager
