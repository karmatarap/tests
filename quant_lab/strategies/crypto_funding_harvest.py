"""
Crypto Funding-Rate Harvest Strategy

Detects extreme funding rates in BTC/ETH perpetual futures and simulates
cash-and-carry trades: long spot (Coinbase) + short perp (Binance).

Strategy Logic:
1. Monitor funding rates every 15-60 minutes
2. When funding > upper threshold (e.g., +0.10% per 8h):
   - Open carry trade: long spot, short perp
   - Earn positive funding while hedged
3. When funding normalizes (between -0.05% and +0.05%):
   - Close position
4. Track accrued funding and spot/perp PnL
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
import json
import os

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class FundingHarvestConfig:
    """Configuration for funding harvest strategy."""
    # Funding rate thresholds (per 8h, in percentage)
    entry_threshold_pct: float = 0.10  # Open when funding > 0.10%
    exit_threshold_pct: float = 0.05   # Close when |funding| < 0.05%
    inverse_entry_threshold_pct: float = -0.10  # For inverse carry (optional)

    # Position sizing
    notional_usd: float = 5000.0  # USD notional per position
    max_positions: int = 2  # Max concurrent positions (BTC + ETH)

    # Timing
    update_interval_minutes: int = 15  # Check every 15 minutes
    max_holding_hours: int = 72  # Max holding period (3 days)

    # Risk
    max_basis_pct: float = 1.0  # Don't enter if basis too wide
    min_annualized_rate_pct: float = 20.0  # Minimum annualized rate to consider

    # Assets
    assets: List[str] = field(default_factory=lambda: ["BTC", "ETH"])


# =============================================================================
# Data Structures
# =============================================================================

class PositionType(Enum):
    """Type of carry trade position."""
    NONE = "NONE"
    LONG_CARRY = "LONG_CARRY"    # Long spot, short perp (collect positive funding)
    SHORT_CARRY = "SHORT_CARRY"  # Short spot, long perp (collect negative funding)


@dataclass
class CarryPosition:
    """Represents a cash-and-carry position."""
    asset: str
    position_type: PositionType
    notional_usd: float

    # Entry details
    entry_time: datetime
    entry_spot_price: float
    entry_perp_price: float
    entry_funding_rate: float

    # Current state
    spot_quantity: float = 0.0
    perp_quantity: float = 0.0

    # Accrued values
    accrued_funding_usd: float = 0.0
    funding_payments: int = 0

    # PnL tracking
    spot_pnl_usd: float = 0.0
    perp_pnl_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "position_type": self.position_type.value,
            "notional_usd": self.notional_usd,
            "entry_time": self.entry_time.isoformat(),
            "entry_spot_price": self.entry_spot_price,
            "entry_perp_price": self.entry_perp_price,
            "entry_funding_rate": self.entry_funding_rate,
            "spot_quantity": self.spot_quantity,
            "perp_quantity": self.perp_quantity,
            "accrued_funding_usd": self.accrued_funding_usd,
            "funding_payments": self.funding_payments,
            "spot_pnl_usd": self.spot_pnl_usd,
            "perp_pnl_usd": self.perp_pnl_usd,
            "total_pnl_usd": self.total_pnl,
            "holding_hours": self.holding_hours,
        }

    @property
    def total_pnl(self) -> float:
        """Total PnL = funding earned + spot PnL + perp PnL"""
        return self.accrued_funding_usd + self.spot_pnl_usd + self.perp_pnl_usd

    @property
    def holding_hours(self) -> float:
        """Hours position has been held."""
        return (datetime.now() - self.entry_time).total_seconds() / 3600


@dataclass
class MarketState:
    """Current market state for an asset."""
    asset: str
    spot_price: float
    perp_price: float
    mark_price: float
    funding_rate: float
    funding_rate_pct: float
    annualized_rate_pct: float
    basis_pct: float
    next_funding_time: Optional[datetime]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "spot_price": self.spot_price,
            "perp_price": self.perp_price,
            "mark_price": self.mark_price,
            "funding_rate": self.funding_rate,
            "funding_rate_pct": self.funding_rate_pct,
            "annualized_rate_pct": self.annualized_rate_pct,
            "basis_pct": self.basis_pct,
            "next_funding_time": self.next_funding_time.isoformat() if self.next_funding_time else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FundingSignal:
    """Trading signal for funding harvest."""
    signal: str  # "OPEN", "CLOSE", "HOLD", "NONE"
    asset: str
    notional_usd: float
    current_funding: float
    reason: str
    position_type: PositionType = PositionType.NONE
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal,
            "asset": self.asset,
            "notional_usd": self.notional_usd,
            "current_funding": self.current_funding,
            "reason": self.reason,
            "position_type": self.position_type.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# =============================================================================
# Strategy Core
# =============================================================================

class CryptoFundingHarvestStrategy:
    """
    Crypto Funding-Rate Harvest Strategy.

    Monitors funding rates and opens/closes cash-and-carry positions
    to harvest extreme funding rates.
    """

    def __init__(self, config: Optional[FundingHarvestConfig] = None):
        self.config = config or FundingHarvestConfig()

        # Positions
        self._positions: Dict[str, CarryPosition] = {}

        # History tracking
        self._funding_history: Dict[str, List[Dict[str, Any]]] = {}
        self._signal_history: List[FundingSignal] = []
        self._closed_positions: List[Dict[str, Any]] = []

        # State
        self._last_update: Optional[datetime] = None
        self._last_funding_times: Dict[str, datetime] = {}

        # Initialize history for each asset
        for asset in self.config.assets:
            self._funding_history[asset] = []

        logger.info(f"Funding Harvest Strategy initialized for {self.config.assets}")

    def update_market_state(self, asset: str, data: Dict[str, Any]) -> Optional[MarketState]:
        """
        Update market state with new data.

        Args:
            asset: Asset symbol (e.g., "BTC")
            data: Market data dictionary

        Returns:
            MarketState object
        """
        try:
            spot_price = data.get("spot_price")
            perp_price = data.get("perp_price")
            funding_rate = data.get("funding_rate", 0)
            funding_rate_pct = data.get("funding_rate_pct", funding_rate * 100)

            if not spot_price or not perp_price:
                return None

            # Calculate basis
            basis_pct = ((perp_price - spot_price) / spot_price) * 100

            state = MarketState(
                asset=asset,
                spot_price=spot_price,
                perp_price=perp_price,
                mark_price=data.get("mark_price", perp_price),
                funding_rate=funding_rate,
                funding_rate_pct=funding_rate_pct,
                annualized_rate_pct=data.get("annualized_funding_pct", funding_rate_pct * 3 * 365),
                basis_pct=basis_pct,
                next_funding_time=data.get("next_funding_time"),
                timestamp=datetime.now(),
            )

            # Store in history
            self._funding_history[asset].append({
                "timestamp": state.timestamp,
                "funding_rate_pct": state.funding_rate_pct,
                "spot_price": state.spot_price,
                "perp_price": state.perp_price,
                "basis_pct": state.basis_pct,
            })

            # Keep last 500 readings
            if len(self._funding_history[asset]) > 500:
                self._funding_history[asset] = self._funding_history[asset][-500:]

            return state

        except Exception as e:
            logger.error(f"Error updating market state for {asset}: {e}")
            return None

    def generate_signal(self, market_state: MarketState) -> FundingSignal:
        """
        Generate trading signal based on market state.

        Args:
            market_state: Current market state

        Returns:
            FundingSignal
        """
        asset = market_state.asset
        funding_pct = market_state.funding_rate_pct
        has_position = asset in self._positions

        # Default signal
        signal = "NONE"
        reason = "No action"
        position_type = PositionType.NONE

        # Check existing position
        if has_position:
            position = self._positions[asset]

            # Check exit conditions
            should_exit, exit_reason = self._check_exit_conditions(
                position, market_state
            )

            if should_exit:
                signal = "CLOSE"
                reason = exit_reason
            else:
                signal = "HOLD"
                reason = f"Holding position, funding={funding_pct:.4f}%"

        else:
            # Check entry conditions
            should_enter, entry_reason, pos_type = self._check_entry_conditions(
                market_state
            )

            if should_enter:
                signal = "OPEN"
                reason = entry_reason
                position_type = pos_type
            else:
                signal = "NONE"
                reason = entry_reason

        funding_signal = FundingSignal(
            signal=signal,
            asset=asset,
            notional_usd=self.config.notional_usd,
            current_funding=funding_pct,
            reason=reason,
            position_type=position_type,
            metadata={
                "spot_price": market_state.spot_price,
                "perp_price": market_state.perp_price,
                "basis_pct": market_state.basis_pct,
                "annualized_rate_pct": market_state.annualized_rate_pct,
                "has_position": has_position,
            },
        )

        # Track signal
        if signal != "NONE":
            self._signal_history.append(funding_signal)
            logger.info(f"Funding signal: {signal} {asset} - {reason}")

        return funding_signal

    def _check_entry_conditions(self, state: MarketState) -> tuple:
        """Check if entry conditions are met."""
        funding_pct = state.funding_rate_pct
        annualized = state.annualized_rate_pct

        # Check max positions
        if len(self._positions) >= self.config.max_positions:
            return False, "Max positions reached", PositionType.NONE

        # Check basis not too wide
        if abs(state.basis_pct) > self.config.max_basis_pct:
            return False, f"Basis too wide: {state.basis_pct:.3f}%", PositionType.NONE

        # Check for long carry (positive funding)
        if funding_pct >= self.config.entry_threshold_pct:
            if annualized >= self.config.min_annualized_rate_pct:
                return (
                    True,
                    f"High positive funding: {funding_pct:.4f}% (ann: {annualized:.1f}%)",
                    PositionType.LONG_CARRY,
                )
            else:
                return False, f"Annualized rate too low: {annualized:.1f}%", PositionType.NONE

        # Check for short carry (negative funding) - optional
        if funding_pct <= self.config.inverse_entry_threshold_pct:
            if abs(annualized) >= self.config.min_annualized_rate_pct:
                return (
                    True,
                    f"High negative funding: {funding_pct:.4f}% (ann: {annualized:.1f}%)",
                    PositionType.SHORT_CARRY,
                )

        return False, f"Funding within normal range: {funding_pct:.4f}%", PositionType.NONE

    def _check_exit_conditions(self, position: CarryPosition, state: MarketState) -> tuple:
        """Check if exit conditions are met."""
        funding_pct = state.funding_rate_pct

        # Check max holding time
        if position.holding_hours >= self.config.max_holding_hours:
            return True, f"Max holding time ({self.config.max_holding_hours}h) exceeded"

        # Check funding normalization
        if position.position_type == PositionType.LONG_CARRY:
            if funding_pct < self.config.exit_threshold_pct:
                return True, f"Funding normalized: {funding_pct:.4f}% < {self.config.exit_threshold_pct}%"

        elif position.position_type == PositionType.SHORT_CARRY:
            if funding_pct > -self.config.exit_threshold_pct:
                return True, f"Funding normalized: {funding_pct:.4f}% > -{self.config.exit_threshold_pct}%"

        return False, "Continue holding"

    def open_position(self, asset: str, signal: FundingSignal,
                      spot_price: float, perp_price: float) -> Optional[CarryPosition]:
        """
        Open a new carry position.

        Args:
            asset: Asset symbol
            signal: Entry signal
            spot_price: Current spot price
            perp_price: Current perp price

        Returns:
            CarryPosition object
        """
        if asset in self._positions:
            logger.warning(f"Position already exists for {asset}")
            return None

        # Calculate quantities
        spot_qty = signal.notional_usd / spot_price
        perp_qty = signal.notional_usd / perp_price

        position = CarryPosition(
            asset=asset,
            position_type=signal.position_type,
            notional_usd=signal.notional_usd,
            entry_time=datetime.now(),
            entry_spot_price=spot_price,
            entry_perp_price=perp_price,
            entry_funding_rate=signal.current_funding,
            spot_quantity=spot_qty,
            perp_quantity=perp_qty,
        )

        self._positions[asset] = position
        logger.info(f"Opened {signal.position_type.value} position for {asset}: "
                   f"{spot_qty:.6f} spot @ {spot_price}, {perp_qty:.6f} perp @ {perp_price}")

        return position

    def close_position(self, asset: str, spot_price: float, perp_price: float) -> Optional[Dict[str, Any]]:
        """
        Close an existing position.

        Args:
            asset: Asset symbol
            spot_price: Current spot price
            perp_price: Current perp price

        Returns:
            Closed position summary
        """
        if asset not in self._positions:
            logger.warning(f"No position to close for {asset}")
            return None

        position = self._positions[asset]

        # Calculate final PnL
        if position.position_type == PositionType.LONG_CARRY:
            # Long spot: profit if price went up
            position.spot_pnl_usd = position.spot_quantity * (spot_price - position.entry_spot_price)
            # Short perp: profit if price went down
            position.perp_pnl_usd = position.perp_quantity * (position.entry_perp_price - perp_price)
        else:
            # Short carry is opposite
            position.spot_pnl_usd = position.spot_quantity * (position.entry_spot_price - spot_price)
            position.perp_pnl_usd = position.perp_quantity * (perp_price - position.entry_perp_price)

        # Create summary
        summary = {
            **position.to_dict(),
            "exit_time": datetime.now().isoformat(),
            "exit_spot_price": spot_price,
            "exit_perp_price": perp_price,
            "final_spot_pnl": position.spot_pnl_usd,
            "final_perp_pnl": position.perp_pnl_usd,
            "final_funding_pnl": position.accrued_funding_usd,
            "final_total_pnl": position.total_pnl,
        }

        self._closed_positions.append(summary)
        del self._positions[asset]

        logger.info(f"Closed position for {asset}: "
                   f"Funding PnL=${position.accrued_funding_usd:.2f}, "
                   f"Spot PnL=${position.spot_pnl_usd:.2f}, "
                   f"Perp PnL=${position.perp_pnl_usd:.2f}, "
                   f"Total=${position.total_pnl:.2f}")

        return summary

    def accrue_funding(self, asset: str, funding_rate_pct: float, mark_price: float):
        """
        Accrue funding payment for an open position.

        Called after each 8h funding settlement.

        Args:
            asset: Asset symbol
            funding_rate_pct: Current funding rate (%)
            mark_price: Mark price at funding time
        """
        if asset not in self._positions:
            return

        position = self._positions[asset]

        # Calculate funding payment
        # For long carry (short perp): receive positive funding, pay negative
        # Funding payment = position_value * funding_rate
        position_value = position.perp_quantity * mark_price

        if position.position_type == PositionType.LONG_CARRY:
            # Short perp receives positive funding
            funding_payment = position_value * (funding_rate_pct / 100)
        else:
            # Long perp pays positive funding (receives negative)
            funding_payment = -position_value * (funding_rate_pct / 100)

        position.accrued_funding_usd += funding_payment
        position.funding_payments += 1

        logger.info(f"{asset} funding accrued: ${funding_payment:.2f} "
                   f"(total: ${position.accrued_funding_usd:.2f}, "
                   f"payments: {position.funding_payments})")

    def update_position_pnl(self, asset: str, spot_price: float, perp_price: float):
        """Update unrealized PnL for an open position."""
        if asset not in self._positions:
            return

        position = self._positions[asset]

        if position.position_type == PositionType.LONG_CARRY:
            position.spot_pnl_usd = position.spot_quantity * (spot_price - position.entry_spot_price)
            position.perp_pnl_usd = position.perp_quantity * (position.entry_perp_price - perp_price)
        else:
            position.spot_pnl_usd = position.spot_quantity * (position.entry_spot_price - spot_price)
            position.perp_pnl_usd = position.perp_quantity * (perp_price - position.entry_perp_price)

    def get_position(self, asset: str) -> Optional[CarryPosition]:
        """Get position for an asset."""
        return self._positions.get(asset)

    def get_all_positions(self) -> Dict[str, CarryPosition]:
        """Get all open positions."""
        return self._positions.copy()

    def get_funding_history(self, asset: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get funding rate history for an asset."""
        return self._funding_history.get(asset, [])[-limit:]

    def get_signal_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signal history."""
        return [s.to_dict() for s in self._signal_history[-limit:]]

    def get_closed_positions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recently closed positions."""
        return self._closed_positions[-limit:]

    def get_total_stats(self) -> Dict[str, Any]:
        """Get total strategy statistics."""
        open_positions = list(self._positions.values())
        closed_positions = self._closed_positions

        total_open_pnl = sum(p.total_pnl for p in open_positions)
        total_closed_pnl = sum(p.get("final_total_pnl", 0) for p in closed_positions)
        total_funding = sum(p.accrued_funding_usd for p in open_positions) + \
                       sum(p.get("final_funding_pnl", 0) for p in closed_positions)

        return {
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "total_open_pnl": total_open_pnl,
            "total_closed_pnl": total_closed_pnl,
            "total_pnl": total_open_pnl + total_closed_pnl,
            "total_funding_earned": total_funding,
            "signals_generated": len(self._signal_history),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get complete strategy state for dashboard."""
        return {
            "config": {
                "entry_threshold_pct": self.config.entry_threshold_pct,
                "exit_threshold_pct": self.config.exit_threshold_pct,
                "notional_usd": self.config.notional_usd,
                "assets": self.config.assets,
            },
            "positions": {asset: pos.to_dict() for asset, pos in self._positions.items()},
            "stats": self.get_total_stats(),
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }


# =============================================================================
# Convenience Function
# =============================================================================

def generate_funding_harvest_signal(market_state: Dict[str, Any],
                                    strategy: Optional[CryptoFundingHarvestStrategy] = None,
                                    config: Optional[FundingHarvestConfig] = None) -> dict:
    """
    Generate funding harvest signal from market state.

    This is the main entry point function.

    Args:
        market_state: Dictionary with market data for an asset
        strategy: Optional strategy instance
        config: Optional configuration

    Returns:
        dict with:
        {
            "signal": "OPEN" | "CLOSE" | "HOLD" | "NONE",
            "asset": "BTC" | "ETH",
            "notional_usd": float,
            "current_funding": float,
            "reason": str
        }
    """
    if strategy is None:
        strategy = CryptoFundingHarvestStrategy(config=config)

    asset = market_state.get("asset", "BTC")

    # Create MarketState object
    state = MarketState(
        asset=asset,
        spot_price=market_state.get("spot_price", 0),
        perp_price=market_state.get("perp_price", 0),
        mark_price=market_state.get("mark_price", market_state.get("perp_price", 0)),
        funding_rate=market_state.get("funding_rate", 0),
        funding_rate_pct=market_state.get("funding_rate_pct", 0),
        annualized_rate_pct=market_state.get("annualized_funding_pct", 0),
        basis_pct=market_state.get("basis_pct", 0),
        next_funding_time=market_state.get("next_funding_time"),
        timestamp=datetime.now(),
    )

    signal = strategy.generate_signal(state)
    return signal.to_dict()
