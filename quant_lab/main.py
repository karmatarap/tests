#!/usr/bin/env python3
"""
Quant Lab - Main Entry Point

A quantitative trading framework supporting:
- Live data from IBKR and crypto exchanges
- Multiple trading strategies
- Paper and live execution
- Real-time dashboard

Usage:
    python main.py                  # Run strategies in paper mode
    python main.py --mode live      # Run in live mode
    python main.py --dashboard      # Launch dashboard only
    python main.py --strategy etf   # Run specific strategy
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import (
    EXECUTION_MODE,
    STRATEGY_CONFIG,
    LOG_CONFIG,
    validate_config,
)
from data_sources import IBKRClient, CryptoClient
from execution import ExecutionRouter, Order, OrderSide, OrderType
from strategies import (
    ETFDislocationStrategy,
    FundingHarvestStrategy,
    VolOfVolStrategy,
    Signal,
    SignalType,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_CONFIG["level"]),
    format=LOG_CONFIG["format"],
)
logger = logging.getLogger(__name__)


class QuantLab:
    """
    Main Quant Lab engine.

    Coordinates data sources, strategies, and execution.
    """

    def __init__(self):
        self.running = False

        # Data sources
        self.ibkr_client: Optional[IBKRClient] = None
        self.crypto_client: Optional[CryptoClient] = None

        # Execution
        self.execution_router: Optional[ExecutionRouter] = None

        # Strategies
        self.strategies: Dict[str, Any] = {}

        # State
        self.last_run_times: Dict[str, datetime] = {}

    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info(f"Initializing Quant Lab in {EXECUTION_MODE} mode...")

        try:
            # Validate configuration
            validate_config()

            # Initialize data sources
            self.ibkr_client = IBKRClient()
            self.crypto_client = CryptoClient()

            # Connect data sources (may fail gracefully)
            if not self.ibkr_client.connect():
                logger.warning("IBKR connection failed - IBKR data will be unavailable")

            if not self.crypto_client.initialize():
                logger.warning("Crypto client init failed - crypto data will be unavailable")

            # Initialize execution router
            self.execution_router = ExecutionRouter()
            self.execution_router.initialize()

            # Initialize strategies
            self._initialize_strategies()

            logger.info("Quant Lab initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def _initialize_strategies(self):
        """Initialize trading strategies."""
        if STRATEGY_CONFIG.get("etf_dislocation", {}).get("enabled", True):
            self.strategies["etf_dislocation"] = ETFDislocationStrategy(
                STRATEGY_CONFIG.get("etf_dislocation")
            )
            logger.info("ETF Dislocation strategy initialized")

        if STRATEGY_CONFIG.get("funding_harvest", {}).get("enabled", True):
            self.strategies["funding_harvest"] = FundingHarvestStrategy(
                STRATEGY_CONFIG.get("funding_harvest")
            )
            logger.info("Funding Harvest strategy initialized")

        if STRATEGY_CONFIG.get("vol_of_vol", {}).get("enabled", True):
            self.strategies["vol_of_vol"] = VolOfVolStrategy(
                STRATEGY_CONFIG.get("vol_of_vol")
            )
            logger.info("Vol of Vol strategy initialized")

    def fetch_market_data(self) -> Dict[str, Dict[str, Any]]:
        """Fetch market data from all sources."""
        data = {}

        # Fetch IBKR data
        if self.ibkr_client and self.ibkr_client.is_connected:
            try:
                # Get ETF quotes
                for symbol in ["SPY", "QQQ", "IWM", "DIA"]:
                    contract = self.ibkr_client.create_stock_contract(symbol)
                    quote = self.ibkr_client.get_quote(contract)
                    if quote:
                        data[symbol] = {
                            "price": quote.get("last") or quote.get("close"),
                            "bid": quote.get("bid"),
                            "ask": quote.get("ask"),
                            "volume": quote.get("volume"),
                            # Mock fair value for demo (would come from index calculation)
                            "fair_value": (quote.get("last") or quote.get("close")) * (1 + (0.001 * (0.5 - hash(symbol) % 100 / 100))),
                        }

                # Get VIX quote
                vix_contract = self.ibkr_client.create_stock_contract("VIX", "CBOE")
                vix_quote = self.ibkr_client.get_quote(vix_contract)
                if vix_quote:
                    data["VIX"] = {
                        "price": vix_quote.get("last") or vix_quote.get("close"),
                    }

            except Exception as e:
                logger.error(f"Error fetching IBKR data: {e}")

        # Fetch crypto data
        if self.crypto_client and self.crypto_client.is_initialized:
            try:
                # Get funding rates
                for symbol in ["BTC/USDT", "ETH/USDT"]:
                    funding = self.crypto_client.get_funding_rate(symbol)
                    if funding:
                        ticker = self.crypto_client.get_binance_ticker(symbol)
                        data[symbol] = {
                            "price": ticker.get("last") if ticker else funding.get("mark_price"),
                            "mark_price": funding.get("mark_price"),
                            "funding_rate": funding.get("funding_rate"),
                            "funding_rate_pct": funding.get("funding_rate_pct"),
                        }

                # Get spot prices
                for symbol in ["BTC/USD", "ETH/USD"]:
                    ticker = self.crypto_client.get_coinbase_ticker(symbol)
                    if ticker:
                        data[symbol] = {
                            "price": ticker.get("last"),
                            "bid": ticker.get("bid"),
                            "ask": ticker.get("ask"),
                        }

            except Exception as e:
                logger.error(f"Error fetching crypto data: {e}")

        return data

    def process_signals(self, signals: List[Signal]):
        """Process trading signals and execute orders."""
        for signal in signals:
            try:
                # Convert signal to order
                order = self._signal_to_order(signal)
                if order:
                    # Submit through execution router
                    success = self.execution_router.submit_order(order)
                    if success:
                        logger.info(f"Order submitted: {order.order_id}")
                        # Update strategy position
                        strategy = self.strategies.get(signal.strategy_id)
                        if strategy:
                            qty = signal.quantity or 0
                            if signal.signal_type == SignalType.BUY:
                                strategy.update_position(signal.symbol, qty)
                            elif signal.signal_type == SignalType.SELL:
                                strategy.update_position(signal.symbol, -qty)
                            elif signal.signal_type == SignalType.CLOSE:
                                strategy.update_position(signal.symbol, 0)

            except Exception as e:
                logger.error(f"Error processing signal {signal.signal_id}: {e}")

    def _signal_to_order(self, signal: Signal) -> Optional[Order]:
        """Convert a trading signal to an order."""
        if signal.signal_type == SignalType.HOLD:
            return None

        if signal.signal_type == SignalType.BUY:
            side = OrderSide.BUY
        elif signal.signal_type in (SignalType.SELL, SignalType.CLOSE):
            side = OrderSide.SELL
        else:
            return None

        # Determine exchange
        exchange = None
        if "/" in signal.symbol:
            exchange = "coinbase"  # Crypto
        else:
            exchange = "ibkr"  # Stocks

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=signal.quantity or 1,
            order_type=OrderType.LIMIT if signal.limit_price else OrderType.MARKET,
            limit_price=signal.limit_price,
            exchange=exchange,
            strategy_id=signal.strategy_id,
        )

        return order

    def run_strategies(self, data: Dict[str, Any]) -> List[Signal]:
        """Run all enabled strategies and collect signals."""
        all_signals = []

        for name, strategy in self.strategies.items():
            if not strategy.enabled:
                continue

            # Check if it's time to run based on schedule
            config = STRATEGY_CONFIG.get(name, {})
            interval = config.get("schedule_interval_seconds", 60)

            last_run = self.last_run_times.get(name)
            if last_run:
                elapsed = (datetime.now() - last_run).total_seconds()
                if elapsed < interval:
                    continue

            try:
                signals = strategy.run(data)
                all_signals.extend(signals)
                self.last_run_times[name] = datetime.now()

            except Exception as e:
                logger.error(f"Error running strategy {name}: {e}")

        return all_signals

    def run_once(self):
        """Run a single iteration of the trading loop."""
        # Fetch market data
        data = self.fetch_market_data()

        if not data:
            logger.warning("No market data available")
            return

        # Run strategies
        signals = self.run_strategies(data)

        # Process signals
        if signals:
            self.process_signals(signals)

    def run(self):
        """Run the main trading loop."""
        self.running = True
        logger.info("Starting Quant Lab trading loop...")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        try:
            while self.running:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Error in trading loop: {e}")

                # Sleep between iterations
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.shutdown()

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def shutdown(self):
        """Shutdown all components."""
        logger.info("Shutting down Quant Lab...")

        # Disconnect data sources
        if self.ibkr_client:
            self.ibkr_client.disconnect()

        if self.crypto_client:
            self.crypto_client.close()

        # Shutdown execution
        if self.execution_router:
            self.execution_router.shutdown()

        logger.info("Quant Lab shutdown complete")

    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            "mode": EXECUTION_MODE,
            "running": self.running,
            "ibkr_connected": self.ibkr_client.is_connected if self.ibkr_client else False,
            "crypto_connected": self.crypto_client.is_initialized if self.crypto_client else False,
            "strategies": {
                name: strategy.get_status()
                for name, strategy in self.strategies.items()
            },
            "paper_summary": self.execution_router.get_paper_summary() if self.execution_router else {},
        }


def run_dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    import os

    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    subprocess.run(["streamlit", "run", dashboard_path])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Quant Lab Trading Framework")
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default=None,
        help="Execution mode (overrides config)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch dashboard only",
    )
    parser.add_argument(
        "--strategy",
        choices=["etf", "funding", "vol", "all"],
        default="all",
        help="Strategy to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit",
    )

    args = parser.parse_args()

    # Override execution mode if specified
    if args.mode:
        import config
        config.EXECUTION_MODE = args.mode

    # Launch dashboard
    if args.dashboard:
        run_dashboard()
        return

    # Initialize and run
    lab = QuantLab()

    if not lab.initialize():
        logger.error("Failed to initialize Quant Lab")
        sys.exit(1)

    # Disable strategies based on args
    if args.strategy != "all":
        strategy_map = {
            "etf": "etf_dislocation",
            "funding": "funding_harvest",
            "vol": "vol_of_vol",
        }
        active_strategy = strategy_map.get(args.strategy)
        for name, strategy in lab.strategies.items():
            if name != active_strategy:
                strategy.disable()

    # Run
    if args.once:
        lab.run_once()
        lab.shutdown()
    else:
        lab.run()


if __name__ == "__main__":
    main()
