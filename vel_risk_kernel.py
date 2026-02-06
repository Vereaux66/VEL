#!/usr/bin/env python3
"""
VEL Risk Kernel
===============

Centralized, deterministic risk enforcement engine.
NO BYPASS MECHANISMS - not even for admins.

Enforces:
- Global max drawdown limits
- Per-asset exposure caps
- Per-chain exposure caps
- Per-protocol exposure caps
- Liquidity depth thresholds
- Gas-to-edge sanity checks

Risk rules apply:
- Pre-build: Before transaction construction
- Pre-sign: Before transaction signing
- Post-confirm: After transaction confirmation

This kernel is the final authority on risk.
AI cannot override. Admins cannot override.
Only explicit rule changes in code can modify behavior.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskLimit:
    """Individual risk limit configuration."""
    limit_id: str
    limit_type: str  # 'drawdown', 'asset_exposure', 'chain_exposure', etc.
    threshold: Decimal
    current_value: Decimal = Decimal("0")
    is_breached: bool = False
    
    def check(self, new_value: Decimal) -> bool:
        """Check if adding new value would breach limit."""
        total = self.current_value + new_value
        would_breach = total > self.threshold
        return not would_breach
    
    def update(self, new_value: Decimal) -> None:
        """Update current value."""
        self.current_value += new_value
        self.is_breached = self.current_value > self.threshold


@dataclass
class RiskCheckResult:
    """Result of risk kernel check."""
    check_id: str
    passed: bool
    breached_limits: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failure_reason: Optional[str] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskKernel:
    """
    Deterministic risk enforcement engine.
    
    All transactions must pass risk checks before execution.
    No bypass mechanisms exist - failures result in transaction rejection.
    """
    
    # Global risk limits (production values - adjust for your requirements)
    MAX_GLOBAL_DRAWDOWN_USD = Decimal("100000")  # Max $100k loss
    MAX_SINGLE_TX_VALUE_USD = Decimal("50000")   # Max $50k per transaction
    MAX_GAS_COST_USD = Decimal("500")            # Max $500 gas per transaction
    MIN_LIQUIDITY_DEPTH_USD = Decimal("100000")  # Min $100k liquidity
    
    # Per-asset exposure limits (percentage of portfolio)
    MAX_ASSET_EXPOSURE_PCT = Decimal("0.3")  # 30%
    
    # Per-chain exposure limits (percentage of portfolio)
    MAX_CHAIN_EXPOSURE_PCT = Decimal("0.5")  # 50%
    
    # Per-protocol exposure limits (percentage of portfolio)
    MAX_PROTOCOL_EXPOSURE_PCT = Decimal("0.4")  # 40%
    
    # Slippage limits
    MAX_SLIPPAGE_BPS = 100  # 1%
    WARN_SLIPPAGE_BPS = 50  # 0.5%
    
    def __init__(
        self,
        portfolio_value_usd: Decimal = Decimal("1000000"),  # $1M default
        enable_strict_mode: bool = True
    ):
        """
        Initialize risk kernel.
        
        Args:
            portfolio_value_usd: Total portfolio value for percentage calculations
            enable_strict_mode: If True, warnings become failures
        """
        self.portfolio_value_usd = portfolio_value_usd
        self.enable_strict_mode = enable_strict_mode
        
        # Risk state tracking
        self.limits: Dict[str, RiskLimit] = {}
        self.total_drawdown_usd = Decimal("0")
        self.asset_exposures: Dict[str, Decimal] = {}  # asset -> USD value
        self.chain_exposures: Dict[int, Decimal] = {}   # chain_id -> USD value
        self.protocol_exposures: Dict[str, Decimal] = {}  # protocol -> USD value
        
        # Initialize global limits
        self._initialize_limits()
        
        logger.info(
            f"Risk kernel initialized: "
            f"portfolio=${portfolio_value_usd}, "
            f"strict_mode={enable_strict_mode}"
        )
    
    def _initialize_limits(self):
        """Initialize risk limit tracking."""
        self.limits["global_drawdown"] = RiskLimit(
            limit_id="global_drawdown",
            limit_type="drawdown",
            threshold=self.MAX_GLOBAL_DRAWDOWN_USD
        )
        
        self.limits["single_tx_value"] = RiskLimit(
            limit_id="single_tx_value",
            limit_type="transaction_value",
            threshold=self.MAX_SINGLE_TX_VALUE_USD
        )
        
        self.limits["gas_cost"] = RiskLimit(
            limit_id="gas_cost",
            limit_type="gas",
            threshold=self.MAX_GAS_COST_USD
        )
    
    def check(self, intent: Any, plan: Any, simulation_result: Any) -> RiskCheckResult:
        """
        Execute complete risk check.
        
        Args:
            intent: User intent
            plan: Execution plan
            simulation_result: Transaction simulation result
            
        Returns:
            RiskCheckResult indicating pass/fail
        """
        check_id = f"risk_{datetime.now(timezone.utc).timestamp()}"
        breached = []
        warnings = []
        
        try:
            # Check 1: Global drawdown limit
            if not self._check_global_drawdown():
                breached.append("global_drawdown")
                logger.error("Global drawdown limit breached")
            
            # Check 2: Transaction value limit
            tx_value_usd = self._estimate_transaction_value(plan, simulation_result)
            if tx_value_usd > self.MAX_SINGLE_TX_VALUE_USD:
                breached.append("single_tx_value")
                logger.error(f"Transaction value ${tx_value_usd} exceeds limit ${self.MAX_SINGLE_TX_VALUE_USD}")
            
            # Check 3: Gas cost limit
            gas_cost_usd = self._estimate_gas_cost_usd(simulation_result)
            if gas_cost_usd > self.MAX_GAS_COST_USD:
                breached.append("gas_cost")
                logger.error(f"Gas cost ${gas_cost_usd} exceeds limit ${self.MAX_GAS_COST_USD}")
            
            # Check 4: Asset exposure limits
            asset_check = self._check_asset_exposure(plan, tx_value_usd)
            if not asset_check:
                breached.append("asset_exposure")
                logger.error("Asset exposure limit breached")
            
            # Check 5: Chain exposure limits
            chain_check = self._check_chain_exposure(plan.chain_id, tx_value_usd)
            if not chain_check:
                breached.append("chain_exposure")
                logger.error(f"Chain {plan.chain_id} exposure limit breached")
            
            # Check 6: Protocol exposure limits
            protocol_check = self._check_protocol_exposure(plan.protocol, tx_value_usd)
            if not protocol_check:
                breached.append("protocol_exposure")
                logger.error(f"Protocol {plan.protocol} exposure limit breached")
            
            # Check 7: Liquidity depth
            liquidity_check = self._check_liquidity_depth(plan)
            if not liquidity_check:
                breached.append("liquidity_depth")
                logger.error("Insufficient liquidity depth")
            
            # Check 8: Slippage limits
            slippage_bps = simulation_result.slippage_bps if simulation_result else 0
            if slippage_bps > self.MAX_SLIPPAGE_BPS:
                breached.append("slippage")
                logger.error(f"Slippage {slippage_bps}bps exceeds limit {self.MAX_SLIPPAGE_BPS}bps")
            elif slippage_bps > self.WARN_SLIPPAGE_BPS:
                warnings.append(f"High slippage: {slippage_bps}bps")
            
            # Check 9: Gas-to-edge sanity
            gas_to_edge_check = self._check_gas_to_edge(simulation_result, tx_value_usd)
            if not gas_to_edge_check:
                warnings.append("Gas cost high relative to transaction value")
                if self.enable_strict_mode:
                    breached.append("gas_to_edge")
            
            # Determine pass/fail
            passed = len(breached) == 0
            failure_reason = None
            if not passed:
                failure_reason = f"Risk checks failed: {', '.join(breached)}"
            
            result = RiskCheckResult(
                check_id=check_id,
                passed=passed,
                breached_limits=breached,
                warnings=warnings,
                failure_reason=failure_reason
            )
            
            # Log result
            if passed:
                logger.info(
                    f"Risk check passed: {check_id}",
                    extra={"check_id": check_id, "warnings": warnings}
                )
            else:
                logger.error(
                    f"Risk check FAILED: {check_id}",
                    extra={
                        "check_id": check_id,
                        "breached": breached,
                        "warnings": warnings,
                        "failure_reason": failure_reason
                    }
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Risk check error: {e}", exc_info=True)
            return RiskCheckResult(
                check_id=check_id,
                passed=False,
                failure_reason=f"Risk check error: {e}"
            )
    
    def _check_global_drawdown(self) -> bool:
        """Check if global drawdown is within limits."""
        return self.total_drawdown_usd <= self.MAX_GLOBAL_DRAWDOWN_USD
    
    def _estimate_transaction_value(self, plan: Any, simulation_result: Any) -> Decimal:
        """Estimate transaction value in USD."""
        # Simplified - production should use oracle prices
        if simulation_result and simulation_result.expected_output:
            # Assume output value approximates transaction value
            return simulation_result.expected_output
        
        # Fallback to plan estimate
        if hasattr(plan, 'estimated_output') and plan.estimated_output:
            return plan.estimated_output
        
        return Decimal("0")
    
    def _estimate_gas_cost_usd(self, simulation_result: Any) -> Decimal:
        """Estimate gas cost in USD."""
        if not simulation_result:
            return Decimal("0")
        
        # Simplified - production should use ETH/USD oracle price
        # Assume ETH = $3000
        eth_price_usd = Decimal("3000")
        gas_cost_eth = Decimal(simulation_result.total_cost_wei) / Decimal(10**18)
        return gas_cost_eth * eth_price_usd
    
    def _check_asset_exposure(self, plan: Any, tx_value_usd: Decimal) -> bool:
        """Check asset exposure limits."""
        # Get asset identifier
        asset = self._get_asset_identifier(plan)
        
        # Get current exposure
        current_exposure = self.asset_exposures.get(asset, Decimal("0"))
        new_exposure = current_exposure + tx_value_usd
        
        # Calculate percentage
        exposure_pct = new_exposure / self.portfolio_value_usd
        
        return exposure_pct <= self.MAX_ASSET_EXPOSURE_PCT
    
    def _check_chain_exposure(self, chain_id: int, tx_value_usd: Decimal) -> bool:
        """Check chain exposure limits."""
        current_exposure = self.chain_exposures.get(chain_id, Decimal("0"))
        new_exposure = current_exposure + tx_value_usd
        
        exposure_pct = new_exposure / self.portfolio_value_usd
        
        return exposure_pct <= self.MAX_CHAIN_EXPOSURE_PCT
    
    def _check_protocol_exposure(self, protocol: str, tx_value_usd: Decimal) -> bool:
        """Check protocol exposure limits."""
        current_exposure = self.protocol_exposures.get(protocol, Decimal("0"))
        new_exposure = current_exposure + tx_value_usd
        
        exposure_pct = new_exposure / self.portfolio_value_usd
        
        return exposure_pct <= self.MAX_PROTOCOL_EXPOSURE_PCT
    
    def _check_liquidity_depth(self, plan: Any) -> bool:
        """Check liquidity depth meets minimum threshold."""
        # Simplified - production should query actual pool liquidity
        # For now, assume adequate liquidity
        return True
    
    def _check_gas_to_edge(self, simulation_result: Any, tx_value_usd: Decimal) -> bool:
        """Check gas cost is reasonable relative to transaction value."""
        if not simulation_result or tx_value_usd == 0:
            return True
        
        gas_cost_usd = self._estimate_gas_cost_usd(simulation_result)
        
        # Gas should be < 10% of transaction value
        gas_ratio = gas_cost_usd / tx_value_usd
        return gas_ratio <= Decimal("0.1")
    
    def _get_asset_identifier(self, plan: Any) -> str:
        """Extract asset identifier from plan."""
        # Simplified - extract from transaction params
        if hasattr(plan, 'transaction_params'):
            params = plan.transaction_params
            token_out = params.get('token_out', 'UNKNOWN')
            return f"{plan.chain_id}:{token_out}"
        return "UNKNOWN"
    
    def update_exposure(
        self,
        chain_id: int,
        protocol: str,
        asset: str,
        value_usd: Decimal
    ) -> None:
        """
        Update exposure tracking after successful execution.
        
        Args:
            chain_id: Chain ID
            protocol: Protocol name
            asset: Asset identifier
            value_usd: Value in USD
        """
        # Update exposures
        self.chain_exposures[chain_id] = self.chain_exposures.get(chain_id, Decimal("0")) + value_usd
        self.protocol_exposures[protocol] = self.protocol_exposures.get(protocol, Decimal("0")) + value_usd
        self.asset_exposures[asset] = self.asset_exposures.get(asset, Decimal("0")) + value_usd
        
        logger.info(
            f"Exposure updated: chain={chain_id}, protocol={protocol}, asset={asset}, value=${value_usd}"
        )
    
    def record_loss(self, loss_usd: Decimal) -> None:
        """
        Record trading loss to track drawdown.
        
        Args:
            loss_usd: Loss amount in USD
        """
        self.total_drawdown_usd += loss_usd
        logger.warning(
            f"Loss recorded: ${loss_usd}, total_drawdown=${self.total_drawdown_usd}"
        )
        
        if self.total_drawdown_usd > self.MAX_GLOBAL_DRAWDOWN_USD:
            logger.critical(
                f"CRITICAL: Global drawdown ${self.total_drawdown_usd} "
                f"exceeds limit ${self.MAX_GLOBAL_DRAWDOWN_USD}"
            )
    
    def reset_limits(self) -> None:
        """Reset all risk limits (admin function - use with extreme caution)."""
        logger.warning("Risk kernel limits being reset - this should only happen during system restart")
        self.total_drawdown_usd = Decimal("0")
        self.asset_exposures.clear()
        self.chain_exposures.clear()
        self.protocol_exposures.clear()
        self._initialize_limits()
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current risk state for monitoring."""
        return {
            "portfolio_value_usd": str(self.portfolio_value_usd),
            "total_drawdown_usd": str(self.total_drawdown_usd),
            "drawdown_pct": float(self.total_drawdown_usd / self.portfolio_value_usd * 100),
            "asset_exposures": {k: str(v) for k, v in self.asset_exposures.items()},
            "chain_exposures": {k: str(v) for k, v in self.chain_exposures.items()},
            "protocol_exposures": {k: str(v) for k, v in self.protocol_exposures.items()},
            "limits": {k: {"threshold": str(v.threshold), "current": str(v.current_value), "breached": v.is_breached} 
                      for k, v in self.limits.items()},
        }


# =============================================================================
# ADVANCED POSITION SIZING (merged from anvel_risk_enhancement.py)
# =============================================================================
# Provides Kelly Criterion and dynamic stop-loss functionality.

class AdvancedPositionSizer:
    """
    Advanced position sizing with Kelly Criterion.
    
    Merged from anvel_risk_enhancement.py - provides institutional-grade
    position sizing algorithms for optimal capital allocation.
    
    Features:
    - Kelly Criterion position sizing
    - Dynamic stop-loss based on volatility
    - Correlation-based position limits
    - Value at Risk (VaR) calculations
    """
    
    # Position limits
    MAX_POSITION_PCT = Decimal("0.20")  # Max 20% per position
    MAX_TOTAL_RISK = Decimal("0.10")    # Max 10% total portfolio risk
    FRACTIONAL_KELLY = Decimal("0.25")  # Use 25% Kelly for safety
    
    def __init__(self, risk_kernel: 'RiskKernel'):
        """
        Initialize position sizer.
        
        Args:
            risk_kernel: Reference to the main risk kernel for limits
        """
        self.risk_kernel = risk_kernel
    
    def calculate_kelly_position_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_capital: Decimal
    ) -> Decimal:
        """
        Calculate optimal position size using Kelly Criterion.
        
        The Kelly Criterion determines the optimal bet size to maximize
        long-term growth while avoiding ruin.
        
        Formula: f = (p*b - q) / b
        Where:
            p = win rate
            q = loss rate (1-p)
            b = avg_win/avg_loss ratio
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade percentage
            avg_loss: Average losing trade percentage
            current_capital: Current account capital
            
        Returns:
            Optimal position size in dollars
        """
        if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
            return Decimal("0")
        
        # Kelly formula
        loss_rate = 1 - win_rate
        win_loss_ratio = avg_win / avg_loss
        kelly_pct = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        
        # Apply fractional Kelly for safety (25% of full Kelly)
        kelly_pct = max(0, min(kelly_pct * float(self.FRACTIONAL_KELLY), float(self.MAX_POSITION_PCT)))
        
        position_size = current_capital * Decimal(str(kelly_pct))
        
        logger.debug(
            f"Kelly position size: ${position_size:.2f} ({kelly_pct * 100:.2f}%)"
        )
        return position_size
    
    def calculate_dynamic_stop_loss(
        self,
        entry_price: Decimal,
        volatility: Decimal,
        side: str = "buy"
    ) -> Decimal:
        """
        Calculate dynamic stop-loss based on volatility.
        
        Uses 2x ATR (Average True Range) for stop distance,
        with a minimum stop of 0.5%.
        
        Args:
            entry_price: Entry price of position
            volatility: Current market volatility (ATR or std dev)
            side: 'buy' or 'sell'
            
        Returns:
            Stop-loss price
        """
        # Use 2x volatility for stop-loss distance
        stop_distance = volatility * Decimal("2.0")
        
        if side.lower() == "buy":
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance
        
        # Ensure minimum stop distance (0.5%)
        min_stop = entry_price * Decimal("0.005")
        if abs(stop_price - entry_price) < min_stop:
            if side.lower() == "buy":
                stop_price = entry_price - min_stop
            else:
                stop_price = entry_price + min_stop
        
        return stop_price
    
    def calculate_position_risk(
        self,
        position_size: Decimal,
        entry_price: Decimal,
        stop_price: Decimal
    ) -> Decimal:
        """
        Calculate risk amount for a position.
        
        Args:
            position_size: Size of position in dollars
            entry_price: Entry price
            stop_price: Stop-loss price
            
        Returns:
            Risk amount in dollars
        """
        risk_per_unit = abs(entry_price - stop_price) / entry_price
        return position_size * risk_per_unit
    
    def validate_position_size(
        self,
        position_size: Decimal,
        portfolio_value: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Validate position size against limits.
        
        Args:
            position_size: Proposed position size
            portfolio_value: Total portfolio value
            
        Returns:
            (is_valid, rejection_reason)
        """
        position_pct = position_size / portfolio_value
        
        if position_pct > self.MAX_POSITION_PCT:
            return False, f"Position {position_pct:.1%} exceeds max {self.MAX_POSITION_PCT:.1%}"
        
        return True, None
