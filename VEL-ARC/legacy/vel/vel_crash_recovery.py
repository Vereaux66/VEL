#!/usr/bin/env python3
"""
VEL Crash Recovery & State Restore
===================================

Production-grade crash recovery system for VEL trading operations.

Features:
- Transaction journal with WAL (Write-Ahead Logging)
- Checkpoint-based state snapshots
- Incremental recovery
- Integrity verification
- Automatic state reconciliation

On restart after crash:
1. Load last valid checkpoint
2. Replay journal entries since checkpoint
3. Verify state consistency
4. Reconcile with on-chain state
5. Resume or halt on inconsistency
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("vel.recovery")


# =============================================================================
# Recovery States
# =============================================================================

class RecoveryState(Enum):
    """Recovery process states."""
    INITIALIZING = "initializing"
    LOADING_CHECKPOINT = "loading_checkpoint"
    REPLAYING_JOURNAL = "replaying_journal"
    VERIFYING_STATE = "verifying_state"
    RECONCILING = "reconciling"
    RECOVERED = "recovered"
    FAILED = "failed"


class JournalEntryType(Enum):
    """Types of journal entries."""
    TRANSACTION_SUBMITTED = "tx_submitted"
    TRANSACTION_CONFIRMED = "tx_confirmed"
    TRANSACTION_FAILED = "tx_failed"
    BALANCE_UPDATE = "balance_update"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    NONCE_ALLOCATED = "nonce_allocated"
    CHECKPOINT = "checkpoint"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class JournalEntry:
    """Write-ahead log entry."""
    entry_id: str
    entry_type: JournalEntryType
    timestamp: float
    data: Dict[str, Any]
    checksum: str = ""
    
    def compute_checksum(self) -> str:
        """Compute entry checksum for integrity verification."""
        content = f"{self.entry_id}:{self.entry_type.value}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def verify(self) -> bool:
        """Verify entry integrity."""
        return self.checksum == self.compute_checksum()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "checksum": self.checksum
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JournalEntry":
        """Create from dictionary."""
        return cls(
            entry_id=d["entry_id"],
            entry_type=JournalEntryType(d["entry_type"]),
            timestamp=d["timestamp"],
            data=d["data"],
            checksum=d["checksum"]
        )


@dataclass
class Checkpoint:
    """State checkpoint for recovery."""
    checkpoint_id: str
    timestamp: float
    last_journal_entry_id: str
    state_snapshot: Dict[str, Any]
    checksum: str = ""
    
    def compute_checksum(self) -> str:
        """Compute checkpoint checksum."""
        content = f"{self.checkpoint_id}:{self.timestamp}:{self.last_journal_entry_id}:{json.dumps(self.state_snapshot, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def verify(self) -> bool:
        """Verify checkpoint integrity."""
        return self.checksum == self.compute_checksum()


@dataclass
class RecoveryResult:
    """Result of recovery process."""
    success: bool
    state: RecoveryState
    checkpoint_restored: Optional[str] = None
    entries_replayed: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recovery_time_ms: float = 0


# =============================================================================
# Write-Ahead Log (WAL)
# =============================================================================

class WriteAheadLog:
    """
    Append-only write-ahead log for crash recovery.
    
    All state changes are first written to the WAL before being applied.
    This ensures durability and enables recovery after crashes.
    """
    
    def __init__(self, wal_path: str = "data/wal"):
        self.wal_path = Path(wal_path)
        self.wal_path.mkdir(parents=True, exist_ok=True)
        
        self._current_file: Optional[Path] = None
        self._lock = threading.Lock()
        self._entry_counter = 0
        
        # Initialize database
        self._db_path = self.wal_path / "journal.db"
        self._init_database()
        
        logger.info(f"WAL initialized at {wal_path}")
    
    def _init_database(self) -> None:
        """Initialize journal database."""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                entry_id TEXT PRIMARY KEY,
                entry_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                data TEXT NOT NULL,
                checksum TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                last_entry_id TEXT NOT NULL,
                state_snapshot TEXT NOT NULL,
                checksum TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_timestamp 
            ON journal_entries(timestamp)
        """)
        
        conn.commit()
        conn.close()
    
    def append(self, entry_type: JournalEntryType, data: Dict[str, Any]) -> JournalEntry:
        """
        Append entry to WAL.
        
        This is synchronous and blocks until written to disk.
        """
        with self._lock:
            self._entry_counter += 1
            entry_id = f"wal_{int(time.time() * 1000)}_{self._entry_counter:08d}"
            
            entry = JournalEntry(
                entry_id=entry_id,
                entry_type=entry_type,
                timestamp=time.time(),
                data=data
            )
            entry.checksum = entry.compute_checksum()
            
            # Write to database
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO journal_entries VALUES (?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id,
                entry.entry_type.value,
                entry.timestamp,
                json.dumps(entry.data),
                entry.checksum,
                datetime.now(timezone.utc).isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"WAL entry appended: {entry_id}")
            return entry
    
    def read_since(self, since_entry_id: Optional[str] = None) -> List[JournalEntry]:
        """Read all entries since a given entry ID."""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        if since_entry_id:
            cursor.execute("""
                SELECT entry_id, entry_type, timestamp, data, checksum
                FROM journal_entries
                WHERE entry_id > ?
                ORDER BY timestamp ASC
            """, (since_entry_id,))
        else:
            cursor.execute("""
                SELECT entry_id, entry_type, timestamp, data, checksum
                FROM journal_entries
                ORDER BY timestamp ASC
            """)
        
        entries = []
        for row in cursor.fetchall():
            entry = JournalEntry(
                entry_id=row[0],
                entry_type=JournalEntryType(row[1]),
                timestamp=row[2],
                data=json.loads(row[3]),
                checksum=row[4]
            )
            entries.append(entry)
        
        conn.close()
        return entries
    
    def get_latest_entry_id(self) -> Optional[str]:
        """Get the ID of the latest journal entry."""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT entry_id FROM journal_entries
            ORDER BY timestamp DESC LIMIT 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def create_checkpoint(self, state_snapshot: Dict[str, Any]) -> Checkpoint:
        """Create a new checkpoint."""
        with self._lock:
            checkpoint_id = f"ckpt_{int(time.time() * 1000)}"
            last_entry_id = self.get_latest_entry_id() or ""
            
            checkpoint = Checkpoint(
                checkpoint_id=checkpoint_id,
                timestamp=time.time(),
                last_journal_entry_id=last_entry_id,
                state_snapshot=state_snapshot
            )
            checkpoint.checksum = checkpoint.compute_checksum()
            
            # Write checkpoint
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?, ?)
            """, (
                checkpoint.checkpoint_id,
                checkpoint.timestamp,
                checkpoint.last_journal_entry_id,
                json.dumps(checkpoint.state_snapshot),
                checkpoint.checksum,
                datetime.now(timezone.utc).isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Checkpoint created: {checkpoint_id}")
            return checkpoint
    
    def get_latest_checkpoint(self) -> Optional[Checkpoint]:
        """Get the most recent valid checkpoint."""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT checkpoint_id, timestamp, last_entry_id, state_snapshot, checksum
            FROM checkpoints
            ORDER BY timestamp DESC LIMIT 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        checkpoint = Checkpoint(
            checkpoint_id=row[0],
            timestamp=row[1],
            last_journal_entry_id=row[2],
            state_snapshot=json.loads(row[3]),
            checksum=row[4]
        )
        
        # Verify integrity
        if not checkpoint.verify():
            logger.error(f"Checkpoint {row[0]} failed integrity check")
            return None
        
        return checkpoint
    
    def compact(self, keep_after_checkpoint: Optional[str] = None) -> int:
        """
        Compact WAL by removing old entries.
        
        Only entries after the specified checkpoint are kept.
        """
        if not keep_after_checkpoint:
            checkpoint = self.get_latest_checkpoint()
            if not checkpoint:
                return 0
            keep_after_checkpoint = checkpoint.last_journal_entry_id
        
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        # Count entries to remove
        cursor.execute("""
            SELECT COUNT(*) FROM journal_entries WHERE entry_id < ?
        """, (keep_after_checkpoint,))
        count = cursor.fetchone()[0]
        
        # Remove old entries
        cursor.execute("""
            DELETE FROM journal_entries WHERE entry_id < ?
        """, (keep_after_checkpoint,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"WAL compacted: {count} entries removed")
        return count


# =============================================================================
# Crash Recovery Manager
# =============================================================================

class CrashRecoveryManager:
    """
    Manages crash recovery and state restoration.
    
    Recovery process:
    1. Detect if recovery is needed (unclean shutdown marker)
    2. Load latest valid checkpoint
    3. Replay journal entries since checkpoint
    4. Verify state consistency
    5. Reconcile with external state (blockchain)
    6. Mark recovery complete or fail
    """
    
    def __init__(
        self,
        wal: WriteAheadLog,
        state_handlers: Optional[Dict[JournalEntryType, Callable]] = None,
        reconciliation_handler: Optional[Callable] = None
    ):
        self.wal = wal
        self.state_handlers = state_handlers or {}
        self.reconciliation_handler = reconciliation_handler
        
        self._state = RecoveryState.INITIALIZING
        self._lock = threading.Lock()
        
        # Shutdown marker path
        self._shutdown_marker = Path(wal.wal_path) / ".clean_shutdown"
        
        logger.info("Crash recovery manager initialized")
    
    @property
    def state(self) -> RecoveryState:
        """Current recovery state."""
        return self._state
    
    def needs_recovery(self) -> bool:
        """Check if recovery is needed (unclean shutdown)."""
        return not self._shutdown_marker.exists()
    
    def mark_clean_startup(self) -> None:
        """Mark system as running (remove clean shutdown marker)."""
        if self._shutdown_marker.exists():
            self._shutdown_marker.unlink()
        logger.info("Marked startup (clean shutdown marker removed)")
    
    def mark_clean_shutdown(self) -> None:
        """Mark system as cleanly shut down."""
        self._shutdown_marker.touch()
        logger.info("Marked clean shutdown")
    
    def recover(self) -> RecoveryResult:
        """
        Perform crash recovery.
        
        Returns RecoveryResult with success/failure and details.
        """
        start_time = time.time()
        result = RecoveryResult(
            success=False,
            state=RecoveryState.INITIALIZING
        )
        
        try:
            # Step 1: Load checkpoint
            self._state = RecoveryState.LOADING_CHECKPOINT
            result.state = self._state
            
            checkpoint = self.wal.get_latest_checkpoint()
            if checkpoint:
                logger.info(f"Loading checkpoint: {checkpoint.checkpoint_id}")
                result.checkpoint_restored = checkpoint.checkpoint_id
                
                # Restore state from checkpoint
                self._restore_checkpoint_state(checkpoint)
            else:
                logger.warning("No checkpoint found, starting from empty state")
                result.warnings.append("No checkpoint found")
            
            # Step 2: Replay journal
            self._state = RecoveryState.REPLAYING_JOURNAL
            result.state = self._state
            
            since_entry = checkpoint.last_journal_entry_id if checkpoint else None
            entries = self.wal.read_since(since_entry)
            
            logger.info(f"Replaying {len(entries)} journal entries")
            
            for entry in entries:
                if not entry.verify():
                    error = f"Journal entry {entry.entry_id} failed integrity check"
                    logger.error(error)
                    result.errors.append(error)
                    continue
                
                try:
                    self._replay_entry(entry)
                    result.entries_replayed += 1
                except Exception as e:
                    error = f"Failed to replay entry {entry.entry_id}: {e}"
                    logger.error(error)
                    result.errors.append(error)
            
            # Step 3: Verify state
            self._state = RecoveryState.VERIFYING_STATE
            result.state = self._state
            
            verification_errors = self._verify_state()
            if verification_errors:
                result.errors.extend(verification_errors)
            
            # Step 4: Reconcile with external state
            self._state = RecoveryState.RECONCILING
            result.state = self._state
            
            if self.reconciliation_handler:
                try:
                    reconciliation_result = self.reconciliation_handler()
                    if not reconciliation_result.get("success", True):
                        result.errors.append(
                            f"Reconciliation failed: {reconciliation_result.get('error', 'unknown')}"
                        )
                except Exception as e:
                    result.errors.append(f"Reconciliation error: {e}")
            
            # Step 5: Determine final result
            if result.errors:
                self._state = RecoveryState.FAILED
                result.state = self._state
                result.success = False
                logger.error(f"Recovery failed with {len(result.errors)} errors")
            else:
                self._state = RecoveryState.RECOVERED
                result.state = self._state
                result.success = True
                logger.info(f"Recovery successful: {result.entries_replayed} entries replayed")
            
        except Exception as e:
            self._state = RecoveryState.FAILED
            result.state = self._state
            result.success = False
            result.errors.append(f"Recovery exception: {e}")
            logger.exception("Recovery failed with exception")
        
        result.recovery_time_ms = (time.time() - start_time) * 1000
        return result
    
    def _restore_checkpoint_state(self, checkpoint: Checkpoint) -> None:
        """
        Restore state from checkpoint.
        
        NOTE: This method must be implemented by the application to restore
        internal state from the snapshot stored in the checkpoint. Override
        this method in a subclass or set a custom handler via register_handler().
        
        The default implementation only logs, as the actual state restoration
        depends on application-specific data structures.
        """
        logger.debug(f"Restoring state from checkpoint {checkpoint.checkpoint_id}")
        logger.info(f"Checkpoint state keys: {list(checkpoint.state_snapshot.keys()) if checkpoint.state_snapshot else []}")
        # Application-specific implementation would restore:
        # - Wallet balances
        # - Nonce states
        # - Position data
        # - Pending transaction states
    
    def _replay_entry(self, entry: JournalEntry) -> None:
        """Replay a single journal entry."""
        handler = self.state_handlers.get(entry.entry_type)
        if handler:
            handler(entry)
        else:
            logger.debug(f"No handler for entry type {entry.entry_type}")
    
    def _verify_state(self) -> List[str]:
        """
        Verify state consistency. Returns list of errors.
        
        NOTE: This method must be implemented by the application to verify
        that the recovered state is consistent. Override this method in a
        subclass or implement custom verification logic.
        
        The default implementation returns an empty list (no errors).
        """
        errors = []
        # Application-specific verification would check:
        # - Wallet balance consistency
        # - Nonce sequence validity
        # - Position calculations
        # - Pending transaction states
        return errors
    
    def create_checkpoint(self, state_getter: Callable[[], Dict[str, Any]]) -> Checkpoint:
        """Create a new checkpoint with current state."""
        state_snapshot = state_getter()
        return self.wal.create_checkpoint(state_snapshot)


# =============================================================================
# State Persistence Helper
# =============================================================================

class StatePersistence:
    """
    Helper class for persistent state management.
    
    Wraps state changes with WAL entries and provides
    automatic recovery integration.
    """
    
    def __init__(
        self,
        wal: WriteAheadLog,
        checkpoint_interval_seconds: int = 300
    ):
        self.wal = wal
        self.checkpoint_interval = checkpoint_interval_seconds
        self._last_checkpoint_time = time.time()
        self._state: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    def record_transaction_submitted(
        self,
        tx_hash: str,
        wallet: str,
        chain_id: int,
        nonce: int,
        **extra
    ) -> JournalEntry:
        """Record transaction submission."""
        data = {
            "tx_hash": tx_hash,
            "wallet": wallet,
            "chain_id": chain_id,
            "nonce": nonce,
            **extra
        }
        return self.wal.append(JournalEntryType.TRANSACTION_SUBMITTED, data)
    
    def record_transaction_confirmed(
        self,
        tx_hash: str,
        block_number: int,
        **extra
    ) -> JournalEntry:
        """Record transaction confirmation."""
        data = {
            "tx_hash": tx_hash,
            "block_number": block_number,
            **extra
        }
        return self.wal.append(JournalEntryType.TRANSACTION_CONFIRMED, data)
    
    def record_transaction_failed(
        self,
        tx_hash: str,
        error: str,
        **extra
    ) -> JournalEntry:
        """Record transaction failure."""
        data = {
            "tx_hash": tx_hash,
            "error": error,
            **extra
        }
        return self.wal.append(JournalEntryType.TRANSACTION_FAILED, data)
    
    def record_balance_update(
        self,
        wallet: str,
        chain_id: int,
        token: str,
        old_balance: str,
        new_balance: str,
        **extra
    ) -> JournalEntry:
        """Record balance update."""
        data = {
            "wallet": wallet,
            "chain_id": chain_id,
            "token": token,
            "old_balance": old_balance,
            "new_balance": new_balance,
            **extra
        }
        return self.wal.append(JournalEntryType.BALANCE_UPDATE, data)
    
    def record_nonce_allocated(
        self,
        wallet: str,
        chain_id: int,
        nonce: int,
        intent_id: str
    ) -> JournalEntry:
        """Record nonce allocation."""
        data = {
            "wallet": wallet,
            "chain_id": chain_id,
            "nonce": nonce,
            "intent_id": intent_id
        }
        return self.wal.append(JournalEntryType.NONCE_ALLOCATED, data)
    
    def maybe_checkpoint(self, state_getter: Callable[[], Dict[str, Any]]) -> Optional[Checkpoint]:
        """Create checkpoint if interval has passed."""
        now = time.time()
        if now - self._last_checkpoint_time >= self.checkpoint_interval:
            self._last_checkpoint_time = now
            return self.wal.create_checkpoint(state_getter())
        return None
