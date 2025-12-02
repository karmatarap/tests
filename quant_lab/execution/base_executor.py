"""
Base Executor

Abstract base class and common data structures for all executors.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Order data class."""
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    exchange: Optional[str] = None  # "ibkr", "coinbase", "binance"
    strategy_id: Optional[str] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "exchange": self.exchange,
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Fill:
    """Fill/execution data class."""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0.0
    fill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filled_at: datetime = field(default_factory=datetime.now)
    exchange: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def value(self) -> float:
        """Calculate fill value (quantity * price)."""
        return self.quantity * self.price

    @property
    def net_value(self) -> float:
        """Calculate net value after commission."""
        if self.side == OrderSide.BUY:
            return -(self.value + self.commission)
        else:
            return self.value - self.commission

    def to_dict(self) -> Dict[str, Any]:
        """Convert fill to dictionary."""
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "value": self.value,
            "commission": self.commission,
            "net_value": self.net_value,
            "filled_at": self.filled_at.isoformat(),
            "exchange": self.exchange,
            "metadata": self.metadata,
        }


class BaseExecutor(ABC):
    """
    Abstract base class for all executors.

    Defines the common interface for paper, IBKR, and Coinbase executors.
    """

    def __init__(self, name: str):
        self.name = name
        self._orders: Dict[str, Order] = {}
        self._fills: List[Fill] = []
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if executor is connected."""
        return self._connected

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the execution venue."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the execution venue."""
        pass

    @abstractmethod
    def submit_order(self, order: Order) -> bool:
        """
        Submit an order for execution.

        Args:
            order: Order to submit

        Returns:
            bool: True if order was successfully submitted
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: ID of order to cancel

        Returns:
            bool: True if cancel was successful
        """
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        Get current status of an order.

        Args:
            order_id: ID of order

        Returns:
            OrderStatus or None if order not found
        """
        pass

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self._orders.get(order_id)

    def get_all_orders(self) -> List[Order]:
        """Get all orders."""
        return list(self._orders.values())

    def get_open_orders(self) -> List[Order]:
        """Get all open (non-terminal) orders."""
        open_statuses = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL}
        return [o for o in self._orders.values() if o.status in open_statuses]

    def get_fills(self, order_id: Optional[str] = None) -> List[Fill]:
        """
        Get fills, optionally filtered by order ID.

        Args:
            order_id: Optional order ID to filter by

        Returns:
            List of fills
        """
        if order_id:
            return [f for f in self._fills if f.order_id == order_id]
        return self._fills.copy()

    def get_fills_for_symbol(self, symbol: str) -> List[Fill]:
        """Get all fills for a symbol."""
        return [f for f in self._fills if f.symbol == symbol]

    def calculate_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Calculate realized PnL from fills.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            Total realized PnL
        """
        fills = self._fills if not symbol else self.get_fills_for_symbol(symbol)
        return sum(f.net_value for f in fills)

    def _store_order(self, order: Order):
        """Store an order internally."""
        self._orders[order.order_id] = order

    def _store_fill(self, fill: Fill):
        """Store a fill internally."""
        self._fills.append(fill)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
