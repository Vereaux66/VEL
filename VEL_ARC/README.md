# VEL Archive (VEL_ARC)

This directory contains archived modules that have been deprecated or consolidated as part of the VEL architecture consolidation effort.

## Purpose

The VEL_ARC directory preserves legacy code for:
- Reference and historical purposes
- Potential future reference during debugging
- Audit trail of architectural changes

**WARNING**: These modules are **NOT** part of the active codebase and should not be imported or used in production.

## Directory Structure

```
VEL_ARC/
├── README.md                    # This file
├── cex_brokers/                 # Removed CEX broker modules
│   ├── anvel_broker_coinbase.py # Archived Coinbase data feed adapter
│   └── anvel_broker_kraken.py   # Archived Kraken data feed adapter
├── legacy_entry_points/         # Deprecated entry points (reserved)
└── deprecated_anvel_modules/    # Other deprecated ANVEL modules (reserved)
```

## CEX Brokers Archive

### Reason for Removal

VEL enforces a **DEX-only trading policy**. Centralized exchange (CEX) integrations have been removed to:

1. **Enforce policy compliance**: All trading happens on-chain through smart contracts
2. **Reduce attack surface**: CEX API keys represent a security risk
3. **Simplify architecture**: One consistent execution path through DEX protocols
4. **Maintain decentralization**: Align with DeFi principles

### Archived Files

| File | Original Purpose | Archived Date |
|------|-----------------|---------------|
| `anvel_broker_coinbase.py` | Read-only Coinbase price feed adapter | 2024-02-06 |
| `anvel_broker_kraken.py` | Read-only Kraken price feed adapter | 2024-02-06 |

### Migration Path

Price discovery should now use:
- **On-chain DEX pools**: Direct price queries from Uniswap, PancakeSwap, etc.
- **Decentralized oracles**: Chainlink, Band Protocol, or similar
- **DEX aggregators**: 1inch, 0x Protocol for best execution prices

## CI/CD Enforcement

The CI pipeline includes a check to prevent reintroduction of CEX modules:
- Files named `anvel_broker_coinbase.py` or `anvel_broker_kraken.py` in the main codebase will fail the build
- Imports from these modules (outside VEL_ARC) will fail the build

## Related Documentation

- `CONSOLIDATION_SUMMARY.md` - AI core consolidation details
- `AI_SELF_REPAIR_CONSOLIDATION.md` - Self-repair module consolidation
- `VEL_EXECUTION_CORE_README.md` - VEL execution pipeline documentation

---

**Archive Created**: 2024-02-06
**Policy**: DEX-only trading enforcement
