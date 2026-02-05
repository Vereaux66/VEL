#!/usr/bin/env python3
"""
VEL Canonical State Ledger
===========================

Single source of truth for all wallet and position state.

Tracks:
- Wallet balances (native + ERC-20)
- Allowances
- Pending transaction impacts
- LP positions
- Lending/borrowing positions
- Realized/unrealized PnL
- Gas spent vs expected

Reconciliation loop:
1. Query on-chain state
2. Compare with ledger
3. Detect divergence
4. Trigger alerts or halt on mismatch

This ledger is authoritative.
Divergence from on-chain state is a critical error.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from web3 import Web3
from anvel_dex_broker_factory import SUPPORTED_CHAINS

logger = logging.getLogger(__name__)


@dataclass
class WalletBalance:
    """Wallet balance record."""
    wallet_address: str
    chain_id: int
    token_address: str  # "native" for native token
    balance: Decimal
    pending_delta: Decimal = Decimal("0")  # From pending transactions
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def effective_balance(self) -> Decimal:
        """Get effective balance including pending changes."""
        return self.balance + self.pending_delta


@dataclass
class TokenAllowance:
    """Token allowance record."""
    wallet_address: str
    chain_id: int
    token_address: str
    spender_address: str
    allowance: Decimal
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LPPosition:
    """Liquidity provider position."""
    position_id: str
    wallet_address: str
    chain_id: int
    protocol: str
    pool_address: str
    token_a: str
    token_b: str
    amount_a: Decimal
    amount_b: Decimal
    liquidity_tokens: Decimal
    entry_price: Decimal
    current_value: Decimal
    unrealized_pnl: Decimal
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LendingPosition:
    """Lending/borrowing position."""
    position_id: str
    wallet_address: str
    chain_id: int
    protocol: str
    position_type: str  # "supply", "borrow"
    token: str
    amount: Decimal
    interest_rate: Decimal
    accrued_interest: Decimal
    collateral_factor: Optional[Decimal] = None
    health_factor: Optional[Decimal] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PnLRecord:
    """Profit/loss record."""
    record_id: str
    wallet_address: str
    chain_id: int
    intent_id: str
    execution_id: str
    realized_pnl: Decimal
    gas_spent: Decimal
    gas_expected: Decimal
    net_pnl: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StateLedger:
    """
    Canonical state ledger.
    
    Maintains single source of truth for all wallet state.
    Continuous reconciliation with on-chain state.
    """
    
    def __init__(self, ledger_path: str = "data/state_ledger.db"):
        """
        Initialize state ledger.
        
        Args:
            ledger_path: Path to SQLite ledger database
        """
        self.ledger_path = ledger_path
        
        # Create data directory (skip for :memory:)
        if ledger_path != ":memory:":
            Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
        
        # For :memory: databases, we need to keep a persistent connection
        self._persistent_conn = None
        if ledger_path == ":memory:":
            self._persistent_conn = sqlite3.connect(ledger_path, check_same_thread=False)
        
        # Initialize database
        self._init_database()
        
        # In-memory cache
        self._balances: Dict[tuple[int, str, str], WalletBalance] = {}
        self._allowances: Dict[tuple[int, str, str, str], TokenAllowance] = {}
        self._lock = threading.Lock()
        
        # Web3 connections
        self._web3_connections: Dict[int, Web3] = {}
        
        logger.info(f"State ledger initialized: {ledger_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.ledger_path)
    
    def _init_database(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Balances table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balances (
                wallet_address TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                token_address TEXT NOT NULL,
                balance TEXT NOT NULL,
                pending_delta TEXT NOT NULL DEFAULT '0',
                last_updated TEXT NOT NULL,
                PRIMARY KEY (wallet_address, chain_id, token_address)
            )
        """)
        
        # Allowances table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS allowances (
                wallet_address TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                token_address TEXT NOT NULL,
                spender_address TEXT NOT NULL,
                allowance TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (wallet_address, chain_id, token_address, spender_address)
            )
        """)
        
        # LP positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lp_positions (
                position_id TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                pool_address TEXT NOT NULL,
                token_a TEXT NOT NULL,
                token_b TEXT NOT NULL,
                amount_a TEXT NOT NULL,
                amount_b TEXT NOT NULL,
                liquidity_tokens TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                current_value TEXT NOT NULL,
                unrealized_pnl TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        
        # Lending positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lending_positions (
                position_id TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                position_type TEXT NOT NULL,
                token TEXT NOT NULL,
                amount TEXT NOT NULL,
                interest_rate TEXT NOT NULL,
                accrued_interest TEXT NOT NULL,
                collateral_factor TEXT,
                health_factor TEXT,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        
        # PnL records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pnl_records (
                record_id TEXT PRIMARY KEY,
                wallet_address TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                intent_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                realized_pnl TEXT NOT NULL,
                gas_spent TEXT NOT NULL,
                gas_expected TEXT NOT NULL,
                net_pnl TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_balances ON balances(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_lp ON lp_positions(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_lending ON lending_positions(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_pnl ON pnl_records(wallet_address)")
        
        conn.commit()
        if not self._persistent_conn:
            conn.close()
        
        logger.info("State ledger database initialized")
    
    def _get_web3(self, chain_id: int) -> Optional[Web3]:
        """Get Web3 connection for chain."""
        if chain_id in self._web3_connections:
            return self._web3_connections[chain_id]
        
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
    
    def get_balance(
        self,
        wallet_address: str,
        chain_id: int,
        token_address: str = "native"
    ) -> Optional[WalletBalance]:
        """
        Get wallet balance.
        
        Args:
            wallet_address: Wallet address
            chain_id: Chain ID
            token_address: Token address ("native" for native token)
            
        Returns:
            WalletBalance or None
        """
        key = (chain_id, wallet_address.lower(), token_address.lower())
        
        with self._lock:
            if key in self._balances:
                return self._balances[key]
        
        # Query from database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT balance, pending_delta, last_updated
            FROM balances
            WHERE wallet_address = ? AND chain_id = ? AND token_address = ?
        """, (wallet_address.lower(), chain_id, token_address.lower()))
        
        row = cursor.fetchone()
        if not self._persistent_conn:
            conn.close()
        
        if row:
            balance = WalletBalance(
                wallet_address=wallet_address.lower(),
                chain_id=chain_id,
                token_address=token_address.lower(),
                balance=Decimal(row[0]),
                pending_delta=Decimal(row[1]),
                last_updated=datetime.fromisoformat(row[2])
            )
            
            with self._lock:
                self._balances[key] = balance
            
            return balance
        
        return None
    
    def update_balance(
        self,
        wallet_address: str,
        chain_id: int,
        token_address: str,
        balance: Decimal,
        pending_delta: Decimal = Decimal("0")
    ) -> bool:
        """
        Update wallet balance.
        
        Args:
            wallet_address: Wallet address
            chain_id: Chain ID
            token_address: Token address
            balance: New balance
            pending_delta: Pending balance delta
            
        Returns:
            True if successful
        """
        try:
            now = datetime.now(timezone.utc)
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO balances VALUES (?, ?, ?, ?, ?, ?)
            """, (
                wallet_address.lower(),
                chain_id,
                token_address.lower(),
                str(balance),
                str(pending_delta),
                now.isoformat()
            ))
            
            conn.commit()
            if not self._persistent_conn:
                conn.close()
            
            # Update cache
            key = (chain_id, wallet_address.lower(), token_address.lower())
            with self._lock:
                self._balances[key] = WalletBalance(
                    wallet_address=wallet_address.lower(),
                    chain_id=chain_id,
                    token_address=token_address.lower(),
                    balance=balance,
                    pending_delta=pending_delta,
                    last_updated=now
                )
            
            logger.debug(
                f"Balance updated: wallet={wallet_address}, chain={chain_id}, "
                f"token={token_address}, balance={balance}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to update balance: {e}", exc_info=True)
            return False
    
    def reconcile(self, execution: Any) -> bool:
        """
        Reconcile ledger state with on-chain state after execution.
        
        Args:
            execution: ExecutionRecord with transaction details
            
        Returns:
            True if state matches on-chain
        """
        try:
            if not execution.plan or not execution.tx_hash:
                logger.warning("Cannot reconcile without plan and tx_hash")
                return False
            
            chain_id = execution.plan.chain_id
            wallet_address = execution.plan.wallet_address
            
            # Get on-chain balances
            on_chain_balances = self._fetch_on_chain_balances(chain_id, wallet_address)
            
            if not on_chain_balances:
                logger.error("Failed to fetch on-chain balances")
                return False
            
            # Compare with ledger
            divergence_detected = False
            
            for token_address, on_chain_balance in on_chain_balances.items():
                ledger_balance = self.get_balance(wallet_address, chain_id, token_address)
                
                if not ledger_balance:
                    # First time seeing this token - record it
                    self.update_balance(wallet_address, chain_id, token_address, on_chain_balance)
                    continue
                
                # Check for divergence (allow small rounding differences)
                difference = abs(ledger_balance.balance - on_chain_balance)
                threshold = Decimal("0.000001")  # 1e-6 tolerance
                
                if difference > threshold:
                    logger.error(
                        f"STATE DIVERGENCE DETECTED: wallet={wallet_address}, "
                        f"chain={chain_id}, token={token_address}, "
                        f"ledger={ledger_balance.balance}, on_chain={on_chain_balance}, "
                        f"diff={difference}"
                    )
                    divergence_detected = True
                else:
                    # Update ledger to match chain
                    self.update_balance(wallet_address, chain_id, token_address, on_chain_balance)
            
            if divergence_detected:
                logger.critical(
                    "CRITICAL: State divergence detected - ledger does not match chain",
                    extra={
                        "execution_id": execution.execution_id,
                        "tx_hash": execution.tx_hash,
                        "wallet": wallet_address,
                        "chain": chain_id
                    }
                )
                return False
            
            logger.info(
                f"State reconciliation passed for execution {execution.execution_id}",
                extra={"execution_id": execution.execution_id}
            )
            return True
            
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}", exc_info=True)
            return False
    
    def _fetch_on_chain_balances(
        self,
        chain_id: int,
        wallet_address: str
    ) -> Optional[Dict[str, Decimal]]:
        """
        Fetch current on-chain balances.
        
        Returns:
            Dict mapping token_address to balance
        """
        try:
            w3 = self._get_web3(chain_id)
            if not w3:
                return None
            
            balances = {}
            
            # Get native token balance
            native_balance_wei = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
            balances["native"] = Decimal(native_balance_wei) / Decimal(10**18)
            
            # For ERC-20 tokens, we'd need to query each token contract
            # This would require maintaining a list of tokens to track
            # For now, just return native balance
            
            return balances
            
        except Exception as e:
            logger.error(f"Failed to fetch on-chain balances: {e}", exc_info=True)
            return None
    
    def record_pnl(
        self,
        wallet_address: str,
        chain_id: int,
        intent_id: str,
        execution_id: str,
        realized_pnl: Decimal,
        gas_spent: Decimal,
        gas_expected: Decimal
    ) -> bool:
        """Record PnL for execution."""
        try:
            record_id = f"pnl_{execution_id}"
            net_pnl = realized_pnl - gas_spent
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO pnl_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id,
                wallet_address.lower(),
                chain_id,
                intent_id,
                execution_id,
                str(realized_pnl),
                str(gas_spent),
                str(gas_expected),
                str(net_pnl),
                datetime.now(timezone.utc).isoformat()
            ))
            
            conn.commit()
            if not self._persistent_conn:
                conn.close()
            
            logger.info(
                f"PnL recorded: execution={execution_id}, "
                f"realized={realized_pnl}, gas={gas_spent}, net={net_pnl}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to record PnL: {e}", exc_info=True)
            return False
    
    def get_total_pnl(self, wallet_address: str, chain_id: Optional[int] = None) -> Decimal:
        """Get total PnL for wallet."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if chain_id:
                cursor.execute("""
                    SELECT SUM(CAST(net_pnl AS REAL)) FROM pnl_records
                    WHERE wallet_address = ? AND chain_id = ?
                """, (wallet_address.lower(), chain_id))
            else:
                cursor.execute("""
                    SELECT SUM(CAST(net_pnl AS REAL)) FROM pnl_records
                    WHERE wallet_address = ?
                """, (wallet_address.lower(),))
            
            result = cursor.fetchone()
            if not self._persistent_conn:
                conn.close()
            
            if result and result[0]:
                return Decimal(str(result[0]))
            return Decimal("0")
            
        except Exception as e:
            logger.error(f"Failed to get total PnL: {e}", exc_info=True)
            return Decimal("0")
    
    def close(self):
        """Close state ledger."""
        self._web3_connections.clear()
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
        logger.info("State ledger closed")
