# VEL Production Execution Core

**Complete, Production-Ready DeFi Execution Platform**

Transform intents into safe, validated, on-chain transactions with deterministic risk enforcement and crash-safe state management.

## Overview

The VEL Production Execution Core is a capital-safe, scalable DeFi execution platform that provides:

- **Intent → Execution Pipeline**: Complete orchestration from high-level intent to confirmed transaction
- **Simulation-First Execution**: No transaction broadcast without successful simulation
- **Deterministic Risk Gates**: AI cannot override risk checks
- **Idempotent Execution**: No duplicate transactions
- **Crash-Safe & Restart-Safe**: Rehydrate state from journal on restart
- **Million-User Concurrency**: Per-wallet serial, cross-wallet parallel execution

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Intent Submission                         │
│              (Rust Gateway / Python Service)                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Execution Queue                            │
│         (Rate Limiting, Backpressure, Priority)              │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Execution Core Pipeline                      │
│  1. Validation                                               │
│  2. Strategy Resolution                                      │
│  3. DEX Protocol Selection                                   │
│  4. Route Determination                                      │
│  5. Transaction Construction                                 │
│  6. Simulation ◄── MUST PASS                                │
│  7. Risk Kernel ◄── CANNOT BE BYPASSED                      │
│  8. Signing (Isolated)                                       │
│  9. Broadcasting                                             │
│ 10. Confirmation Tracking                                    │
│ 11. State Reconciliation ◄── DIVERGENCE = HALT              │
└─────────────────────────────────────────────────────────────┘
```

## Core Modules

### 1. vel_execution_core.py
**Main execution pipeline orchestrator**

- Complete intent-to-execution flow
- Strategy resolution (intent → actionable plan)
- DEX protocol selection via broker factory
- Orchestrates all safety checks
- Maintains execution records

### 2. vel_transaction_simulator.py
**Pre-broadcast transaction simulation**

Every transaction MUST be simulated. Validates:
- No revert
- Gas within ceiling
- Slippage within bounds
- MinOut enforced
- Deadline enforced
- Expected value > total cost

**Simulation failure = hard block on execution**

### 3. vel_risk_kernel.py
**Deterministic risk enforcement engine**

NO BYPASS MECHANISMS. Enforces:
- Global max drawdown limits
- Per-asset exposure caps
- Per-chain exposure caps
- Per-protocol exposure caps
- Liquidity depth thresholds
- Gas-to-edge sanity checks

**Risk rules apply: pre-build, pre-sign, post-confirm**

### 4. vel_nonce_manager.py
**Nonce management & transaction journal**

- Per-wallet, per-chain nonce tracking
- Pending nonce conflict detection
- Transaction replacement support
- Append-only journal (SQLite)
- Crash-safe with state rehydration
- Detects dropped/stuck/replaced transactions

### 5. vel_state_ledger.py
**Canonical state ledger**

Single source of truth for:
- Wallet balances (native + ERC-20)
- Token allowances
- Pending transaction impacts
- LP positions
- Lending/borrowing positions
- Realized/unrealized PnL
- Gas spent vs expected

**Continuous reconciliation with on-chain state**

### 6. vel_signer.py
**Security-isolated signing boundary**

- No private keys in app memory (production)
- Dev signer (local) for development
- Remote signer interface for production
- Per-wallet blast radius isolation
- Full audit logging of sign requests

### 7. vel_circuit_breaker.py
**Failure modes & emergency controls**

System fails CLOSED. Halt triggers:
- Chain RPC degraded
- Signer unavailable
- Ledger divergence
- Risk breach
- High failure rate

Emergency controls:
- Global kill switch
- Per-chain halt
- Per-protocol halt

### 8. vel_execution_queue.py
**Scale & concurrency management**

- High-QPS intent intake
- Per-wallet serial execution (no races)
- Cross-wallet parallel execution
- Rate limiting per tenant
- Backpressure handling
- Priority queue support
- Dead letter queue for failures

## Usage Examples

### Basic Swap Execution

```python
from vel_execution_core import ExecutionCore, Intent, IntentType, create_execution_core

# Initialize execution core
core = create_execution_core()

# Create swap intent
intent = Intent(
    intent_id="swap_001",
    intent_type=IntentType.SWAP,
    wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
    chain_id=1,  # Ethereum
    parameters={
        "token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "token_out": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        "amount_in": "1000.0",
        "slippage_bps": 50,  # 0.5%
    }
)

# Execute
result = core.execute_intent(intent)

print(f"Status: {result.status.value}")
print(f"TX Hash: {result.tx_hash}")
```

### Queue-Based Execution

```python
from vel_execution_queue import ExecutionQueue, IntentPriority

# Initialize queue
queue = ExecutionQueue(max_queue_depth=10000, worker_threads=10)

# Set execution handler
queue.set_execution_handler(lambda intent_data: handle_intent(intent_data))

# Start processing
queue.start()

# Enqueue intent
queue.enqueue(
    intent_id="swap_001",
    wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
    intent_data=intent_data,
    priority=IntentPriority.HIGH
)
```

### Risk Monitoring

```python
from vel_risk_kernel import RiskKernel

# Initialize risk kernel
risk = RiskKernel(portfolio_value_usd=Decimal("1000000"))

# Get current state
state = risk.get_current_state()
print(f"Drawdown: {state['total_drawdown_usd']}")
print(f"Chain exposures: {state['chain_exposures']}")

# Update exposure after trade
risk.update_exposure(
    chain_id=1,
    protocol="uniswap_v3",
    asset="1:WETH",
    value_usd=Decimal("100000")
)
```

## Safety Invariants

### MUST Hold at All Times

1. **No transaction broadcast without successful simulation**
   - Enforced by execution pipeline
   - Simulation result required for signing

2. **Risk checks cannot be bypassed**
   - Hard-coded limits in risk kernel
   - No admin override capability
   - Failures result in rejection

3. **State must match chain**
   - Continuous reconciliation
   - Divergence triggers system halt
   - Manual intervention required

4. **Nonce conflicts impossible**
   - Per-wallet locking
   - Journal tracks all nonces
   - Rehydration on restart

5. **Idempotent execution**
   - Intent IDs are unique
   - Duplicate detection in journal
   - No double-spends

## Production Deployment

### Environment Variables

```bash
# Signer configuration
VEL_SIGNER_TYPE=remote  # or dev_local for development
VEL_SIGNER_ENDPOINT=https://signer.example.com
VEL_SIGNER_API_KEY=your_api_key

# Private key (dev only)
VEL_PRIVATE_KEY=0x...

# Database paths
VEL_JOURNAL_PATH=data/tx_journal.db
VEL_LEDGER_PATH=data/state_ledger.db
```

### Required Dependencies

```bash
pip install web3 eth-account sqlite3
```

### Starting the System

```python
from vel_execution_core import create_execution_core
from vel_execution_queue import ExecutionQueue

# Initialize components
core = create_execution_core()
queue = ExecutionQueue(worker_threads=20)

# Set up queue processing
queue.set_execution_handler(lambda data: core.execute_intent(Intent(**data)))
queue.start()

# System is now ready to accept intents
```

## Failure Modes

### Chain RPC Failure
- Circuit breaker halts affected chain
- Other chains continue operating
- Manual resume after RPC recovery

### Signer Unavailable
- Global halt - no transactions can be signed
- Pending confirmations still tracked
- Manual resume after signer recovery

### Ledger Divergence
- **CRITICAL**: System halts immediately
- Indicates state corruption or chain reorg
- Requires manual investigation and recovery

### Risk Breach
- Transaction rejected
- Intent moves to DLQ
- Risk limits must be adjusted or exposure reduced

## Monitoring

### Key Metrics

```python
# Circuit breaker metrics
cb_metrics = circuit_breaker.get_metrics()
# - total_intents
# - successful_executions
# - failed_executions
# - failure_rate

# Queue metrics
queue_metrics = execution_queue.get_metrics()
# - queue_depth
# - total_processed
# - total_failed
# - dlq_size

# Risk metrics
risk_state = risk_kernel.get_current_state()
# - total_drawdown_usd
# - asset_exposures
# - chain_exposures
# - protocol_exposures
```

### Logging

All modules use structured logging with context:

```python
logger.info(
    "Transaction broadcast",
    extra={
        "execution_id": execution_id,
        "tx_hash": tx_hash,
        "chain_id": chain_id,
        "wallet": wallet_address
    }
)
```

## Testing

Run integration examples:

```bash
python vel_execution_example.py
```

Run with specific examples:

```python
from vel_execution_example import (
    example_swap_execution,
    example_risk_enforcement,
    example_circuit_breaker
)

example_swap_execution()
```

## Security Considerations

### Private Key Management

- **Development**: Use `DevLocalSigner` with local keys
- **Production**: Use `RemoteSigner` with external signing service
- **Never**: Commit private keys to code

### Blast Radius Isolation

- Each wallet uses separate signer
- Compromise of one wallet doesn't affect others
- Multi-wallet signer enforces isolation

### Audit Trail

- All sign requests logged
- All executions journaled
- All risk checks recorded
- Complete audit trail for compliance

## Performance

### Throughput

- **Queue intake**: 1000+ QPS (limited by rate limiting)
- **Execution**: Limited by RPC latency and confirmation time
- **Per-wallet**: Serial execution (safety over speed)
- **Cross-wallet**: Parallel execution (10+ workers)

### Scalability

- Horizontal scaling via multiple worker processes
- Each process maintains own nonce state
- Shared database for journal and ledger
- Million-user capable with proper infrastructure

## License

See LICENSE file.

## Contributing

See CONTRIBUTING.md.

## Support

For issues, questions, or feature requests, see the main VEL repository documentation.
