"""
Coinbase Executor

Executor for placing orders via Coinbase using CCXT.
"""

import logging
from typing import Optional, Dict
from datetime import datetime

import ccxt

from .base_executor import (
    BaseExecutor, Order, Fill, OrderSide, OrderType, OrderStatus
)

import sys
sys.path.insert(0, '..')
from config import COINBASE_CONFIG, EXECUTION_MODE

logger = logging.getLogger(__name__)


class CoinbaseExecutor(BaseExecutor):
    """
    Coinbase order executor.

    Connects to Coinbase via CCXT and submits orders for execution.
    Only active when EXECUTION_MODE is 'live'.
    """

    def __init__(self):
        super().__init__("Coinbase")
        self._exchange: Optional[ccxt.Exchange] = None
        self._external_order_map: Dict[str, str] = {}  # Maps our order_id to exchange order_id

    def connect(self) -> bool:
        """Connect to Coinbase."""
        if EXECUTION_MODE == "paper":
            logger.warning("Coinbase executor disabled in paper mode")
            return False

        if self._connected:
            return True

        try:
            self._exchange = ccxt.coinbase({
                "apiKey": COINBASE_CONFIG["api_key"],
                "secret": COINBASE_CONFIG["api_secret"],
                "sandbox": COINBASE_CONFIG["sandbox"],
                "enableRateLimit": True,
            })

            # Test connection by loading markets
            self._exchange.load_markets()

            self._connected = True
            logger.info("Coinbase executor connected")
            return True

        except Exception as e:
            logger.error(f"Failed to connect Coinbase executor: {e}")
            return False

    def disconnect(self):
        """Disconnect from Coinbase."""
        self._exchange = None
        self._connected = False
        logger.info("Coinbase executor disconnected")

    def submit_order(self, order: Order) -> bool:
        """
        Submit an order to Coinbase.

        Args:
            order: Order to submit

        Returns:
            bool: True if order submission was successful
        """
        if not self._connected or not self._exchange:
            logger.error("Coinbase executor not connected")
            return False

        if EXECUTION_MODE == "paper":
            logger.warning("Cannot submit orders in paper mode via Coinbase executor")
            return False

        try:
            side = order.side.value  # "buy" or "sell"
            symbol = order.symbol
            amount = abs(order.quantity)
            price = order.limit_price

            # Create order based on type
            if order.order_type == OrderType.MARKET:
                result = self._exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                )
            elif order.order_type == OrderType.LIMIT:
                result = self._exchange.create_limit_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=price,
                )
            else:
                # Default to market order
                result = self._exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                )

            # Store the external order ID
            external_id = result.get("id")
            self._external_order_map[order.order_id] = external_id

            # Update order status
            order.status = OrderStatus.SUBMITTED
            order.exchange = "coinbase"
            order.metadata["external_id"] = external_id
            self._store_order(order)

            logger.info(f"Coinbase order submitted: {order.order_id} -> {external_id}")

            # Check if immediately filled (market orders)
            if result.get("status") == "closed":
                self._process_fill(order, result)

            return True

        except Exception as e:
            logger.error(f"Failed to submit Coinbase order: {e}")
            order.status = OrderStatus.REJECTED
            self._store_order(order)
            return False

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order on Coinbase.

        Args:
            order_id: ID of order to cancel

        Returns:
            bool: True if cancellation was successful
        """
        if not self._connected or not self._exchange:
            logger.error("Coinbase executor not connected")
            return False

        external_id = self._external_order_map.get(order_id)
        if not external_id:
            logger.error(f"Order {order_id} not found in Coinbase orders")
            return False

        order = self._orders.get(order_id)
        if not order:
            logger.error(f"Order {order_id} not found")
            return False

        try:
            self._exchange.cancel_order(external_id, order.symbol)

            order.status = OrderStatus.CANCELLED
            logger.info(f"Coinbase order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel Coinbase order: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        Get status of an order.

        Args:
            order_id: ID of order

        Returns:
            OrderStatus or None
        """
        if not self._connected or not self._exchange:
            order = self._orders.get(order_id)
            return order.status if order else None

        external_id = self._external_order_map.get(order_id)
        order = self._orders.get(order_id)

        if not external_id or not order:
            return order.status if order else None

        try:
            result = self._exchange.fetch_order(external_id, order.symbol)
            status_str = result.get("status", "")

            status_map = {
                "open": OrderStatus.SUBMITTED,
                "closed": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
                "expired": OrderStatus.CANCELLED,
                "rejected": OrderStatus.REJECTED,
            }

            return status_map.get(status_str, OrderStatus.PENDING)

        except Exception as e:
            logger.error(f"Failed to get Coinbase order status: {e}")
            return order.status if order else None

    def _process_fill(self, order: Order, result: dict):
        """Process a fill from Coinbase order result."""
        filled_amount = result.get("filled", 0)
        avg_price = result.get("average", result.get("price", 0))
        fee = result.get("fee", {}).get("cost", 0) if result.get("fee") else 0

        if filled_amount > 0:
            fill = Fill(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=filled_amount,
                price=avg_price,
                commission=fee,
                exchange="coinbase",
                filled_at=datetime.now(),
            )
            self._store_fill(fill)
            order.status = OrderStatus.FILLED
            logger.info(f"Coinbase fill: {fill.quantity} {order.symbol} @ {fill.price}")

    def sync_order_status(self, order_id: str):
        """Sync order status and fills from Coinbase."""
        if not self._connected or not self._exchange:
            return

        external_id = self._external_order_map.get(order_id)
        order = self._orders.get(order_id)

        if not external_id or not order:
            return

        try:
            result = self._exchange.fetch_order(external_id, order.symbol)

            # Update status
            new_status = self.get_order_status(order_id)
            if new_status:
                order.status = new_status

            # Process any fills
            if result.get("filled", 0) > 0:
                self._process_fill(order, result)

        except Exception as e:
            logger.error(f"Failed to sync Coinbase order: {e}")

    def get_balance(self) -> Dict[str, float]:
        """Get current balances from Coinbase."""
        if not self._connected or not self._exchange:
            return {}

        try:
            balance = self._exchange.fetch_balance()
            return {k: v for k, v in balance.get("total", {}).items() if v > 0}
        except Exception as e:
            logger.error(f"Failed to get Coinbase balance: {e}")
            return {}

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get open orders from Coinbase."""
        if not self._connected or not self._exchange:
            return []

        try:
            return self._exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to get Coinbase open orders: {e}")
            return []
