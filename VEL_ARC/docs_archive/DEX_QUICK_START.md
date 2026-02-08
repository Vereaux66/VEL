# VEL DEX Quick Start Guide

## Installation

Add to your `Cargo.toml`:
```toml
[dependencies]
vel-dex = { path = "vel-trading/vel-dex" }
```

## Basic Usage

### 1. Initialize Adapter

```rust
use vel_dex::{UniswapV3Adapter, ChainConfig, SlippageConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load chain configuration
    let chain_config = ChainConfig::ethereum_mainnet();
    
    // Initialize adapter (read-only mode)
    let adapter = UniswapV3Adapter::new(
        &chain_config.rpc_url,
        None, // No private key = read-only
        chain_config,
    ).await?;
    
    println!("Connected to {}", adapter.name());
    Ok(())
}
```

### 2. Get Token Quote

```rust
use ethers::types::{Address, U256};

// Token addresses (example: USDC -> WETH)
let usdc: Address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".parse()?;
let weth: Address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".parse()?;

// Amount: 1,000 USDC (6 decimals)
let amount_in = U256::from(1_000_000_000);

// Get quote with 0.5% slippage tolerance
let slippage = SlippageConfig::new(50)?;
let quote = adapter.get_quote(usdc, weth, amount_in, slippage).await?;

println!("Expected output: {}", quote.amount_out);
println!("Price: {}", quote.price);
println!("Price impact: {}%", quote.price_impact);
```

### 3. Check Balances

```rust
// Check native balance (ETH, BNB, etc.)
let native_balance = adapter.get_native_balance().await?;
println!("Native balance: {}", native_balance);

// Check ERC-20 token balance
let token_balance = adapter.get_token_balance(usdc).await?;
println!("USDC balance: {}", token_balance);
```

### 4. Execute Swap (with wallet)

```rust
// Initialize adapter with private key for signing
let private_key = std::env::var("PRIVATE_KEY")?;
let adapter = UniswapV3Adapter::new(
    &chain_config.rpc_url,
    Some(&private_key),
    chain_config,
).await?;

// Get quote
let quote = adapter.get_quote(usdc, weth, amount_in, slippage).await?;

// Calculate minimum output with slippage protection
let min_amount_out = slippage.calculate_min_amount_out(quote.amount_out);

// Execute swap
let result = adapter.execute_swap(
    usdc,
    weth,
    amount_in,
    min_amount_out,
    quote.deadline,
).await?;

println!("Swap executed: {:?}", result.tx_hash);
println!("Gas used: {}", result.gas_used);
```

## PancakeSwap on BSC

```rust
use vel_dex::{PancakeSwapAdapter, ChainConfig};

// BSC configuration
let bsc_config = ChainConfig::bsc_mainnet();

// Initialize PancakeSwap adapter
let pancake = PancakeSwapAdapter::new(
    &bsc_config.rpc_url,
    Some(&private_key),
    bsc_config,
).await?;

// Same interface as Uniswap!
let quote = pancake.get_quote(token_in, token_out, amount, slippage).await?;
```

## Multi-Chain Support

```rust
// Ethereum
let eth = ChainConfig::ethereum_mainnet();

// BSC
let bsc = ChainConfig::bsc_mainnet();

// Polygon
let polygon = ChainConfig::polygon_mainnet();

// Arbitrum
let arbitrum = ChainConfig::arbitrum_mainnet();

// Optimism
let optimism = ChainConfig::optimism_mainnet();

// Base
let base = ChainConfig::base_mainnet();

// Testnets
let sepolia = ChainConfig::ethereum_sepolia();
let bsc_test = ChainConfig::bsc_testnet();
```

## Error Handling

```rust
use vel_dex::DexError;

match adapter.execute_swap(...).await {
    Ok(result) => println!("Success: {:?}", result.tx_hash),
    Err(DexError::InsufficientLiquidity { requested, available }) => {
        eprintln!("Not enough liquidity: need {}, have {}", requested, available);
    }
    Err(DexError::SlippageExceeded { expected, actual }) => {
        eprintln!("Slippage too high: expected {}, got {}", expected, actual);
    }
    Err(DexError::TransactionFailed(msg)) => {
        eprintln!("Transaction failed: {}", msg);
    }
    Err(e) => eprintln!("Error: {}", e),
}
```

## Token Approvals

```rust
// Check if token is approved for spending
let token: Address = "0x...".parse()?;
let amount = U256::from(1_000_000_000);

if !adapter.check_allowance(token, amount).await? {
    println!("Approving token...");
    
    // Approve with unlimited allowance
    let tx_hash = adapter.approve_token(token, U256::MAX).await?;
    
    println!("Approved: {:?}", tx_hash);
}
```

## Gas Price Configuration

```rust
// Custom chain with gas price limits
let custom_config = ChainConfig {
    chain_id: 1,
    name: "Ethereum".to_string(),
    rpc_url: "https://eth.llamarpc.com".to_string(),
    native_symbol: "ETH".to_string(),
    block_time_ms: 12000,
    confirmation_blocks: 2,
    gas_price_gwei: GasPriceConfig {
        min_gwei: 10.0,
        max_gwei: 100.0,  // Won't pay more than 100 gwei
        default_gwei: 30.0,
    },
};
```

## Token Information

```rust
// Get token metadata
let token_info = adapter.get_token_info(token_address).await?;

println!("Symbol: {}", token_info.symbol);
println!("Name: {}", token_info.name);
println!("Decimals: {}", token_info.decimals);
```

## Health Checks

```rust
// Check if DEX is accessible
if adapter.health_check().await? {
    println!("DEX is healthy");
} else {
    println!("DEX is unavailable");
}
```

## Utility Functions

```rust
use vel_dex::traits::utils;
use rust_decimal::Decimal;

// Convert human-readable to token units
let amount = Decimal::new(1000, 0); // 1000.0
let decimals = 6; // USDC has 6 decimals
let token_units = utils::to_token_units(amount, decimals)?;

// Convert token units to human-readable
let human_readable = utils::from_token_units(token_units, decimals)?;

// Calculate price
let price = utils::calculate_price(
    amount_in,
    amount_out,
    decimals_in,
    decimals_out,
)?;

// Validate inputs
utils::validate_token_address(address)?;
utils::validate_amount(amount)?;
```

## Environment Variables

```bash
# RPC endpoints
export ETH_RPC_URL="https://eth.llamarpc.com"
export BSC_RPC_URL="https://bsc-dataseed1.binance.org"

# Private key (NEVER commit this!)
export PRIVATE_KEY="0x..."

# Optional: Override gas settings
export MAX_GAS_PRICE_GWEI="100"
export SLIPPAGE_BPS="50"
```

## Complete Example

```rust
use vel_dex::{
    UniswapV3Adapter, DexAdapter, SlippageConfig,
    ChainConfig, DexError,
};
use ethers::types::{Address, U256};
use std::env;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Load configuration
    let rpc_url = env::var("ETH_RPC_URL")
        .unwrap_or_else(|_| "https://eth.llamarpc.com".to_string());
    let private_key = env::var("PRIVATE_KEY").ok();
    
    // Initialize
    let chain_config = ChainConfig::ethereum_mainnet();
    let adapter = UniswapV3Adapter::new(
        &rpc_url,
        private_key.as_deref(),
        chain_config,
    ).await?;
    
    println!("✓ Connected to {}", adapter.name());
    
    // Token addresses
    let usdc: Address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".parse()?;
    let weth: Address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".parse()?;
    
    // Amount to swap: 1000 USDC
    let amount_in = U256::from(1_000_000_000);
    
    // Configure slippage: 0.5%
    let slippage = SlippageConfig::new(50)?;
    
    // Get quote
    println!("Getting quote...");
    let quote = adapter.get_quote(usdc, weth, amount_in, slippage).await?;
    
    println!("✓ Quote received:");
    println!("  Input: {} USDC", amount_in);
    println!("  Output: {} WETH", quote.amount_out);
    println!("  Price: {} WETH per USDC", quote.price);
    println!("  Impact: {}%", quote.price_impact);
    println!("  Gas estimate: {}", quote.gas_estimate);
    
    // Execute swap (only if we have a private key)
    if private_key.is_some() {
        println!("\nExecuting swap...");
        let min_out = slippage.calculate_min_amount_out(quote.amount_out);
        
        match adapter.execute_swap(
            usdc,
            weth,
            amount_in,
            min_out,
            quote.deadline,
        ).await {
            Ok(result) => {
                println!("✓ Swap successful!");
                println!("  Tx hash: {:?}", result.tx_hash);
                println!("  Gas used: {}", result.gas_used);
                println!("  Block: {}", result.block_number);
            }
            Err(e) => {
                eprintln!("✗ Swap failed: {}", e);
            }
        }
    } else {
        println!("\n⚠ Skipping swap (no private key provided)");
        println!("  Set PRIVATE_KEY env var to execute swaps");
    }
    
    Ok(())
}
```

## Testing

```bash
# Run all vel-dex tests
cargo test -p vel-dex

# Run with logging
RUST_LOG=debug cargo test -p vel-dex -- --nocapture

# Run specific test
cargo test -p vel-dex test_uniswap_v3_creation
```

## Further Documentation

- Full API documentation: `cargo doc --no-deps -p vel-dex --open`
- README: `vel-trading/vel-dex/README.md`
- Implementation details: `IMPLEMENTATION_SUMMARY.md`
- Python reference: `anvel_broker_dex_base.py`, `anvel_broker_uniswap.py`

## Support

For issues or questions:
1. Check the comprehensive README in `vel-trading/vel-dex/`
2. Review error messages (they are explicit and helpful)
3. Consult the Python reference implementations
4. Refer to archived CEX code in `VEL_ARC/cex_originals/` for patterns

---

**Quick Start Version**: 1.0.0
**Last Updated**: 2025-02-04
**Status**: Production Ready ✅
