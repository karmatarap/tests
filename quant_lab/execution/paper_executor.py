"""
Paper Executor

Simulates order execution for paper trading.
Records hypothetical trades and tracks PnL without sending real orders.

Supports logging trades to:
- In-memory list
- CSV file
- SQLite database
"""

import logging
import csv
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
import json
import os

from .base_executor import (
    BaseExecutor, Order, Fill, OrderSide, OrderType, OrderStatus
)

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Paper trading position."""
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        """Calculate position market value (requires current price)."""
        return self.quantity * self.avg_cost

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "market_value": self.market_value,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
        }


class PaperExecutor(BaseExecutor):
    """
    Paper trading executor.

    Simulates order execution without sending real orders.
    Tracks positions, fills, and PnL for backtesting/paper trading.

    Supports logging trades to:
    - In-memory list (always active)
    - CSV file (optional)
    - SQLite database (optional)
    """

    def __init__(self, initial_capital: float = 100000.0,
                 price_provider: Optional[Callable[[str], float]] = None,
                 csv_log_path: Optional[str] = None,
                 sqlite_log_path: Optional[str] = None,
                 log_dir: Optional[str] = None):
        """
        Initialize paper executor.

        Args:
            initial_capital: Starting capital for paper trading
            price_provider: Optional function to get current price for a symbol
            csv_log_path: Path for CSV trade log (or auto-generate if log_dir set)
            sqlite_log_path: Path for SQLite trade log (or auto-generate if log_dir set)
            log_dir: Directory for auto-generated log files
        """
        super().__init__("Paper")
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self._positions: Dict[str, Position] = {}
        self._price_provider = price_provider
        self._trade_log: List[dict] = []
        self._connected = True  # Always connected

        # Set up logging paths
        self._log_dir = Path(log_dir) if log_dir else None
        self._csv_log_path = csv_log_path
        self._sqlite_log_path = sqlite_log_path

        # Auto-generate log paths if log_dir is specified
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            if not self._csv_log_path:
                self._csv_log_path = str(self._log_dir / f"trades_{date_str}.csv")
            if not self._sqlite_log_path:
                self._sqlite_log_path = str(self._log_dir / "trades.db")

        # Initialize CSV log
        if self._csv_log_path:
            self._init_csv_log()

        # Initialize SQLite log
        if self._sqlite_log_path:
            self._init_sqlite_log()

    def _init_csv_log(self):
        """Initialize CSV trade log file."""
        try:
            csv_path = Path(self._csv_log_path)
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Write header if file doesn't exist
            if not csv_path.exists():
                with open(csv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp", "order_id", "symbol", "side", "quantity",
                        "price", "value", "commission", "strategy_id",
                        "cash_after", "portfolio_value"
                    ])
                logger.info(f"CSV trade log initialized: {self._csv_log_path}")
        except Exception as e:
            logger.error(f"Failed to initialize CSV log: {e}")
            self._csv_log_path = None

    def _init_sqlite_log(self):
        """Initialize SQLite trade log database."""
        try:
            db_path = Path(self._sqlite_log_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect(self._sqlite_log_path)
            cursor = conn.cursor()

            # Create trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    value REAL NOT NULL,
                    commission REAL NOT NULL,
                    strategy_id TEXT,
                    cash_after REAL,
                    portfolio_value REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create positions snapshot table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_cost REAL NOT NULL,
                    market_value REAL,
                    realized_pnl REAL,
                    unrealized_pnl REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create portfolio snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cash REAL NOT NULL,
                    portfolio_value REAL NOT NULL,
                    total_pnl REAL NOT NULL,
                    return_pct REAL NOT NULL,
                    num_positions INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_id)")

            conn.commit()
            conn.close()
            logger.info(f"SQLite trade log initialized: {self._sqlite_log_path}")

        except Exception as e:
            logger.error(f"Failed to initialize SQLite log: {e}")
            self._sqlite_log_path = None

    def _log_to_csv(self, trade_record: dict):
        """Append trade record to CSV file."""
        if not self._csv_log_path:
            return

        try:
            with open(self._csv_log_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    trade_record.get("timestamp"),
                    trade_record.get("order_id"),
                    trade_record.get("symbol"),
                    trade_record.get("side"),
                    trade_record.get("quantity"),
                    trade_record.get("price"),
                    trade_record.get("value"),
                    trade_record.get("commission"),
                    trade_record.get("strategy_id"),
                    trade_record.get("cash_after"),
                    trade_record.get("portfolio_value"),
                ])
        except Exception as e:
            logger.error(f"Failed to write to CSV log: {e}")

    def _log_to_sqlite(self, trade_record: dict):
        """Insert trade record into SQLite database."""
        if not self._sqlite_log_path:
            return

        try:
            conn = sqlite3.connect(self._sqlite_log_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO trades (
                    timestamp, order_id, symbol, side, quantity,
                    price, value, commission, strategy_id,
                    cash_after, portfolio_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_record.get("timestamp"),
                trade_record.get("order_id"),
                trade_record.get("symbol"),
                trade_record.get("side"),
                trade_record.get("quantity"),
                trade_record.get("price"),
                trade_record.get("value"),
                trade_record.get("commission"),
                trade_record.get("strategy_id"),
                trade_record.get("cash_after"),
                trade_record.get("portfolio_value"),
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to write to SQLite log: {e}")

    def save_position_snapshot(self):
        """Save current position snapshot to SQLite."""
        if not self._sqlite_log_path:
            return

        try:
            conn = sqlite3.connect(self._sqlite_log_path)
            cursor = conn.cursor()
            timestamp = datetime.now().isoformat()

            for symbol, pos in self._positions.items():
                current_price = self.get_current_price(symbol) or pos.avg_cost
                market_value = pos.quantity * current_price
                unrealized_pnl = 0.0
                if pos.quantity > 0:
                    unrealized_pnl = pos.quantity * (current_price - pos.avg_cost)
                elif pos.quantity < 0:
                    unrealized_pnl = abs(pos.quantity) * (pos.avg_cost - current_price)

                cursor.execute("""
                    INSERT INTO position_snapshots (
                        timestamp, symbol, quantity, avg_cost,
                        market_value, realized_pnl, unrealized_pnl
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp, symbol, pos.quantity, pos.avg_cost,
                    market_value, pos.realized_pnl, unrealized_pnl
                ))

            conn.commit()
            conn.close()
            logger.debug(f"Position snapshot saved at {timestamp}")
        except Exception as e:
            logger.error(f"Failed to save position snapshot: {e}")

    def save_portfolio_snapshot(self):
        """Save current portfolio snapshot to SQLite."""
        if not self._sqlite_log_path:
            return

        try:
            conn = sqlite3.connect(self._sqlite_log_path)
            cursor = conn.cursor()

            portfolio_value = self.get_portfolio_value()
            total_pnl = self.get_total_pnl()
            return_pct = (portfolio_value / self.initial_capital - 1) * 100
            num_positions = len([p for p in self._positions.values() if p.quantity != 0])

            cursor.execute("""
                INSERT INTO portfolio_snapshots (
                    timestamp, cash, portfolio_value, total_pnl,
                    return_pct, num_positions
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                self.cash,
                portfolio_value,
                total_pnl,
                return_pct,
                num_positions,
            ))

            conn.commit()
            conn.close()
            logger.debug("Portfolio snapshot saved")
        except Exception as e:
            logger.error(f"Failed to save portfolio snapshot: {e}")

    def get_trades_from_csv(self, limit: int = 100) -> List[dict]:
        """Read recent trades from CSV file."""
        if not self._csv_log_path or not Path(self._csv_log_path).exists():
            return []

        try:
            trades = []
            with open(self._csv_log_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
            return trades[-limit:]
        except Exception as e:
            logger.error(f"Failed to read CSV log: {e}")
            return []

    def get_trades_from_sqlite(self, limit: int = 100,
                                symbol: Optional[str] = None,
                                strategy_id: Optional[str] = None) -> List[dict]:
        """Query trades from SQLite database."""
        if not self._sqlite_log_path:
            return []

        try:
            conn = sqlite3.connect(self._sqlite_log_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM trades WHERE 1=1"
            params = []

            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            if strategy_id:
                query += " AND strategy_id = ?"
                params.append(strategy_id)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to query SQLite log: {e}")
            return []

    def get_portfolio_history(self, limit: int = 100) -> List[dict]:
        """Get portfolio snapshot history from SQLite."""
        if not self._sqlite_log_path:
            return []

        try:
            conn = sqlite3.connect(self._sqlite_log_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM portfolio_snapshots
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to query portfolio history: {e}")
            return []

    def connect(self) -> bool:
        """Paper executor is always connected."""
        self._connected = True
        logger.info("Paper executor ready")
        return True

    def disconnect(self):
        """Disconnect paper executor."""
        self._connected = False
        logger.info("Paper executor disconnected")

    def set_price_provider(self, provider: Callable[[str], float]):
        """Set the price provider function."""
        self._price_provider = provider

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if self._price_provider:
            try:
                return self._price_provider(symbol)
            except Exception as e:
                logger.error(f"Price provider error for {symbol}: {e}")
        return None

    def submit_order(self, order: Order) -> bool:
        """
        Submit a paper order (simulate execution).

        Args:
            order: Order to execute

        Returns:
            bool: True if order was executed
        """
        order.exchange = "paper"
        self._store_order(order)

        # Get fill price
        fill_price = self._determine_fill_price(order)
        if fill_price is None:
            logger.warning(f"No price available for {order.symbol}, using limit price or 100.0")
            fill_price = order.limit_price or 100.0

        # Calculate fill value
        fill_value = order.quantity * fill_price

        # Check if we have enough cash for buys
        if order.side == OrderSide.BUY:
            if fill_value > self.cash:
                order.status = OrderStatus.REJECTED
                logger.warning(f"Insufficient cash for order: need {fill_value}, have {self.cash}")
                return False

        # Simulate commission (0.1% of trade value)
        commission = abs(fill_value) * 0.001

        # Execute the fill
        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            exchange="paper",
            filled_at=datetime.now(),
        )
        self._store_fill(fill)

        # Update position
        self._update_position(order.symbol, order.side, order.quantity, fill_price)

        # Update cash
        if order.side == OrderSide.BUY:
            self.cash -= (fill_value + commission)
        else:
            self.cash += (fill_value - commission)

        # Update order status
        order.status = OrderStatus.FILLED

        # Log the trade
        self._log_trade(order, fill)

        logger.info(f"Paper fill: {order.side.value} {order.quantity} {order.symbol} "
                   f"@ {fill_price} (commission: {commission:.2f})")

        return True

    def _determine_fill_price(self, order: Order) -> Optional[float]:
        """Determine the fill price for an order."""
        # Try to get current market price
        current_price = self.get_current_price(order.symbol)

        if order.order_type == OrderType.MARKET:
            return current_price
        elif order.order_type == OrderType.LIMIT:
            if current_price is None:
                return order.limit_price
            # Simulate limit order fill logic
            if order.side == OrderSide.BUY and current_price <= order.limit_price:
                return current_price
            elif order.side == OrderSide.SELL and current_price >= order.limit_price:
                return current_price
            # Would not fill at market, use limit price for simulation
            return order.limit_price
        else:
            return current_price or order.limit_price

    def _update_position(self, symbol: str, side: OrderSide, quantity: float, price: float):
        """Update position after a fill."""
        if symbol not in self._positions:
            self._positions[symbol] = Position(symbol=symbol)

        pos = self._positions[symbol]

        if side == OrderSide.BUY:
            # Calculate new average cost
            if pos.quantity >= 0:
                # Adding to long or opening long
                total_cost = (pos.quantity * pos.avg_cost) + (quantity * price)
                pos.quantity += quantity
                pos.avg_cost = total_cost / pos.quantity if pos.quantity != 0 else 0
            else:
                # Covering short
                if quantity >= abs(pos.quantity):
                    # Full cover + potential new long
                    realized_pnl = abs(pos.quantity) * (pos.avg_cost - price)
                    pos.realized_pnl += realized_pnl
                    remaining = quantity - abs(pos.quantity)
                    pos.quantity = remaining
                    pos.avg_cost = price if remaining > 0 else 0
                else:
                    # Partial cover
                    realized_pnl = quantity * (pos.avg_cost - price)
                    pos.realized_pnl += realized_pnl
                    pos.quantity += quantity
        else:  # SELL
            if pos.quantity > 0:
                # Closing or reducing long
                if quantity >= pos.quantity:
                    # Full close + potential new short
                    realized_pnl = pos.quantity * (price - pos.avg_cost)
                    pos.realized_pnl += realized_pnl
                    remaining = quantity - pos.quantity
                    pos.quantity = -remaining
                    pos.avg_cost = price if remaining > 0 else 0
                else:
                    # Partial close
                    realized_pnl = quantity * (price - pos.avg_cost)
                    pos.realized_pnl += realized_pnl
                    pos.quantity -= quantity
            else:
                # Adding to short or opening short
                total_cost = (abs(pos.quantity) * pos.avg_cost) + (quantity * price)
                pos.quantity -= quantity
                pos.avg_cost = total_cost / abs(pos.quantity) if pos.quantity != 0 else 0

    def _log_trade(self, order: Order, fill: Fill):
        """Log trade for history (in-memory, CSV, and SQLite)."""
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "price": fill.price,
            "value": fill.value,
            "commission": fill.commission,
            "strategy_id": order.strategy_id,
            "cash_after": self.cash,
            "portfolio_value": self.get_portfolio_value(),
        }

        # Log to in-memory list
        self._trade_log.append(trade_record)

        # Log to CSV
        self._log_to_csv(trade_record)

        # Log to SQLite
        self._log_to_sqlite(trade_record)

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a paper order.

        Args:
            order_id: ID of order to cancel

        Returns:
            bool: True (paper orders can always be cancelled if pending)
        """
        order = self._orders.get(order_id)
        if not order:
            return False

        if order.status in {OrderStatus.PENDING, OrderStatus.SUBMITTED}:
            order.status = OrderStatus.CANCELLED
            logger.info(f"Paper order cancelled: {order_id}")
            return True
        return False

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get order status."""
        order = self._orders.get(order_id)
        return order.status if order else None

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a symbol."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all positions."""
        return self._positions.copy()

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value (cash + positions)."""
        position_value = 0.0
        for symbol, pos in self._positions.items():
            if pos.quantity != 0:
                price = self.get_current_price(symbol)
                if price:
                    position_value += pos.quantity * price
                else:
                    position_value += pos.quantity * pos.avg_cost
        return self.cash + position_value

    def get_total_pnl(self) -> float:
        """Calculate total PnL (realized + unrealized)."""
        realized = sum(pos.realized_pnl for pos in self._positions.values())

        unrealized = 0.0
        for symbol, pos in self._positions.items():
            if pos.quantity != 0:
                price = self.get_current_price(symbol) or pos.avg_cost
                if pos.quantity > 0:
                    unrealized += pos.quantity * (price - pos.avg_cost)
                else:
                    unrealized += abs(pos.quantity) * (pos.avg_cost - price)

        return realized + unrealized

    def get_trade_log(self) -> List[dict]:
        """Get trade history."""
        return self._trade_log.copy()

    def get_summary(self) -> dict:
        """Get paper trading summary."""
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "portfolio_value": self.get_portfolio_value(),
            "total_pnl": self.get_total_pnl(),
            "return_pct": (self.get_portfolio_value() / self.initial_capital - 1) * 100,
            "num_trades": len(self._trade_log),
            "num_positions": len([p for p in self._positions.values() if p.quantity != 0]),
        }

    def reset(self):
        """Reset paper trading state."""
        self.cash = self.initial_capital
        self._positions.clear()
        self._orders.clear()
        self._fills.clear()
        self._trade_log.clear()
        logger.info("Paper executor reset")

    def save_state(self, filepath: str):
        """Save paper trading state to file."""
        state = {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "positions": {k: v.to_dict() for k, v in self._positions.items()},
            "trade_log": self._trade_log,
            "orders": [o.to_dict() for o in self._orders.values()],
            "fills": [f.to_dict() for f in self._fills],
        }
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
        logger.info(f"Paper state saved to {filepath}")

    def load_state(self, filepath: str):
        """Load paper trading state from file."""
        if not os.path.exists(filepath):
            logger.warning(f"State file not found: {filepath}")
            return

        with open(filepath, "r") as f:
            state = json.load(f)

        self.initial_capital = state.get("initial_capital", self.initial_capital)
        self.cash = state.get("cash", self.initial_capital)

        self._positions.clear()
        for symbol, pos_dict in state.get("positions", {}).items():
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=pos_dict.get("quantity", 0),
                avg_cost=pos_dict.get("avg_cost", 0),
                realized_pnl=pos_dict.get("realized_pnl", 0),
            )

        self._trade_log = state.get("trade_log", [])
        logger.info(f"Paper state loaded from {filepath}")
