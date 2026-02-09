#!/usr/bin/env python3
"""
ANVEL DEX Broker Factory

Decentralized exchange broker factory for cross-chain trading.
Supports Layer 1, Layer 2, and Layer 3 networks with multiple DEX protocols.

This module provides:
- Multi-chain DEX connections (10+ chains)
- Multi-protocol support (Uniswap, Sushiswap, Curve, etc.)
- Unified interface for all DEX operations
- Gas optimization and slippage protection

DECENTRALIZED ONLY: No centralized exchange support.
All trading happens on-chain through smart contracts.
"""

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from anvel_broker_base import BrokerBase

# Optional DEX broker import (requires web3)
try:
    from anvel_broker_dex_base import DEXBrokerBase
    DEX_BROKER_AVAILABLE = True
except ImportError:
    DEXBrokerBase = None
    DEX_BROKER_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==============================================================================
# CHAIN CONFIGURATION
# ==============================================================================

class ChainType(Enum):
    """Blockchain layer classification."""
    LAYER_1 = "layer_1"  # Ethereum, BSC, Avalanche
    LAYER_2 = "layer_2"  # Arbitrum, Optimism, Base, Polygon
    LAYER_3 = "layer_3"  # Application-specific chains


@dataclass
class ChainConfig:
    """Configuration for a blockchain network."""
    chain_id: int
    name: str
    chain_type: ChainType
    native_token: str
    default_rpc: str
    block_time_seconds: float
    is_active: bool = True


# Supported blockchain networks
SUPPORTED_CHAINS: Dict[int, ChainConfig] = {
    # Layer 1 Networks
    1: ChainConfig(
        chain_id=1,
        name="Ethereum Mainnet",
        chain_type=ChainType.LAYER_1,
        native_token="ETH",
        default_rpc="https://eth.llamarpc.com",
        block_time_seconds=12.0,
    ),
    56: ChainConfig(
        chain_id=56,
        name="BNB Smart Chain",
        chain_type=ChainType.LAYER_1,
        native_token="BNB",
        default_rpc="https://bsc-dataseed.binance.org",
        block_time_seconds=3.0,
    ),
    43114: ChainConfig(
        chain_id=43114,
        name="Avalanche C-Chain",
        chain_type=ChainType.LAYER_1,
        native_token="AVAX",
        default_rpc="https://api.avax.network/ext/bc/C/rpc",
        block_time_seconds=2.0,
    ),
    
    # Layer 2 Networks
    42161: ChainConfig(
        chain_id=42161,
        name="Arbitrum One",
        chain_type=ChainType.LAYER_2,
        native_token="ETH",
        default_rpc="https://arb1.arbitrum.io/rpc",
        block_time_seconds=0.25,
    ),
    10: ChainConfig(
        chain_id=10,
        name="Optimism",
        chain_type=ChainType.LAYER_2,
        native_token="ETH",
        default_rpc="https://mainnet.optimism.io",
        block_time_seconds=2.0,
    ),
    137: ChainConfig(
        chain_id=137,
        name="Polygon",
        chain_type=ChainType.LAYER_2,
        native_token="MATIC",
        default_rpc="https://polygon-rpc.com",
        block_time_seconds=2.0,
    ),
    8453: ChainConfig(
        chain_id=8453,
        name="Base",
        chain_type=ChainType.LAYER_2,
        native_token="ETH",
        default_rpc="https://mainnet.base.org",
        block_time_seconds=2.0,
    ),
    324: ChainConfig(
        chain_id=324,
        name="zkSync Era",
        chain_type=ChainType.LAYER_2,
        native_token="ETH",
        default_rpc="https://mainnet.era.zksync.io",
        block_time_seconds=1.0,
    ),
    59144: ChainConfig(
        chain_id=59144,
        name="Linea",
        chain_type=ChainType.LAYER_2,
        native_token="ETH",
        default_rpc="https://rpc.linea.build",
        block_time_seconds=2.0,
    ),
    
    # Layer 3 Networks
    660279: ChainConfig(
        chain_id=660279,
        name="Xai",
        chain_type=ChainType.LAYER_3,
        native_token="XAI",
        default_rpc="https://xai-chain.net/rpc",
        block_time_seconds=0.25,
    ),
}


# ==============================================================================
# DEX CONFIGURATION
# ==============================================================================

@dataclass
class DEXConfig:
    """Configuration for a DEX protocol."""
    name: str
    protocol_type: str  # uniswap_v2, uniswap_v3, curve, balancer
    supported_chains: List[int]
    router_addresses: Dict[int, str]  # chain_id -> router address
    fee_tiers: List[int]  # Available fee tiers in basis points
    is_active: bool = True


# Supported DEX protocols
SUPPORTED_DEXES: Dict[str, DEXConfig] = {
    "uniswap_v3": DEXConfig(
        name="Uniswap V3",
        protocol_type="uniswap_v3",
        supported_chains=[1, 42161, 10, 137, 8453],
        router_addresses={
            1: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            42161: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            10: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            137: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            8453: "0x2626664c2603336E57B271c5C0b26F421741e481",
        },
        fee_tiers=[100, 500, 3000, 10000],  # 0.01%, 0.05%, 0.3%, 1%
    ),
    "pancakeswap_v3": DEXConfig(
        name="PancakeSwap V3",
        protocol_type="uniswap_v3",
        supported_chains=[56, 1, 42161, 324],
        router_addresses={
            56: "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
            1: "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
            42161: "0x32226588378236Fd0c7c4053999F88aC0e5cAc77",
            324: "0xD70C70AD87aa8D45b8D59600342FB3AEe76E3c68",
        },
        fee_tiers=[100, 500, 2500, 10000],
    ),
    "pancakeswap_v2": DEXConfig(
        name="PancakeSwap V2",
        protocol_type="uniswap_v2",
        supported_chains=[56],
        router_addresses={
            56: "0x10ED43C718714eb63d5aA57B78B54704E256024E",  # BSC Router V2
        },
        fee_tiers=[25],  # 0.25% standard
    ),
    "sushiswap": DEXConfig(
        name="SushiSwap",
        protocol_type="uniswap_v2",
        supported_chains=[1, 42161, 10, 137, 43114],
        router_addresses={
            1: "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
            42161: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            10: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            137: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            43114: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        },
        fee_tiers=[30],  # 0.3% standard
    ),
    "curve": DEXConfig(
        name="Curve Finance",
        protocol_type="curve",
        supported_chains=[1, 42161, 10, 137],
        router_addresses={
            1: "0x99a58482BD75cbab83b27EC03CA68fF489b5788f",
            42161: "0xF0d4c12A5768D806021F80a262B4d39d26C58b8D",
            10: "0x0DCDED3545D565bA3B19E683431381007245d983",
            137: "0x0DCDED3545D565bA3B19E683431381007245d983",
        },
        fee_tiers=[4],  # ~0.04% for stablecoin pools
    ),
    "velodrome": DEXConfig(
        name="Velodrome",
        protocol_type="solidly",
        supported_chains=[10],
        router_addresses={
            10: "0xa062aE8A9c5e11aaA026fc2670B0D65cCc8B2858",
        },
        fee_tiers=[5, 30, 100],
    ),
    "aerodrome": DEXConfig(
        name="Aerodrome",
        protocol_type="solidly",
        supported_chains=[8453],
        router_addresses={
            8453: "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        },
        fee_tiers=[5, 30, 100],
    ),
    "camelot": DEXConfig(
        name="Camelot",
        protocol_type="uniswap_v2",
        supported_chains=[42161],
        router_addresses={
            42161: "0xc873fEcbd354f5A56E00E710B90EF4201db2448d",
        },
        fee_tiers=[30],
    ),
    "quickswap": DEXConfig(
        name="QuickSwap",
        protocol_type="uniswap_v3",
        supported_chains=[137],
        router_addresses={
            137: "0xf5b509bB0909a69B1c207E495f687a596C168E12",
        },
        fee_tiers=[100, 500, 3000, 10000],
    ),
    "trader_joe": DEXConfig(
        name="Trader Joe",
        protocol_type="lb_dex",
        supported_chains=[43114, 42161],
        router_addresses={
            43114: "0xb4315e873dBcf96Ffd0acd8EA43f689D8c20fB30",
            42161: "0xb4315e873dBcf96Ffd0acd8EA43f689D8c20fB30",
        },
        fee_tiers=[10, 20, 50, 100],
    ),
    "syncswap": DEXConfig(
        name="SyncSwap",
        protocol_type="uniswap_v2",
        supported_chains=[324, 59144],
        router_addresses={
            324: "0x2da10A1e27bF85cEdD8FFb1AbBe97e53391C0295",
            59144: "0x80e38291e06339d10AAB483C65695D004dBD5C69",
        },
        fee_tiers=[30],
    ),
}


# ==============================================================================
# DEX BROKER FACTORY
# ==============================================================================

class DEXBrokerFactory:
    """
    Factory for creating DEX broker instances.
    
    Provides unified access to multiple DEX protocols across multiple chains.
    All brokers implement the same interface for consistent trading operations.
    """

    def __init__(self):
        """Initialize the DEX broker factory."""
        self._brokers: Dict[str, DEXBrokerBase] = {}
        self._initialized_chains: set = set()

    def get_supported_chains(self) -> List[ChainConfig]:
        """Get list of supported blockchain networks."""
        return [c for c in SUPPORTED_CHAINS.values() if c.is_active]

    def get_supported_dexes(self, chain_id: Optional[int] = None) -> List[DEXConfig]:
        """
        Get list of supported DEX protocols.
        
        Args:
            chain_id: Optional chain ID to filter DEXes by
            
        Returns:
            List of DEX configurations
        """
        dexes = [d for d in SUPPORTED_DEXES.values() if d.is_active]
        
        if chain_id:
            dexes = [d for d in dexes if chain_id in d.supported_chains]
        
        return dexes

    def get_broker(
        self,
        dex_name: str,
        chain_id: int,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> Optional[DEXBrokerBase]:
        """
        Get or create a DEX broker instance.
        
        Args:
            dex_name: Name of the DEX protocol
            chain_id: Blockchain chain ID
            rpc_url: Optional RPC URL (uses default if not provided)
            private_key: Private key for signing transactions
            
        Returns:
            DEX broker instance or None if not supported
        """
        # Validate inputs
        if dex_name not in SUPPORTED_DEXES:
            logger.error("Unsupported DEX: %s", dex_name)
            return None
        
        if chain_id not in SUPPORTED_CHAINS:
            logger.error("Unsupported chain: %d", chain_id)
            return None
        
        dex_config = SUPPORTED_DEXES[dex_name]
        chain_config = SUPPORTED_CHAINS[chain_id]
        
        if chain_id not in dex_config.supported_chains:
            logger.error(
                "DEX %s not available on chain %s",
                dex_name, chain_config.name
            )
            return None
        
        # Generate broker key
        broker_key = f"{dex_name}:{chain_id}"
        
        # Return cached broker if available
        if broker_key in self._brokers:
            return self._brokers[broker_key]
        
        # Get RPC URL
        rpc = rpc_url or os.getenv(
            f"{dex_name.upper()}_RPC_{chain_id}",
            chain_config.default_rpc
        )
        
        # Get private key from env if not provided
        if not private_key:
            private_key = os.getenv("VEL_PRIVATE_KEY") or os.getenv("ANVEL_PRIVATE_KEY")
        
        try:
            # Create appropriate broker based on protocol type and DEX name
            if dex_config.protocol_type == "uniswap_v3":
                from anvel_broker_uniswap import UniswapV3Broker
                broker = UniswapV3Broker(
                    rpc_url=rpc,
                    private_key=private_key,
                    chain_id=chain_id,
                    router_address=dex_config.router_addresses.get(chain_id),
                )
            elif dex_name == "pancakeswap_v2" or (dex_name.startswith("pancakeswap") and chain_id == 56):
                # Use PancakeSwap broker for BSC
                from anvel_broker_pancakeswap import PancakeSwapBroker
                broker = PancakeSwapBroker(
                    rpc_url=rpc,
                    private_key=private_key,
                )
            elif dex_config.protocol_type == "uniswap_v2":
                # Use base DEX broker for V2-style
                broker = DEXBrokerBase(
                    rpc_url=rpc,
                    private_key=private_key,
                    chain_id=chain_id,
                )
            else:
                # Generic DEX broker
                broker = DEXBrokerBase(
                    rpc_url=rpc,
                    private_key=private_key,
                    chain_id=chain_id,
                )
            
            self._brokers[broker_key] = broker
            logger.info(
                "Created broker: %s on %s",
                dex_name, chain_config.name
            )
            
            return broker
            
        except Exception as e:
            logger.error(
                "Failed to create broker %s on chain %d: %s",
                dex_name, chain_id, e
            )
            return None

    def get_best_route(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best trading route across all DEXes on a chain.
        
        Args:
            chain_id: Blockchain chain ID
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to trade
            
        Returns:
            Best route information or None if no route found
        """
        best_route = None
        best_output = Decimal("0")
        
        # Check all DEXes on this chain
        for dex_name, dex_config in SUPPORTED_DEXES.items():
            if chain_id not in dex_config.supported_chains:
                continue
            
            try:
                broker = self.get_broker(dex_name, chain_id)
                if not broker:
                    continue
                
                # Get quote
                quote = broker.get_quote(token_in, token_out, amount_in)
                if quote and quote.get('amount_out', 0) > best_output:
                    best_output = Decimal(str(quote['amount_out']))
                    best_route = {
                        'dex_name': dex_name,
                        'chain_id': chain_id,
                        'token_in': token_in,
                        'token_out': token_out,
                        'amount_in': amount_in,
                        'expected_output': best_output,
                        'router_address': dex_config.router_addresses.get(chain_id),
                    }
                    
            except Exception as e:
                logger.debug("Quote failed for %s: %s", dex_name, e)
                continue
        
        return best_route

    def close_all(self):
        """Close all broker connections."""
        for broker in self._brokers.values():
            try:
                if hasattr(broker, 'close'):
                    broker.close()
            except Exception as e:
                logger.warning("Error closing broker: %s", e)
        
        self._brokers.clear()
        logger.info("All brokers closed")


# ==============================================================================
# GLOBAL FACTORY INSTANCE
# ==============================================================================

_factory_instance: Optional[DEXBrokerFactory] = None


def get_dex_factory() -> DEXBrokerFactory:
    """Get the global DEX broker factory instance."""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = DEXBrokerFactory()
    return _factory_instance


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

def get_dex_broker(
    dex_name: str,
    chain_id: int,
    **kwargs
) -> Optional[DEXBrokerBase]:
    """
    Convenience function to get a DEX broker.
    
    Args:
        dex_name: Name of the DEX protocol
        chain_id: Blockchain chain ID
        **kwargs: Additional arguments for broker creation
        
    Returns:
        DEX broker instance
    """
    return get_dex_factory().get_broker(dex_name, chain_id, **kwargs)


def list_available_dexes(chain_id: Optional[int] = None) -> List[str]:
    """
    List available DEX names.
    
    Args:
        chain_id: Optional chain ID to filter by
        
    Returns:
        List of DEX names
    """
    dexes = get_dex_factory().get_supported_dexes(chain_id)
    return [d.name for d in dexes]


def list_available_chains() -> List[str]:
    """
    List available chain names.
    
    Returns:
        List of chain names
    """
    chains = get_dex_factory().get_supported_chains()
    return [c.name for c in chains]


# ==============================================================================
# MODULE EXPORTS
# ==============================================================================

__all__ = [
    # Enums
    'ChainType',
    # Data classes
    'ChainConfig',
    'DEXConfig',
    # Constants
    'SUPPORTED_CHAINS',
    'SUPPORTED_DEXES',
    # Factory
    'DEXBrokerFactory',
    'get_dex_factory',
    # Convenience functions
    'get_dex_broker',
    'list_available_dexes',
    'list_available_chains',
]
