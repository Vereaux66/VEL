-- ANVEL Database Schema
-- Version: 1.0.0
-- 
-- This schema provides the database structure for the ANVEL trading system.
-- 
-- NOTE: This schema requires PostgreSQL 13+ and uses PostgreSQL-specific features:
-- - Trigger functions (plpgsql)
-- - JSONB columns
-- - PostgreSQL-specific data types
-- For SQLite development, use the migration script which provides compatible alternatives.
--
-- Tables:
-- - schema_version: Tracks migration versions
-- - users: User accounts
-- - sessions: User sessions
-- - trades: Trade execution records
-- - trade_ledger: Immutable ledger entries
-- - positions: Current position snapshots
-- - balance_snapshots: Balance history
-- - failed_trades: Failed trade records
-- - settings: User/system settings

-- ============================================================================
-- SCHEMA VERSION TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT INTO schema_version (version, description)
VALUES (1, 'Initial schema')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- USERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(512) NOT NULL,
    totp_secret VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    two_factor_enabled BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================================
-- SESSIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(512) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    is_valid BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- ============================================================================
-- TRADES
-- ============================================================================

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER REFERENCES users(id),
    execution_id VARCHAR(64),
    strategy_id VARCHAR(64),
    chain_id INTEGER NOT NULL,
    protocol VARCHAR(64) NOT NULL,
    token_in VARCHAR(64) NOT NULL,
    token_out VARCHAR(64) NOT NULL,
    amount_in NUMERIC(36, 18) NOT NULL,
    amount_out NUMERIC(36, 18),
    min_amount_out NUMERIC(36, 18),
    slippage_bps INTEGER,
    tx_hash VARCHAR(128),
    block_number BIGINT,
    gas_used BIGINT,
    gas_price_wei NUMERIC(36, 0),
    status VARCHAR(32) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_trades_trade_id ON trades(trade_id);
CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_tx_hash ON trades(tx_hash);

-- ============================================================================
-- TRADE LEDGER (IMMUTABLE)
-- ============================================================================

CREATE TABLE IF NOT EXISTS trade_ledger (
    id SERIAL PRIMARY KEY,
    ledger_id VARCHAR(64) NOT NULL UNIQUE,
    trade_id VARCHAR(64) NOT NULL,
    entry_type VARCHAR(32) NOT NULL,  -- 'debit', 'credit', 'fee'
    token VARCHAR(64) NOT NULL,
    amount NUMERIC(36, 18) NOT NULL,
    balance_before NUMERIC(36, 18),
    balance_after NUMERIC(36, 18),
    chain_id INTEGER,
    tx_hash VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Immutability constraint: no updates or deletes through application
    CONSTRAINT ledger_immutable CHECK (created_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ledger_ledger_id ON trade_ledger(ledger_id);
CREATE INDEX IF NOT EXISTS idx_ledger_trade_id ON trade_ledger(trade_id);
CREATE INDEX IF NOT EXISTS idx_ledger_created ON trade_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_token ON trade_ledger(token);

-- Prevent updates to ledger entries
CREATE OR REPLACE FUNCTION prevent_ledger_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Ledger entries are immutable and cannot be updated';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ledger_immutable_trigger ON trade_ledger;
CREATE TRIGGER ledger_immutable_trigger
    BEFORE UPDATE ON trade_ledger
    FOR EACH ROW
    EXECUTE FUNCTION prevent_ledger_update();

-- Prevent deletions from ledger entries
CREATE OR REPLACE FUNCTION prevent_ledger_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Ledger entries are immutable and cannot be deleted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ledger_immutable_delete_trigger ON trade_ledger;
CREATE TRIGGER ledger_immutable_delete_trigger
    BEFORE DELETE ON trade_ledger
    FOR EACH ROW
    EXECUTE FUNCTION prevent_ledger_delete();

-- NOTE: TRUNCATE is not affected by row-level triggers.
-- Ensure application roles do not have TRUNCATE privilege on trade_ledger.
-- ============================================================================
-- POSITIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token VARCHAR(64) NOT NULL,
    chain_id INTEGER NOT NULL,
    quantity NUMERIC(36, 18) NOT NULL DEFAULT 0,
    avg_entry_price NUMERIC(36, 18),
    cost_basis_usd NUMERIC(36, 18),
    current_value_usd NUMERIC(36, 18),
    unrealized_pnl NUMERIC(36, 18),
    realized_pnl NUMERIC(36, 18) DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_user_token_chain UNIQUE (user_id, token, chain_id)
);

CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_positions_token ON positions(token);

-- ============================================================================
-- BALANCE SNAPSHOTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    wallet_address VARCHAR(64),
    chain_id INTEGER NOT NULL,
    token VARCHAR(64) NOT NULL,
    balance NUMERIC(36, 18) NOT NULL,
    balance_usd NUMERIC(36, 18),
    snapshot_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_balance_user ON balance_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_balance_snapshot ON balance_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_balance_token_chain ON balance_snapshots(token, chain_id);

-- ============================================================================
-- FAILED TRADES
-- ============================================================================

CREATE TABLE IF NOT EXISTS failed_trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER REFERENCES users(id),
    execution_id VARCHAR(64),
    strategy_id VARCHAR(64),
    chain_id INTEGER,
    protocol VARCHAR(64),
    token_in VARCHAR(64),
    token_out VARCHAR(64),
    amount_in NUMERIC(36, 18),
    error_code VARCHAR(32),
    error_message TEXT,
    stack_trace TEXT,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_failed_trade_id ON failed_trades(trade_id);
CREATE INDEX IF NOT EXISTS idx_failed_user ON failed_trades(user_id);
CREATE INDEX IF NOT EXISTS idx_failed_at ON failed_trades(failed_at);

-- ============================================================================
-- SETTINGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    key VARCHAR(128) NOT NULL,
    value JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_user_key UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_settings_user ON settings(user_id);
CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);

-- ============================================================================
-- RISK METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS risk_metrics (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    metric_date DATE NOT NULL,
    daily_pnl NUMERIC(36, 18) DEFAULT 0,
    daily_drawdown NUMERIC(10, 6) DEFAULT 0,
    max_drawdown NUMERIC(10, 6) DEFAULT 0,
    sharpe_ratio NUMERIC(10, 6),
    win_rate NUMERIC(10, 6),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_user_date UNIQUE (user_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_risk_user ON risk_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_date ON risk_metrics(metric_date);

-- ============================================================================
-- API KEYS
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(512) NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,  -- For identification
    name VARCHAR(64),
    permissions JSONB DEFAULT '[]',
    rate_limit INTEGER DEFAULT 100,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

-- ============================================================================
-- SCHEMA VERSION CHECK FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION get_schema_version()
RETURNS INTEGER AS $$
    SELECT COALESCE(MAX(version), 0) FROM schema_version;
$$ LANGUAGE SQL;

-- ============================================================================
-- GRANTS (adjust based on your user)
-- ============================================================================

-- Grant permissions to the anvel user (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO anvel;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO anvel;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anvel;
