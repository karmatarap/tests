"""
IBKR Executor

Executor for placing orders via Interactive Brokers.
"""

import logging
from typing import Optional, Dict
from datetime import datetime

from ib_insync import IB, Stock, MarketOrder, LimitOrder, StopOrder, Trade

from .base_executor import (
    BaseExecutor, Order, Fill, OrderSide, OrderType, OrderStatus
)

import sys
sys.path.insert(0, '..')
from config import IBKR_CONFIG, EXECUTION_MODE

logger = logging.getLogger(__name__)


class IBKRExecutor(BaseExecutor):
    """
    IBKR order executor.

    Connects to TWS/Gateway and submits orders for execution.
    Only active when EXECUTION_MODE is 'live'.
    """

    def __init__(self):
        super().__init__("IBKR")
        self.ib = IB()
        self._trade_map: Dict[str, Trade] = {}  # Maps our order_id to IBKR Trade

    def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway."""
        if EXECUTION_MODE == "paper":
            logger.warning("IBKR executor disabled in paper mode")
            return False

        if self._connected:
            return True

        try:
            self.ib.connect(
                host=IBKR_CONFIG["host"],
                port=IBKR_CONFIG["port"],
                clientId=IBKR_CONFIG["client_id"],
                timeout=IBKR_CONFIG["timeout"],
                readonly=False,  # Need write access for orders
            )
            self._connected = True
            logger.info(f"IBKR executor connected to {IBKR_CONFIG['host']}:{IBKR_CONFIG['port']}")

            # Set up order status callbacks
            self.ib.orderStatusEvent += self._on_order_status

            return True
        except Exception as e:
            logger.error(f"Failed to connect IBKR executor: {e}")
            return False

    def disconnect(self):
        """Disconnect from IBKR."""
        if self.ib.isConnected():
            self.ib.disconnect()
        self._connected = False
        logger.info("IBKR executor disconnected")

    def _create_ib_contract(self, order: Order):
        """Create an IBKR contract from our order."""
        # For now, assume stocks. Can be extended for options, futures, etc.
        return Stock(order.symbol, "SMART", "USD")

    def _create_ib_order(self, order: Order):
        """Create an IBKR order from our order."""
        action = "BUY" if order.side == OrderSide.BUY else "SELL"
        quantity = abs(order.quantity)

        if order.order_type == OrderType.MARKET:
            return MarketOrder(action, quantity)
        elif order.order_type == OrderType.LIMIT:
            return LimitOrder(action, quantity, order.limit_price)
        elif order.order_type == OrderType.STOP:
            return StopOrder(action, quantity, order.stop_price)
        else:
            # Default to market
            return MarketOrder(action, quantity)

    def submit_order(self, order: Order) -> bool:
        """
        Submit an order to IBKR.

        Args:
            order: Order to submit

        Returns:
            bool: True if order submission was successful
        """
        if not self._connected:
            logger.error("IBKR executor not connected")
            return False

        if EXECUTION_MODE == "paper":
            logger.warning("Cannot submit orders in paper mode via IBKR executor")
            return False

        try:
            contract = self._create_ib_contract(order)
            ib_order = self._create_ib_order(order)

            # Qualify the contract
            self.ib.qualifyContracts(contract)

            # Place the order
            trade = self.ib.placeOrder(contract, ib_order)

            # Store the trade reference
            self._trade_map[order.order_id] = trade

            # Update order status
            order.status = OrderStatus.SUBMITTED
            order.exchange = "ibkr"
            self._store_order(order)

            logger.info(f"IBKR order submitted: {order.order_id} - {order.side.value} "
                       f"{order.quantity} {order.symbol}")
            return True

        except Exception as e:
            logger.error(f"Failed to submit IBKR order: {e}")
            order.status = OrderStatus.REJECTED
            self._store_order(order)
            return False

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order on IBKR.

        Args:
            order_id: ID of order to cancel

        Returns:
            bool: True if cancellation was successful
        """
        if not self._connected:
            logger.error("IBKR executor not connected")
            return False

        trade = self._trade_map.get(order_id)
        if not trade:
            logger.error(f"Order {order_id} not found in IBKR trades")
            return False

        try:
            self.ib.cancelOrder(trade.order)

            order = self._orders.get(order_id)
            if order:
                order.status = OrderStatus.CANCELLED

            logger.info(f"IBKR order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel IBKR order: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        Get status of an order.

        Args:
            order_id: ID of order

        Returns:
            OrderStatus or None
        """
        trade = self._trade_map.get(order_id)
        if not trade:
            order = self._orders.get(order_id)
            return order.status if order else None

        # Map IBKR status to our status
        ib_status = trade.orderStatus.status

        status_map = {
            "PendingSubmit": OrderStatus.PENDING,
            "PreSubmitted": OrderStatus.PENDING,
            "Submitted": OrderStatus.SUBMITTED,
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "ApiCancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.REJECTED,
        }

        return status_map.get(ib_status, OrderStatus.PENDING)

    def _on_order_status(self, trade: Trade):
        """Callback for IBKR order status updates."""
        # Find our order by matching the trade
        order_id = None
        for oid, t in self._trade_map.items():
            if t == trade:
                order_id = oid
                break

        if not order_id:
            return

        order = self._orders.get(order_id)
        if not order:
            return

        # Update status
        new_status = self.get_order_status(order_id)
        if new_status:
            order.status = new_status

        # Check for fills
        if trade.fills:
            for ib_fill in trade.fills:
                # Create our fill record
                fill = Fill(
                    order_id=order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=ib_fill.execution.shares,
                    price=ib_fill.execution.price,
                    commission=ib_fill.commissionReport.commission
                        if ib_fill.commissionReport else 0,
                    exchange="ibkr",
                    filled_at=datetime.now(),
                )
                self._store_fill(fill)
                logger.info(f"IBKR fill: {fill.quantity} {order.symbol} @ {fill.price}")

    def get_positions(self) -> Dict[str, float]:
        """Get current positions from IBKR."""
        if not self._connected:
            return {}

        positions = {}
        for pos in self.ib.positions():
            positions[pos.contract.symbol] = pos.position
        return positions

    def get_account_value(self) -> Optional[float]:
        """Get account net liquidation value."""
        if not self._connected:
            return None

        for av in self.ib.accountSummary():
            if av.tag == "NetLiquidation":
                return float(av.value)
        return None
