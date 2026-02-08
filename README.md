# VEL - Enterprise DeFi Trading Platform

[![CI/CD Pipeline](https://github.com/Vereaux66/VEL/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Vereaux66/VEL/actions)
[![Tests](https://img.shields.io/badge/tests-174%20passed-brightgreen.svg)](#testing)
[![Security](https://img.shields.io/badge/security-military--grade-green.svg)](SECURITY.md)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A production-ready, enterprise-grade decentralized trading system with AI-powered strategies, military-grade security, and multi-chain support. Designed for 100,000+ user scalability.

## 🌟 Features

### Trading Engine
- **DEX-Only Execution**: All trades executed on-chain through smart contracts
- **Multi-Chain Support**: Ethereum, Arbitrum, Optimism, Polygon, BSC, Base
- **Slippage Protection**: Configurable tolerance with MEV resistance
- **Batch Trading**: Execute multiple swaps in a single transaction
- **Risk Kernel**: Real-time risk validation gate for all trades

### AI/ML Capabilities
- **Predictive Analytics**: Market regime detection and price prediction
- **Self-Healing**: Autonomous system repair and recovery
- **Continuous Learning**: Encrypted knowledge transfer between components
- **Strategy Optimization**: ML-powered trading strategy adaptation

### Security
- **Military-Grade Encryption**: AES-256-GCM with PBKDF2 key derivation
- **Intrusion Detection**: Real-time threat analysis and response
- **Rate Limiting**: Configurable burst protection
- **Session Management**: Fingerprint-based hijacking detection
- **Smart Contract Security**: ReentrancyGuard, Pausable, SafeERC20
- **Connection Hardening**: Automatic reconnection, health monitoring, wire-up verification

### Infrastructure
- **Kubernetes-Ready**: Helm charts for EKS deployment
- **Auto-Scaling**: 6-24 pod scaling for production
- **Observability**: OpenTelemetry, Prometheus, Grafana integration
- **Circuit Breakers**: Automatic halt on anomalies
- **Connection Management**: Health monitoring with automatic failover

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 16+
- Redis 7+

### Single Launch Authority

**All deployments use a single entry point:**

```bash
# Set required environment variable
export ANVEL_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
export ANVEL_WEB_PASSWORD="your_secure_password_here"

# Launch the system
python run.py
```

### Launch Options

```bash
# Validate prerequisites only (no launch)
python run.py --validate-only

# Show all options
python run.py --help
```

## 📋 Boot Sequence

The system initializes in this exact deterministic order:

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

## ⚙️ Configuration

### Required Environment Variables
```bash
ANVEL_MASTER_KEY=<64-character hex string>  # REQUIRED - encryption key
ANVEL_WEB_PASSWORD=<min 12 characters>       # REQUIRED - web auth
```

### Optional Configuration
```bash
# Database
ANVEL_DB_HOST=localhost
ANVEL_DB_PORT=5432
ANVEL_DB_NAME=vel
ANVEL_DB_USER=vel
ANVEL_DB_PASSWORD=<password>

# Redis
ANVEL_REDIS_URL=redis://localhost:6379/0

# Trading Mode
ANVEL_MODE=demo|paper|live
```

## 📁 Project Structure

```
VEL/
├── run.py                    # SINGLE LAUNCH AUTHORITY
├── README.md                 # This file
├── SECURITY.md               # Security documentation
├── CONTRIBUTING.md           # Contribution guidelines
│
├── contracts/                # Smart Contracts
│   ├── VELTradeExecutor.sol  # Main trading contract
│   ├── hardhat.config.js     # Hardhat configuration
│   └── scripts/deploy.js     # Deployment script
│
├── frontend/                 # React Frontend
│   ├── src/
│   │   ├── components/       # Reusable components
│   │   ├── pages/            # Page components
│   │   ├── context/          # React context providers
│   │   └── utils/            # Utility functions
│   └── package.json
│
├── ai/                       # AI/ML Modules
│   ├── core.py               # AI supervisor and training
│   ├── introspection.py      # System introspection
│   ├── learning.py           # Continuous learning
│   └── self_repair.py        # Self-healing capabilities
│
├── runtime/                  # Runtime Components
│   ├── boot.py               # Boot sequence
│   ├── config_loader.py      # Configuration loading
│   ├── health.py             # Health checks
│   └── service_registry.py   # Service registration
│
├── config/                   # Configuration Files
│   ├── system.json           # System configuration
│   ├── trading.json          # Trading parameters
│   ├── networks.json         # Blockchain networks
│   └── ai.json               # AI configuration
│
├── Core Security Modules
│   ├── vel_security_core.py      # Military-grade security framework
│   ├── vel_security_middleware.py # JWT, rate limiting, signatures
│   ├── vel_connection_hardening.py # Connection management & validation
│   └── vel_circuit_breaker.py    # Failure modes & emergency controls
│
├── Core Trading Modules
│   ├── vel_risk_kernel.py        # Deterministic risk enforcement
│   ├── vel_rpc_manager.py        # Multi-provider RPC with failover
│   ├── anvel_trade_engine.py     # High-performance trading engine
│   └── anvel_advanced_trading_strategies.py # Professional strategies
│
├── tests/                    # Test Suite (174 tests)
│   ├── test_security.py      # Security tests (30 tests)
│   ├── test_connection_hardening.py # Connection tests (23 tests)
│   ├── test_config_validator.py
│   ├── test_rpc_manager.py
│   ├── test_trade_lifecycle.py
│   └── test_infrastructure.py
│
├── .github/
│   └── workflows/
│       └── ci-cd.yml         # CI/CD pipeline
│
└── VEL_ARC/                  # Archive (deprecated code)
    ├── docs_archive/         # Archived documentation
    ├── legacy_pdfs/          # Archived PDFs
    └── cex_brokers/          # Archived CEX modules
```

## 🔐 Security

### Smart Contract Security
- ReentrancyGuard protection
- Emergency pause capability
- Router/token whitelisting
- Slippage bounds enforcement
- Deadline validation

### Backend Security
- AES-256-GCM encryption
- PBKDF2 key derivation (100k iterations)
- HMAC-SHA512 integrity verification
- Session fingerprinting
- Rate limiting with burst protection
- SQL injection protection
- XSS prevention
- Path traversal detection

### Connection Hardening
- **Automatic Reconnection**: Exponential backoff with jitter
- **Health Monitoring**: Continuous connection health checks
- **Wire-up Verification**: System integrity validation
- **Graceful Degradation**: Automatic failover on connection issues
- **SSL/TLS Enforcement**: HTTPS/WSS required for external connections

See [SECURITY.md](SECURITY.md) for full details.

## 🧪 Testing

**174 tests passing** across all modules:

```bash
# Run all tests
ANVEL_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))') \
python -m pytest tests/ -v

# Run specific test suite
python -m pytest tests/test_security.py -v
python -m pytest tests/test_connection_hardening.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Test Coverage
| Module | Tests | Status |
|--------|-------|--------|
| Security | 30 | ✅ Pass |
| Connection Hardening | 23 | ✅ Pass |
| Config Validator | 21 | ✅ Pass |
| Infrastructure | 20 | ✅ Pass |
| RPC Manager | 18 | ✅ Pass |
| Trade Lifecycle | 22 | ✅ Pass |
| Production Readiness | 25 | ✅ Pass |
| AI Safety | 4 | ✅ Pass |

## 📊 API Endpoints

### Health & Status
```
GET  /health              # System health check
GET  /api/status          # Trading system status
```

### Trading
```
POST /api/trade/execute   # Execute trade
GET  /api/trade/history   # Trade history
GET  /api/positions       # Current positions
```

### Portfolio
```
GET  /api/portfolio       # Portfolio overview
GET  /api/performance     # Performance metrics
```

## 🚢 Deployment

### AWS Deployment Readiness

**✅ Infrastructure and deployment tooling are in place for AWS**

See **[AWS_DEPLOYMENT_READINESS.md](AWS_DEPLOYMENT_READINESS.md)** for the comprehensive deployment checklist, including one-time AWS provisioning and secrets configuration required before the first deploy.

Quick readiness check:
```bash
./scripts/aws_deployment_readiness_check.sh --verbose
```

### Docker (Local Development)
```bash
docker-compose up -d
```

### Kubernetes (EKS) - Production
```bash
# Automated deployment
cd aws && ./deploy.sh

# Or manual Helm deployment
helm upgrade --install vel-trading ./aws/helm/vel \
  --namespace vel-system \
  --create-namespace \
  --set global.environment=production
```

### AWS CodeDeploy
The system includes AWS CodeDeploy integration via `appspec.yml`.

### Deployment Documentation
- **[AWS_DEPLOYMENT_READINESS.md](AWS_DEPLOYMENT_READINESS.md)**: Complete AWS deployment checklist
- **aws/deploy.sh**: Automated deployment script (745 lines)
- **scripts/aws_deployment_readiness_check.sh**: Pre-deployment validation

## 📈 Monitoring

### Prometheus Metrics
- Trade execution latency
- Risk check pass/fail rates
- Circuit breaker status
- System resource usage

### Logging
- Structured JSON logging
- Correlation IDs for request tracing
- OpenTelemetry integration

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## 📜 License

MIT License - see LICENSE file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes. Trading cryptocurrencies involves substantial risk of loss. Never invest more than you can afford to lose. The authors are not responsible for any financial losses incurred through the use of this software.

---

**Built with ❤️ for the DeFi community**
