"""
ETF-Futures Spread Strategy Runner

Integrates the ETF-Futures spread strategy with IBKR data and execution.
Runs on a configurable schedule and manages positions.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from .etf_futures_spread import (
    ETFFuturesSpreadStrategy,
    StrategyConfig,
    SpreadPairConfig,
    MarketState,
    TradeSignal,
    PositionSide,
    DEFAULT_PAIRS,
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
class RunnerState:
    """State tracking for the runner."""
    running: bool = False
    last_update: Optional[datetime] = None
    error_count: int = 0
    successful_updates: int = 0
    signals_generated: int = 0
    trades_executed: int = 0


class SpreadStrategyRunner:
    """
    Runner for ETF-Futures Spread Strategy.

    Integrates with IBKR for data and execution, runs on schedule,
    and manages positions across multiple pairs.
    """

    def __init__(self,
                 ibkr_client: Optional[IBKRClient] = None,
                 execution_router: Optional[ExecutionRouter] = None,
                 strategy_config: Optional[StrategyConfig] = None,
                 pairs: Optional[Dict[str, SpreadPairConfig]] = None,
                 on_signal_callback: Optional[Callable[[TradeSignal], None]] = None):
        """
        Initialize the runner.

        Args:
            ibkr_client: IBKR client for market data
            execution_router: Execution router for order submission
            strategy_config: Strategy configuration
            pairs: Pair configurations
            on_signal_callback: Optional callback for new signals
        """
        self.ibkr_client = ibkr_client
        self.execution_router = execution_router
        self.pairs = pairs or DEFAULT_PAIRS

        # Create strategy
        self.strategy = ETFFuturesSpreadStrategy(
            config=strategy_config,
            pairs=self.pairs,
        )

        # State
        self._state = RunnerState()
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._market_states: Dict[str, MarketState] = {}
        self._signal_history: List[TradeSignal] = []
        self._on_signal_callback = on_signal_callback

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

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

            # Connect to IBKR
            if not self.ibkr_client.is_connected:
                if not self.ibkr_client.connect():
                    logger.warning("IBKR connection failed - will use mock data")

            # Initialize execution router if not provided
            if self.execution_router is None:
                self.execution_router = ExecutionRouter()
                self.execution_router.initialize()

            # Initialize positions tracking
            for pair_id in self.pairs:
                self._positions[pair_id] = {
                    "side": PositionSide.FLAT,
                    "etf_qty": 0.0,
                    "futures_qty": 0.0,
                    "entry_price_etf": 0.0,
                    "entry_price_futures": 0.0,
                    "entry_time": None,
                    "entry_z_score": None,
                }

            logger.info("Spread strategy runner initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize runner: {e}")
            return False

    def fetch_market_data(self, pair_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch market data for a pair from IBKR.

        Args:
            pair_id: Pair identifier

        Returns:
            Dictionary with ETF and futures prices
        """
        if pair_id not in self.pairs:
            return None

        pair_config = self.pairs[pair_id]

        try:
            if self.ibkr_client and self.ibkr_client.is_connected:
                # Create contracts
                etf_contract = self.ibkr_client.create_stock_contract(
                    pair_config.etf_symbol
                )
                futures_contract = self.ibkr_client.create_future_contract(
                    pair_config.futures_symbol,
                    exchange=pair_config.futures_exchange,
                )

                # Get quotes
                etf_quote = self.ibkr_client.get_quote(etf_contract)
                futures_quote = self.ibkr_client.get_quote(futures_contract)

                if etf_quote and futures_quote:
                    etf_mid = (etf_quote["bid"] + etf_quote["ask"]) / 2 if etf_quote["bid"] and etf_quote["ask"] else etf_quote["last"]
                    futures_mid = (futures_quote["bid"] + futures_quote["ask"]) / 2 if futures_quote["bid"] and futures_quote["ask"] else futures_quote["last"]

                    return {
                        "etf_price": etf_mid,
                        "etf_bid": etf_quote.get("bid"),
                        "etf_ask": etf_quote.get("ask"),
                        "futures_price": futures_mid,
                        "futures_bid": futures_quote.get("bid"),
                        "futures_ask": futures_quote.get("ask"),
                        "timestamp": datetime.now(),
                    }

            # Fallback to mock data for testing
            return self._generate_mock_data(pair_id)

        except Exception as e:
            logger.error(f"Error fetching market data for {pair_id}: {e}")
            return self._generate_mock_data(pair_id)

    def _generate_mock_data(self, pair_id: str) -> Dict[str, Any]:
        """Generate mock market data for testing."""
        pair_config = self.pairs[pair_id]

        # Base prices (approximate current levels)
        base_prices = {
            "SPY_ES": (450.0, 4500.0),
            "QQQ_NQ": (380.0, 15200.0),
            "IWM_RTY": (200.0, 2000.0),
        }

        etf_base, futures_base = base_prices.get(pair_id, (100.0, 1000.0))

        # Add some random noise
        etf_price = etf_base + np.random.randn() * 0.5
        futures_price = futures_base + np.random.randn() * 5

        # Add spread noise (occasionally larger for signal generation)
        if np.random.random() < 0.1:  # 10% chance of dislocation
            etf_price += np.random.choice([-1, 1]) * np.random.uniform(0.5, 1.5)

        return {
            "etf_price": etf_price,
            "etf_bid": etf_price - 0.01,
            "etf_ask": etf_price + 0.01,
            "futures_price": futures_price,
            "futures_bid": futures_price - 0.25,
            "futures_ask": futures_price + 0.25,
            "timestamp": datetime.now(),
        }

    def update_pair(self, pair_id: str) -> Optional[TradeSignal]:
        """
        Update a single pair with new market data and generate signal.

        Args:
            pair_id: Pair identifier

        Returns:
            TradeSignal if a signal was generated
        """
        # Fetch market data
        market_data = self.fetch_market_data(pair_id)
        if not market_data:
            return None

        # Update strategy with new prices
        spread_data = self.strategy.update_prices(
            pair_id=pair_id,
            etf_price=market_data["etf_price"],
            futures_price=market_data["futures_price"],
            timestamp=market_data["timestamp"],
        )

        # Skip if we don't have enough history for z-score
        if spread_data.z_score is None:
            logger.debug(f"{pair_id}: Insufficient history for z-score")
            return None

        # Get current position
        position = self._positions[pair_id]

        # Create market state
        pair_config = self.pairs[pair_id]
        spread_history = [h["spread"] for h in self.strategy._spread_history[pair_id]]

        market_state = MarketState(
            pair_id=pair_id,
            config=pair_config,
            etf_price=market_data["etf_price"],
            etf_bid=market_data.get("etf_bid", market_data["etf_price"] - 0.01),
            etf_ask=market_data.get("etf_ask", market_data["etf_price"] + 0.01),
            futures_price=market_data["futures_price"],
            futures_bid=market_data.get("futures_bid", market_data["futures_price"] - 0.25),
            futures_ask=market_data.get("futures_ask", market_data["futures_price"] + 0.25),
            spread=spread_data.spread,
            spread_history=spread_history,
            z_score=spread_data.z_score,
            timestamp=market_data["timestamp"],
            position_side=position["side"],
            position_etf_qty=position["etf_qty"],
            position_futures_qty=position["futures_qty"],
            entry_z_score=position["entry_z_score"],
            entry_time=position["entry_time"],
        )

        # Store market state
        self._market_states[pair_id] = market_state

        # Generate signal
        signal = self.strategy.generate_signal(market_state)

        # Process signal
        if signal.signal not in ("FLAT",):
            self._state.signals_generated += 1
            self._signal_history.append(signal)

            # Execute if not FLAT
            if signal.signal in ("LONG", "SHORT", "CLOSE"):
                self._execute_signal(pair_id, signal)

            # Callback
            if self._on_signal_callback:
                self._on_signal_callback(signal)

            return signal

        return None

    def _execute_signal(self, pair_id: str, signal: TradeSignal):
        """
        Execute a trading signal.

        Args:
            pair_id: Pair identifier
            signal: Signal to execute
        """
        logger.info(f"Executing signal: {signal.signal} for {pair_id}")

        position = self._positions[pair_id]

        if signal.signal == "LONG":
            # Long ETF, Short Future
            self._execute_trade(
                signal.symbol_etf,
                OrderSide.BUY,
                signal.size_etf,
                "ibkr",
            )
            self._execute_trade(
                signal.symbol_hedge,
                OrderSide.SELL,
                signal.size_hedge,
                "ibkr",
            )

            # Update position tracking
            position["side"] = PositionSide.LONG_ETF
            position["etf_qty"] = signal.size_etf
            position["futures_qty"] = -signal.size_hedge
            position["entry_price_etf"] = signal.metadata.get("etf_price", 0)
            position["entry_price_futures"] = signal.metadata.get("futures_price", 0)
            position["entry_time"] = datetime.now()
            position["entry_z_score"] = signal.z_score

        elif signal.signal == "SHORT":
            # Short ETF, Long Future
            self._execute_trade(
                signal.symbol_etf,
                OrderSide.SELL,
                signal.size_etf,
                "ibkr",
            )
            self._execute_trade(
                signal.symbol_hedge,
                OrderSide.BUY,
                signal.size_hedge,
                "ibkr",
            )

            position["side"] = PositionSide.SHORT_ETF
            position["etf_qty"] = -signal.size_etf
            position["futures_qty"] = signal.size_hedge
            position["entry_price_etf"] = signal.metadata.get("etf_price", 0)
            position["entry_price_futures"] = signal.metadata.get("futures_price", 0)
            position["entry_time"] = datetime.now()
            position["entry_z_score"] = signal.z_score

        elif signal.signal == "CLOSE":
            # Close existing position
            if position["side"] == PositionSide.LONG_ETF:
                self._execute_trade(
                    signal.symbol_etf,
                    OrderSide.SELL,
                    abs(position["etf_qty"]),
                    "ibkr",
                )
                self._execute_trade(
                    signal.symbol_hedge,
                    OrderSide.BUY,
                    abs(position["futures_qty"]),
                    "ibkr",
                )
            elif position["side"] == PositionSide.SHORT_ETF:
                self._execute_trade(
                    signal.symbol_etf,
                    OrderSide.BUY,
                    abs(position["etf_qty"]),
                    "ibkr",
                )
                self._execute_trade(
                    signal.symbol_hedge,
                    OrderSide.SELL,
                    abs(position["futures_qty"]),
                    "ibkr",
                )

            # Reset position
            position["side"] = PositionSide.FLAT
            position["etf_qty"] = 0.0
            position["futures_qty"] = 0.0
            position["entry_time"] = None
            position["entry_z_score"] = None

        self._state.trades_executed += 1

    def _execute_trade(self, symbol: str, side: OrderSide, quantity: float, exchange: str):
        """Submit a trade order."""
        if not self.execution_router:
            logger.warning(f"No execution router - would trade {side.value} {quantity} {symbol}")
            return

        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            exchange=exchange,
            strategy_id="etf_futures_spread",
        )

        success = self.execution_router.submit_order(order)
        if success:
            logger.info(f"Order submitted: {side.value} {quantity} {symbol}")
        else:
            logger.error(f"Order failed: {side.value} {quantity} {symbol}")

    def run_once(self) -> Dict[str, Optional[TradeSignal]]:
        """
        Run a single update cycle for all pairs.

        Returns:
            Dictionary of pair_id -> signal (None if no signal)
        """
        results = {}

        for pair_id in self.pairs:
            try:
                signal = self.update_pair(pair_id)
                results[pair_id] = signal
            except Exception as e:
                logger.error(f"Error updating {pair_id}: {e}")
                self._state.error_count += 1
                results[pair_id] = None

        self._state.last_update = datetime.now()
        self._state.successful_updates += 1

        return results

    def _run_loop(self):
        """Main run loop (called in thread)."""
        interval = self.strategy.config.update_interval_seconds

        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                self._state.error_count += 1

            # Wait for next interval
            self._stop_event.wait(interval)

        self._state.running = False
        logger.info("Spread strategy runner stopped")

    def start(self):
        """Start the runner in a background thread."""
        if self._state.running:
            logger.warning("Runner already running")
            return

        self._stop_event.clear()
        self._state.running = True

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info("Spread strategy runner started")

    def stop(self):
        """Stop the runner."""
        if not self._state.running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

        logger.info("Spread strategy runner stopped")

    def get_state(self) -> Dict[str, Any]:
        """Get current runner state."""
        return {
            "running": self._state.running,
            "last_update": self._state.last_update.isoformat() if self._state.last_update else None,
            "error_count": self._state.error_count,
            "successful_updates": self._state.successful_updates,
            "signals_generated": self._state.signals_generated,
            "trades_executed": self._state.trades_executed,
            "execution_mode": EXECUTION_MODE,
            "pairs": list(self.pairs.keys()),
            "positions": {
                pair_id: {
                    "side": pos["side"].value,
                    "etf_qty": pos["etf_qty"],
                    "futures_qty": pos["futures_qty"],
                }
                for pair_id, pos in self._positions.items()
            },
        }

    def get_market_state(self, pair_id: str) -> Optional[MarketState]:
        """Get current market state for a pair."""
        return self._market_states.get(pair_id)

    def get_signal_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signal history."""
        return [s.to_dict() for s in self._signal_history[-limit:]]

    def get_spread_chart_data(self, pair_id: str, minutes: int = 60) -> pd.DataFrame:
        """Get spread data for charting."""
        return self.strategy.get_spread_history(pair_id, minutes)

    def shutdown(self):
        """Shutdown the runner and connections."""
        self.stop()

        if self.ibkr_client:
            self.ibkr_client.disconnect()

        if self.execution_router:
            self.execution_router.shutdown()

        logger.info("Spread strategy runner shutdown complete")
