# VEL - Decentralized Autonomous Trading System

<p align="center">
  <strong>Enterprise-Grade Multi-Chain DeFi Trading Platform</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Solidity-0.8.19-363636.svg" alt="Solidity">
  <img src="https://img.shields.io/badge/Chains-10+-green.svg" alt="Chains">
  <img src="https://img.shields.io/badge/DEXs-10+-orange.svg" alt="DEXs">
  <img src="https://img.shields.io/badge/Tests-1000+-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## 🎯 What Is VEL?

VEL is a **production-grade decentralized trading platform** that:

- ✅ Pools capital from multiple users into automated trading strategies
- ✅ Executes trades across **10+ DEXs** on **10 blockchain networks**
- ✅ Distributes profits transparently through smart contracts
- ✅ Operates 100% on-chain with no centralized custody

**All trading happens through audited smart contracts on decentralized exchanges—never on centralized platforms like Binance or Coinbase.**

---

## 🚀 How It Works

### 1. Deposit Funds
- Minimum deposit: **$10 USD**
- Maximum deposit: **$100,000 USD**
- 30-day lock period with flexible withdrawal of earnings
- Single-tier system with **graduated yield bonuses** based on deposit size

### 2. Automated Trading
VEL continuously monitors price opportunities across:
- **Cross-chain arbitrage** — Buy low on one DEX, sell high on another
- **Momentum strategies** — Follow strong price trends with volume confirmation
- **Mean reversion** — Capitalize on temporary price deviations
- **MEV-protected execution** — Front-running protection through private transactions

### 3. Earn Rewards
- Base yield: **10% APY** (achievable through DEX strategies)
- Bonus yield: Up to **+8% APY** for larger deposits
- Maximum effective yield: **18% APY** for $50K+ deposits
- Weekly earnings withdrawals (minimum $15)

---

## 💰 Graduated Yield Structure

The larger your deposit, the higher your yield bonus:

| Deposit Range | Tier | Base APY | Bonus | Effective APY |
|---------------|------|----------|-------|---------------|
| $10 - $499 | Standard | 10% | +0% | **10%** |
| $500 - $999 | Bronze | 10% | +1% | **11%** |
| $1,000 - $1,999 | Silver | 10% | +2% | **12%** |
| $2,000 - $4,999 | Gold | 10% | +3% | **13%** |
| $5,000 - $9,999 | Platinum | 10% | +4% | **14%** |
| $10,000 - $24,999 | Diamond | 10% | +5% | **15%** |
| $25,000 - $49,999 | Elite | 10% | +6% | **16%** |
| $50,000 - $100,000 | Premier | 10% | +8% | **18%** |

### Why These Rates Are Sustainable

- **DEX arbitrage**: 10-25% APY from cross-DEX price inefficiencies
- **LP provision**: 8-20% APY on major trading pairs
- **Yield farming**: 15-40% APY on established protocols
- **MEV capture**: Additional returns from transaction ordering

**Reinvestment Bonus**: +2% added to principal when you reinvest instead of withdraw.

---

## 💸 Fee Structure

VEL maintains minimal, transparent fees:

| Fee Type | Amount | Purpose |
|----------|--------|---------|
| Deposit Fee | 0.05% | Infrastructure maintenance |
| Withdrawal Fee | 0.05% | Gas cost subsidy |
| Trading Profit Fee | 0.1% | Development & operations |

**Example**: On a $10,000 deposit, you pay $5. On $1,000 profit, you pay $1.

---

## 🤝 Referral Program

Earn passive income by referring new users:

| Bonus Type | Amount |
|------------|--------|
| Referrer Bonus | 5% of referred deposit |
| Referred Bonus | 2% added to deposit |

- Generate referral codes after making any deposit
- No limit on referrals
- Bonuses credited immediately and withdrawable weekly

---

## ⛓️ Supported Blockchains

### Layer 1 (Base Chains)
| Network | Chain ID | Native Token |
|---------|----------|--------------|
| Ethereum | 1 | ETH |
| BNB Smart Chain | 56 | BNB |
| Avalanche C-Chain | 43114 | AVAX |

### Layer 2 (Scaling Solutions)
| Network | Chain ID | Native Token |
|---------|----------|--------------|
| Arbitrum One | 42161 | ETH |
| Optimism | 10 | ETH |
| Polygon | 137 | MATIC |
| Base | 8453 | ETH |
| zkSync Era | 324 | ETH |
| Linea | 59144 | ETH |

### Layer 3 (App-Specific)
| Network | Chain ID | Native Token |
|---------|----------|--------------|
| Xai | 660279 | XAI |

---

## 🔄 Supported DEXs

| DEX | Chains | Type |
|-----|--------|------|
| **Uniswap V3** | ETH, ARB, OP, POLY, BASE | AMM (Concentrated) |
| **PancakeSwap** | BSC, ETH, ARB, zkSync | AMM (Hybrid) |
| **SushiSwap** | Multi-chain | AMM |
| **Curve Finance** | ETH, ARB, OP, POLY | Stablecoin AMM |
| **Velodrome** | Optimism | ve(3,3) DEX |
| **Aerodrome** | Base | ve(3,3) DEX |
| **Camelot** | Arbitrum | AMM + NFT |
| **QuickSwap** | Polygon | AMM |
| **Trader Joe** | Avalanche, ARB | AMM |
| **SyncSwap** | zkSync Era | AMM |

---

## 📈 Trading Strategies

### Cross-Chain Arbitrage
```
Monitor prices across all chains/DEXs → Find price discrepancy → Execute atomic swap
```
Captures 0.1-3% per trade from price inefficiencies between venues.

### Momentum Trading
```
Detect strong trend + volume confirmation → Enter position → Trail stop + take profit
```
Follows sustained price movements with AI-powered signal filtering.

### Mean Reversion
```
Calculate moving averages → Identify oversold/overbought → Counter-trade with limits
```
Profits from temporary price deviations in stable asset pairs.

### MEV-Protected Execution
```
Batch orders → Submit via private RPC → Avoid front-running
```
Uses Flashbots and similar services to protect trades from MEV extraction.

---

## 🔐 Security Architecture

### Smart Contract Security
- **Multi-signature governance** — No single point of failure
- **Time-locked upgrades** — 48-hour delay on contract changes
- **Circuit breakers** — Automatic pause on anomaly detection
- **Reentrancy guards** — Protection against common attack vectors

### Operational Security
- **Private key isolation** — HSM-based key management
- **Rate limiting** — Protection against DoS attacks
- **Slippage protection** — Maximum 2% slippage tolerance
- **Gas price limits** — Circuit breaker for extreme gas conditions

### Self-Healing Capabilities
- **RPC failover** — Automatic switch to backup nodes
- **Transaction retry** — Exponential backoff with nonce management
- **Health monitoring** — Continuous contract state verification
- **Auto-recovery** — Restart trading after transient failures

---

## 🛠️ Smart Contracts

VEL deploys 9 production-grade Solidity contracts:

| Contract | Purpose | Lines |
|----------|---------|-------|
| `VELMultiDEXRouter` | Multi-DEX swap aggregation | 742 |
| `VELPooledTradingVault` | User deposits & graduated yields | 786 |
| `VELAtomicSwapHTLC` | Hash Time-Locked Contracts | 363 |
| `VELCrosschainBridge` | Cross-chain asset transfers | 455 |
| `VELGovernanceController` | DAO voting & proposals | 547 |
| `VELRewardsSystem` | Staking & loyalty rewards | 638 |
| `VELAnonymousOrderExecutor` | Privacy-preserving orders | 430 |
| `VELDecentralizedVault` | Multi-sig capital vault | 326 |
| `VELUserFundVault` | SaaS user fund isolation | 480 |

### Contract Deployment
```bash
cd contracts
npm install
npx hardhat compile
npx hardhat run scripts/deploy.py --network mainnet
```

---

## ✅ Current Capabilities

| Feature | Status | Description |
|---------|--------|-------------|
| Single-tier deposits | ✅ | $10-$100K with graduated bonuses |
| Graduated yield bonuses | ✅ | 10-18% APY based on deposit size |
| Multi-chain trading | ✅ | 10 blockchains supported |
| DEX aggregation | ✅ | 10+ DEXs with best-price routing |
| Referral system | ✅ | 5%/2% bonuses for referrer/referred |
| Weekly earnings withdrawal | ✅ | Minimum $15 threshold |
| Profit distribution | ✅ | Daily calculation, proportional share |
| Reinvestment bonuses | ✅ | +2% for reinvesting deposits |
| Self-healing operations | ✅ | RPC failover, retry logic |
| Circuit breakers | ✅ | Auto-pause on anomalies |
| Smart contract integration | ✅ | 9 production contracts |
| Cross-chain bridges | ✅ | Via VELCrosschainBridge |
| HTLC atomic swaps | ✅ | Via VELAtomicSwapHTLC |

---

## ❌ Limitations

| Limitation | Reason |
|------------|--------|
| No guaranteed profits | Trading inherently carries risk |
| No early withdrawal | Lock periods are enforced on-chain |
| No fiat on-ramp | Crypto-only deposits via supported stablecoins |
| No CEX trading | 100% decentralized by design |
| No transaction reversal | Blockchain transactions are final |

---

## 📋 Requirements

### Minimum Thresholds
| Action | Minimum | Maximum |
|--------|---------|---------|
| Deposit | $10 | $100,000 |
| Earnings Withdrawal | $15 | No limit |
| Referral Deposit | $10 | $100,000 |

### Withdrawal Rules
- **Earnings**: Withdrawable weekly (7-day cooldown)
- **Deposits**: Withdrawable after 30-day lock period
- **Fees**: 0.05% on all withdrawals

---

## 🖥️ Installation

### Prerequisites
- Python 3.12+
- Node.js 18+ (for smart contracts)
- PostgreSQL 14+ (optional, for persistence)
- Redis 7+ (optional, for caching)

### Quick Start

```bash
# Clone repository
git clone https://github.com/Vereaux66/VEL.git
cd VEL

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run tests
pytest tests/ -v

# Start the system
python ANVEL_MASTER.py
```

### Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f vel-trading

# Stop services
docker-compose down
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# Required: Wallet Configuration
VEL_PRIVATE_KEY=your_private_key_here

# Optional: Database (PostgreSQL)
ANVEL_DB_HOST=localhost
ANVEL_DB_PORT=5432
ANVEL_DB_NAME=vel
ANVEL_DB_USER=vel
ANVEL_DB_PASSWORD=your_password

# Optional: Redis Cache
ANVEL_REDIS_URL=redis://localhost:6379/0

# Optional: Web Interface
ANVEL_WEB_HOST=0.0.0.0
ANVEL_WEB_PORT=8080
ANVEL_WEB_PASSWORD=your_web_password

# Optional: RPC Endpoints (override defaults)
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
ARB_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY
```

### API Usage

```python
from anvel_pooled_trading_engine import create_pooled_trading_engine, DepositTier, get_deposit_tier_info
from decimal import Decimal

# Create engine instance
engine = create_pooled_trading_engine()

# Check yield for deposit amount
info = get_deposit_tier_info(Decimal("10000.00"))
print(f"Tier: {info['tier_name']}")           # Diamond
print(f"APY: {info['effective_apy_percent']}%")  # 15.0%
print(f"Annual earnings: ${info['annual_earnings_estimate']:.2f}")  # $1,500.00

# Create deposit
deposit = engine.deposit(
    user_id="user_wallet_address",
    amount=Decimal("10000.00"),
    tier=DepositTier.STANDARD,
)
print(f"Deposit ID: {deposit.deposit_id}")
print(f"Unlock date: {deposit.unlock_timestamp}")

# Withdraw earnings (after cooldown)
earnings = engine.withdraw_earnings("user_wallet_address")
print(f"Withdrawn: ${earnings:.2f}")
```

---

## ⚠️ Risk Disclosure

| Risk Type | Description | Mitigation |
|-----------|-------------|------------|
| **Market Risk** | Crypto prices are volatile | Diversified strategies, stop-losses |
| **Smart Contract Risk** | Bugs in code | Audits, formal verification, bug bounty |
| **Liquidity Risk** | Slippage on large trades | Order splitting, liquidity checks |
| **Bridge Risk** | Cross-chain message failures | Multiple confirmations, timeout refunds |
| **Operational Risk** | System downtime | Redundancy, health monitoring |

**⚠️ IMPORTANT: Only deposit funds you can afford to lose. Past performance does not guarantee future results.**

---

## ❓ FAQ

<details>
<summary><b>How are yields generated?</b></summary>

VEL generates yields through:
1. **DEX arbitrage** — Profiting from price differences across exchanges
2. **LP provision** — Earning swap fees as a liquidity provider
3. **Yield farming** — Participating in DeFi protocol incentives
4. **MEV capture** — Extracting value from transaction ordering

The 10-18% APY range is achievable and sustainable in DeFi markets.
</details>

<details>
<summary><b>What happens if the system goes down?</b></summary>

Your funds are held in smart contracts, not centralized wallets. Even if VEL's off-chain systems fail:
- Deposits remain locked in the vault contract
- After the lock period, you can withdraw directly from the contract
- No operator can access your funds
</details>

<details>
<summary><b>Can I withdraw early?</b></summary>

No. The 30-day lock period is enforced by smart contracts. This ensures pool stability and prevents bank-run scenarios. You can withdraw earnings weekly.
</details>

<details>
<summary><b>What tokens can I deposit?</b></summary>

VEL accepts stablecoins on supported chains:
- **USDC** — Circle's USD Coin
- **USDT** — Tether
- **DAI** — MakerDAO's decentralized stablecoin
</details>

<details>
<summary><b>How are profits distributed?</b></summary>

1. Trading profits are calculated daily
2. 0.1% goes to system operation fees
3. Remaining profits are distributed proportionally based on:
   - Your deposit amount
   - Your tier bonus multiplier
   - Time deposited in the pool
</details>

---

## 📁 Project Structure

```
VEL/
├── 📦 Core Trading Engine
│   ├── anvel_pooled_trading_engine.py    # Deposit/withdrawal/yield logic
│   ├── anvel_pooled_trading_integration.py # Database integration
│   ├── anvel_pooled_trading_api.py       # REST API endpoints
│   ├── anvel_smart_contract_manager.py   # Contract interaction layer
│   └── anvel_contract_integration.py     # High-level contract bridge
│
├── 📊 Trading Strategies
│   ├── anvel_defi_strategies.py          # Strategy implementations
│   ├── anvel_automated_executor.py       # Trade execution engine
│   ├── anvel_scalping_engine.py          # High-frequency strategies
│   └── anvel_crosschain_contracts.py     # Cross-chain operations
│
├── 🔌 DEX Integration
│   ├── anvel_broker_dex_base.py          # Base DEX broker class
│   ├── anvel_broker_uniswap.py           # Uniswap V3 integration
│   ├── anvel_broker_pancakeswap.py       # PancakeSwap integration
│   └── anvel_dex_broker_factory.py       # Broker factory pattern
│
├── 📝 Smart Contracts
│   └── contracts/core/
│       ├── VELPooledTradingVault.sol     # Main vault contract
│       ├── VELMultiDEXRouter.sol         # DEX routing
│       ├── VELAtomicSwapHTLC.sol         # Hash Time-Lock Contracts
│       ├── VELCrosschainBridge.sol       # Cross-chain bridge
│       ├── VELGovernanceController.sol   # DAO governance
│       ├── VELRewardsSystem.sol          # Rewards distribution
│       ├── VELAnonymousOrderExecutor.sol # Privacy orders
│       ├── VELDecentralizedVault.sol     # Multi-sig vault
│       └── VELUserFundVault.sol          # User fund isolation
│
├── 🧪 Tests
│   └── tests/
│       ├── test_pooled_trading_engine.py # Core engine tests
│       ├── test_graduated_bonus_system.py # Yield calculation tests
│       ├── test_smart_contract_manager.py # Contract manager tests
│       ├── test_contract_integration.py  # Integration tests
│       └── test_crosschain_contracts.py  # Cross-chain tests
│
├── 🐳 Infrastructure
│   ├── docker-compose.yml                # Local development
│   ├── docker-compose.aws.yml            # AWS deployment
│   ├── k8s/                              # Kubernetes manifests
│   └── iac/                              # Infrastructure as Code
│
└── 📚 Documentation
    └── docs/                             # Extended documentation
```

---

## 🧪 Testing

VEL maintains **1000+ tests** across the codebase:

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_pooled_trading_engine.py -v
pytest tests/test_graduated_bonus_system.py -v
pytest tests/test_smart_contract_manager.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run integration tests only
pytest tests/ -v -k "integration"
```

### Test Categories
- **Unit tests** — Individual function verification
- **Integration tests** — Component interaction
- **Contract tests** — Smart contract behavior
- **Edge case tests** — Boundary conditions
- **Failure tests** — Error handling paths

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest tests/ -v`)
5. Run linting (`flake8 .`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚖️ Legal Disclaimer

**VEL is experimental software provided "as is" without warranty of any kind.**

- This is not financial advice
- Trading cryptocurrencies involves substantial risk of loss
- Past performance does not guarantee future results
- The developers are not responsible for any financial losses
- Users are responsible for complying with their local regulations

**By using VEL, you acknowledge and accept these risks.**

---

<p align="center">
  <strong>Built for the DeFi community 🌐</strong>
</p>
