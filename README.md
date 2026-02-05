# VEL - Autonomous DeFi Trading Platform

A production-ready decentralized trading system with AI-powered strategies and multi-chain support.

## Quick Start - Single Launch Authority

**All deployments use a single entry point:**

```bash
# Set required environment variable
export ANVEL_WEB_PASSWORD="your_secure_password_here"

# Launch the system (setup + full boot)
python run.py
```

This unified launcher enforces:
- ✓ Mandatory preflight validation (hard fail on missing requirements)
- ✓ Deterministic service initialization order
- ✓ Execution spine verification
- ✓ Circuit breaker activation
- ✓ Persistence continuity checks
- ✓ Same boot sequence for all deployment modes

### Launch Options

```bash
# Validate prerequisites only (no launch)
python run.py --validate-only

# Show all options
python run.py --help
```

## Boot Sequence (Deterministic Order)

The system always initializes in this exact order:

| Phase | Component | Status |
|-------|-----------|--------|
| 1 | Preflight Validation | Must pass |
| 2 | Persistence Layer | Must pass |
| 3 | External Connectivity | Must pass |
| 4 | Service Registry | Must pass |
| 5 | Execution Pipeline | Must pass |
| 6 | Schedulers/Workers | Optional |
| 7 | Monitoring | Optional |
| 8 | Execution Spine Verification | Warning only |
| 9 | Circuit Breaker Activation | Warning only |

**If any required phase fails, the system refuses to start.**

## Environment Variables

### Required
```bash
ANVEL_WEB_PASSWORD=<min 12 characters>  # Required for all deployments
```

### Optional
```bash
ANVEL_DB_HOST=localhost
ANVEL_DB_PORT=5432
ANVEL_DB_NAME=vel
ANVEL_DB_USER=vel
ANVEL_DB_PASSWORD=<password>
ANVEL_REDIS_URL=redis://localhost:6379/0
ANVEL_MODE=demo|paper|live
```

## Deployment Consistency

All deployment modes use identical configuration:

### Local Development
```bash
export ANVEL_WEB_PASSWORD="your_password"
python run.py
```

### Docker
```dockerfile
# In docker-compose.yml, the entrypoint must be:
command: ["python", "run.py"]
```

### AWS / Cloud
```yaml
# In task definition / deployment config:
entrypoint: ["python", "run.py"]
```

## Execution Spine

Every trade passes through the complete chain:

```
Market Data → Signal Engine → Risk Validation → Execution Manager → Ledger Write → Monitoring
```

The launcher verifies this chain is connected before marking the system operational.

## Circuit Breakers

Circuit breakers are wired to the execution stage and can:
- Halt all trading immediately
- Stop order broadcast
- Log halt reason with timestamp
- Notify monitoring systems

## Persistence Guarantees

The system ensures:
- Nonce/order state persists after restart
- Open trade states are recoverable
- Execution logs are stored in `data/state/`

## System Requirements

| Component | Minimum |
|-----------|---------|
| Python | 3.10+ |
| Memory | 4GB RAM |
| Storage | 2GB free |

## Project Structure

```
VEL/
├── run.py                    # SINGLE LAUNCH AUTHORITY
├── config/                   # Configuration files
├── data/state/               # Persistent state storage
├── logs/                     # Execution logs
│
├── Core Components
│   ├── anvel_event_bus.py    # Central messaging
│   ├── vel_risk_kernel.py    # Risk validation gate
│   ├── anvel_circuit_breaker.py
│   └── anvel_trade_engine.py
│
└── Documentation
    ├── TRADING_SYSTEM_README.md
    ├── SECURITY.md
    └── CONTRIBUTING.md
```

## Additional Documentation

- [Trading System Details](TRADING_SYSTEM_README.md)
- [Security Guidelines](SECURITY.md)
- [Contributing Guide](CONTRIBUTING.md)

## License

MIT License

## Disclaimer

This software is for educational purposes. Trading cryptocurrencies involves substantial risk. Never invest more than you can afford to lose.
