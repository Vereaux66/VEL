#!/usr/bin/env python3
"""
ANVEL Database Service
Production-ready database layer for the webapp with PostgreSQL integration.

Handles:
- User authentication and session management
- Trade history persistence
- Position tracking
- Settings and configuration
"""

import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Database driver import with fallback
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    log.warning("psycopg2 not available - database operations will be disabled")


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "anvel"
    user: str = "anvel"
    password: str = ""
    min_connections: int = 2
    max_connections: int = 10
    connection_timeout: int = 10

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("ANVEL_DB_HOST", "localhost"),
            port=int(os.getenv("ANVEL_DB_PORT", "5432")),
            database=os.getenv("ANVEL_DB_NAME", "anvel"),
            user=os.getenv("ANVEL_DB_USER", "anvel"),
            password=os.getenv("ANVEL_DB_PASSWORD", ""),
            min_connections=int(os.getenv("ANVEL_DB_MIN_CONN", "2")),
            max_connections=int(os.getenv("ANVEL_DB_MAX_CONN", "10")),
        )


class DatabaseService:
    """
    Production-ready database service for ANVEL webapp.
    
    Features:
    - Connection pooling
    - Automatic reconnection
    - Transaction support
    - Error handling with fail-closed behavior
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize database service.
        
        Args:
            config: Database configuration (defaults to env vars)
        """
        self.config = config or DatabaseConfig.from_env()
        self._pool: Optional[Any] = None
        self._initialized = False

        if not PSYCOPG2_AVAILABLE:
            log.warning("Database service disabled - psycopg2 not available")
            return

        self._initialize_pool()

    def _initialize_pool(self) -> bool:
        """Initialize connection pool."""
        if not PSYCOPG2_AVAILABLE:
            return False

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self.config.min_connections,
                maxconn=self.config.max_connections,
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.database,
                user=self.config.user,
                password=self.config.password,
                connect_timeout=self.config.connection_timeout,
            )
            self._initialized = True
            log.info(
                "Database connection pool initialized: %s@%s:%d/%s",
                self.config.user, self.config.host,
                self.config.port, self.config.database
            )
            return True
        except Exception as e:
            log.error("Failed to initialize database pool: %s", e)
            self._initialized = False
            return False

    @property
    def is_available(self) -> bool:
        """Check if database is available."""
        return self._initialized and self._pool is not None

    @contextmanager
    def get_connection(self):
        """
        Get database connection from pool with automatic cleanup.
        
        Usage:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(...)
        """
        if not self.is_available:
            raise RuntimeError("Database not available")

        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            log.error("Database error: %s", e)
            raise
        except (ValueError, TypeError) as e:
            if conn:
                conn.rollback()
            log.error("Data error in database operation: %s", e)
            raise
        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def transaction(self):
        """
        Execute operations in a transaction.
        Automatically commits on success, rolls back on failure.
        """
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                log.error("Transaction rolled back due to database error: %s", e)
                raise
            except (ValueError, TypeError, KeyError) as e:
                conn.rollback()
                log.error("Transaction rolled back due to data error: %s", e)
                raise

    def close(self):
        """Close connection pool."""
        if self._pool:
            self._pool.closeall()
            self._initialized = False
            log.info("Database connection pool closed")

    # =========================================================================
    # User Operations
    # =========================================================================

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Get user by username.
        
        Args:
            username: Username to lookup
            
        Returns:
            User dict or None if not found
        """
        if not self.is_available:
            return None

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, username, email, password_hash, totp_secret,
                               is_active, risk_profile, settings, created_at,
                               last_login
                        FROM users
                        WHERE username = %s AND is_active = true
                    """, (username,))
                    return cur.fetchone()
        except Exception as e:
            log.error("Failed to get user by username: %s", e)
            return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by UUID."""
        if not self.is_available:
            return None

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, username, email, is_active, risk_profile,
                               settings, created_at, last_login
                        FROM users
                        WHERE id = %s
                    """, (user_id,))
                    return cur.fetchone()
        except Exception as e:
            log.error("Failed to get user by id: %s", e)
            return None

    def update_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp."""
        if not self.is_available:
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users 
                        SET last_login = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (user_id,))
                    return cur.rowcount > 0
        except Exception as e:
            log.error("Failed to update last login: %s", e)
            return False

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        totp_secret: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create new user.
        
        Returns:
            User UUID or None on failure
        """
        if not self.is_available:
            return None

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (username, email, password_hash, totp_secret)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (username, email, password_hash, totp_secret))
                    result = cur.fetchone()
                    return str(result[0]) if result else None
        except Exception as e:
            log.error("Failed to create user: %s", e)
            return None

    # =========================================================================
    # Trade Operations
    # =========================================================================

    def record_trade(
        self,
        user_id: str,
        exchange: str,
        pair: str,
        side: str,
        order_type: str,
        price: Decimal,
        quantity: Decimal,
        total: Decimal,
        fee: Decimal = Decimal("0"),
        status: str = "filled",
        strategy: Optional[str] = None,
        signal_confidence: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[int]:
        """
        Record a trade to the database.
        
        Returns:
            Trade ID or None on failure
        """
        if not self.is_available:
            return None

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO trades (
                            user_id, exchange, pair, side, order_type,
                            price, quantity, total, fee, status,
                            strategy, signal_confidence, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s
                        )
                        RETURNING id
                    """, (
                        user_id, exchange, pair, side, order_type,
                        price, quantity, total, fee, status,
                        strategy, signal_confidence,
                        metadata if metadata else {},
                    ))
                    result = cur.fetchone()
                    trade_id = result[0] if result else None
                    log.info(
                        "Trade recorded: %s %s %s %s @ %s (id=%s)",
                        side, quantity, pair, order_type, price, trade_id
                    )
                    return trade_id
        except Exception as e:
            log.error("Failed to record trade: %s", e)
            return None

    def get_trade_history(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        pair: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Get trade history for a user.
        
        Args:
            user_id: User UUID
            limit: Max trades to return (default 50)
            offset: Pagination offset
            pair: Filter by trading pair
            start_time: Filter trades after this time
            end_time: Filter trades before this time
            
        Returns:
            List of trade dicts
        """
        if not self.is_available:
            return []

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT id, timestamp, exchange, pair, side, order_type,
                               price, quantity, total, fee, pnl, status,
                               strategy, signal_confidence, metadata
                        FROM trades
                        WHERE user_id = %s
                    """
                    params = [user_id]

                    if pair:
                        query += " AND pair = %s"
                        params.append(pair)

                    if start_time:
                        query += " AND timestamp >= %s"
                        params.append(start_time)

                    if end_time:
                        query += " AND timestamp <= %s"
                        params.append(end_time)

                    query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])

                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            log.error("Failed to get trade history: %s", e)
            return []

    def get_trade_stats(
        self,
        user_id: str,
        period_days: int = 30,
    ) -> Dict:
        """
        Get trading statistics for a user.
        
        Args:
            user_id: User UUID
            period_days: Number of days to analyze
            
        Returns:
            Stats dict with total_trades, win_rate, total_pnl, etc.
        """
        if not self.is_available:
            return {}

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    start_time = datetime.utcnow() - timedelta(days=period_days)

                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_trades,
                            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                            COALESCE(SUM(pnl), 0) as total_pnl,
                            COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0) as gross_profit,
                            COALESCE(SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 0) as gross_loss,
                            COALESCE(SUM(fee), 0) as total_fees,
                            COALESCE(AVG(pnl), 0) as avg_pnl,
                            COALESCE(MAX(pnl), 0) as best_trade,
                            COALESCE(MIN(pnl), 0) as worst_trade
                        FROM trades
                        WHERE user_id = %s 
                          AND timestamp >= %s 
                          AND status = 'filled'
                    """, (user_id, start_time))

                    result = cur.fetchone()
                    if not result:
                        return {}

                    stats = dict(result)
                    total = stats.get("total_trades", 0)
                    winning = stats.get("winning_trades", 0)

                    stats["win_rate"] = (winning / total * 100) if total > 0 else 0
                    stats["period_days"] = period_days

                    return stats
        except Exception as e:
            log.error("Failed to get trade stats: %s", e)
            return {}

    # =========================================================================
    # Position Operations
    # =========================================================================

    def get_portfolio(self, user_id: str) -> List[Dict]:
        """Get user's portfolio positions."""
        if not self.is_available:
            return []

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT asset, quantity, average_price, current_price,
                               pnl_absolute, pnl_percentage, last_updated
                        FROM portfolio
                        WHERE user_id = %s AND quantity > 0
                        ORDER BY pnl_absolute DESC NULLS LAST
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            log.error("Failed to get portfolio: %s", e)
            return []

    def update_position(
        self,
        user_id: str,
        asset: str,
        quantity: Decimal,
        average_price: Decimal,
        current_price: Optional[Decimal] = None,
    ) -> bool:
        """
        Update or create a portfolio position.
        Uses UPSERT for atomic operation.
        """
        if not self.is_available:
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    pnl_absolute = None
                    pnl_percentage = None

                    if current_price and average_price > 0:
                        pnl_absolute = (current_price - average_price) * quantity
                        pnl_percentage = ((current_price - average_price) / average_price) * 100

                    cur.execute("""
                        INSERT INTO portfolio (
                            user_id, asset, quantity, average_price,
                            current_price, pnl_absolute, pnl_percentage
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, asset) DO UPDATE SET
                            quantity = EXCLUDED.quantity,
                            average_price = EXCLUDED.average_price,
                            current_price = EXCLUDED.current_price,
                            pnl_absolute = EXCLUDED.pnl_absolute,
                            pnl_percentage = EXCLUDED.pnl_percentage,
                            last_updated = CURRENT_TIMESTAMP
                    """, (
                        user_id, asset, quantity, average_price,
                        current_price, pnl_absolute, pnl_percentage
                    ))
                    return True
        except Exception as e:
            log.error("Failed to update position: %s", e)
            return False

    # =========================================================================
    # Order Operations
    # =========================================================================

    def create_order(
        self,
        user_id: str,
        exchange: str,
        pair: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        take_profit_price: Optional[Decimal] = None,
    ) -> Optional[str]:
        """
        Create a new order.
        
        Returns:
            Order UUID or None on failure
        """
        if not self.is_available:
            return None

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO orders (
                            user_id, exchange, pair, side, order_type,
                            quantity, price, stop_price, take_profit_price,
                            status
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
                        )
                        RETURNING id
                    """, (
                        user_id, exchange, pair, side, order_type,
                        quantity, price, stop_price, take_profit_price
                    ))
                    result = cur.fetchone()
                    return str(result[0]) if result else None
        except Exception as e:
            log.error("Failed to create order: %s", e)
            return None

    def get_open_orders(self, user_id: str) -> List[Dict]:
        """Get user's open/pending orders."""
        if not self.is_available:
            return []

        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, exchange, pair, side, order_type,
                               price, quantity, filled_quantity, status,
                               stop_price, take_profit_price, created_at
                        FROM orders
                        WHERE user_id = %s 
                          AND status IN ('pending', 'open', 'partially_filled')
                        ORDER BY created_at DESC
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            log.error("Failed to get open orders: %s", e)
            return []

    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_quantity: Optional[Decimal] = None,
        exchange_order_id: Optional[str] = None,
    ) -> bool:
        """Update order status."""
        if not self.is_available:
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    updates = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
                    params = [status]

                    if filled_quantity is not None:
                        updates.append("filled_quantity = %s")
                        params.append(filled_quantity)

                    if exchange_order_id:
                        updates.append("exchange_order_id = %s")
                        params.append(exchange_order_id)

                    params.append(order_id)

                    # Note: updates list contains only hardcoded column names,
                    # not user input, so this is safe from SQL injection
                    cur.execute(f"""
                        UPDATE orders 
                        SET {', '.join(updates)}
                        WHERE id = %s
                    """, params)
                    return cur.rowcount > 0
        except Exception as e:
            log.error("Failed to update order status: %s", e)
            return False

    # =========================================================================
    # Session/Auth Operations
    # =========================================================================

    def store_session(
        self,
        session_id: str,
        user_id: str,
        ip_address: str,
        user_agent: str,
        expires_at: datetime,
    ) -> bool:
        """Store user session (for session management)."""
        if not self.is_available:
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Create sessions table if not exists
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_sessions (
                            session_id VARCHAR(255) PRIMARY KEY,
                            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                            ip_address VARCHAR(45),
                            user_agent TEXT,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                            is_active BOOLEAN DEFAULT true
                        )
                    """)

                    cur.execute("""
                        INSERT INTO user_sessions (
                            session_id, user_id, ip_address, user_agent, expires_at
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE SET
                            ip_address = EXCLUDED.ip_address,
                            expires_at = EXCLUDED.expires_at,
                            is_active = true
                    """, (session_id, user_id, ip_address, user_agent, expires_at))
                    return True
        except Exception as e:
            log.error("Failed to store session: %s", e)
            return False

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a user session."""
        if not self.is_available:
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE user_sessions 
                        SET is_active = false 
                        WHERE session_id = %s
                    """, (session_id,))
                    return cur.rowcount > 0
        except Exception as e:
            log.error("Failed to invalidate session: %s", e)
            return False

    def invalidate_all_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user (for security events)."""
        if not self.is_available:
            return 0

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE user_sessions 
                        SET is_active = false 
                        WHERE user_id = %s AND is_active = true
                    """, (user_id,))
                    count = cur.rowcount
                    if count > 0:
                        log.warning(
                            "Invalidated %d sessions for user %s",
                            count, user_id
                        )
                    return count
        except Exception as e:
            log.error("Failed to invalidate user sessions: %s", e)
            return 0

    # =========================================================================
    # Health Check
    # =========================================================================

    def health_check(self) -> Dict:
        """
        Check database health status.
        
        Returns:
            Health status dict
        """
        result = {
            "available": self.is_available,
            "driver": "psycopg2" if PSYCOPG2_AVAILABLE else None,
        }

        if not self.is_available:
            result["error"] = "Database not available"
            return result

        try:
            start = time.time()
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            latency_ms = (time.time() - start) * 1000

            result["healthy"] = True
            result["latency_ms"] = round(latency_ms, 2)
            result["host"] = self.config.host
            result["database"] = self.config.database

        except Exception as e:
            result["healthy"] = False
            result["error"] = str(e)

        return result


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get or create the database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service


def init_database_service(config: Optional[DatabaseConfig] = None) -> DatabaseService:
    """Initialize database service with custom config."""
    global _db_service
    _db_service = DatabaseService(config)
    return _db_service
