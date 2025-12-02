"""
ETF Dislocation Strategy

Identifies and trades ETF price dislocations relative to NAV or fair value.
Looks for situations where ETF price deviates significantly from underlying value.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType

import sys
sys.path.insert(0, '..')
from config import STRATEGY_CONFIG, ETF_SYMBOLS

logger = logging.getLogger(__name__)


class ETFDislocationStrategy(BaseStrategy):
    """
    ETF Dislocation Strategy.

    Monitors ETF prices versus their fair value (NAV or calculated fair value)
    and generates signals when dislocations exceed thresholds.

    Trading Logic:
    - BUY when ETF trades at discount to fair value
    - SELL when ETF trades at premium to fair value
    - Expect mean reversion to fair value
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or STRATEGY_CONFIG.get("etf_dislocation", {})
        super().__init__("etf_dislocation", config)

        # Strategy parameters
        self.dislocation_threshold_pct = config.get("dislocation_threshold_pct", 0.1)
        self.max_position_size = config.get("max_position_size", 100)

        # State tracking
        self._fair_values: Dict[str, float] = {}
        self._dislocations: Dict[str, List[float]] = {}
        self._last_prices: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "ETF Dislocation"

    @property
    def description(self) -> str:
        return "Trades ETF price dislocations relative to fair value/NAV"

    def on_data(self, data: Dict[str, Any]) -> List[Signal]:
        """
        Process market data and generate dislocation signals.

        Expected data format:
        {
            "SPY": {"price": 450.0, "fair_value": 449.5, "volume": 1000000},
            "QQQ": {"price": 380.0, "fair_value": 381.0, "volume": 500000},
            ...
        }
        """
        signals = []

        for symbol, symbol_data in data.items():
            if symbol not in ETF_SYMBOLS:
                continue

            try:
                signal = self._analyze_symbol(symbol, symbol_data)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        return signals

    def _analyze_symbol(self, symbol: str, data: Dict[str, Any]) -> Optional[Signal]:
        """Analyze a single symbol for dislocation."""
        price = data.get("price")
        fair_value = data.get("fair_value") or data.get("nav")

        if not price or not fair_value:
            return None

        # Calculate dislocation
        dislocation_pct = ((price - fair_value) / fair_value) * 100

        # Track dislocation history
        if symbol not in self._dislocations:
            self._dislocations[symbol] = []
        self._dislocations[symbol].append(dislocation_pct)

        # Keep last 100 readings
        if len(self._dislocations[symbol]) > 100:
            self._dislocations[symbol] = self._dislocations[symbol][-100:]

        # Update state
        self._fair_values[symbol] = fair_value
        self._last_prices[symbol] = price

        # Generate signal if dislocation exceeds threshold
        current_position = self.get_position(symbol)

        if dislocation_pct < -self.dislocation_threshold_pct:
            # ETF trading at discount - potential buy
            if current_position <= 0:
                quantity = self._calculate_quantity(symbol, data)
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(dislocation_pct) / self.dislocation_threshold_pct / 2, 1.0),
                    quantity=quantity,
                    metadata={
                        "dislocation_pct": dislocation_pct,
                        "fair_value": fair_value,
                        "price": price,
                        "reason": "ETF discount to fair value",
                    },
                )
                logger.info(f"{symbol}: Discount {dislocation_pct:.3f}% - BUY signal")
                return signal

        elif dislocation_pct > self.dislocation_threshold_pct:
            # ETF trading at premium - potential sell
            if current_position >= 0:
                quantity = abs(current_position) if current_position > 0 else self._calculate_quantity(symbol, data)
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(abs(dislocation_pct) / self.dislocation_threshold_pct / 2, 1.0),
                    quantity=quantity,
                    metadata={
                        "dislocation_pct": dislocation_pct,
                        "fair_value": fair_value,
                        "price": price,
                        "reason": "ETF premium to fair value",
                    },
                )
                logger.info(f"{symbol}: Premium {dislocation_pct:.3f}% - SELL signal")
                return signal

        # Check for mean reversion to close positions
        if abs(dislocation_pct) < self.dislocation_threshold_pct / 2:
            if current_position != 0:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE,
                    strength=0.5,
                    quantity=abs(current_position),
                    metadata={
                        "dislocation_pct": dislocation_pct,
                        "reason": "Dislocation normalized",
                    },
                )
                logger.info(f"{symbol}: Dislocation normalized - CLOSE signal")
                return signal

        return None

    def _calculate_quantity(self, symbol: str, data: Dict[str, Any]) -> float:
        """Calculate position size."""
        # Use configured max position size
        quantity = self.max_position_size

        # Adjust for signal strength based on dislocation magnitude
        dislocation = abs(data.get("dislocation_pct", 0))
        if dislocation > self.dislocation_threshold_pct * 2:
            quantity = self.max_position_size
        else:
            quantity = int(self.max_position_size * 0.5)

        return float(quantity)

    def get_dislocation(self, symbol: str) -> Optional[float]:
        """Get current dislocation for a symbol."""
        if symbol in self._dislocations and self._dislocations[symbol]:
            return self._dislocations[symbol][-1]
        return None

    def get_dislocation_stats(self, symbol: str) -> Dict[str, float]:
        """Get dislocation statistics for a symbol."""
        if symbol not in self._dislocations or not self._dislocations[symbol]:
            return {}

        data = self._dislocations[symbol]
        return {
            "current": data[-1],
            "mean": np.mean(data),
            "std": np.std(data),
            "min": min(data),
            "max": max(data),
            "count": len(data),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get strategy state for dashboard."""
        return {
            "fair_values": self._fair_values.copy(),
            "last_prices": self._last_prices.copy(),
            "dislocations": {k: v[-1] if v else None for k, v in self._dislocations.items()},
            "threshold": self.dislocation_threshold_pct,
        }
