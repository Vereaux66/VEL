#!/usr/bin/env python3
"""
ANVEL Input Validation Utilities

Provides centralized input validation for trading operations, API inputs,
and configuration parameters. Ensures data integrity and prevents invalid
operations from propagating through the system.

Features:
- Order validation (symbol, quantity, price, side)
- Configuration validation
- Numeric range validation
- Type coercion with validation
- Sanitization utilities
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

log = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Validation Result Types
# =============================================================================

@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    value: Any = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @staticmethod
    def success(value: Any) -> "ValidationResult":
        """Create a successful validation result."""
        return ValidationResult(is_valid=True, value=value)

    @staticmethod
    def failure(errors: Union[str, List[str]]) -> "ValidationResult":
        """Create a failed validation result."""
        if isinstance(errors, str):
            errors = [errors]
        return ValidationResult(is_valid=False, errors=errors)

    def __bool__(self) -> bool:
        return self.is_valid


class ValidationError(ValueError):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


# =============================================================================
# Numeric Validators
# =============================================================================

def validate_positive_number(
    value: Any,
    field_name: str = "value",
    min_value: float = 0.0,
    max_value: Optional[float] = None,
    allow_zero: bool = False,
) -> ValidationResult:
    """
    Validate that a value is a positive number within a range.

    Args:
        value: Value to validate
        field_name: Name for error messages
        min_value: Minimum allowed value (default 0.0)
        max_value: Maximum allowed value (optional)
        allow_zero: Whether zero is allowed

    Returns:
        ValidationResult with validated value or errors
    """
    try:
        num = float(value)
    except (ValueError, TypeError):
        return ValidationResult.failure(f"{field_name} must be a valid number")

    if not allow_zero and num <= 0:
        return ValidationResult.failure(f"{field_name} must be greater than 0")

    if allow_zero and num < 0:
        return ValidationResult.failure(f"{field_name} must be non-negative")

    if num < min_value:
        return ValidationResult.failure(f"{field_name} must be at least {min_value}")

    if max_value is not None and num > max_value:
        return ValidationResult.failure(f"{field_name} must be at most {max_value}")

    return ValidationResult.success(num)


def validate_quantity(
    quantity: Any,
    min_quantity: float = 0.0,
    max_quantity: float = 1_000_000_000.0,
) -> ValidationResult:
    """
    Validate a trading quantity.

    Args:
        quantity: Quantity to validate
        min_quantity: Minimum allowed quantity
        max_quantity: Maximum allowed quantity

    Returns:
        ValidationResult with validated quantity
    """
    result = validate_positive_number(
        quantity,
        field_name="quantity",
        min_value=min_quantity,
        max_value=max_quantity,
    )

    if result.is_valid:
        # Round to 8 decimal places (common for crypto)
        result.value = round(result.value, 8)

    return result


def validate_price(
    price: Any,
    min_price: float = 0.0,
    max_price: float = 1_000_000_000.0,
    allow_none: bool = True,
) -> ValidationResult:
    """
    Validate a price value.

    Args:
        price: Price to validate
        min_price: Minimum allowed price
        max_price: Maximum allowed price
        allow_none: Whether None is allowed (for market orders)

    Returns:
        ValidationResult with validated price
    """
    if price is None and allow_none:
        return ValidationResult.success(None)

    if price is None:
        return ValidationResult.failure("price is required")

    result = validate_positive_number(
        price,
        field_name="price",
        min_value=min_price,
        max_value=max_price,
    )

    if result.is_valid:
        # Round to 8 decimal places
        result.value = round(result.value, 8)

    return result


def validate_percentage(
    value: Any,
    field_name: str = "percentage",
    min_value: float = 0.0,
    max_value: float = 100.0,
) -> ValidationResult:
    """
    Validate a percentage value (0-100).

    Args:
        value: Value to validate
        field_name: Name for error messages
        min_value: Minimum percentage
        max_value: Maximum percentage

    Returns:
        ValidationResult with validated percentage
    """
    result = validate_positive_number(
        value,
        field_name=field_name,
        min_value=min_value,
        max_value=max_value,
        allow_zero=True,
    )

    return result


# =============================================================================
# String Validators
# =============================================================================

# Valid trading symbol pattern (alphanumeric with optional separators)
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9]{1,10}(/|-|_)?[A-Za-z0-9]{0,10}$")


def validate_symbol(
    symbol: Any,
    max_length: int = 20,
) -> ValidationResult:
    """
    Validate a trading symbol.

    Args:
        symbol: Symbol to validate
        max_length: Maximum symbol length

    Returns:
        ValidationResult with normalized symbol
    """
    if not isinstance(symbol, str):
        return ValidationResult.failure("symbol must be a string")

    if not symbol or not symbol.strip():
        return ValidationResult.failure("symbol cannot be empty")

    # Normalize to uppercase
    normalized = symbol.upper().strip()

    if len(normalized) > max_length:
        return ValidationResult.failure(f"symbol cannot exceed {max_length} characters")

    if not SYMBOL_PATTERN.match(normalized):
        return ValidationResult.failure(
            "symbol must contain only letters, numbers, and common separators (/, -, _)"
        )

    return ValidationResult.success(normalized)


def validate_side(side: Any) -> ValidationResult:
    """
    Validate a trading side (buy/sell).

    Args:
        side: Side to validate

    Returns:
        ValidationResult with normalized side
    """
    if not isinstance(side, str):
        return ValidationResult.failure("side must be a string")

    normalized = side.lower().strip()

    if normalized not in ("buy", "sell"):
        return ValidationResult.failure("side must be 'buy' or 'sell'")

    return ValidationResult.success(normalized)


def validate_order_type(order_type: Any) -> ValidationResult:
    """
    Validate an order type.

    Args:
        order_type: Order type to validate

    Returns:
        ValidationResult with normalized order type
    """
    if not isinstance(order_type, str):
        return ValidationResult.failure("order_type must be a string")

    normalized = order_type.lower().strip()

    valid_types = ("market", "limit", "stop", "stop_limit")
    if normalized not in valid_types:
        return ValidationResult.failure(
            f"order_type must be one of: {', '.join(valid_types)}"
        )

    return ValidationResult.success(normalized)


# =============================================================================
# Order Validation
# =============================================================================

@dataclass
class OrderValidationResult:
    """Result of order validation."""

    is_valid: bool
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    order_type: Optional[str] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def __bool__(self) -> bool:
        return self.is_valid


def validate_order(
    symbol: Any,
    side: Any,
    quantity: Any,
    price: Any = None,
    order_type: Any = "market",
    max_quantity: float = 1_000_000.0,
    max_price: float = 1_000_000_000.0,
) -> OrderValidationResult:
    """
    Validate a complete order.

    Args:
        symbol: Trading symbol
        side: Order side (buy/sell)
        quantity: Order quantity
        price: Limit price (optional for market orders)
        order_type: Order type (market, limit, etc.)
        max_quantity: Maximum allowed quantity
        max_price: Maximum allowed price

    Returns:
        OrderValidationResult with validated fields or errors
    """
    errors: List[str] = []

    # Validate each field
    symbol_result = validate_symbol(symbol)
    if not symbol_result:
        errors.extend(symbol_result.errors)

    side_result = validate_side(side)
    if not side_result:
        errors.extend(side_result.errors)

    quantity_result = validate_quantity(quantity, max_quantity=max_quantity)
    if not quantity_result:
        errors.extend(quantity_result.errors)

    order_type_result = validate_order_type(order_type)
    if not order_type_result:
        errors.extend(order_type_result.errors)

    # Price validation depends on order type
    validated_order_type = order_type_result.value if order_type_result else None
    if validated_order_type in ("limit", "stop_limit"):
        price_result = validate_price(price, max_price=max_price, allow_none=False)
    else:
        price_result = validate_price(price, max_price=max_price, allow_none=True)

    if not price_result:
        errors.extend(price_result.errors)

    if errors:
        return OrderValidationResult(is_valid=False, errors=errors)

    return OrderValidationResult(
        is_valid=True,
        symbol=symbol_result.value,
        side=side_result.value,
        quantity=quantity_result.value,
        price=price_result.value,
        order_type=order_type_result.value,
    )


# =============================================================================
# Configuration Validation
# =============================================================================

def validate_config_dict(
    config: Any,
    required_keys: Optional[List[str]] = None,
    optional_keys: Optional[List[str]] = None,
    validators: Optional[Dict[str, Callable[[Any], ValidationResult]]] = None,
) -> ValidationResult:
    """
    Validate a configuration dictionary.

    Args:
        config: Configuration dict to validate
        required_keys: Keys that must be present
        optional_keys: Keys that may be present
        validators: Custom validators for specific keys

    Returns:
        ValidationResult with validated config
    """
    if not isinstance(config, dict):
        return ValidationResult.failure("config must be a dictionary")

    errors: List[str] = []
    validated: Dict[str, Any] = {}

    required_keys = required_keys or []
    optional_keys = optional_keys or []
    validators = validators or {}

    # Check required keys
    for key in required_keys:
        if key not in config:
            errors.append(f"missing required key: {key}")
        else:
            value = config[key]
            if key in validators:
                result = validators[key](value)
                if not result:
                    errors.extend([f"{key}: {e}" for e in result.errors])
                else:
                    validated[key] = result.value
            else:
                validated[key] = value

    # Validate optional keys that are present
    all_allowed = set(required_keys) | set(optional_keys)
    for key, value in config.items():
        if key in required_keys:
            continue  # Already validated

        if key not in all_allowed and all_allowed:
            errors.append(f"unexpected key: {key}")
            continue

        if key in validators:
            result = validators[key](value)
            if not result:
                errors.extend([f"{key}: {e}" for e in result.errors])
            else:
                validated[key] = result.value
        else:
            validated[key] = value

    if errors:
        return ValidationResult.failure(errors)

    return ValidationResult.success(validated)


# =============================================================================
# Type Coercion with Validation
# =============================================================================

def coerce_to_decimal(
    value: Any,
    field_name: str = "value",
    default: Optional[Decimal] = None,
) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Coerce a value to Decimal with validation.

    Args:
        value: Value to coerce
        field_name: Name for error messages
        default: Default value if coercion fails

    Returns:
        Tuple of (decimal_value, error_message)
    """
    if value is None:
        return default, None

    try:
        return Decimal(str(value)), None
    except (InvalidOperation, ValueError, TypeError) as e:
        return default, f"{field_name} could not be converted to Decimal: {e}"


def coerce_to_float(
    value: Any,
    field_name: str = "value",
    default: Optional[float] = None,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Coerce a value to float with validation.

    Args:
        value: Value to coerce
        field_name: Name for error messages
        default: Default value if coercion fails

    Returns:
        Tuple of (float_value, error_message)
    """
    if value is None:
        return default, None

    try:
        return float(value), None
    except (ValueError, TypeError) as e:
        return default, f"{field_name} could not be converted to float: {e}"


def coerce_to_int(
    value: Any,
    field_name: str = "value",
    default: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """
    Coerce a value to int with validation.

    Args:
        value: Value to coerce
        field_name: Name for error messages
        default: Default value if coercion fails

    Returns:
        Tuple of (int_value, error_message)
    """
    if value is None:
        return default, None

    try:
        return int(value), None
    except (ValueError, TypeError) as e:
        return default, f"{field_name} could not be converted to int: {e}"


# =============================================================================
# Sanitization Utilities
# =============================================================================

def sanitize_string(
    value: Any,
    max_length: int = 1000,
    strip: bool = True,
    lowercase: bool = False,
    uppercase: bool = False,
) -> str:
    """
    Sanitize a string value.

    Args:
        value: Value to sanitize
        max_length: Maximum length after sanitization
        strip: Whether to strip whitespace
        lowercase: Convert to lowercase
        uppercase: Convert to uppercase

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        value = str(value) if value is not None else ""

    if strip:
        value = value.strip()

    if lowercase:
        value = value.lower()
    elif uppercase:
        value = value.upper()

    if len(value) > max_length:
        value = value[:max_length]

    return value


def sanitize_for_logging(
    value: Any,
    max_length: int = 500,
    mask_keys: Optional[List[str]] = None,
) -> Any:
    """
    Sanitize a value for safe logging.

    Args:
        value: Value to sanitize
        max_length: Maximum length for strings
        mask_keys: Keys to mask in dictionaries (e.g., 'password', 'secret')

    Returns:
        Sanitized value safe for logging
    """
    mask_keys = mask_keys or ["password", "secret", "key", "token", "auth"]

    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + "...[truncated]"
        return value

    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            if any(mask in k.lower() for mask in mask_keys):
                sanitized[k] = "***MASKED***"
            else:
                sanitized[k] = sanitize_for_logging(v, max_length, mask_keys)
        return sanitized

    if isinstance(value, (list, tuple)):
        return type(value)(
            sanitize_for_logging(item, max_length, mask_keys) for item in value
        )

    return value
