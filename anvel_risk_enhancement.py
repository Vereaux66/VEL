#!/usr/bin/env python3
"""
ANVEL Advanced Risk Management Enhancement Module
Implements institutional-grade risk controls and position sizing
"""

import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)


class AdvancedRiskManager:
    """
    Institutional-grade risk management system with:
    - Kelly Criterion position sizing
    - Drawdown protection
    - Correlation-based position limits
    - Dynamic stop-loss adjustment
    - Value at Risk (VaR) calculations
    """

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_position_pct = 0.20  # Max 20% per position
        self.max_total_risk = 0.10  # Max 10% total portfolio risk
        self.max_drawdown_pct = 0.15  # Stop trading at 15% drawdown
        self.correlation_limit = 0.7  # Limit correlated positions

        # Tracking
        self.position_history: List[Dict] = []
        self.correlation_matrix: Dict[Tuple[str, str], float] = {}
        self.peak_capital = initial_capital
        self.current_drawdown = 0.0

        logger.info("Advanced Risk Manager initialized")

    def calculate_kelly_position_size(
        self, win_rate: float, avg_win: float, avg_loss: float, current_capital: float
    ) -> float:
        """
        Calculate optimal position size using Kelly Criterion

        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade %
            avg_loss: Average losing trade %
            current_capital: Current account capital

        Returns:
            Optimal position size in dollars
        """
        if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
            return 0.0

        # Kelly formula: f = (p*b - q) / b
        # where p = win_rate, q = loss_rate, b = avg_win/avg_loss ratio
        loss_rate = 1 - win_rate
        win_loss_ratio = avg_win / avg_loss

        kelly_pct = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio

        # Use fractional Kelly (25%) for safety
        kelly_pct = max(0, min(kelly_pct * 0.25, self.max_position_pct))

        position_size = current_capital * kelly_pct

        logger.debug(
            f"Kelly position size: ${position_size:.2f} ({kelly_pct * 100:.2f}%)"
        )
        return position_size

    def calculate_dynamic_stop_loss(
        self, entry_price: float, volatility: float, side: str = "buy"
    ) -> float:
        """
        Calculate dynamic stop-loss based on volatility

        Args:
            entry_price: Entry price of position
            volatility: Current market volatility (ATR or std dev)
            side: 'buy' or 'sell'

        Returns:
            Stop-loss price
        """
        # Use 2x ATR for stop-loss distance
        stop_distance = volatility * 2.0

        if side.lower() == "buy":
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        # Ensure minimum stop distance (0.5%)
        min_stop = entry_price * 0.005
        if abs(stop_price - entry_price) < min_stop:
            stop_price = (
                entry_price - min_stop
                if side.lower() == "buy"
                else entry_price + min_stop
            )

        return stop_price

    def calculate_position_risk(
        self, position_size: float, entry_price: float, stop_loss: float
    ) -> float:
        """Calculate risk amount for a position"""
        risk_per_unit = abs(entry_price - stop_loss)
        quantity = position_size / entry_price
        total_risk = quantity * risk_per_unit
        return total_risk

    def check_correlation_risk(
        self, symbol: str, open_positions: Dict[str, Any]
    ) -> bool:
        """
        Check if adding position would violate correlation limits

        Returns:
            True if position is allowed, False if too correlated
        """
        if not open_positions:
            return True

        # Check correlation with existing positions
        for existing_symbol in open_positions.keys():
            if existing_symbol == symbol:
                continue

            correlation = self._get_correlation(symbol, existing_symbol)

            if abs(correlation) > self.correlation_limit:
                logger.warning(
                    f"High correlation detected: {symbol} <-> {existing_symbol} "
                    f"({correlation:.2f})"
                )
                return False

        return True

    def _get_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation between two symbols (simplified)"""
        # In production, this would calculate actual correlation from price history
        # For now, return mock correlation based on asset class

        crypto_pairs = {"BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE"}

        if symbol1 in crypto_pairs and symbol2 in crypto_pairs:
            return 0.6  # Cryptos are generally correlated

        return 0.2  # Low correlation for different asset classes

    def calculate_var(
        self,
        positions: List[Dict],
        confidence_level: float = 0.95,
        time_horizon_days: int = 1,
    ) -> float:
        """
        Calculate Value at Risk (VaR) for portfolio

        Args:
            positions: List of current positions
            confidence_level: Confidence level (0.95 = 95%)
            time_horizon_days: Time horizon in days

        Returns:
            VaR amount in dollars
        """
        if not positions:
            return 0.0

        # Simplified VaR calculation using historical method
        total_value = sum(p.get("value", 0) for p in positions)
        avg_volatility = sum(p.get("volatility", 0.02) for p in positions) / len(
            positions
        )

        # VaR = Value * Volatility * Z-score * sqrt(time)
        # Z-score for 95% confidence = 1.645
        z_score = 1.645 if confidence_level == 0.95 else 2.33  # 99% = 2.33

        var = total_value * avg_volatility * z_score * (time_horizon_days**0.5)

        logger.info(f"Portfolio VaR (95%, 1-day): ${var:.2f}")
        return var

    def update_drawdown(self, current_capital: float) -> None:
        """Update peak capital and current drawdown"""
        self.current_capital = current_capital

        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = (
                self.peak_capital - current_capital
            ) / self.peak_capital

    def should_halt_trading(self) -> Tuple[bool, str]:
        """
        Check if trading should be halted due to risk limits

        Returns:
            (should_halt, reason)
        """
        # Check drawdown limit
        if self.current_drawdown >= self.max_drawdown_pct:
            reason = f"Maximum drawdown reached: {self.current_drawdown * 100:.1f}%"
            logger.warning(reason)
            return True, reason

        # Check if capital is too low
        if self.current_capital < self.initial_capital * 0.5:
            reason = "Capital dropped below 50% of initial"
            logger.warning(reason)
            return True, reason

        return False, ""

    def optimize_portfolio_allocation(
        self, signals: List[Dict], current_capital: float
    ) -> List[Dict]:
        """
        Optimize portfolio allocation across multiple signals
        using Modern Portfolio Theory principles

        Args:
            signals: List of trading signals with scores
            current_capital: Current available capital

        Returns:
            Optimized list of positions with sizes
        """
        if not signals:
            return []

        # Sort signals by score
        sorted_signals = sorted(signals, key=lambda x: x.get("score", 0), reverse=True)

        # Calculate total risk budget
        risk_budget = current_capital * self.max_total_risk
        allocated_positions = []
        remaining_budget = risk_budget

        for signal in sorted_signals:
            if remaining_budget <= 0:
                break

            score = signal.get("score", 0)
            if score <= 0:
                continue

            # Allocate risk proportional to signal strength
            risk_allocation = min(
                remaining_budget * (score / 1.0),  # Normalize by max score
                current_capital * self.max_position_pct,
            )

            position = {
                "symbol": signal.get("symbol"),
                "side": signal.get("side"),
                "risk_allocation": risk_allocation,
                "score": score,
            }

            allocated_positions.append(position)
            remaining_budget -= risk_allocation

        logger.info(
            f"Optimized {len(allocated_positions)} positions from {len(signals)} signals"
        )
        return allocated_positions

    def get_risk_metrics(self) -> Dict[str, float]:
        """Get current risk metrics for monitoring"""
        return {
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "current_drawdown_pct": self.current_drawdown * 100,
            "max_drawdown_pct": self.max_drawdown_pct * 100,
            "max_position_pct": self.max_position_pct * 100,
            "max_total_risk_pct": self.max_total_risk * 100,
            "capital_utilization_pct": (
                (self.initial_capital - self.current_capital)
                / self.initial_capital
                * 100
            ),
        }


def test_risk_manager():
    """Test the advanced risk manager"""
    rm = AdvancedRiskManager(initial_capital=100000)

    # Test Kelly sizing
    position_size = rm.calculate_kelly_position_size(
        win_rate=0.65, avg_win=0.02, avg_loss=0.01, current_capital=100000
    )
    print(f"Kelly position size: ${position_size:.2f}")

    # Test dynamic stop-loss
    stop = rm.calculate_dynamic_stop_loss(
        entry_price=50000, volatility=1000, side="buy"
    )
    print(f"Dynamic stop-loss: ${stop:.2f}")

    # Test VaR
    positions = [
        {"value": 10000, "volatility": 0.02},
        {"value": 15000, "volatility": 0.03},
    ]
    var = rm.calculate_var(positions)
    print(f"Portfolio VaR: ${var:.2f}")

    # Test metrics
    print("\nRisk Metrics:")
    for key, value in rm.get_risk_metrics().items():
        print(f"  {key}: {value:.2f}")


if __name__ == "__main__":
    test_risk_manager()
