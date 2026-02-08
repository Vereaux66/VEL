# VEL Archive (VEL_ARC)

This directory contains archived modules, documentation, and legacy files that have been deprecated or consolidated as part of the VEL architecture hardening effort.

## Purpose

The VEL_ARC directory preserves legacy code and documentation for:
- Reference and historical purposes
- Potential future reference during debugging
- Audit trail of architectural changes

**WARNING**: These modules are **NOT** part of the active codebase and should not be imported or used in production.

## Directory Structure

```
VEL_ARC/
├── README.md                    # This file
├── docs_archive/                # Archived documentation
│   ├── AI_SELF_REPAIR_CONSOLIDATION.md
│   ├── CHANGELOG.md
│   ├── CODE_STANDARDS.md
│   ├── CONSOLIDATION_SUMMARY.md
│   ├── DEX_QUICK_START.md
│   ├── IMPLEMENTATION_STATUS.md
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── OPERATIONAL_HARDENING_SUMMARY.md
│   ├── PR_COMPLETION_REPORT.md
│   ├── STATUS_REPORT.md
│   ├── TRADING_SYSTEM_README.md
│   ├── VEL_EXECUTION_CORE_README.md
│   └── VEL_EXECUTION_DELIVERY_REPORT.md
├── legacy_pdfs/                 # Archived PDF documentation
│   ├── anvel_execution_controller.pdf
│   ├── anvel_remote_executor.pdf
│   ├── anvel_trade_validator.pdf
│   ├── anvel_wallet_manager.pdf
│   ├── dockercompose_production.pdf
│   ├── vel_config_loader.pdf
│   ├── vel_observability.pdf
│   ├── vel_simulation_engine.pdf
│   ├── vel_strategy_router.pdf
│   └── vel_trade_ledger.pdf
├── cex_brokers/                 # Removed CEX broker modules
│   ├── anvel_broker_coinbase.py
│   └── anvel_broker_kraken.py
├── anvel_ai_legacy/             # Consolidated AI modules
│   ├── anvel_advanced_ai_core.py
│   ├── anvel_autonomous_core.py
│   ├── anvel_brain_modules.py
│   ├── anvel_consciousness.py
│   ├── anvel_evolving_code_repair.py
│   ├── anvel_import_repairer.py
│   └── anvel_predictive_healing.py
├── out_of_scope/                # Modules outside DEX-only scope
│   ├── anvel_btcpay_integration.py
│   ├── anvel_crypto_payment_integration.py
│   ├── anvel_monero_privacy.py
│   ├── anvel_social_signal.py
│   ├── anvel_startup_wizard.py
│   ├── anvel_runtime_wizard.py
│   ├── anvel_saas_integration_example.py
│   ├── anvel_operational_ledger.py
│   └── btcpay_scanner.py
└── overlapping_merged/          # Functionality merged into VEL modules
    ├── anvel_circuit_breaker.py  → merged into vel_circuit_breaker.py
    ├── anvel_risk_enhancement.py → merged into vel_risk_kernel.py
    ├── anvel_heartbeat_monitor.py → replaced by vel_health_server.py
    └── anvel_logging.py          → replaced by vel_structured_logging.py
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

## ANVEL AI Legacy Archive

### Reason for Consolidation

The AI modules have been consolidated into a unified `ai/` package to:

1. **Reduce code duplication**: Single source of truth for AI functionality
2. **Improve maintainability**: Fewer files to manage and test
3. **Ensure consistency**: Unified APIs and behavior
4. **Remove dead code**: Stub modules and incomplete implementations removed

### Consolidation Mapping

| Archived Module | Consolidated Into | Notes |
|-----------------|------------------|-------|
| `anvel_advanced_ai_core.py` | `ai/core.py` | Training engine, encryption |
| `anvel_autonomous_core.py` | `ai/core.py`, `ai/self_repair.py` | Self-healing, autonomous ops |
| `anvel_brain_modules.py` | `ai/core.py` | BrainSubsystems, diagnostics |
| `anvel_consciousness.py` | `ai/introspection.py` | Event logging, awareness |
| `anvel_evolving_code_repair.py` | `ai/self_repair.py` | Code repair, evolution |
| `anvel_import_repairer.py` | `ai/self_repair.py` | Import repair strategies |
| `anvel_predictive_healing.py` | `ai/introspection.py` | Predictive analysis |

### New Import Paths

```python
# OLD (deprecated)
from anvel_advanced_ai_core import get_ai_core
from anvel_import_repairer import get_repairer
from anvel_brain_modules import BrainSubsystems

# NEW (use these)
from ai.core import AICore, AISupervisor, BrainSubsystems
from ai.self_repair import create_import_repairer
from ai.introspection import IntrospectionEngine
```

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
**Policy**: DEX-only trading, AI consolidation
**Status**: Active archival
