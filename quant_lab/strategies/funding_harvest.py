"""
Funding Harvest Strategy

Captures funding rate payments on perpetual futures.
Goes long or short perpetual based on funding rate direction to earn funding.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType

import sys
sys.path.insert(0, '..')
from config import STRATEGY_CONFIG, CRYPTO_SYMBOLS

logger = logging.getLogger(__name__)


class FundingHarvestStrategy(BaseStrategy):
    """
    Funding Harvest Strategy.

    Monitors perpetual futures funding rates and positions to capture
    positive funding payments while hedging with spot if needed.

    Trading Logic:
    - When funding rate is positive and high: SHORT perp (receive funding from longs)
    - When funding rate is negative and high: LONG perp (receive funding from shorts)
    - Optionally hedge with spot position
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or STRATEGY_CONFIG.get("funding_harvest", {})
        super().__init__("funding_harvest", config)

        # Strategy parameters
        self.min_funding_rate_pct = config.get("min_funding_rate_pct", 0.01)
        self.max_position_size_usd = config.get("max_position_size_usd", 10000)
        self.hedge_enabled = config.get("hedge_enabled", False)

        # State tracking
        self._funding_rates: Dict[str, List[Dict[str, Any]]] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._cumulative_funding: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "Funding Harvest"

    @property
    def description(self) -> str:
        return "Captures funding rate payments on perpetual futures"

    def on_data(self, data: Dict[str, Any]) -> List[Signal]:
        """
        Process funding rate data and generate signals.

        Expected data format:
        {
            "BTC/USDT": {
                "funding_rate": 0.0003,  # 0.03%
                "funding_rate_pct": 0.03,
                "mark_price": 45000.0,
                "index_price": 44980.0,
                "next_funding_time": "2024-01-01T08:00:00Z",
                "spot_price": 44990.0,  # Optional for hedging
            },
            ...
        }
        """
        signals = []

        for symbol, symbol_data in data.items():
            if not self._is_perpetual_symbol(symbol):
                continue

            try:
                signal = self._analyze_funding(symbol, symbol_data)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing funding for {symbol}: {e}")

        return signals

    def _is_perpetual_symbol(self, symbol: str) -> bool:
        """Check if symbol is a perpetual futures symbol."""
        # Check against configured crypto symbols
        symbol_config = CRYPTO_SYMBOLS.get(symbol, {})
        return symbol_config.get("type") == "perpetual" or "/USDT" in symbol

    def _analyze_funding(self, symbol: str, data: Dict[str, Any]) -> Optional[Signal]:
        """Analyze funding rate for a symbol."""
        funding_rate = data.get("funding_rate")
        funding_rate_pct = data.get("funding_rate_pct") or (funding_rate * 100 if funding_rate else None)
        mark_price = data.get("mark_price")

        if funding_rate_pct is None or mark_price is None:
            return None

        # Track funding rate history
        if symbol not in self._funding_rates:
            self._funding_rates[symbol] = []

        self._funding_rates[symbol].append({
            "rate": funding_rate_pct,
            "mark_price": mark_price,
            "timestamp": datetime.now(),
        })

        # Keep last 100 readings
        if len(self._funding_rates[symbol]) > 100:
            self._funding_rates[symbol] = self._funding_rates[symbol][-100:]

        # Calculate average funding rate
        recent_rates = [r["rate"] for r in self._funding_rates[symbol][-8:]]  # Last 8 hours
        avg_funding = np.mean(recent_rates) if recent_rates else funding_rate_pct

        # Get current position
        current_position = self.get_position(symbol)

        # High positive funding: SHORT to receive funding
        if funding_rate_pct > self.min_funding_rate_pct:
            if current_position >= 0:  # Not already short
                quantity = self._calculate_position_size(symbol, mark_price)

                # Annualized funding rate (8h funding * 3 * 365)
                annualized_rate = funding_rate_pct * 3 * 365

                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(funding_rate_pct / self.min_funding_rate_pct / 5, 1.0),
                    quantity=quantity,
                    metadata={
                        "funding_rate_pct": funding_rate_pct,
                        "avg_funding_8h": avg_funding,
                        "annualized_rate": annualized_rate,
                        "mark_price": mark_price,
                        "reason": "Positive funding - short to receive",
                    },
                )
                logger.info(f"{symbol}: Funding {funding_rate_pct:.4f}% - SHORT signal "
                           f"(annualized: {annualized_rate:.2f}%)")
                return signal

        # High negative funding: LONG to receive funding
        elif funding_rate_pct < -self.min_funding_rate_pct:
            if current_position <= 0:  # Not already long
                quantity = self._calculate_position_size(symbol, mark_price)

                annualized_rate = abs(funding_rate_pct) * 3 * 365

                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(funding_rate_pct) / self.min_funding_rate_pct / 5, 1.0),
                    quantity=quantity,
                    metadata={
                        "funding_rate_pct": funding_rate_pct,
                        "avg_funding_8h": avg_funding,
                        "annualized_rate": annualized_rate,
                        "mark_price": mark_price,
                        "reason": "Negative funding - long to receive",
                    },
                )
                logger.info(f"{symbol}: Funding {funding_rate_pct:.4f}% - LONG signal "
                           f"(annualized: {annualized_rate:.2f}%)")
                return signal

        # Neutral funding - consider closing position
        elif abs(funding_rate_pct) < self.min_funding_rate_pct / 2:
            if current_position != 0:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE,
                    strength=0.5,
                    quantity=abs(current_position),
                    metadata={
                        "funding_rate_pct": funding_rate_pct,
                        "reason": "Funding rate normalized",
                    },
                )
                logger.info(f"{symbol}: Funding normalized - CLOSE signal")
                return signal

        return None

    def _calculate_position_size(self, symbol: str, price: float) -> float:
        """Calculate position size in base currency."""
        # Position size in USD
        position_usd = self.max_position_size_usd

        # Convert to base currency
        quantity = position_usd / price

        return quantity

    def record_funding_payment(self, symbol: str, payment: float):
        """Record a funding payment received/paid."""
        if symbol not in self._cumulative_funding:
            self._cumulative_funding[symbol] = 0.0
        self._cumulative_funding[symbol] += payment
        logger.info(f"Funding payment for {symbol}: {payment:.4f} "
                   f"(cumulative: {self._cumulative_funding[symbol]:.4f})")

    def get_funding_stats(self, symbol: str) -> Dict[str, Any]:
        """Get funding rate statistics for a symbol."""
        if symbol not in self._funding_rates or not self._funding_rates[symbol]:
            return {}

        rates = [r["rate"] for r in self._funding_rates[symbol]]

        return {
            "current": rates[-1] if rates else 0,
            "mean": np.mean(rates),
            "std": np.std(rates),
            "min": min(rates),
            "max": max(rates),
            "count": len(rates),
            "cumulative_funding": self._cumulative_funding.get(symbol, 0),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get strategy state for dashboard."""
        current_rates = {}
        for symbol, rates in self._funding_rates.items():
            if rates:
                current_rates[symbol] = {
                    "current_rate": rates[-1]["rate"],
                    "mark_price": rates[-1]["mark_price"],
                    "timestamp": rates[-1]["timestamp"].isoformat(),
                }

        return {
            "funding_rates": current_rates,
            "cumulative_funding": self._cumulative_funding.copy(),
            "min_threshold": self.min_funding_rate_pct,
            "max_position_usd": self.max_position_size_usd,
        }

    def estimate_daily_funding(self, symbol: str) -> float:
        """Estimate daily funding income based on recent rates."""
        if symbol not in self._funding_rates or not self._funding_rates[symbol]:
            return 0.0

        # Get last 24 hours of rates (3 funding periods)
        recent_rates = [r["rate"] for r in self._funding_rates[symbol][-3:]]
        if not recent_rates:
            return 0.0

        # Estimate daily funding (3 payments per day)
        avg_rate = np.mean(recent_rates)
        position = abs(self.get_position(symbol))

        if position == 0:
            return 0.0

        # Daily funding = position * avg_rate * 3
        return position * avg_rate / 100 * 3
