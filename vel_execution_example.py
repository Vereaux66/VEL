#!/usr/bin/env python3
"""
VEL Production Execution System - Integration Example
=====================================================

Complete end-to-end example demonstrating:
1. Intent submission
2. Validation and routing
3. Simulation
4. Risk checking
5. Signing
6. Broadcasting
7. Confirmation
8. State reconciliation

This example shows how all components work together
in a production-safe DeFi execution pipeline.
"""

import logging
import sys
from decimal import Decimal

from vel_execution_core import (
    Intent,
    IntentType,
    create_execution_core
)
from vel_risk_kernel import RiskKernel
from vel_state_ledger import StateLedger
from vel_circuit_breaker import CircuitBreakerManager
from vel_execution_queue import ExecutionQueue, IntentPriority

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_swap_execution():
    """Example: Execute a swap intent."""
    logger.info("=" * 80)
    logger.info("Example: Swap Execution")
    logger.info("=" * 80)
    
    # Initialize execution core
    execution_core = create_execution_core()
    
    # Create swap intent
    intent = Intent(
        intent_id="swap_001",
        intent_type=IntentType.SWAP,
        wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
        chain_id=1,  # Ethereum mainnet
        parameters={
            "token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "token_out": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "amount_in": "1000.0",  # 1000 USDC
            "slippage_bps": 50,  # 0.5%
            "min_amount_out": "0.0",
            "deadline": 300  # 5 minutes
        }
    )
    
    logger.info(f"Created intent: {intent.intent_id}")
    
    # Execute intent
    try:
        result = execution_core.execute_intent(intent)
        
        logger.info(f"Execution status: {result.status.value}")
        logger.info(f"Execution ID: {result.execution_id}")
        
        if result.plan:
            logger.info(f"Protocol: {result.plan.protocol}")
            logger.info(f"Estimated gas: {result.plan.estimated_gas}")
        
        if result.simulation_result:
            logger.info(f"Simulation passed: {result.simulation_result.success}")
            logger.info(f"Estimated gas: {result.simulation_result.estimated_gas}")
        
        if result.risk_check_result:
            logger.info(f"Risk check passed: {result.risk_check_result.passed}")
            if result.risk_check_result.warnings:
                logger.warning(f"Warnings: {result.risk_check_result.warnings}")
        
        if result.tx_hash:
            logger.info(f"Transaction hash: {result.tx_hash}")
        
        if result.error_message:
            logger.error(f"Error: {result.error_message}")
        
        return result
        
    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        return None


def example_queued_execution():
    """Example: Queue-based execution with multiple intents."""
    logger.info("=" * 80)
    logger.info("Example: Queued Execution")
    logger.info("=" * 80)
    
    # Initialize components
    execution_core = create_execution_core()
    execution_queue = ExecutionQueue(
        max_queue_depth=1000,
        worker_threads=4
    )
    
    # Set up execution handler
    def handle_intent(intent_data: dict) -> bool:
        """Process intent from queue."""
        try:
            intent = Intent(
                intent_id=intent_data["intent_id"],
                intent_type=IntentType[intent_data["intent_type"]],
                wallet_address=intent_data["wallet_address"],
                chain_id=intent_data["chain_id"],
                parameters=intent_data["parameters"]
            )
            
            result = execution_core.execute_intent(intent)
            return result.status.value == "completed"
            
        except Exception as e:
            logger.error(f"Intent handling error: {e}", exc_info=True)
            return False
    
    execution_queue.set_execution_handler(handle_intent)
    
    # Start queue processing
    execution_queue.start()
    
    # Enqueue multiple intents
    intents = [
        {
            "intent_id": f"swap_{i:03d}",
            "intent_type": "SWAP",
            "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            "chain_id": 1,
            "parameters": {
                "token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "token_out": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "amount_in": str(100 * (i + 1)),
                "slippage_bps": 50,
            }
        }
        for i in range(5)
    ]
    
    for intent_data in intents:
        success = execution_queue.enqueue(
            intent_id=intent_data["intent_id"],
            wallet_address=intent_data["wallet_address"],
            intent_data=intent_data,
            priority=IntentPriority.NORMAL
        )
        
        if success:
            logger.info(f"Enqueued: {intent_data['intent_id']}")
        else:
            logger.error(f"Failed to enqueue: {intent_data['intent_id']}")
    
    # Wait for processing
    import time
    logger.info("Waiting for queue processing...")
    time.sleep(5)
    
    # Get metrics
    metrics = execution_queue.get_metrics()
    logger.info(f"Queue metrics: {metrics}")
    
    # Stop queue
    execution_queue.stop()
    
    logger.info("Queue processing complete")


def example_risk_enforcement():
    """Example: Risk kernel enforcement."""
    logger.info("=" * 80)
    logger.info("Example: Risk Enforcement")
    logger.info("=" * 80)
    
    # Initialize risk kernel
    risk_kernel = RiskKernel(
        portfolio_value_usd=Decimal("1000000"),  # $1M
        enable_strict_mode=True
    )
    
    # Check current risk state
    state = risk_kernel.get_current_state()
    logger.info(f"Risk state: {state}")
    
    # Simulate recording exposures
    risk_kernel.update_exposure(
        chain_id=1,
        protocol="uniswap_v3",
        asset="1:WETH",
        value_usd=Decimal("100000")  # $100k WETH exposure
    )
    
    risk_kernel.update_exposure(
        chain_id=56,
        protocol="pancakeswap_v3",
        asset="56:BNB",
        value_usd=Decimal("50000")  # $50k BNB exposure
    )
    
    # Check updated state
    state = risk_kernel.get_current_state()
    logger.info(f"Updated risk state: {state}")
    
    # Simulate loss
    risk_kernel.record_loss(Decimal("5000"))  # $5k loss
    
    logger.info(f"Total drawdown: ${risk_kernel.total_drawdown_usd}")


def example_circuit_breaker():
    """Example: Circuit breaker triggering."""
    logger.info("=" * 80)
    logger.info("Example: Circuit Breaker")
    logger.info("=" * 80)
    
    # Initialize circuit breaker
    cb = CircuitBreakerManager()
    
    # Check status
    logger.info(f"Is halted: {cb.is_halted()}")
    
    # Record some failures
    for i in range(15):
        if i % 3 == 0:
            cb.record_success()
        else:
            cb.record_failure()
    
    # Check metrics
    metrics = cb.get_metrics()
    logger.info(f"Metrics: {metrics}")
    
    # Check if halted due to failure rate
    logger.info(f"Is halted: {cb.is_halted()}")
    
    if cb.is_halted():
        state = cb.get_state()
        logger.info(f"Halt state: {state}")


def example_state_ledger():
    """Example: State ledger and reconciliation."""
    logger.info("=" * 80)
    logger.info("Example: State Ledger")
    logger.info("=" * 80)
    
    # Initialize ledger
    ledger = StateLedger()
    
    # Update balance
    wallet = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    chain_id = 1
    
    ledger.update_balance(
        wallet_address=wallet,
        chain_id=chain_id,
        token_address="native",
        balance=Decimal("10.5"),  # 10.5 ETH
        pending_delta=Decimal("-0.1")  # 0.1 ETH pending
    )
    
    # Get balance
    balance = ledger.get_balance(wallet, chain_id, "native")
    if balance:
        logger.info(f"Balance: {balance.balance} ETH")
        logger.info(f"Pending delta: {balance.pending_delta} ETH")
        logger.info(f"Effective balance: {balance.effective_balance()} ETH")
    
    # Record PnL
    ledger.record_pnl(
        wallet_address=wallet,
        chain_id=chain_id,
        intent_id="swap_001",
        execution_id="exec_001",
        realized_pnl=Decimal("50.0"),  # $50 profit
        gas_spent=Decimal("10.0"),     # $10 gas
        gas_expected=Decimal("8.0")    # Expected $8
    )
    
    # Get total PnL
    total_pnl = ledger.get_total_pnl(wallet, chain_id)
    logger.info(f"Total PnL: ${total_pnl}")


def main():
    """Run all examples."""
    logger.info("VEL Production Execution System - Integration Examples")
    logger.info("=" * 80)
    
    try:
        # Example 1: Single swap execution
        example_swap_execution()
        print()
        
        # Example 2: Risk enforcement
        example_risk_enforcement()
        print()
        
        # Example 3: Circuit breaker
        example_circuit_breaker()
        print()
        
        # Example 4: State ledger
        example_state_ledger()
        print()
        
        # Example 5: Queued execution (commented out as it waits)
        # example_queued_execution()
        
        logger.info("=" * 80)
        logger.info("All examples completed successfully")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
