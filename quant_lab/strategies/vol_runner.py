"""
Vol-of-Vol Mean Reversion Strategy Runner

Integrates the vol mean reversion strategy with IBKR data and execution.
Runs on a configurable schedule and manages positions.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .vol_mean_reversion import (
    VolMeanReversionStrategy,
    VolMeanReversionConfig,
    VolMarketState,
    VolSignal,
    VolPosition,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_sources.ibkr_client import IBKRClient
from execution.execution_router import ExecutionRouter
from execution.base_executor import Order, OrderSide, OrderType
from config import EXECUTION_MODE

logger = logging.getLogger(__name__)


@dataclass
class VolRunnerState:
    """State tracking for the runner."""
    running: bool = False
    last_update: Optional[datetime] = None
    error_count: int = 0
    successful_updates: int = 0
    signals_generated: int = 0


class VolMeanReversionRunner:
    """
    Runner for Vol-of-Vol Mean Reversion Strategy.

    Integrates with IBKR for VIX and volatility ETF data.
    """

    def __init__(self,
                 ibkr_client: Optional[IBKRClient] = None,
                 execution_router: Optional[ExecutionRouter] = None,
                 config: Optional[VolMeanReversionConfig] = None,
                 on_signal_callback: Optional[Callable[[VolSignal], None]] = None):
        """
        Initialize the runner.

        Args:
            ibkr_client: IBKR client for market data
            execution_router: Execution router for order submission
            config: Strategy configuration
            on_signal_callback: Optional callback for new signals
        """
        self.ibkr_client = ibkr_client
        self.execution_router = execution_router
        self.config = config or VolMeanReversionConfig()

        # Create strategy
        self.strategy = VolMeanReversionStrategy(config=self.config)

        # State
        self._state = VolRunnerState()
        self._last_market_state: Optional[VolMarketState] = None
        self._on_signal_callback = on_signal_callback

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Cache for prev close prices
        self._prev_closes: Dict[str, float] = {}

    @property
    def is_running(self) -> bool:
        """Check if runner is running."""
        return self._state.running

    def initialize(self) -> bool:
        """Initialize connections and state."""
        try:
            # Initialize IBKR client if not provided
            if self.ibkr_client is None:
                self.ibkr_client = IBKRClient()

            # Connect if not connected
            if not self.ibkr_client.is_connected:
                if not self.ibkr_client.connect():
                    logger.warning("IBKR connection failed - will use mock data")

            # Initialize execution router if not provided
            if self.execution_router is None:
                self.execution_router = ExecutionRouter()
                self.execution_router.initialize()

            logger.info("Vol Mean Reversion Runner initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize runner: {e}")
            return False

    def fetch_market_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch VIX and volatility ETF data.

        Returns:
            Dictionary with market data
        """
        try:
            if self.ibkr_client and self.ibkr_client.is_connected:
                return self._fetch_live_data()
            else:
                return self._generate_mock_data()

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return self._generate_mock_data()

    def _fetch_live_data(self) -> Dict[str, Any]:
        """Fetch live data from IBKR."""
        data = {}

        # VIX (index contract)
        vix_contract = self.ibkr_client.create_index_contract("VIX", "CBOE")
        vix_quote = self.ibkr_client.get_quote(vix_contract)
        if vix_quote:
            current_price = vix_quote.get("last") or vix_quote.get("close", 0)
            prev_close = vix_quote.get("close") or self._prev_closes.get("VIX", current_price)
            self._prev_closes["VIX"] = prev_close

            data["VIX"] = {
                "price": current_price,
                "prev_close": prev_close,
                "high": vix_quote.get("high"),
                "low": vix_quote.get("low"),
            }

        # UVXY
        uvxy_contract = self.ibkr_client.create_stock_contract("UVXY")
        uvxy_quote = self.ibkr_client.get_quote(uvxy_contract)
        if uvxy_quote:
            data["UVXY"] = {
                "price": uvxy_quote.get("last") or uvxy_quote.get("close"),
                "bid": uvxy_quote.get("bid"),
                "ask": uvxy_quote.get("ask"),
                "volume": uvxy_quote.get("volume"),
            }

        # SVXY
        svxy_contract = self.ibkr_client.create_stock_contract("SVXY")
        svxy_quote = self.ibkr_client.get_quote(svxy_contract)
        if svxy_quote:
            data["SVXY"] = {
                "price": svxy_quote.get("last") or svxy_quote.get("close"),
                "bid": svxy_quote.get("bid"),
                "ask": svxy_quote.get("ask"),
                "volume": svxy_quote.get("volume"),
            }

        # VXX
        vxx_contract = self.ibkr_client.create_stock_contract("VXX")
        vxx_quote = self.ibkr_client.get_quote(vxx_contract)
        if vxx_quote:
            data["VXX"] = {
                "price": vxx_quote.get("last") or vxx_quote.get("close"),
                "bid": vxx_quote.get("bid"),
                "ask": vxx_quote.get("ask"),
                "volume": vxx_quote.get("volume"),
            }

        return data

    def _generate_mock_data(self) -> Dict[str, Any]:
        """Generate mock market data for testing."""
        import numpy as np

        # Get or set previous close
        vix_prev = self._prev_closes.get("VIX", 20.0)

        # Generate VIX with occasional spikes
        if np.random.random() < 0.1:
            # 10% chance of spike/crash
            vix_change = np.random.choice([-1, 1]) * np.random.uniform(10, 35)
        else:
            vix_change = np.random.uniform(-5, 5)

        vix_price = max(10, vix_prev * (1 + vix_change / 100))

        # Update prev close occasionally (simulate new day)
        if np.random.random() < 0.05:
            self._prev_closes["VIX"] = vix_price

        # Correlated ETF prices
        uvxy_base = 12.0
        svxy_base = 45.0
        vxx_base = 22.0

        # UVXY moves up when VIX spikes
        uvxy_mult = 1 + (vix_change / 100) * 1.5  # 1.5x leverage
        svxy_mult = 1 - (vix_change / 100) * 0.5  # Inverse
        vxx_mult = 1 + (vix_change / 100)

        return {
            "VIX": {
                "price": vix_price,
                "prev_close": vix_prev,
            },
            "UVXY": {
                "price": uvxy_base * uvxy_mult + np.random.randn() * 0.5,
            },
            "SVXY": {
                "price": svxy_base * svxy_mult + np.random.randn() * 0.5,
            },
            "VXX": {
                "price": vxx_base * vxx_mult + np.random.randn() * 0.2,
            },
        }

    def update(self) -> Optional[VolSignal]:
        """
        Run a single update cycle.

        Returns:
            VolSignal if a signal was generated
        """
        # Fetch market data
        market_data = self.fetch_market_data()
        if not market_data or "VIX" not in market_data:
            return None

        # Update strategy market state
        state = self.strategy.update_market_state(market_data)
        if not state:
            return None

        self._last_market_state = state

        # Update position PnL if we have one
        position = self.strategy.get_position()
        if position:
            instrument_data = market_data.get(position.instrument, {})
            price = instrument_data.get("price")
            if price:
                position.update_pnl(price)

        # Generate signal
        signal = self.strategy.generate_signal(state)

        # Execute signal
        if signal.signal in ("SHORT_VOL", "LONG_VOL", "EXIT", "STOP_LOSS"):
            self._execute_signal(signal, market_data)
            self._state.signals_generated += 1

            if self._on_signal_callback:
                self._on_signal_callback(signal)

            return signal

        return None

    def _execute_signal(self, signal: VolSignal, market_data: Dict[str, Any]):
        """Execute a trading signal."""
        if signal.signal in ("SHORT_VOL", "LONG_VOL"):
            # Open position
            instrument_data = market_data.get(signal.instrument, {})
            price = instrument_data.get("price")

            if not price:
                logger.warning(f"No price for {signal.instrument}")
                return

            position = self.strategy.open_position(signal, price)

            if position and EXECUTION_MODE == "live":
                self._execute_order(signal, price)

        elif signal.signal in ("EXIT", "STOP_LOSS"):
            # Close position
            position = self.strategy.get_position()
            if not position:
                return

            instrument_data = market_data.get(position.instrument, {})
            price = instrument_data.get("price")

            if not price:
                logger.warning(f"No price for {position.instrument}")
                return

            summary = self.strategy.close_position(price, signal.reason)

            if summary and EXECUTION_MODE == "live":
                self._execute_close_order(position, price)

    def _execute_order(self, signal: VolSignal, price: float):
        """Execute an order on IBKR."""
        if not self.execution_router:
            logger.warning(f"No execution router - would trade {signal.instrument}")
            return

        quantity = signal.notional_usd / price

        # Determine side based on position type
        if signal.position_type == "LONG":
            side = OrderSide.BUY
        else:
            side = OrderSide.SELL

        order = Order(
            symbol=signal.instrument,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            exchange="ibkr",
            strategy_id="vol_mean_reversion",
        )

        success = self.execution_router.submit_order(order)
        if success:
            logger.info(f"Order submitted: {side.value} {quantity:.2f} {signal.instrument}")
        else:
            logger.error(f"Order failed: {side.value} {quantity:.2f} {signal.instrument}")

    def _execute_close_order(self, position: VolPosition, price: float):
        """Execute a close order on IBKR."""
        if not self.execution_router:
            return

        # Opposite of entry side
        if position.position_type == "LONG":
            side = OrderSide.SELL
        else:
            side = OrderSide.BUY

        order = Order(
            symbol=position.instrument,
            side=side,
            quantity=position.quantity,
            order_type=OrderType.MARKET,
            exchange="ibkr",
            strategy_id="vol_mean_reversion",
        )

        success = self.execution_router.submit_order(order)
        if success:
            logger.info(f"Close order submitted: {side.value} {position.quantity:.2f} {position.instrument}")

    def run_once(self) -> Optional[VolSignal]:
        """Run a single update."""
        try:
            signal = self.update()
            self._state.last_update = datetime.now()
            self._state.successful_updates += 1
            return signal

        except Exception as e:
            logger.error(f"Error in update: {e}")
            self._state.error_count += 1
            return None

    def _run_loop(self):
        """Main run loop (called in thread)."""
        # Default to checking every minute
        interval = 60

        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                self._state.error_count += 1

            # Wait for next interval
            self._stop_event.wait(interval)

        self._state.running = False
        logger.info("Vol Mean Reversion Runner stopped")

    def start(self):
        """Start the runner in a background thread."""
        if self._state.running:
            logger.warning("Runner already running")
            return

        self._stop_event.clear()
        self._state.running = True

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info("Vol Mean Reversion Runner started")

    def stop(self):
        """Stop the runner."""
        if not self._state.running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

        logger.info("Vol Mean Reversion Runner stopped")

    def get_state(self) -> Dict[str, Any]:
        """Get current runner state."""
        return {
            "running": self._state.running,
            "last_update": self._state.last_update.isoformat() if self._state.last_update else None,
            "error_count": self._state.error_count,
            "successful_updates": self._state.successful_updates,
            "signals_generated": self._state.signals_generated,
            "execution_mode": EXECUTION_MODE,
            "last_market_state": self._last_market_state.to_dict() if self._last_market_state else None,
            "strategy_state": self.strategy.get_state(),
        }

    def get_position(self) -> Optional[Dict[str, Any]]:
        """Get current position."""
        position = self.strategy.get_position()
        return position.to_dict() if position else None

    def get_closed_positions(self) -> List[Dict[str, Any]]:
        """Get closed positions."""
        return self.strategy.get_closed_positions()

    def manual_short_vol(self) -> Optional[VolSignal]:
        """Manually trigger a short vol trade."""
        market_data = self.fetch_market_data()
        if not market_data:
            return None

        state = self.strategy.update_market_state(market_data)
        if not state:
            return None

        signal = VolSignal(
            signal="SHORT_VOL",
            instrument=self.config.preferred_short_vol,
            notional_usd=self.config.notional_usd,
            vix_change_pct=state.vix_change_pct,
            vix_price=state.vix_price,
            reason="Manual short vol",
            position_type="LONG" if self.config.preferred_short_vol == "SVXY" else "SHORT",
        )

        self._execute_signal(signal, market_data)
        return signal

    def manual_long_vol(self) -> Optional[VolSignal]:
        """Manually trigger a long vol trade."""
        market_data = self.fetch_market_data()
        if not market_data:
            return None

        state = self.strategy.update_market_state(market_data)
        if not state:
            return None

        signal = VolSignal(
            signal="LONG_VOL",
            instrument=self.config.preferred_long_vol,
            notional_usd=self.config.notional_usd,
            vix_change_pct=state.vix_change_pct,
            vix_price=state.vix_price,
            reason="Manual long vol",
            position_type="LONG" if self.config.preferred_long_vol in ["UVXY", "VXX"] else "SHORT",
        )

        self._execute_signal(signal, market_data)
        return signal

    def manual_close(self) -> Optional[Dict[str, Any]]:
        """Manually close the current position."""
        if not self.strategy.has_position():
            logger.warning("No position to close")
            return None

        market_data = self.fetch_market_data()
        if not market_data:
            return None

        position = self.strategy.get_position()
        instrument_data = market_data.get(position.instrument, {})
        price = instrument_data.get("price")

        if not price:
            return None

        summary = self.strategy.close_position(price, "Manual close")

        if summary and EXECUTION_MODE == "live":
            self._execute_close_order(position, price)

        return summary

    def shutdown(self):
        """Shutdown the runner."""
        self.stop()

        if self.execution_router:
            self.execution_router.shutdown()

        logger.info("Vol Mean Reversion Runner shutdown complete")
