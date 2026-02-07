# ANVEL Code Quality Standards

## Overview

This document defines the institutional-grade code quality standards for the ANVEL AI Trading System. All code must meet these standards before merging to main.

## Code Quality Metrics

### Target Metrics
- **Flake8 Issues**: 0 critical issues
- **Test Coverage**: ≥80%
- **Security Issues**: 0 high/critical
- **Documentation**: All public APIs documented
- **Type Hints**: All public functions

## Python Code Standards

### Formatting

1. **Line Length**: 88 characters (Black default)
2. **Indentation**: 4 spaces (no tabs)
3. **Blank Lines**: 
   - 2 blank lines between top-level functions/classes
   - 1 blank line between methods
   - No trailing whitespace
4. **Imports**:
   - Standard library first
   - Third-party second
   - Local imports last
   - Sorted alphabetically within groups

### Example:
```python
import os
import sys
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from anvel_brain import ANVELBrain
from anvel_memory import Memory


class TradingStrategy:
    """Base class for trading strategies."""

    def __init__(self, name: str, risk_level: float = 0.02):
        """Initialize strategy.

        Args:
            name: Strategy name
            risk_level: Risk per trade (0-1)
        """
        self.name = name
        self.risk_level = risk_level

    def execute(self, market_data: Dict) -> Optional[Dict]:
        """Execute trading logic.

        Args:
            market_data: Current market data

        Returns:
            Trade signal dict or None
        """
        raise NotImplementedError
```

## Linting Rules

### Flake8 Configuration (.flake8)
- E501: Line too long - ignored (handled by Black)
- W503: Line break before binary operator - ignored (Black style)
- E402: Module import not at top - ignored (conditional imports OK)
- E722: Bare except - ignored (logging exceptions acceptable)

### Enforced Rules
- E1-E9: Indentation, whitespace, naming
- W1-W6: Warnings about code style
- F: PyFlakes errors (undefined variables, imports)
- C: Complexity warnings

## Type Hints

### Required
All public functions and methods must have type hints:

```python
def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI indicator."""
    ...

def get_account_balance() -> Dict[str, float]:
    """Get current account balance."""
    ...
```

### Optional
Private functions (_function) may omit type hints if obvious:

```python
def _internal_helper(x):
    """Simple internal calculation."""
    return x * 2
```

## Documentation Standards

### Module Docstrings
```python
"""
ANVEL Trading Strategy Core

This module implements the core trading strategy logic including:
- Strategy base classes
- Signal generation
- Position sizing
- Risk management

Example:
    >>> strategy = MomentumStrategy('BTC/USD')
    >>> signal = strategy.execute(market_data)
"""
```

### Class Docstrings
```python
class ANVELBrain:
    """AI decision-making core for ANVEL.

    The Brain processes market data, generates predictions,
    and makes trading decisions using multiple AI models.

    Attributes:
        models: List of ML models
        memory: Long-term memory storage
        confidence_threshold: Minimum confidence for trades (0-1)

    Example:
        >>> brain = ANVELBrain()
        >>> brain.train(historical_data)
        >>> decision = brain.decide(current_market)
    """
```

### Function Docstrings
```python
def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_percent: float
) -> float:
    """Calculate position size based on risk parameters.

    Uses the risk-per-trade formula to determine optimal position size
    while respecting the maximum risk percentage.

    Args:
        account_balance: Total account balance in USD
        risk_percent: Percentage of account to risk (0-100)
        stop_loss_percent: Stop loss as percentage (0-100)

    Returns:
        Position size in USD

    Raises:
        ValueError: If parameters are out of valid range

    Example:
        >>> calculate_position_size(10000, 2, 1)
        2000.0
    """
```

## Testing Standards

### Coverage Requirements
- Overall: ≥80%
- Critical modules (brain, trading, risk): ≥90%
- Utility modules: ≥70%

### Test Organization
```python
# tests/test_strategy_core.py
import pytest
from anvel_strategy_core import TradingStrategy


class TestTradingStrategy:
    """Test suite for TradingStrategy class."""

    @pytest.fixture
    def strategy(self):
        """Create strategy instance for testing."""
        return TradingStrategy("Test", risk_level=0.02)

    def test_initialization(self, strategy):
        """Test strategy initializes correctly."""
        assert strategy.name == "Test"
        assert strategy.risk_level == 0.02

    def test_execute_raises_not_implemented(self, strategy):
        """Test base execute raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            strategy.execute({})

    @pytest.mark.parametrize("risk_level", [0.01, 0.02, 0.05])
    def test_risk_levels(self, risk_level):
        """Test various risk levels."""
        strategy = TradingStrategy("Test", risk_level=risk_level)
        assert strategy.risk_level == risk_level
```

## Security Standards

### No Hardcoded Secrets
```python
# ❌ BAD
api_key = "sk_live_abc123..."

# ✅ GOOD
import os
api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable required")
```

### Input Validation
```python
def place_order(symbol: str, quantity: float, price: float):
    """Place trading order."""
    # Validate inputs
    if not symbol or not symbol.isalnum():
        raise ValueError("Invalid symbol")
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    if price <= 0:
        raise ValueError("Price must be positive")

    # ... place order
```

### SQL Injection Prevention
```python
# ❌ BAD
cursor.execute(f"SELECT * FROM trades WHERE symbol = '{symbol}'")

# ✅ GOOD
cursor.execute("SELECT * FROM trades WHERE symbol = %s", (symbol,))
```

## Git Commit Standards

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation only
- **style**: Code style (formatting, no logic change)
- **refactor**: Code restructuring
- **test**: Adding/updating tests
- **chore**: Maintenance tasks

### Examples
```
feat(brain): add ensemble model support

Implements ensemble voting for multiple AI models to improve
prediction accuracy. Includes weighted voting based on historical
model performance.

Closes #123
```

```
fix(trading): correct position sizing calculation

Fixed bug where position size exceeded max risk when stop loss
was very tight. Now correctly calculates based on account risk.

Fixes #456
```

## Code Review Checklist

### Before Submitting PR
- [ ] All tests pass
- [ ] Coverage ≥80%
- [ ] No flake8 errors
- [ ] No security issues (bandit)
- [ ] Documentation updated
- [ ] Type hints added
- [ ] Commit messages follow convention
- [ ] Branch rebased on main

### Reviewers Check
- [ ] Code follows standards
- [ ] Tests are comprehensive
- [ ] Documentation is clear
- [ ] No security vulnerabilities
- [ ] Performance acceptable
- [ ] Error handling robust
- [ ] Logging appropriate

## Automated Checks

### Pre-commit Hooks
Run automatically on every commit:
- Black (formatting)
- isort (import sorting)
- Flake8 (linting)
- Bandit (security)
- detect-secrets (credential scanning)

### CI/CD Pipeline
Runs on every PR:
1. Linting (flake8, ruff)
2. Type checking (mypy)
3. Security scan (bandit, safety)
4. Tests (pytest with coverage)
5. Build verification
6. Integration tests

## Performance Standards

### Response Times
- API endpoints: <100ms (p95)
- Trading decisions: <10ms
- Database queries: <50ms
- External API calls: <500ms

### Resource Usage
- Memory: <2GB per worker
- CPU: <50% average
- Database connections: <10 per worker

## Monitoring Standards

### Logging Levels
- **DEBUG**: Detailed diagnostic info
- **INFO**: General operational events
- **WARNING**: Unexpected but handled
- **ERROR**: Errors requiring attention
- **CRITICAL**: System failures

### Metrics to Track
- Request latency
- Error rates
- Trade execution success
- Model prediction accuracy
- System resource usage

## Tools

### Required Tools
```bash
pip install black isort flake8 mypy bandit pytest pytest-cov
```

### Pre-commit Setup
```bash
pip install pre-commit
pre-commit install
```

### Running Checks Manually
```bash
# Format
black .
isort .

# Lint
flake8 .

# Security
bandit -r . -ll

# Test
pytest tests/ --cov --cov-report=html
```

## References

- [PEP 8](https://pep8.org/) - Python Style Guide
- [PEP 257](https://www.python.org/dev/peps/pep-0257/) - Docstring Conventions
- [PEP 484](https://www.python.org/dev/peps/pep-0484/) - Type Hints
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [Black Documentation](https://black.readthedocs.io/)

---

**Version**: 1.0
**Last Updated**: December 2024
**Status**: Enforced for all new code
