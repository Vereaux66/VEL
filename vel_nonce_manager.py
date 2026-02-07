#!/usr/bin/env python3
"""
VEL Nonce Manager & Transaction Journal
========================================

Per-wallet, per-chain nonce management with transaction safety guarantees.

Features:
- Pending nonce tracking
- Nonce conflict detection and resolution
- Transaction replacement (speed-up / cancel)
- Dropped/stuck/replaced transaction detection
- Append-only transaction journal
- Crash-safe restart with state rehydration

Journal records:
- intent_id
- tx_hash
- nonce
- gas parameters
- simulation result
- submission time
- confirmation state
- replacement transactions

On restart:
1. Rehydrate nonce state from journal
2. Reconcile with on-chain state
3. Resume safely or halt on inconsistency
"""

import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from web3 import Web3
from web3.exceptions import TransactionNotFound
from anvel_dex_broker_factory import SUPPORTED_CHAINS

logger = logging.getLogger(__name__)


@dataclass
class TransactionJournalEntry:
    """Transaction journal entry."""
    journal_id: str
    intent_id: str
    execution_id: str
    chain_id: int
    wallet_address: str
    nonce: int
    tx_hash: Optional[str] = None
    gas_price: int = 0
    gas_limit: int = 0
    max_fee_per_gas: Optional[int] = None
    max_priority_fee_per_gas: Optional[int] = None
    transaction_type: int = 0  # 0=legacy, 2=EIP-1559
    value: int = 0
    simulation_passed: bool = False
    simulation_id: Optional[str] = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: Optional[datetime] = None
    confirmation_block: Optional[int] = None
    status: str = "pending"  # pending, confirmed, failed, dropped, replaced
    replaced_by: Optional[str] = None  # tx_hash of replacement
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d['submitted_at'] = self.submitted_at.isoformat()
        if self.confirmed_at:
            d['confirmed_at'] = self.confirmed_at.isoformat()
        return d


class NonceManager:
    """
    Per-wallet, per-chain nonce manager with transaction journal.
    
    Ensures:
    - No nonce conflicts
    - No duplicate transactions
    - Safe recovery after crashes
    - Transaction replacement support
    """
    
    def __init__(self, journal_path: str = "data/tx_journal.db"):
        """
        Initialize nonce manager.
        
        Args:
            journal_path: Path to SQLite journal database
        """
        self.journal_path = journal_path
        
        # Create data directory if needed (skip for :memory:)
        if journal_path != ":memory:":
            Path(journal_path).parent.mkdir(parents=True, exist_ok=True)
        
        # For :memory: databases, we need to keep a persistent connection
        self._persistent_conn = None
        if journal_path == ":memory:":
            self._persistent_conn = sqlite3.connect(journal_path, check_same_thread=False)
        
        # Initialize database
        self._init_database()
        
        # In-memory state
        self._nonce_state: Dict[tuple[int, str], int] = {}  # (chain_id, wallet) -> next_nonce
        self._pending_nonces: Dict[tuple[int, str], Set[int]] = {}  # (chain_id, wallet) -> set(nonces)
        self._tx_by_hash: Dict[str, TransactionJournalEntry] = {}
        self._lock = threading.Lock()
        
        # Web3 connections
        self._web3_connections: Dict[int, Web3] = {}
        
        # Rehydrate state from journal
        self._rehydrate_state()
        
        logger.info(f"Nonce manager initialized with journal: {journal_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.journal_path)
    
    def _init_database(self):
        """Initialize SQLite database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                journal_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                nonce INTEGER NOT NULL,
                tx_hash TEXT,
                gas_price INTEGER,
                gas_limit INTEGER,
                max_fee_per_gas INTEGER,
                max_priority_fee_per_gas INTEGER,
                transaction_type INTEGER,
                value INTEGER,
                simulation_passed INTEGER,
                simulation_id TEXT,
                submitted_at TEXT NOT NULL,
                confirmed_at TEXT,
                confirmation_block INTEGER,
                status TEXT NOT NULL,
                replaced_by TEXT,
                error TEXT,
                UNIQUE(chain_id, wallet_address, nonce)
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(tx_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_chain ON transactions(wallet_address, chain_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON transactions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_intent ON transactions(intent_id)")
        
        conn.commit()
        if not self._persistent_conn:
            conn.close()
        
        logger.info("Transaction journal database initialized")
    
    def _rehydrate_state(self):
        """Rehydrate nonce state from journal on startup."""
        logger.info("Rehydrating nonce state from journal...")
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        pending_count = 0
        try:
            # Get all pending transactions
            cursor.execute("""
                SELECT chain_id, wallet_address, nonce, tx_hash, status
                FROM transactions
                WHERE status IN ('pending', 'submitted')
                ORDER BY chain_id, wallet_address, nonce
            """)
            
            for row in cursor.fetchall():
                chain_id, wallet_address, nonce, tx_hash, status = row
                key = (chain_id, wallet_address.lower())
                
                # Track pending nonce
                if key not in self._pending_nonces:
                    self._pending_nonces[key] = set()
                self._pending_nonces[key].add(nonce)
                pending_count += 1
            
            logger.info(f"Rehydrated {pending_count} pending transactions")
        except sqlite3.OperationalError:
            # Table doesn't exist yet (fresh database)
            logger.info("No transactions table found - fresh database")
        
        if not self._persistent_conn:
            conn.close()
        
        # Reconcile with on-chain state
        if pending_count > 0:
            self._reconcile_with_chain()
    
    def _reconcile_with_chain(self):
        """Reconcile journal state with on-chain state."""
        logger.info("Reconciling nonce state with blockchain...")
        
        for (chain_id, wallet_address), pending_nonces in self._pending_nonces.items():
            try:
                # Get on-chain transaction count (next nonce)
                w3 = self._get_web3(chain_id)
                if not w3:
                    logger.error(f"Cannot connect to chain {chain_id} for reconciliation")
                    continue
                
                on_chain_nonce = w3.eth.get_transaction_count(
                    Web3.to_checksum_address(wallet_address)
                )
                
                # Update our state
                self._nonce_state[(chain_id, wallet_address)] = on_chain_nonce
                
                # Check for nonce gaps
                if pending_nonces:
                    min_pending = min(pending_nonces)
                    if min_pending < on_chain_nonce:
                        logger.warning(
                            f"Nonce gap detected: wallet={wallet_address}, "
                            f"chain={chain_id}, on_chain={on_chain_nonce}, "
                            f"min_pending={min_pending}"
                        )
                        # Update stuck transactions
                        self._update_stuck_transactions(chain_id, wallet_address, on_chain_nonce)
                
                logger.info(
                    f"Reconciled wallet {wallet_address} on chain {chain_id}: "
                    f"nonce={on_chain_nonce}, pending={len(pending_nonces)}"
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to reconcile wallet {wallet_address} on chain {chain_id}: {e}",
                    exc_info=True
                )
    
    def _update_stuck_transactions(self, chain_id: int, wallet_address: str, on_chain_nonce: int):
        """Update status of stuck transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE transactions
            SET status = 'dropped'
            WHERE chain_id = ? AND wallet_address = ? AND nonce < ? AND status = 'pending'
        """, (chain_id, wallet_address, on_chain_nonce))
        
        updated = cursor.rowcount
        conn.commit()
        if not self._persistent_conn:
            conn.close()
        
        if updated > 0:
            logger.warning(f"Marked {updated} transactions as dropped")
    
    def _get_web3(self, chain_id: int) -> Optional[Web3]:
        """Get Web3 connection for chain.
        
        Uses RPC manager if available for better failover and health tracking,
        otherwise falls back to direct connection.
        """
        if chain_id in self._web3_connections:
            return self._web3_connections[chain_id]
        
        # Try using RPC manager first (recommended for production)
        try:
            from vel_rpc_manager import get_rpc_manager
            rpc_manager = get_rpc_manager()
            w3 = rpc_manager.get_web3(chain_id)
            if w3 and w3.is_connected():
                self._web3_connections[chain_id] = w3
                logger.debug(f"Using RPC manager for chain {chain_id}")
                return w3
        except (ImportError, RuntimeError) as e:
            logger.debug(f"RPC manager not available, using direct connection: {e}")
        
        # Fallback to direct connection
        if chain_id not in SUPPORTED_CHAINS:
            return None
        
        chain_config = SUPPORTED_CHAINS[chain_id]
        try:
            w3 = Web3(Web3.HTTPProvider(chain_config.default_rpc))
            if w3.is_connected():
                self._web3_connections[chain_id] = w3
                return w3
        except Exception as e:
            logger.error(f"Failed to connect to chain {chain_id}: {e}")
        
        return None
    
    def get_next_nonce(self, chain_id: int, wallet_address: str) -> int:
        """
        Get next available nonce for wallet on chain.
        
        Uses distributed locking when available to prevent race conditions
        across multiple processes.
        
        Args:
            chain_id: Blockchain chain ID
            wallet_address: Wallet address
            
        Returns:
            Next nonce to use
            
        Raises:
            RuntimeError: If unable to acquire lock or connect to chain
        """
        wallet_address = wallet_address.lower()
        key = (chain_id, wallet_address)
        
        # Try to use distributed locking for cross-process safety
        lock_context = None
        try:
            from vel_distributed_locks import DistributedLockManager, LockType
            lock_manager = DistributedLockManager()
            resource_id = f"{chain_id}:{wallet_address}"
            lock_context = lock_manager.lock(LockType.NONCE, resource_id)
        except (ImportError, Exception) as e:
            # Fall back to thread-local locking
            logger.debug(f"Distributed locks not available, using local lock: {e}")
            lock_context = None
        
        try:
            # Enter distributed lock context if available
            if lock_context:
                lock_context.__enter__()
            
            with self._lock:
                # Get current nonce from state or chain
                if key in self._nonce_state:
                    nonce = self._nonce_state[key]
                else:
                    # First time - query chain
                    w3 = self._get_web3(chain_id)
                    if not w3:
                        raise RuntimeError(f"Cannot connect to chain {chain_id}")
                    
                    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(wallet_address))
                    self._nonce_state[key] = nonce
                
                # Track as pending
                if key not in self._pending_nonces:
                    self._pending_nonces[key] = set()
                self._pending_nonces[key].add(nonce)
                
                # Increment for next call
                self._nonce_state[key] = nonce + 1
                
                logger.debug(f"Allocated nonce {nonce} for wallet {wallet_address} on chain {chain_id}")
                return nonce
        finally:
            # Exit distributed lock context
            if lock_context:
                try:
                    lock_context.__exit__(None, None, None)
                except Exception:
                    pass
    
    def journal_transaction(self, entry: TransactionJournalEntry) -> bool:
        """
        Record transaction in journal.
        
        Args:
            entry: Transaction journal entry
            
        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.journal_id,
                entry.intent_id,
                entry.execution_id,
                entry.chain_id,
                entry.wallet_address.lower(),
                entry.nonce,
                entry.tx_hash,
                entry.gas_price,
                entry.gas_limit,
                entry.max_fee_per_gas,
                entry.max_priority_fee_per_gas,
                entry.transaction_type,
                entry.value,
                1 if entry.simulation_passed else 0,
                entry.simulation_id,
                entry.submitted_at.isoformat(),
                entry.confirmed_at.isoformat() if entry.confirmed_at else None,
                entry.confirmation_block,
                entry.status,
                entry.replaced_by,
                entry.error
            ))
            
            conn.commit()
            if not self._persistent_conn:
                conn.close()
            
            # Update in-memory cache
            if entry.tx_hash:
                self._tx_by_hash[entry.tx_hash] = entry
            
            logger.info(
                f"Transaction journaled: {entry.tx_hash}",
                extra={"tx_hash": entry.tx_hash, "nonce": entry.nonce, "chain_id": entry.chain_id}
            )
            return True
            
        except sqlite3.IntegrityError as e:
            logger.error(f"Duplicate transaction detected: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to journal transaction: {e}", exc_info=True)
            return False
    
    def broadcast_transaction(self, chain_id: int, signed_tx: str) -> Optional[str]:
        """
        Broadcast signed transaction.
        
        Args:
            chain_id: Chain ID
            signed_tx: Signed transaction hex
            
        Returns:
            Transaction hash or None
        """
        try:
            w3 = self._get_web3(chain_id)
            if not w3:
                raise RuntimeError(f"Cannot connect to chain {chain_id}")
            
            tx_hash = w3.eth.send_raw_transaction(signed_tx)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"Transaction broadcast: {tx_hash_hex}")
            return tx_hash_hex
            
        except Exception as e:
            logger.error(f"Transaction broadcast failed: {e}", exc_info=True)
            return None
    
    def wait_for_confirmation(
        self,
        chain_id: int,
        tx_hash: str,
        wallet_address: str,
        confirmation_blocks: int = 2,
        timeout: int = 300
    ) -> bool:
        """
        Wait for transaction confirmation.
        
        Args:
            chain_id: Chain ID
            tx_hash: Transaction hash
            wallet_address: Wallet address
            confirmation_blocks: Required confirmations
            timeout: Timeout in seconds
            
        Returns:
            True if confirmed
        """
        w3 = self._get_web3(chain_id)
        if not w3:
            return False
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                
                if receipt and receipt['blockNumber']:
                    current_block = w3.eth.block_number
                    confirmations = current_block - receipt['blockNumber']
                    
                    if confirmations >= confirmation_blocks:
                        # Update journal
                        self._update_transaction_status(
                            tx_hash=tx_hash,
                            status="confirmed",
                            confirmation_block=receipt['blockNumber']
                        )
                        
                        # Remove from pending
                        key = (chain_id, wallet_address.lower())
                        with self._lock:
                            if key in self._pending_nonces:
                                # Get transaction nonce
                                tx = w3.eth.get_transaction(tx_hash)
                                if tx and 'nonce' in tx:
                                    self._pending_nonces[key].discard(tx['nonce'])
                        
                        logger.info(
                            f"Transaction confirmed: {tx_hash}, "
                            f"block={receipt['blockNumber']}, confirmations={confirmations}"
                        )
                        return True
                    
                    logger.debug(f"Waiting for confirmations: {confirmations}/{confirmation_blocks}")
                    
            except TransactionNotFound:
                logger.debug(f"Transaction not found yet: {tx_hash}")
            except Exception as e:
                logger.error(f"Error checking transaction status: {e}")
            
            time.sleep(2)
        
        logger.error(f"Transaction confirmation timeout: {tx_hash}")
        return False
    
    def _update_transaction_status(
        self,
        tx_hash: str,
        status: str,
        confirmation_block: Optional[int] = None,
        error: Optional[str] = None
    ):
        """Update transaction status in journal."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            updates = ["status = ?"]
            params = [status]
            
            if confirmation_block:
                updates.append("confirmation_block = ?")
                updates.append("confirmed_at = ?")
                params.append(confirmation_block)
                params.append(datetime.now(timezone.utc).isoformat())
            
            if error:
                updates.append("error = ?")
                params.append(error)
            
            params.append(tx_hash)
            
            cursor.execute(f"""
                UPDATE transactions
                SET {', '.join(updates)}
                WHERE tx_hash = ?
            """, params)
            
            conn.commit()
            if not self._persistent_conn:
                conn.close()
            
        except Exception as e:
            logger.error(f"Failed to update transaction status: {e}", exc_info=True)
    
    def get_pending_transactions(
        self,
        chain_id: Optional[int] = None,
        wallet_address: Optional[str] = None
    ) -> List[TransactionJournalEntry]:
        """Get pending transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM transactions WHERE status = 'pending'"
        params = []
        
        if chain_id:
            query += " AND chain_id = ?"
            params.append(chain_id)
        
        if wallet_address:
            query += " AND wallet_address = ?"
            params.append(wallet_address.lower())
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        if not self._persistent_conn:
            conn.close()
        
        # Convert to TransactionJournalEntry objects
        entries = []
        for row in rows:
            entries.append(TransactionJournalEntry(
                intent_id=row[0],
                chain_id=row[1],
                wallet_address=row[2],
                tx_hash=row[3],
                nonce=row[4],
                gas_price=row[5],
                gas_limit=row[6],
                simulation_success=bool(row[7]),
                submitted_at=datetime.fromisoformat(row[8]) if row[8] else None,
                confirmed_at=datetime.fromisoformat(row[9]) if row[9] else None,
                status=row[10],
            ))
        return entries
    
    def close(self):
        """Close nonce manager and connections."""
        self._web3_connections.clear()
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
        logger.info("Nonce manager closed")
