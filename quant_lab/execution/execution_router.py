"""
Execution Router

Routes orders to the appropriate executor based on EXECUTION_MODE and order properties.
"""

import logging
from typing import Optional, Dict, Any

from .base_executor import BaseExecutor, Order, OrderStatus
from .paper_executor import PaperExecutor
from .ibkr_executor import IBKRExecutor
from .coinbase_executor import CoinbaseExecutor

import sys
sys.path.insert(0, '..')
from config import EXECUTION_MODE

logger = logging.getLogger(__name__)


class ExecutionRouter:
    """
    Routes orders to the appropriate executor.

    In paper mode: All orders go to PaperExecutor
    In live mode: Orders are routed to IBKR or Coinbase based on symbol/exchange
    """

    def __init__(self):
        self._paper_executor: Optional[PaperExecutor] = None
        self._ibkr_executor: Optional[IBKRExecutor] = None
        self._coinbase_executor: Optional[CoinbaseExecutor] = None
        self._initialized = False

    @property
    def mode(self) -> str:
        """Get current execution mode."""
        return EXECUTION_MODE

    @property
    def is_paper(self) -> bool:
        """Check if in paper mode."""
        return EXECUTION_MODE == "paper"

    def initialize(self, initial_capital: float = 100000.0) -> bool:
        """
        Initialize executors based on execution mode.

        Args:
            initial_capital: Initial capital for paper trading

        Returns:
            bool: True if initialization successful
        """
        try:
            # Always initialize paper executor (for tracking)
            self._paper_executor = PaperExecutor(initial_capital=initial_capital)
            self._paper_executor.connect()

            if EXECUTION_MODE == "live":
                # Initialize live executors
                self._ibkr_executor = IBKRExecutor()
                self._coinbase_executor = CoinbaseExecutor()

                # Connect (may fail if credentials not configured)
                ibkr_ok = self._ibkr_executor.connect()
                coinbase_ok = self._coinbase_executor.connect()

                if not ibkr_ok:
                    logger.warning("IBKR executor failed to connect")
                if not coinbase_ok:
                    logger.warning("Coinbase executor failed to connect")

            self._initialized = True
            logger.info(f"Execution router initialized in {EXECUTION_MODE} mode")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize execution router: {e}")
            return False

    def shutdown(self):
        """Shutdown all executors."""
        if self._paper_executor:
            self._paper_executor.disconnect()
        if self._ibkr_executor:
            self._ibkr_executor.disconnect()
        if self._coinbase_executor:
            self._coinbase_executor.disconnect()
        self._initialized = False
        logger.info("Execution router shutdown")

    def _get_executor_for_order(self, order: Order) -> Optional[BaseExecutor]:
        """Determine which executor to use for an order."""
        if EXECUTION_MODE == "paper":
            return self._paper_executor

        # In live mode, route based on exchange
        exchange = order.exchange or self._infer_exchange(order.symbol)

        if exchange == "ibkr":
            return self._ibkr_executor
        elif exchange in ("coinbase", "binance"):
            return self._coinbase_executor
        else:
            # Default to paper for unknown exchanges
            logger.warning(f"Unknown exchange for {order.symbol}, using paper executor")
            return self._paper_executor

    def _infer_exchange(self, symbol: str) -> str:
        """Infer exchange from symbol format."""
        # Crypto symbols typically have / (e.g., BTC/USD)
        if "/" in symbol:
            return "coinbase"
        # Stock symbols are typically just letters
        return "ibkr"

    def submit_order(self, order: Order) -> bool:
        """
        Submit an order through the appropriate executor.

        Args:
            order: Order to submit

        Returns:
            bool: True if order was submitted successfully
        """
        if not self._initialized:
            logger.error("Execution router not initialized")
            return False

        executor = self._get_executor_for_order(order)
        if not executor:
            logger.error(f"No executor available for order: {order.order_id}")
            return False

        logger.info(f"Routing order {order.order_id} to {executor.name} executor")
        return executor.submit_order(order)

    def cancel_order(self, order_id: str, exchange: Optional[str] = None) -> bool:
        """
        Cancel an order.

        Args:
            order_id: ID of order to cancel
            exchange: Optional exchange hint

        Returns:
            bool: True if cancellation was successful
        """
        # Try all executors
        executors = [self._paper_executor, self._ibkr_executor, self._coinbase_executor]

        for executor in executors:
            if executor and executor.get_order(order_id):
                return executor.cancel_order(order_id)

        logger.error(f"Order {order_id} not found in any executor")
        return False

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get status of an order from any executor."""
        executors = [self._paper_executor, self._ibkr_executor, self._coinbase_executor]

        for executor in executors:
            if executor:
                status = executor.get_order_status(order_id)
                if status:
                    return status
        return None

    def get_all_orders(self) -> list:
        """Get all orders from all executors."""
        orders = []
        executors = [self._paper_executor, self._ibkr_executor, self._coinbase_executor]

        for executor in executors:
            if executor:
                orders.extend(executor.get_all_orders())
        return orders

    def get_all_fills(self) -> list:
        """Get all fills from all executors."""
        fills = []
        executors = [self._paper_executor, self._ibkr_executor, self._coinbase_executor]

        for executor in executors:
            if executor:
                fills.extend(executor.get_fills())
        return fills

    def get_positions(self) -> Dict[str, Any]:
        """Get positions from appropriate executor."""
        if EXECUTION_MODE == "paper":
            return {k: v.to_dict() for k, v in self._paper_executor.get_all_positions().items()}
        else:
            positions = {}
            if self._ibkr_executor:
                positions["ibkr"] = self._ibkr_executor.get_positions()
            if self._coinbase_executor:
                positions["coinbase"] = self._coinbase_executor.get_balance()
            return positions

    def get_paper_summary(self) -> Dict[str, Any]:
        """Get paper trading summary."""
        if self._paper_executor:
            return self._paper_executor.get_summary()
        return {}

    @property
    def paper_executor(self) -> Optional[PaperExecutor]:
        """Access paper executor directly."""
        return self._paper_executor

    @property
    def ibkr_executor(self) -> Optional[IBKRExecutor]:
        """Access IBKR executor directly."""
        return self._ibkr_executor

    @property
    def coinbase_executor(self) -> Optional[CoinbaseExecutor]:
        """Access Coinbase executor directly."""
        return self._coinbase_executor

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
