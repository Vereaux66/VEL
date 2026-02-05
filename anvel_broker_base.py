#!/usr/bin/env python3
from typing import Any, Dict, Optional


class BrokerBase:  # pragma: no cover
    name = "base"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "bid": None,
            "ask": None,
            "source": self.name,
            "status": "unsupported",
            "message": "Broker adapter does not implement get_quote",
        }

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "last": None,
            "bid": None,
            "ask": None,
            "source": self.name,
            "status": "unsupported",
            "message": "Broker adapter does not implement get_ticker",
        }

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        return {
            "status": "simulated",
            "symbol": symbol.upper(),
            "side": side,
            "qty": qty,
            "price": price,
            "type": order_type,
            "note": "Broker adapter does not implement submit_order",
        }

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict[str, Any]:
        """Place an order (alias for submit_order with consistent naming)"""
        return self.submit_order(symbol, side, amount, price, order_type)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order"""
        return {
            "status": "simulated",
            "order_id": order_id,
            "message": "Broker adapter does not implement cancel_order",
        }

    def get_balance(self) -> Dict[str, Any]:
        """Get account balance"""
        return {
            "status": "simulated",
            "balances": {},
            "message": "Broker adapter does not implement get_balance",
        }

    def get_positions(self) -> Dict[str, Any]:
        """Get open positions"""
        return {
            "status": "simulated",
            "positions": [],
            "message": "Broker adapter does not implement get_positions",
        }
