"""
Vol-of-Vol Mean Reversion Strategy

Monitors VIX for daily % changes (spikes/crashes) and trades
volatility instruments (UVXY, SVXY, VXX) for mean reversion.

Strategy Logic:
- VIX spike (+15%+): Short vol via SVXY (expect mean reversion down)
- VIX extreme spike (+30%+): Aggressive short vol with larger size
- VIX crash (-10%-): Long vol via UVXY (expect vol to normalize)
- Exit when VIX change normalizes or holding limit reached
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class VolSignalType(Enum):
    """Types of volatility signals."""
    NONE = "NONE"
    SHORT_VOL = "SHORT_VOL"  # VIX spike - short vol
    LONG_VOL = "LONG_VOL"    # VIX crash - long vol
    EXIT = "EXIT"            # Exit position
    STOP_LOSS = "STOP_LOSS"  # Emergency exit


@dataclass
class VolMeanReversionConfig:
    """Configuration for Vol Mean Reversion Strategy."""
    # VIX thresholds (daily % change)
    vix_spike_threshold_pct: float = 15.0      # +15% = spike
    vix_crash_threshold_pct: float = -10.0     # -10% = crash
    vix_extreme_spike_pct: float = 30.0        # +30% = extreme spike

    # Mean reversion levels
    lookback_days: int = 20                     # Rolling stats window
    mean_reversion_z: float = 1.5               # Z-score for mean reversion

    # Position sizing
    notional_usd: float = 3000.0
    max_position_pct: float = 0.02              # Max 2% of portfolio

    # Timing
    max_holding_days: int = 3                   # Max holding period
    check_time_before_close_mins: int = 60      # Check near market close

    # Stop loss
    stop_loss_pct: float = 15.0                 # 15% adverse move

    # Instruments
    preferred_short_vol: str = "SVXY"           # For short vol trades
    preferred_long_vol: str = "UVXY"            # For long vol trades


@dataclass
class VolMarketState:
    """Current volatility market state."""
    vix_price: float
    vix_prev_close: float
    vix_change_pct: float
    vix_mean_20d: Optional[float] = None
    vix_std_20d: Optional[float] = None
    vix_zscore: Optional[float] = None

    # Instrument prices
    uvxy_price: Optional[float] = None
    svxy_price: Optional[float] = None
    vxx_price: Optional[float] = None

    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vix_price": self.vix_price,
            "vix_prev_close": self.vix_prev_close,
            "vix_change_pct": self.vix_change_pct,
            "vix_mean_20d": self.vix_mean_20d,
            "vix_std_20d": self.vix_std_20d,
            "vix_zscore": self.vix_zscore,
            "uvxy_price": self.uvxy_price,
            "svxy_price": self.svxy_price,
            "vxx_price": self.vxx_price,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class VolSignal:
    """Volatility trading signal."""
    signal: str                     # SHORT_VOL, LONG_VOL, EXIT, NONE
    instrument: Optional[str]       # UVXY, SVXY, VXX
    notional_usd: float
    vix_change_pct: float
    vix_price: float
    reason: str
    is_extreme: bool = False
    position_type: Optional[str] = None  # "LONG" or "SHORT"
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal,
            "instrument": self.instrument,
            "notional_usd": self.notional_usd,
            "vix_change_pct": self.vix_change_pct,
            "vix_price": self.vix_price,
            "reason": self.reason,
            "is_extreme": self.is_extreme,
            "position_type": self.position_type,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class VolPosition:
    """Volatility position tracking."""
    instrument: str
    position_type: str              # "LONG" or "SHORT"
    signal_type: VolSignalType      # What triggered entry
    quantity: float
    entry_price: float
    entry_vix: float
    entry_vix_change_pct: float
    notional_usd: float
    entry_time: datetime
    max_holding_days: int

    # Current state
    current_price: Optional[float] = None
    current_pnl_usd: float = 0.0
    current_pnl_pct: float = 0.0
    holding_hours: float = 0.0

    def update_pnl(self, current_price: float):
        """Update P&L based on current price."""
        self.current_price = current_price

        if self.position_type == "LONG":
            self.current_pnl_usd = (current_price - self.entry_price) * self.quantity
            self.current_pnl_pct = ((current_price / self.entry_price) - 1) * 100
        else:  # SHORT
            self.current_pnl_usd = (self.entry_price - current_price) * self.quantity
            self.current_pnl_pct = ((self.entry_price / current_price) - 1) * 100

        self.holding_hours = (datetime.now() - self.entry_time).total_seconds() / 3600

    def should_exit_time(self) -> bool:
        """Check if position has exceeded max holding time."""
        holding_days = self.holding_hours / 24
        return holding_days >= self.max_holding_days

    def should_stop_loss(self, stop_loss_pct: float) -> bool:
        """Check if stop loss triggered."""
        return self.current_pnl_pct <= -stop_loss_pct

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument": self.instrument,
            "position_type": self.position_type,
            "signal_type": self.signal_type.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_vix": self.entry_vix,
            "entry_vix_change_pct": self.entry_vix_change_pct,
            "notional_usd": self.notional_usd,
            "entry_time": self.entry_time.isoformat(),
            "current_price": self.current_price,
            "current_pnl_usd": self.current_pnl_usd,
            "current_pnl_pct": self.current_pnl_pct,
            "holding_hours": self.holding_hours,
        }


class VolMeanReversionStrategy:
    """
    Vol-of-Vol Mean Reversion Strategy.

    Detects VIX spikes/crashes and trades volatility instruments
    for mean reversion.
    """

    def __init__(self, config: Optional[VolMeanReversionConfig] = None):
        self.config = config or VolMeanReversionConfig()

        # Position tracking
        self._position: Optional[VolPosition] = None
        self._closed_positions: List[Dict[str, Any]] = []

        # VIX history for rolling stats
        self._vix_history: deque = deque(maxlen=100)
        self._daily_closes: deque = deque(maxlen=50)

        # Signal history
        self._signal_history: List[VolSignal] = []

        # Stats
        self._total_trades = 0
        self._winning_trades = 0
        self._total_pnl = 0.0

    def update_market_state(self, market_data: Dict[str, Any]) -> Optional[VolMarketState]:
        """
        Update market state from raw market data.

        Args:
            market_data: Dictionary with VIX, UVXY, SVXY, VXX prices

        Returns:
            VolMarketState or None if insufficient data
        """
        vix_data = market_data.get("VIX", {})
        vix_price = vix_data.get("price") or vix_data.get("last")
        vix_prev_close = vix_data.get("prev_close") or vix_data.get("close")

        if vix_price is None:
            return None

        # Calculate daily change
        if vix_prev_close and vix_prev_close > 0:
            vix_change_pct = ((vix_price / vix_prev_close) - 1) * 100
        else:
            vix_change_pct = 0.0

        # Update history
        self._vix_history.append({
            "price": vix_price,
            "timestamp": datetime.now(),
        })

        # Calculate rolling stats
        vix_mean_20d = None
        vix_std_20d = None
        vix_zscore = None

        if len(self._vix_history) >= self.config.lookback_days:
            recent = [v["price"] for v in list(self._vix_history)[-self.config.lookback_days:]]
            vix_mean_20d = np.mean(recent)
            vix_std_20d = np.std(recent)
            if vix_std_20d > 0:
                vix_zscore = (vix_price - vix_mean_20d) / vix_std_20d

        state = VolMarketState(
            vix_price=vix_price,
            vix_prev_close=vix_prev_close or vix_price,
            vix_change_pct=vix_change_pct,
            vix_mean_20d=vix_mean_20d,
            vix_std_20d=vix_std_20d,
            vix_zscore=vix_zscore,
            uvxy_price=market_data.get("UVXY", {}).get("price"),
            svxy_price=market_data.get("SVXY", {}).get("price"),
            vxx_price=market_data.get("VXX", {}).get("price"),
            timestamp=datetime.now(),
        )

        return state

    def generate_signal(self, state: VolMarketState) -> VolSignal:
        """
        Generate trading signal based on current market state.

        Args:
            state: Current volatility market state

        Returns:
            VolSignal with trade recommendation
        """
        # Check existing position first
        if self._position:
            return self._check_exit_conditions(state)

        # Check for entry conditions
        return self._check_entry_conditions(state)

    def _check_entry_conditions(self, state: VolMarketState) -> VolSignal:
        """Check for new entry conditions."""
        vix_change = state.vix_change_pct

        # Extreme VIX spike (+30%+): Aggressive short vol
        if vix_change >= self.config.vix_extreme_spike_pct:
            instrument = self.config.preferred_short_vol
            return VolSignal(
                signal="SHORT_VOL",
                instrument=instrument,
                notional_usd=self.config.notional_usd * 1.5,  # Larger size for extreme
                vix_change_pct=vix_change,
                vix_price=state.vix_price,
                reason=f"Extreme VIX spike: {vix_change:+.1f}% - aggressive short vol",
                is_extreme=True,
                position_type="LONG" if instrument in ["SVXY"] else "SHORT",
            )

        # VIX spike (+15%+): Short vol
        if vix_change >= self.config.vix_spike_threshold_pct:
            instrument = self.config.preferred_short_vol
            return VolSignal(
                signal="SHORT_VOL",
                instrument=instrument,
                notional_usd=self.config.notional_usd,
                vix_change_pct=vix_change,
                vix_price=state.vix_price,
                reason=f"VIX spike: {vix_change:+.1f}% - short vol for mean reversion",
                is_extreme=False,
                position_type="LONG" if instrument in ["SVXY"] else "SHORT",
            )

        # VIX crash (-10% or worse): Long vol
        if vix_change <= self.config.vix_crash_threshold_pct:
            instrument = self.config.preferred_long_vol
            return VolSignal(
                signal="LONG_VOL",
                instrument=instrument,
                notional_usd=self.config.notional_usd,
                vix_change_pct=vix_change,
                vix_price=state.vix_price,
                reason=f"VIX crash: {vix_change:+.1f}% - long vol expecting normalization",
                is_extreme=False,
                position_type="LONG" if instrument in ["UVXY", "VXX"] else "SHORT",
            )

        # No entry signal
        return VolSignal(
            signal="NONE",
            instrument=None,
            notional_usd=0,
            vix_change_pct=vix_change,
            vix_price=state.vix_price,
            reason=f"No entry: VIX change {vix_change:+.1f}% within normal range",
        )

    def _check_exit_conditions(self, state: VolMarketState) -> VolSignal:
        """Check exit conditions for existing position."""
        pos = self._position
        if not pos:
            return VolSignal(
                signal="NONE",
                instrument=None,
                notional_usd=0,
                vix_change_pct=state.vix_change_pct,
                vix_price=state.vix_price,
                reason="No position",
            )

        # Update position PnL
        current_price = self._get_instrument_price(pos.instrument, state)
        if current_price:
            pos.update_pnl(current_price)

        # Check stop loss
        if pos.should_stop_loss(self.config.stop_loss_pct):
            return VolSignal(
                signal="STOP_LOSS",
                instrument=pos.instrument,
                notional_usd=pos.notional_usd,
                vix_change_pct=state.vix_change_pct,
                vix_price=state.vix_price,
                reason=f"Stop loss: P&L {pos.current_pnl_pct:+.1f}% < -{self.config.stop_loss_pct}%",
            )

        # Check max holding time
        if pos.should_exit_time():
            return VolSignal(
                signal="EXIT",
                instrument=pos.instrument,
                notional_usd=pos.notional_usd,
                vix_change_pct=state.vix_change_pct,
                vix_price=state.vix_price,
                reason=f"Max holding: {pos.holding_hours:.1f}h >= {self.config.max_holding_days * 24}h",
            )

        # Check mean reversion (VIX normalized)
        if state.vix_zscore is not None:
            if pos.signal_type == VolSignalType.SHORT_VOL:
                # Short vol after spike - exit when VIX back to normal
                if state.vix_zscore < self.config.mean_reversion_z:
                    return VolSignal(
                        signal="EXIT",
                        instrument=pos.instrument,
                        notional_usd=pos.notional_usd,
                        vix_change_pct=state.vix_change_pct,
                        vix_price=state.vix_price,
                        reason=f"Mean reversion: VIX z-score {state.vix_zscore:.2f} normalized",
                    )
            elif pos.signal_type == VolSignalType.LONG_VOL:
                # Long vol after crash - exit when VIX bounces
                if state.vix_zscore > -self.config.mean_reversion_z:
                    return VolSignal(
                        signal="EXIT",
                        instrument=pos.instrument,
                        notional_usd=pos.notional_usd,
                        vix_change_pct=state.vix_change_pct,
                        vix_price=state.vix_price,
                        reason=f"Mean reversion: VIX z-score {state.vix_zscore:.2f} bounced",
                    )

        # Hold position
        return VolSignal(
            signal="NONE",
            instrument=pos.instrument,
            notional_usd=0,
            vix_change_pct=state.vix_change_pct,
            vix_price=state.vix_price,
            reason=f"Hold: {pos.instrument} P&L {pos.current_pnl_pct:+.1f}%, {pos.holding_hours:.1f}h",
        )

    def _get_instrument_price(self, instrument: str, state: VolMarketState) -> Optional[float]:
        """Get current price for an instrument."""
        if instrument == "UVXY":
            return state.uvxy_price
        elif instrument == "SVXY":
            return state.svxy_price
        elif instrument == "VXX":
            return state.vxx_price
        return None

    def open_position(self, signal: VolSignal, price: float) -> Optional[VolPosition]:
        """
        Open a new position based on signal.

        Args:
            signal: The entry signal
            price: Entry price

        Returns:
            VolPosition if opened successfully
        """
        if self._position:
            logger.warning("Already have position, cannot open new")
            return None

        if signal.signal not in ("SHORT_VOL", "LONG_VOL"):
            return None

        quantity = signal.notional_usd / price

        self._position = VolPosition(
            instrument=signal.instrument,
            position_type=signal.position_type,
            signal_type=VolSignalType[signal.signal],
            quantity=quantity,
            entry_price=price,
            entry_vix=signal.vix_price,
            entry_vix_change_pct=signal.vix_change_pct,
            notional_usd=signal.notional_usd,
            entry_time=datetime.now(),
            max_holding_days=self.config.max_holding_days,
            current_price=price,
        )

        self._signal_history.append(signal)
        logger.info(f"Opened {signal.signal} position: {signal.instrument} "
                   f"qty={quantity:.4f} @ ${price:.2f}")

        return self._position

    def close_position(self, price: float, reason: str = "Manual") -> Optional[Dict[str, Any]]:
        """
        Close the current position.

        Args:
            price: Exit price
            reason: Reason for closing

        Returns:
            Summary of closed position
        """
        if not self._position:
            return None

        pos = self._position
        pos.update_pnl(price)

        summary = {
            "instrument": pos.instrument,
            "position_type": pos.position_type,
            "signal_type": pos.signal_type.value,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "exit_price": price,
            "entry_vix": pos.entry_vix,
            "notional_usd": pos.notional_usd,
            "pnl_usd": pos.current_pnl_usd,
            "pnl_pct": pos.current_pnl_pct,
            "holding_hours": pos.holding_hours,
            "entry_time": pos.entry_time.isoformat(),
            "exit_time": datetime.now().isoformat(),
            "exit_reason": reason,
        }

        self._closed_positions.append(summary)
        self._total_trades += 1
        self._total_pnl += pos.current_pnl_usd

        if pos.current_pnl_usd > 0:
            self._winning_trades += 1

        logger.info(f"Closed {pos.instrument}: P&L ${pos.current_pnl_usd:+.2f} "
                   f"({pos.current_pnl_pct:+.1f}%) - {reason}")

        self._position = None
        return summary

    def get_position(self) -> Optional[VolPosition]:
        """Get current position."""
        return self._position

    def has_position(self) -> bool:
        """Check if there's an open position."""
        return self._position is not None

    def get_closed_positions(self) -> List[Dict[str, Any]]:
        """Get history of closed positions."""
        return self._closed_positions

    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics."""
        win_rate = (self._winning_trades / self._total_trades * 100
                   if self._total_trades > 0 else 0)

        return {
            "total_trades": self._total_trades,
            "winning_trades": self._winning_trades,
            "losing_trades": self._total_trades - self._winning_trades,
            "win_rate_pct": win_rate,
            "total_pnl_usd": self._total_pnl,
            "has_position": self.has_position(),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get full strategy state for dashboard."""
        vix_stats = {}
        if len(self._vix_history) >= 5:
            recent = [v["price"] for v in self._vix_history]
            vix_stats = {
                "current": recent[-1],
                "mean_20d": np.mean(recent[-20:]) if len(recent) >= 20 else np.mean(recent),
                "std_20d": np.std(recent[-20:]) if len(recent) >= 20 else np.std(recent),
                "min": min(recent),
                "max": max(recent),
            }

        return {
            "config": {
                "spike_threshold": self.config.vix_spike_threshold_pct,
                "crash_threshold": self.config.vix_crash_threshold_pct,
                "extreme_threshold": self.config.vix_extreme_spike_pct,
                "max_holding_days": self.config.max_holding_days,
                "stop_loss_pct": self.config.stop_loss_pct,
            },
            "vix_stats": vix_stats,
            "position": self._position.to_dict() if self._position else None,
            "stats": self.get_stats(),
            "recent_signals": [s.to_dict() for s in self._signal_history[-10:]],
        }


def generate_vol_of_vol_signal(market_state: Dict[str, Any],
                                strategy: Optional[VolMeanReversionStrategy] = None,
                                config: Optional[VolMeanReversionConfig] = None) -> dict:
    """
    Generate a vol-of-vol trading signal.

    This is the main entry point function for the strategy.

    Args:
        market_state: Dictionary with market data:
            {
                "VIX": {"price": 20.5, "prev_close": 18.0},
                "UVXY": {"price": 12.5},
                "SVXY": {"price": 45.0},
                "VXX": {"price": 22.0},
            }
        strategy: Optional existing strategy instance
        config: Optional configuration

    Returns:
        dict with signal:
        {
            "signal": "SHORT_VOL" | "LONG_VOL" | "EXIT" | "STOP_LOSS" | "NONE",
            "instrument": "UVXY" | "SVXY" | "VXX" | None,
            "notional_usd": float,
            "vix_change_pct": float,
            "vix_price": float,
            "reason": str,
            "is_extreme": bool,
            "position_type": "LONG" | "SHORT" | None,
        }
    """
    if strategy is None:
        strategy = VolMeanReversionStrategy(config)

    # Update market state
    state = strategy.update_market_state(market_state)

    if state is None:
        return {
            "signal": "NONE",
            "instrument": None,
            "notional_usd": 0,
            "vix_change_pct": 0,
            "vix_price": 0,
            "reason": "Insufficient market data",
            "is_extreme": False,
            "position_type": None,
        }

    # Generate signal
    signal = strategy.generate_signal(state)

    return signal.to_dict()


def create_vol_market_state(vix_price: float,
                            vix_prev_close: float,
                            uvxy_price: Optional[float] = None,
                            svxy_price: Optional[float] = None,
                            vxx_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Create a market state dictionary for the strategy.

    Args:
        vix_price: Current VIX price
        vix_prev_close: Previous day VIX close
        uvxy_price: Optional UVXY price
        svxy_price: Optional SVXY price
        vxx_price: Optional VXX price

    Returns:
        Dictionary suitable for generate_vol_of_vol_signal()
    """
    state = {
        "VIX": {
            "price": vix_price,
            "prev_close": vix_prev_close,
        }
    }

    if uvxy_price:
        state["UVXY"] = {"price": uvxy_price}
    if svxy_price:
        state["SVXY"] = {"price": svxy_price}
    if vxx_price:
        state["VXX"] = {"price": vxx_price}

    return state
