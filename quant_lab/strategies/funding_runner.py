"""
Crypto Funding Harvest Strategy Runner

Integrates the funding harvest strategy with crypto data sources and execution.
Runs on a configurable schedule and manages positions.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .crypto_funding_harvest import (
    CryptoFundingHarvestStrategy,
    FundingHarvestConfig,
    MarketState,
    FundingSignal,
    CarryPosition,
    PositionType,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_sources.crypto_client import CryptoClient
from execution.execution_router import ExecutionRouter
from execution.base_executor import Order, OrderSide, OrderType
from config import EXECUTION_MODE

logger = logging.getLogger(__name__)


@dataclass
class RunnerState:
    """State tracking for the runner."""
    running: bool = False
    last_update: Optional[datetime] = None
    last_funding_check: Dict[str, datetime] = None
    error_count: int = 0
    successful_updates: int = 0
    signals_generated: int = 0

    def __post_init__(self):
        if self.last_funding_check is None:
            self.last_funding_check = {}


class FundingHarvestRunner:
    """
    Runner for Crypto Funding Harvest Strategy.

    Integrates with Coinbase/Binance for data and manages simulated positions.
    """

    def __init__(self,
                 crypto_client: Optional[CryptoClient] = None,
                 execution_router: Optional[ExecutionRouter] = None,
                 config: Optional[FundingHarvestConfig] = None,
                 on_signal_callback: Optional[Callable[[FundingSignal], None]] = None):
        """
        Initialize the runner.

        Args:
            crypto_client: Crypto client for market data
            execution_router: Execution router for order submission
            config: Strategy configuration
            on_signal_callback: Optional callback for new signals
        """
        self.crypto_client = crypto_client
        self.execution_router = execution_router
        self.config = config or FundingHarvestConfig()

        # Create strategy
        self.strategy = CryptoFundingHarvestStrategy(config=self.config)

        # State
        self._state = RunnerState()
        self._market_states: Dict[str, MarketState] = {}
        self._on_signal_callback = on_signal_callback

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Track funding times to detect new funding settlements
        self._next_funding_times: Dict[str, datetime] = {}

    @property
    def is_running(self) -> bool:
        """Check if runner is running."""
        return self._state.running

    def initialize(self) -> bool:
        """Initialize connections and state."""
        try:
            # Initialize crypto client if not provided
            if self.crypto_client is None:
                self.crypto_client = CryptoClient()

            # Initialize crypto client
            if not self.crypto_client.is_initialized:
                if not self.crypto_client.initialize():
                    logger.warning("Crypto client init failed - will use mock data")

            # Initialize execution router if not provided
            if self.execution_router is None:
                self.execution_router = ExecutionRouter()
                self.execution_router.initialize()

            logger.info(f"Funding Harvest Runner initialized for {self.config.assets}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize runner: {e}")
            return False

    def fetch_market_data(self, asset: str) -> Optional[Dict[str, Any]]:
        """
        Fetch market data for an asset.

        Args:
            asset: Asset symbol (e.g., "BTC")

        Returns:
            Dictionary with spot and perp data
        """
        try:
            if self.crypto_client and self.crypto_client.is_initialized:
                data = self.crypto_client.get_spot_and_perp_prices(asset)
                if data:
                    return data

            # Fallback to mock data for testing
            return self._generate_mock_data(asset)

        except Exception as e:
            logger.error(f"Error fetching market data for {asset}: {e}")
            return self._generate_mock_data(asset)

    def _generate_mock_data(self, asset: str) -> Dict[str, Any]:
        """Generate mock market data for testing."""
        import numpy as np

        base_prices = {
            "BTC": (45000.0, 45100.0),
            "ETH": (2500.0, 2505.0),
        }

        spot_base, perp_base = base_prices.get(asset, (1000.0, 1001.0))

        # Add some noise
        spot_price = spot_base + np.random.randn() * 50
        perp_price = perp_base + np.random.randn() * 50

        # Random funding rate (occasionally extreme)
        if np.random.random() < 0.2:
            funding_rate = np.random.choice([-1, 1]) * np.random.uniform(0.0005, 0.002)
        else:
            funding_rate = np.random.uniform(-0.0003, 0.0003)

        funding_pct = funding_rate * 100

        return {
            "asset": asset,
            "spot_symbol": f"{asset}/USD",
            "perp_symbol": f"{asset}/USDT",
            "spot_price": spot_price,
            "perp_price": perp_price,
            "mark_price": perp_price,
            "funding_rate": funding_rate,
            "funding_rate_pct": funding_pct,
            "annualized_funding_pct": funding_pct * 3 * 365,
            "basis_pct": ((perp_price - spot_price) / spot_price) * 100,
            "next_funding_time": datetime.now() + timedelta(hours=np.random.uniform(0.5, 8)),
            "timestamp": datetime.now(),
        }

    def update_asset(self, asset: str) -> Optional[FundingSignal]:
        """
        Update a single asset with new market data and generate signal.

        Args:
            asset: Asset symbol

        Returns:
            FundingSignal if a signal was generated
        """
        # Fetch market data
        market_data = self.fetch_market_data(asset)
        if not market_data:
            return None

        # Update strategy market state
        state = self.strategy.update_market_state(asset, market_data)
        if not state:
            return None

        self._market_states[asset] = state

        # Check for funding settlement
        self._check_funding_settlement(asset, market_data)

        # Update position PnL if we have one
        position = self.strategy.get_position(asset)
        if position:
            self.strategy.update_position_pnl(
                asset,
                market_data["spot_price"],
                market_data["perp_price"]
            )

        # Generate signal
        signal = self.strategy.generate_signal(state)

        # Execute signal
        if signal.signal in ("OPEN", "CLOSE"):
            self._execute_signal(asset, signal, market_data)
            self._state.signals_generated += 1

            if self._on_signal_callback:
                self._on_signal_callback(signal)

            return signal

        return None

    def _check_funding_settlement(self, asset: str, market_data: Dict[str, Any]):
        """Check if funding has settled and accrue payment."""
        next_funding = market_data.get("next_funding_time")

        if not next_funding:
            return

        prev_next_funding = self._next_funding_times.get(asset)

        # If next funding time has moved forward, a settlement occurred
        if prev_next_funding and next_funding > prev_next_funding:
            position = self.strategy.get_position(asset)
            if position:
                funding_pct = market_data.get("funding_rate_pct", 0)
                mark_price = market_data.get("mark_price", market_data.get("perp_price", 0))
                self.strategy.accrue_funding(asset, funding_pct, mark_price)
                logger.info(f"Funding settlement detected for {asset}")

        self._next_funding_times[asset] = next_funding

    def _execute_signal(self, asset: str, signal: FundingSignal, market_data: Dict[str, Any]):
        """Execute a trading signal."""
        spot_price = market_data["spot_price"]
        perp_price = market_data["perp_price"]

        if signal.signal == "OPEN":
            position = self.strategy.open_position(
                asset, signal, spot_price, perp_price
            )

            if position and EXECUTION_MODE == "live":
                # In live mode, execute spot leg on Coinbase
                self._execute_spot_trade(
                    asset, position.position_type, position.spot_quantity, spot_price
                )
                # Perp leg is simulated (Binance futures would need additional setup)
                logger.info(f"Live spot trade executed for {asset}, perp simulated")

        elif signal.signal == "CLOSE":
            summary = self.strategy.close_position(asset, spot_price, perp_price)

            if summary and EXECUTION_MODE == "live":
                # Close spot position
                position_type = PositionType[summary["position_type"]]
                spot_qty = summary["spot_quantity"]
                self._execute_spot_trade(
                    asset, position_type, spot_qty, spot_price, close=True
                )

    def _execute_spot_trade(self, asset: str, position_type: PositionType,
                            quantity: float, price: float, close: bool = False):
        """Execute spot trade on Coinbase."""
        if not self.execution_router:
            logger.warning(f"No execution router - would trade {asset}")
            return

        symbol = f"{asset}/USD"

        # Determine side
        if position_type == PositionType.LONG_CARRY:
            # Long carry = long spot initially, sell to close
            side = OrderSide.SELL if close else OrderSide.BUY
        else:
            # Short carry = short spot initially, buy to close
            side = OrderSide.BUY if close else OrderSide.SELL

        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            exchange="coinbase",
            strategy_id="funding_harvest",
        )

        success = self.execution_router.submit_order(order)
        if success:
            logger.info(f"Spot order submitted: {side.value} {quantity} {symbol}")
        else:
            logger.error(f"Spot order failed: {side.value} {quantity} {symbol}")

    def run_once(self) -> Dict[str, Optional[FundingSignal]]:
        """Run a single update cycle for all assets."""
        results = {}

        for asset in self.config.assets:
            try:
                signal = self.update_asset(asset)
                results[asset] = signal
            except Exception as e:
                logger.error(f"Error updating {asset}: {e}")
                self._state.error_count += 1
                results[asset] = None

        self._state.last_update = datetime.now()
        self._state.successful_updates += 1

        return results

    def _run_loop(self):
        """Main run loop (called in thread)."""
        interval = self.config.update_interval_minutes * 60

        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                self._state.error_count += 1

            # Wait for next interval
            self._stop_event.wait(interval)

        self._state.running = False
        logger.info("Funding Harvest Runner stopped")

    def start(self):
        """Start the runner in a background thread."""
        if self._state.running:
            logger.warning("Runner already running")
            return

        self._stop_event.clear()
        self._state.running = True

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info("Funding Harvest Runner started")

    def stop(self):
        """Stop the runner."""
        if not self._state.running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

        logger.info("Funding Harvest Runner stopped")

    def get_state(self) -> Dict[str, Any]:
        """Get current runner state."""
        return {
            "running": self._state.running,
            "last_update": self._state.last_update.isoformat() if self._state.last_update else None,
            "error_count": self._state.error_count,
            "successful_updates": self._state.successful_updates,
            "signals_generated": self._state.signals_generated,
            "execution_mode": EXECUTION_MODE,
            "assets": self.config.assets,
            "strategy_state": self.strategy.get_state(),
            "market_states": {
                asset: state.to_dict() for asset, state in self._market_states.items()
            },
        }

    def get_position(self, asset: str) -> Optional[Dict[str, Any]]:
        """Get position for an asset."""
        position = self.strategy.get_position(asset)
        return position.to_dict() if position else None

    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all positions."""
        return {
            asset: pos.to_dict()
            for asset, pos in self.strategy.get_all_positions().items()
        }

    def get_funding_history(self, asset: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get funding history for an asset."""
        return self.strategy.get_funding_history(asset, limit)

    def manual_open(self, asset: str) -> Optional[FundingSignal]:
        """Manually open a position for an asset."""
        market_data = self.fetch_market_data(asset)
        if not market_data:
            logger.error(f"No market data for {asset}")
            return None

        state = self.strategy.update_market_state(asset, market_data)
        if not state:
            return None

        # Force open signal
        signal = FundingSignal(
            signal="OPEN",
            asset=asset,
            notional_usd=self.config.notional_usd,
            current_funding=state.funding_rate_pct,
            reason="Manual open",
            position_type=PositionType.LONG_CARRY if state.funding_rate_pct > 0 else PositionType.SHORT_CARRY,
        )

        self._execute_signal(asset, signal, market_data)
        return signal

    def manual_close(self, asset: str) -> Optional[Dict[str, Any]]:
        """Manually close a position for an asset."""
        if asset not in self.strategy._positions:
            logger.warning(f"No position to close for {asset}")
            return None

        market_data = self.fetch_market_data(asset)
        if not market_data:
            return None

        signal = FundingSignal(
            signal="CLOSE",
            asset=asset,
            notional_usd=0,
            current_funding=market_data.get("funding_rate_pct", 0),
            reason="Manual close",
        )

        self._execute_signal(asset, signal, market_data)
        return self.strategy.get_closed_positions()[-1] if self.strategy.get_closed_positions() else None

    def shutdown(self):
        """Shutdown the runner and connections."""
        self.stop()

        if self.crypto_client:
            self.crypto_client.close()

        if self.execution_router:
            self.execution_router.shutdown()

        logger.info("Funding Harvest Runner shutdown complete")
