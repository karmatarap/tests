"""
Vol of Vol Strategy

Trades volatility of volatility using VIX and volatility ETFs.
Identifies when volatility itself is unusually volatile and trades mean reversion.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType

import sys
sys.path.insert(0, '..')
from config import STRATEGY_CONFIG, VOL_SYMBOLS

logger = logging.getLogger(__name__)


class VolOfVolStrategy(BaseStrategy):
    """
    Volatility of Volatility Strategy.

    Monitors VIX and vol products to identify:
    - Vol spikes for mean reversion trades
    - Vol regime changes
    - Vol of vol opportunities

    Trading Logic:
    - When VIX spikes above threshold: SHORT vol (sell UVXY or buy SVXY)
    - When VIX crashes below normal: LONG vol (buy UVXY or sell SVXY)
    - Uses vol of vol (VVIX-like measure) to time entries
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or STRATEGY_CONFIG.get("vol_of_vol", {})
        super().__init__("vol_of_vol", config)

        # Strategy parameters
        self.vol_spike_threshold = config.get("vol_spike_threshold", 2.0)  # std devs
        self.lookback_periods = config.get("lookback_periods", 20)
        self.vix_mean = config.get("vix_mean", 20.0)  # Long-term VIX average

        # State tracking - use deques for efficient rolling windows
        self._vix_history: deque = deque(maxlen=100)
        self._vol_of_vol_history: deque = deque(maxlen=50)
        self._product_prices: Dict[str, deque] = {}
        self._regime: str = "normal"  # "normal", "elevated", "spike", "low"

    @property
    def name(self) -> str:
        return "Vol of Vol"

    @property
    def description(self) -> str:
        return "Trades volatility spikes and mean reversion using VIX products"

    def on_data(self, data: Dict[str, Any]) -> List[Signal]:
        """
        Process volatility data and generate signals.

        Expected data format:
        {
            "VIX": {"price": 18.5, "change_pct": 5.2},
            "UVXY": {"price": 12.5, "volume": 5000000},
            "SVXY": {"price": 45.0, "volume": 1000000},
        }
        """
        signals = []

        # Extract VIX data
        vix_data = data.get("VIX", {})
        vix_price = vix_data.get("price")

        if vix_price is None:
            return signals

        # Update VIX history
        self._vix_history.append({
            "price": vix_price,
            "timestamp": datetime.now(),
        })

        # Calculate vol of vol
        vol_of_vol = self._calculate_vol_of_vol()

        # Update vol of vol history
        if vol_of_vol is not None:
            self._vol_of_vol_history.append(vol_of_vol)

        # Update regime
        self._update_regime(vix_price, vol_of_vol)

        # Update product prices
        for symbol in ["UVXY", "SVXY"]:
            if symbol in data:
                if symbol not in self._product_prices:
                    self._product_prices[symbol] = deque(maxlen=50)
                self._product_prices[symbol].append(data[symbol].get("price"))

        # Generate signals based on regime and vol of vol
        try:
            regime_signals = self._generate_regime_signals(vix_price, vol_of_vol, data)
            signals.extend(regime_signals)
        except Exception as e:
            logger.error(f"Error generating regime signals: {e}")

        return signals

    def _calculate_vol_of_vol(self) -> Optional[float]:
        """Calculate volatility of VIX (vol of vol)."""
        if len(self._vix_history) < self.lookback_periods:
            return None

        # Get recent VIX prices
        recent_vix = [v["price"] for v in list(self._vix_history)[-self.lookback_periods:]]

        # Calculate returns
        returns = np.diff(np.log(recent_vix))

        # Vol of vol is the standard deviation of VIX returns
        vol_of_vol = np.std(returns) * np.sqrt(252)  # Annualized

        return vol_of_vol

    def _update_regime(self, vix_price: float, vol_of_vol: Optional[float]):
        """Update volatility regime."""
        old_regime = self._regime

        if vix_price > self.vix_mean * 1.5:
            self._regime = "spike"
        elif vix_price > self.vix_mean * 1.2:
            self._regime = "elevated"
        elif vix_price < self.vix_mean * 0.7:
            self._regime = "low"
        else:
            self._regime = "normal"

        if old_regime != self._regime:
            logger.info(f"Vol regime change: {old_regime} -> {self._regime} (VIX: {vix_price:.2f})")

    def _generate_regime_signals(self, vix_price: float, vol_of_vol: Optional[float],
                                  data: Dict[str, Any]) -> List[Signal]:
        """Generate signals based on vol regime."""
        signals = []

        if len(self._vix_history) < self.lookback_periods:
            return signals

        # Calculate VIX z-score
        vix_prices = [v["price"] for v in self._vix_history]
        vix_mean = np.mean(vix_prices)
        vix_std = np.std(vix_prices)
        vix_zscore = (vix_price - vix_mean) / vix_std if vix_std > 0 else 0

        # Check vol of vol threshold
        vol_of_vol_elevated = False
        if vol_of_vol is not None and len(self._vol_of_vol_history) > 5:
            vov_mean = np.mean(list(self._vol_of_vol_history))
            vov_std = np.std(list(self._vol_of_vol_history))
            if vov_std > 0:
                vov_zscore = (vol_of_vol - vov_mean) / vov_std
                vol_of_vol_elevated = vov_zscore > 1.5

        # Get current positions
        uvxy_position = self.get_position("UVXY")
        svxy_position = self.get_position("SVXY")

        # VIX SPIKE: Short vol (short UVXY or long SVXY)
        if vix_zscore > self.vol_spike_threshold:
            # VIX spike - expect mean reversion, short vol
            if uvxy_position >= 0 and "UVXY" in data:
                uvxy_price = data["UVXY"].get("price", 0)
                if uvxy_price > 0:
                    signal = Signal(
                        symbol="UVXY",
                        signal_type=SignalType.SELL,
                        strength=min(vix_zscore / self.vol_spike_threshold / 2, 1.0),
                        quantity=100,
                        metadata={
                            "vix": vix_price,
                            "vix_zscore": vix_zscore,
                            "vol_of_vol": vol_of_vol,
                            "regime": self._regime,
                            "reason": "VIX spike - short vol for mean reversion",
                        },
                    )
                    signals.append(signal)
                    logger.info(f"VIX spike {vix_zscore:.2f}σ - SHORT UVXY signal")

            # Alternatively, long SVXY
            if svxy_position <= 0 and "SVXY" in data:
                svxy_price = data["SVXY"].get("price", 0)
                if svxy_price > 0:
                    signal = Signal(
                        symbol="SVXY",
                        signal_type=SignalType.BUY,
                        strength=min(vix_zscore / self.vol_spike_threshold / 2, 1.0),
                        quantity=50,
                        metadata={
                            "vix": vix_price,
                            "vix_zscore": vix_zscore,
                            "regime": self._regime,
                            "reason": "VIX spike - long inverse vol for mean reversion",
                        },
                    )
                    signals.append(signal)
                    logger.info(f"VIX spike {vix_zscore:.2f}σ - LONG SVXY signal")

        # VIX LOW: Long vol (long UVXY or short SVXY)
        elif vix_zscore < -self.vol_spike_threshold:
            # VIX very low - expect vol to rise
            if uvxy_position <= 0 and "UVXY" in data:
                uvxy_price = data["UVXY"].get("price", 0)
                if uvxy_price > 0:
                    signal = Signal(
                        symbol="UVXY",
                        signal_type=SignalType.BUY,
                        strength=min(abs(vix_zscore) / self.vol_spike_threshold / 2, 1.0),
                        quantity=50,  # Smaller size for long vol
                        metadata={
                            "vix": vix_price,
                            "vix_zscore": vix_zscore,
                            "vol_of_vol": vol_of_vol,
                            "regime": self._regime,
                            "reason": "VIX low - long vol expecting increase",
                        },
                    )
                    signals.append(signal)
                    logger.info(f"VIX low {vix_zscore:.2f}σ - LONG UVXY signal")

        # Mean reversion: close positions when VIX normalizes
        elif abs(vix_zscore) < 0.5:
            # VIX normalized - close vol positions
            if uvxy_position != 0:
                signal = Signal(
                    symbol="UVXY",
                    signal_type=SignalType.CLOSE,
                    strength=0.5,
                    quantity=abs(uvxy_position),
                    metadata={
                        "vix": vix_price,
                        "vix_zscore": vix_zscore,
                        "reason": "VIX normalized",
                    },
                )
                signals.append(signal)
                logger.info("VIX normalized - CLOSE UVXY")

            if svxy_position != 0:
                signal = Signal(
                    symbol="SVXY",
                    signal_type=SignalType.CLOSE,
                    strength=0.5,
                    quantity=abs(svxy_position),
                    metadata={
                        "vix": vix_price,
                        "vix_zscore": vix_zscore,
                        "reason": "VIX normalized",
                    },
                )
                signals.append(signal)
                logger.info("VIX normalized - CLOSE SVXY")

        return signals

    def get_current_vix(self) -> Optional[float]:
        """Get current VIX level."""
        if self._vix_history:
            return self._vix_history[-1]["price"]
        return None

    def get_vol_of_vol(self) -> Optional[float]:
        """Get current vol of vol."""
        if self._vol_of_vol_history:
            return self._vol_of_vol_history[-1]
        return None

    def get_vix_stats(self) -> Dict[str, Any]:
        """Get VIX statistics."""
        if not self._vix_history:
            return {}

        vix_prices = [v["price"] for v in self._vix_history]

        return {
            "current": vix_prices[-1],
            "mean": np.mean(vix_prices),
            "std": np.std(vix_prices),
            "min": min(vix_prices),
            "max": max(vix_prices),
            "zscore": (vix_prices[-1] - np.mean(vix_prices)) / np.std(vix_prices)
                if np.std(vix_prices) > 0 else 0,
        }

    def get_state(self) -> Dict[str, Any]:
        """Get strategy state for dashboard."""
        vix_stats = self.get_vix_stats()

        return {
            "regime": self._regime,
            "current_vix": self.get_current_vix(),
            "vol_of_vol": self.get_vol_of_vol(),
            "vix_stats": vix_stats,
            "threshold": self.vol_spike_threshold,
            "lookback": self.lookback_periods,
        }
