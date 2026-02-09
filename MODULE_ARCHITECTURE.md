# VEL Trading Platform - Module Architecture

## Overview

The VEL trading system consists of **39 active Python modules** that work together
to provide automated DEX trading capabilities.

## Entry Point

```bash
python vel_main.py
```

This single command loads and wires all 39 modules.

## Module Categories

### ANVEL Modules (25 files)

| Module | Purpose |
|--------|---------|
| `anvel_event_bus.py` | Pub/sub event messaging |
| `anvel_market_data.py` | Real-time price feeds |
| `anvel_broker_base.py` | Abstract broker interface |
| `anvel_broker_dex_base.py` | DEX-specific broker base |
| `anvel_broker_factory.py` | Broker instantiation |
| `anvel_dex_broker_factory.py` | DEX factory with multi-chain |
| `anvel_broker_uniswap.py` | Uniswap V3 trading |
| `anvel_broker_pancakeswap.py` | PancakeSwap V2 trading |
| `anvel_pooled_trading_engine.py` | Multi-user pooled trading |
| `anvel_pooled_trading_integration.py` | Pool-strategy integration |
| `anvel_defi_strategies.py` | DeFi yield strategies |
| `anvel_automated_executor.py` | Auto-execution pipeline |
| `anvel_strategy_core.py` | Strategy base classes |
| `anvel_continuous_learning.py` | Adaptive ML refinement |
| `anvel_analytics_core.py` | Trading analytics |
| `anvel_eternal_learning_engine.py` | Continuous learning |
| `anvel_dependency_utils.py` | Lazy loading utilities |
| `anvel_monitoring.py` | Health monitoring |
| `anvel_web_server.py` | Flask REST API |
| `anvel_watchlist.py` | Token watchlist |
| `anvel_watchlist_service.py` | Watchlist API service |
| `anvel_subscription_manager.py` | SaaS subscription tiers |
| `anvel_referral_system.py` | User referral tracking |
| `anvel_smart_contract_manager.py` | On-chain contract calls |
| `anvel_hybrid_interfaces.py` | Hybrid trading interfaces |

### VEL Execution Modules (14 files)

| Module | Purpose |
|--------|---------|
| `vel_execution_core.py` | Main execution engine |
| `vel_execution_queue.py` | Transaction queue |
| `vel_risk_kernel.py` | Risk assessment |
| `vel_circuit_breaker.py` | Failure protection |
| `vel_signer.py` | Transaction signing |
| `vel_nonce_manager.py` | Nonce tracking |
| `vel_state_ledger.py` | State management |
| `vel_transaction_simulator.py` | TX simulation |
| `vel_token_registry.py` | Token metadata |
| `vel_mev_protection.py` | MEV protection |
| `vel_backpressure.py` | Queue control |
| `vel_chain_finality.py` | Block confirmations |
| `vel_chaos_scenarios.py` | Chaos testing |
| `vel_operational_controls.py` | Runtime controls |

## System Flow

```
                    ┌─────────────────────────────────────────┐
                    │           vel_main.py                   │
                    │     (Unified Entry Point)               │
                    └─────────────────┬───────────────────────┘
                                      │
           ┌──────────────────────────┼──────────────────────────┐
           │                          │                          │
           ▼                          ▼                          ▼
    ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
    │ Event Bus   │          │ Market Data │          │ Monitoring  │
    │             │          │             │          │             │
    └──────┬──────┘          └──────┬──────┘          └─────────────┘
           │                        │
           ▼                        ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    DEX Broker Factory                       │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
    │  │  Uniswap    │  │ PancakeSwap │  │  (more...)  │         │
    │  └─────────────┘  └─────────────┘  └─────────────┘         │
    └─────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  VEL Execution Engine                       │
    │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
    │  │Risk Kernel│ │  Signer   │ │ Nonce Mgr │ │State Ledger│  │
    │  └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
    │  ┌───────────┐ ┌───────────┐ ┌───────────┐                 │
    │  │ Circuit   │ │   MEV     │ │ TX        │                 │
    │  │ Breaker   │ │ Protection│ │ Simulator │                 │
    │  └───────────┘ └───────────┘ └───────────┘                 │
    └─────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  Blockchain   │
                              │ (ETH, BSC,    │
                              │  Arbitrum...) │
                              └───────────────┘
```

## Configuration

- `anvel_config.json` - Main configuration
- `config/*.json` - Component configs
- `.env` - Environment variables

## Dependencies

See `requirements.txt` for Python dependencies.

---

*Generated: 2026-02-09*
