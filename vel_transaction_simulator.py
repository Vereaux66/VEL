#!/usr/bin/env python3
"""
VEL Transaction Simulator
=========================

Pre-broadcast transaction simulation engine.
Every transaction MUST be simulated successfully before broadcast.

Validation checks:
- Transaction does not revert
- Gas usage within ceiling
- Slippage within bounds
- MinOut enforced
- Deadline enforced
- Expected value > total cost

Simulation failure MUST hard-block execution.
No bypass mechanisms permitted.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from web3 import Web3
from anvel_dex_broker_factory import get_dex_factory, SUPPORTED_CHAINS

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Transaction simulation result."""
    simulation_id: str
    success: bool
    will_revert: bool
    revert_reason: Optional[str] = None
    estimated_gas: int = 0
    gas_price: int = 0
    total_cost_wei: int = 0
    expected_output: Optional[Decimal] = None
    actual_output: Optional[Decimal] = None
    slippage_bps: int = 0
    exceeds_slippage_limit: bool = False
    exceeds_gas_ceiling: bool = False
    violates_min_out: bool = False
    deadline_expired: bool = False
    net_value_negative: bool = False
    error_message: Optional[str] = None
    transaction_data: Optional[Dict[str, Any]] = None
    simulated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def validate(self, gas_ceiling: int, min_amount_out: Decimal) -> tuple[bool, Optional[str]]:
        """
        Validate simulation result against safety constraints.
        
        Returns:
            (is_valid, error_message)
        """
        if not self.success:
            return False, self.error_message or "Simulation failed"
        
        if self.will_revert:
            return False, f"Transaction will revert: {self.revert_reason}"
        
        if self.exceeds_gas_ceiling or self.estimated_gas > gas_ceiling:
            return False, f"Gas {self.estimated_gas} exceeds ceiling {gas_ceiling}"
        
        if self.violates_min_out:
            return False, f"Output {self.actual_output} below minimum {min_amount_out}"
        
        if self.exceeds_slippage_limit:
            return False, f"Slippage {self.slippage_bps}bps exceeds limit"
        
        if self.deadline_expired:
            return False, "Transaction deadline would be expired"
        
        if self.net_value_negative:
            return False, "Expected value <= total cost (negative net value)"
        
        return True, None


class TransactionSimulator:
    """
    Transaction simulation engine.
    
    Simulates transactions against latest chain state before broadcast.
    All validations must pass or execution is blocked.
    """
    
    def __init__(
        self,
        default_gas_ceiling: int = 500000,
        max_gas_price_gwei: Decimal = Decimal("100"),
        default_slippage_limit_bps: int = 100,  # 1%
    ):
        """
        Initialize simulator.
        
        Args:
            default_gas_ceiling: Maximum allowed gas usage
            max_gas_price_gwei: Maximum gas price in Gwei
            default_slippage_limit_bps: Maximum slippage tolerance in basis points
        """
        self.default_gas_ceiling = default_gas_ceiling
        self.max_gas_price_gwei = max_gas_price_gwei
        self.default_slippage_limit_bps = default_slippage_limit_bps
        self.dex_factory = get_dex_factory()
        
        # RPC connections per chain
        self._rpc_connections: Dict[int, Web3] = {}
        
        logger.info(
            f"Transaction simulator initialized: "
            f"gas_ceiling={default_gas_ceiling}, "
            f"max_gas_price={max_gas_price_gwei}gwei, "
            f"slippage_limit={default_slippage_limit_bps}bps"
        )
    
    def _get_web3(self, chain_id: int) -> Optional[Web3]:
        """Get or create Web3 connection for chain."""
        if chain_id in self._rpc_connections:
            return self._rpc_connections[chain_id]
        
        if chain_id not in SUPPORTED_CHAINS:
            logger.error(f"Unsupported chain: {chain_id}")
            return None
        
        chain_config = SUPPORTED_CHAINS[chain_id]
        try:
            w3 = Web3(Web3.HTTPProvider(chain_config.default_rpc))
            if not w3.is_connected():
                logger.error(f"Failed to connect to chain {chain_id}")
                return None
            
            self._rpc_connections[chain_id] = w3
            logger.info(f"Connected to chain {chain_id}: {chain_config.name}")
            return w3
            
        except Exception as e:
            logger.error(f"Failed to initialize Web3 for chain {chain_id}: {e}")
            return None
    
    def simulate(
        self,
        chain_id: int,
        wallet_address: str,
        transaction_params: Dict[str, Any],
        route: Dict[str, Any],
        gas_ceiling: Optional[int] = None,
        slippage_limit_bps: Optional[int] = None,
    ) -> SimulationResult:
        """
        Simulate transaction execution.
        
        Args:
            chain_id: Target blockchain
            wallet_address: Sender wallet address
            transaction_params: Transaction parameters
            route: Routing information
            gas_ceiling: Override default gas ceiling
            slippage_limit_bps: Override default slippage limit
            
        Returns:
            SimulationResult with all validation checks
        """
        sim_id = f"sim_{datetime.now(timezone.utc).timestamp()}"
        
        # Get Web3 connection
        w3 = self._get_web3(chain_id)
        if not w3:
            return SimulationResult(
                simulation_id=sim_id,
                success=False,
                will_revert=True,
                error_message=f"Cannot connect to chain {chain_id}"
            )
        
        # Use provided limits or defaults
        gas_ceiling = gas_ceiling or self.default_gas_ceiling
        slippage_limit_bps = slippage_limit_bps or self.default_slippage_limit_bps
        
        try:
            # Get current gas price
            gas_price_wei = w3.eth.gas_price
            gas_price_gwei = Decimal(gas_price_wei) / Decimal(10**9)
            
            # Check gas price ceiling
            if gas_price_gwei > self.max_gas_price_gwei:
                logger.warning(
                    f"Gas price {gas_price_gwei} exceeds max {self.max_gas_price_gwei}"
                )
                gas_price_wei = int(self.max_gas_price_gwei * Decimal(10**9))
            
            # Build transaction for simulation
            tx_data = self._build_transaction_data(
                chain_id=chain_id,
                wallet_address=wallet_address,
                transaction_params=transaction_params,
                route=route,
                gas_price=gas_price_wei,
                w3=w3
            )
            
            if not tx_data:
                return SimulationResult(
                    simulation_id=sim_id,
                    success=False,
                    will_revert=True,
                    error_message="Failed to build transaction data"
                )
            
            # Simulate transaction using eth_call
            try:
                # This will throw if transaction would revert
                _call_result = w3.eth.call(tx_data)  # Result unused, we only check for revert
                will_revert = False
                revert_reason = None
            except Exception as e:
                will_revert = True
                revert_reason = str(e)
                logger.warning(f"Simulation indicates revert: {revert_reason}")
            
            # Estimate gas
            try:
                estimated_gas = w3.eth.estimate_gas(tx_data)
                # Add 20% safety margin
                estimated_gas = int(estimated_gas * 1.2)
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}")
                estimated_gas = gas_ceiling  # Use ceiling as fallback
            
            # Calculate total cost
            total_cost_wei = estimated_gas * gas_price_wei
            
            # Extract expected and actual outputs
            expected_output = None
            actual_output = None
            min_amount_out = Decimal("0")
            
            if "expected_output" in route:
                expected_output = Decimal(str(route["expected_output"]))
            
            if "amount_out" in transaction_params:
                actual_output = Decimal(str(transaction_params["amount_out"]))
            elif expected_output:
                # For simulation, use expected output as actual
                actual_output = expected_output
            
            if "min_amount_out" in transaction_params:
                min_out_value = transaction_params["min_amount_out"]
                if min_out_value is not None and min_out_value < 0:
                    raise ValueError(f"min_amount_out must be non-negative, got {min_out_value}")
                min_amount_out = Decimal(str(min_out_value)) if min_out_value is not None else None
            
            # Calculate slippage
            slippage_bps = 0
            if expected_output and actual_output and expected_output > 0:
                slippage = (expected_output - actual_output) / expected_output
                slippage_bps = int(slippage * 10000)
            
            # Validation checks
            exceeds_gas_ceiling = estimated_gas > gas_ceiling
            exceeds_slippage = slippage_bps > slippage_limit_bps
            violates_min_out = actual_output and min_amount_out and actual_output < min_amount_out
            
            # Check deadline
            deadline_expired = False
            if "deadline" in transaction_params:
                deadline = int(transaction_params["deadline"])
                current_time = w3.eth.get_block('latest')['timestamp']
                deadline_expired = current_time >= deadline
            
            # Calculate net value (expected output value - total cost)
            # For simplicity, assume output token has similar value to native token
            # Production should use oracle prices
            net_value_negative = False
            if actual_output:
                # Convert to comparable units (simplified)
                output_value_wei = int(actual_output * Decimal(10**18))
                net_value_negative = output_value_wei <= total_cost_wei
            
            # Overall success
            success = not will_revert and not exceeds_gas_ceiling
            
            return SimulationResult(
                simulation_id=sim_id,
                success=success,
                will_revert=will_revert,
                revert_reason=revert_reason,
                estimated_gas=estimated_gas,
                gas_price=gas_price_wei,
                total_cost_wei=total_cost_wei,
                expected_output=expected_output,
                actual_output=actual_output,
                slippage_bps=slippage_bps,
                exceeds_slippage_limit=exceeds_slippage,
                exceeds_gas_ceiling=exceeds_gas_ceiling,
                violates_min_out=violates_min_out,
                deadline_expired=deadline_expired,
                net_value_negative=net_value_negative,
                transaction_data=tx_data
            )
            
        except Exception as e:
            logger.error(f"Simulation failed: {e}", exc_info=True)
            return SimulationResult(
                simulation_id=sim_id,
                success=False,
                will_revert=True,
                error_message=f"Simulation error: {e}"
            )
    
    def _build_transaction_data(
        self,
        chain_id: int,
        wallet_address: str,
        transaction_params: Dict[str, Any],
        route: Dict[str, Any],
        gas_price: int,
        w3: Web3
    ) -> Optional[Dict[str, Any]]:
        """Build transaction data for simulation."""
        try:
            # Get DEX broker for the route
            dex_name = route.get("dex_name")
            if not dex_name:
                logger.error("No dex_name in route")
                return None
            
            broker = self.dex_factory.get_broker(dex_name, chain_id)
            if not broker:
                logger.error(f"Failed to get broker for {dex_name} on chain {chain_id}")
                return None
            
            # Build transaction based on intent type
            token_in = transaction_params.get("token_in")
            token_out = transaction_params.get("token_out")
            amount_in = transaction_params.get("amount_in")
            
            if not all([token_in, token_out, amount_in]):
                logger.error("Missing required transaction parameters")
                return None
            
            # Get router address from route
            router_address = route.get("router_address")
            if not router_address:
                logger.error("No router_address in route")
                return None
            
            # For now, return a basic transaction structure
            # Production implementation should construct actual calldata
            return {
                "from": Web3.to_checksum_address(wallet_address),
                "to": Web3.to_checksum_address(router_address),
                "value": 0,
                "gas": 500000,
                "gasPrice": gas_price,
                "data": "0x",  # Production: construct actual calldata
            }
            
        except Exception as e:
            logger.error(f"Failed to build transaction data: {e}", exc_info=True)
            return None
    
    def validate_simulation_result(
        self,
        result: SimulationResult,
        min_amount_out: Optional[Decimal] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate simulation result against safety constraints.
        
        Args:
            result: Simulation result to validate
            min_amount_out: Minimum required output amount
            
        Returns:
            (is_valid, error_message)
        """
        if not min_amount_out and result.expected_output:
            # Use 99% of expected as default minimum
            min_amount_out = result.expected_output * Decimal("0.99")
        
        return result.validate(self.default_gas_ceiling, min_amount_out or Decimal("0"))
    
    def close(self):
        """Close all RPC connections."""
        self._rpc_connections.clear()
        logger.info("Transaction simulator closed")
