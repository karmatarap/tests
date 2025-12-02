"""
ETF-Futures Spread Dislocation Strategy

Detects short-term dislocations between an ETF and its underlying index futures
(e.g., SPY vs ES, QQQ vs NQ) and generates mean-reversion long/short signals.

This is an intraday pairs trading strategy that:
1. Computes the spread between ETF and scaled futures price
2. Calculates z-score of current spread vs historical
3. Generates signals when z-score exceeds entry threshold
4. Exits when z-score reverts to exit threshold
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import deque
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class SpreadPairConfig:
    """Configuration for an ETF-Futures pair."""
    etf_symbol: str
    futures_symbol: str
    futures_exchange: str = "CME"
    futures_multiplier: float = 1.0  # Contract multiplier (ES=50, NQ=20)
    scaling_factor: float = 1.0  # k in spread = ETF - k * Future
    etf_shares_per_future: int = 500  # Hedge ratio: ETF shares per 1 future


# Default pairs configuration
DEFAULT_PAIRS = {
    "SPY_ES": SpreadPairConfig(
        etf_symbol="SPY",
        futures_symbol="ES",
        futures_exchange="CME",
        futures_multiplier=50.0,
        scaling_factor=0.1,  # SPY ~= ES / 10
        etf_shares_per_future=500,
    ),
    "QQQ_NQ": SpreadPairConfig(
        etf_symbol="QQQ",
        futures_symbol="NQ",
        futures_exchange="CME",
        futures_multiplier=20.0,
        scaling_factor=0.025,  # QQQ ~= NQ / 40
        etf_shares_per_future=400,
    ),
    "IWM_RTY": SpreadPairConfig(
        etf_symbol="IWM",
        futures_symbol="RTY",
        futures_exchange="CME",
        futures_multiplier=50.0,
        scaling_factor=0.5,  # IWM ~= RTY / 2
        etf_shares_per_future=500,
    ),
}


@dataclass
class StrategyConfig:
    """Strategy configuration parameters."""
    # Z-score thresholds
    z_entry: float = 2.0  # Enter when |z| > z_entry
    z_exit: float = 0.5   # Exit when |z| < z_exit

    # Lookback for z-score calculation
    lookback_minutes: int = 60  # Minutes of history for z-score

    # Position sizing
    notional_per_leg_usd: float = 5000.0  # Fixed notional per leg
    max_position_pct: float = 0.01  # Max 1% of portfolio per position
    use_pct_sizing: bool = False  # If True, use portfolio % instead of fixed

    # Execution
    update_interval_seconds: int = 60  # How often to check signals
    max_spread_age_seconds: int = 5  # Max age of price data

    # Risk limits
    max_daily_trades: int = 20
    stop_loss_z: float = 4.0  # Emergency stop if z-score hits this
    max_holding_minutes: int = 240  # Max time to hold position


# =============================================================================
# Data Structures
# =============================================================================

class PositionSide(Enum):
    """Current position side."""
    FLAT = "FLAT"
    LONG_ETF = "LONG"   # Long ETF, Short Future
    SHORT_ETF = "SHORT"  # Short ETF, Long Future


@dataclass
class SpreadData:
    """Spread price data point."""
    timestamp: datetime
    etf_price: float
    futures_price: float
    spread: float
    z_score: Optional[float] = None


@dataclass
class MarketState:
    """Current market state for a pair."""
    pair_id: str
    config: SpreadPairConfig
    etf_price: float
    etf_bid: float
    etf_ask: float
    futures_price: float
    futures_bid: float
    futures_ask: float
    spread: float
    spread_history: List[float]
    z_score: float
    timestamp: datetime
    position_side: PositionSide = PositionSide.FLAT
    position_etf_qty: float = 0.0
    position_futures_qty: float = 0.0
    entry_z_score: Optional[float] = None
    entry_time: Optional[datetime] = None
    unrealized_pnl: float = 0.0


@dataclass
class TradeSignal:
    """Trading signal output."""
    signal: str  # "LONG", "SHORT", "FLAT", "CLOSE"
    symbol_etf: str
    symbol_hedge: str
    size_etf: float
    size_hedge: float
    reason: str
    z_score: float
    spread: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal": self.signal,
            "symbol_etf": self.symbol_etf,
            "symbol_hedge": self.symbol_hedge,
            "size_etf": self.size_etf,
            "size_hedge": self.size_hedge,
            "reason": self.reason,
            "z_score": self.z_score,
            "spread": self.spread,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# =============================================================================
# Strategy Core
# =============================================================================

class ETFFuturesSpreadStrategy:
    """
    ETF-Futures Spread Dislocation Strategy.

    Monitors spread between ETF and futures, generates mean-reversion signals
    based on z-score of current spread vs historical distribution.
    """

    def __init__(self, config: Optional[StrategyConfig] = None,
                 pairs: Optional[Dict[str, SpreadPairConfig]] = None):
        """
        Initialize strategy.

        Args:
            config: Strategy configuration
            pairs: Dictionary of pair configurations
        """
        self.config = config or StrategyConfig()
        self.pairs = pairs or DEFAULT_PAIRS

        # State tracking per pair
        self._spread_history: Dict[str, deque] = {}
        self._positions: Dict[str, MarketState] = {}
        self._daily_trades: int = 0
        self._last_trade_date: Optional[datetime] = None
        self._trade_log: List[Dict[str, Any]] = []

        # Initialize spread history deques
        for pair_id in self.pairs:
            self._spread_history[pair_id] = deque(maxlen=self.config.lookback_minutes * 2)

        logger.info(f"ETF-Futures Spread Strategy initialized with {len(self.pairs)} pairs")

    def update_prices(self, pair_id: str, etf_price: float, futures_price: float,
                      etf_bid: float = None, etf_ask: float = None,
                      futures_bid: float = None, futures_ask: float = None,
                      timestamp: Optional[datetime] = None) -> SpreadData:
        """
        Update prices and calculate spread for a pair.

        Args:
            pair_id: Pair identifier (e.g., "SPY_ES")
            etf_price: Current ETF mid price
            futures_price: Current futures mid price
            etf_bid/ask: Optional bid/ask for ETF
            futures_bid/ask: Optional bid/ask for futures
            timestamp: Price timestamp

        Returns:
            SpreadData with calculated spread and z-score
        """
        if pair_id not in self.pairs:
            raise ValueError(f"Unknown pair: {pair_id}")

        pair_config = self.pairs[pair_id]
        timestamp = timestamp or datetime.now()

        # Calculate spread: ETF - k * Future
        spread = etf_price - pair_config.scaling_factor * futures_price

        # Store in history
        self._spread_history[pair_id].append({
            "timestamp": timestamp,
            "spread": spread,
            "etf_price": etf_price,
            "futures_price": futures_price,
        })

        # Calculate z-score
        z_score = self._calculate_z_score(pair_id)

        spread_data = SpreadData(
            timestamp=timestamp,
            etf_price=etf_price,
            futures_price=futures_price,
            spread=spread,
            z_score=z_score,
        )

        logger.debug(f"{pair_id}: spread={spread:.4f}, z={z_score:.2f}" if z_score else
                    f"{pair_id}: spread={spread:.4f}, z=N/A (insufficient history)")

        return spread_data

    def _calculate_z_score(self, pair_id: str) -> Optional[float]:
        """Calculate z-score of current spread."""
        history = self._spread_history[pair_id]

        if len(history) < self.config.lookback_minutes:
            return None

        # Get recent spreads
        spreads = [h["spread"] for h in list(history)[-self.config.lookback_minutes:]]

        mean_spread = np.mean(spreads)
        std_spread = np.std(spreads)

        if std_spread < 1e-8:  # Avoid division by zero
            return 0.0

        current_spread = history[-1]["spread"]
        z_score = (current_spread - mean_spread) / std_spread

        return z_score

    def generate_signal(self, market_state: MarketState) -> TradeSignal:
        """
        Generate trading signal based on market state.

        This is the main signal generation function.

        Args:
            market_state: Current market state for a pair

        Returns:
            TradeSignal with action and sizing
        """
        pair_config = self.pairs[market_state.pair_id]
        z = market_state.z_score
        current_position = market_state.position_side

        # Default: no action
        signal = "FLAT"
        reason = "No signal"
        size_etf = 0.0
        size_hedge = 0.0

        # Check daily trade limit
        if self._should_reset_daily_count():
            self._daily_trades = 0
            self._last_trade_date = datetime.now().date()

        if self._daily_trades >= self.config.max_daily_trades:
            return TradeSignal(
                signal="FLAT",
                symbol_etf=pair_config.etf_symbol,
                symbol_hedge=pair_config.futures_symbol,
                size_etf=0.0,
                size_hedge=0.0,
                reason="Daily trade limit reached",
                z_score=z,
                spread=market_state.spread,
            )

        # Calculate position sizes
        size_etf, size_hedge = self._calculate_position_size(
            market_state.etf_price,
            market_state.futures_price,
            pair_config,
        )

        # ========== ENTRY LOGIC ==========
        if current_position == PositionSide.FLAT:
            if z > self.config.z_entry:
                # ETF rich relative to futures
                # Signal: SHORT ETF, LONG Future
                signal = "SHORT"
                reason = f"ETF rich: z={z:.2f} > {self.config.z_entry}"
                logger.info(f"{market_state.pair_id}: {reason}")

            elif z < -self.config.z_entry:
                # ETF cheap relative to futures
                # Signal: LONG ETF, SHORT Future
                signal = "LONG"
                reason = f"ETF cheap: z={z:.2f} < -{self.config.z_entry}"
                logger.info(f"{market_state.pair_id}: {reason}")

        # ========== EXIT LOGIC ==========
        elif current_position == PositionSide.LONG_ETF:
            # Currently long ETF, short future
            # Exit if z-score reverts OR stop loss
            if abs(z) < self.config.z_exit:
                signal = "CLOSE"
                reason = f"Mean reversion: |z|={abs(z):.2f} < {self.config.z_exit}"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.info(f"{market_state.pair_id}: {reason}")

            elif z > self.config.stop_loss_z:
                signal = "CLOSE"
                reason = f"Stop loss: z={z:.2f} > {self.config.stop_loss_z}"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.warning(f"{market_state.pair_id}: {reason}")

            elif self._check_max_holding(market_state):
                signal = "CLOSE"
                reason = f"Max holding time exceeded"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.info(f"{market_state.pair_id}: {reason}")

        elif current_position == PositionSide.SHORT_ETF:
            # Currently short ETF, long future
            if abs(z) < self.config.z_exit:
                signal = "CLOSE"
                reason = f"Mean reversion: |z|={abs(z):.2f} < {self.config.z_exit}"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.info(f"{market_state.pair_id}: {reason}")

            elif z < -self.config.stop_loss_z:
                signal = "CLOSE"
                reason = f"Stop loss: z={z:.2f} < -{self.config.stop_loss_z}"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.warning(f"{market_state.pair_id}: {reason}")

            elif self._check_max_holding(market_state):
                signal = "CLOSE"
                reason = f"Max holding time exceeded"
                size_etf = abs(market_state.position_etf_qty)
                size_hedge = abs(market_state.position_futures_qty)
                logger.info(f"{market_state.pair_id}: {reason}")

        trade_signal = TradeSignal(
            signal=signal,
            symbol_etf=pair_config.etf_symbol,
            symbol_hedge=pair_config.futures_symbol,
            size_etf=size_etf,
            size_hedge=size_hedge,
            reason=reason,
            z_score=z,
            spread=market_state.spread,
            metadata={
                "pair_id": market_state.pair_id,
                "etf_price": market_state.etf_price,
                "futures_price": market_state.futures_price,
                "current_position": current_position.value,
            },
        )

        # Track trade
        if signal in ("LONG", "SHORT"):
            self._daily_trades += 1

        return trade_signal

    def _calculate_position_size(self, etf_price: float, futures_price: float,
                                  pair_config: SpreadPairConfig) -> Tuple[float, float]:
        """
        Calculate position sizes for ETF and futures.

        Returns:
            Tuple of (etf_shares, futures_contracts)
        """
        notional = self.config.notional_per_leg_usd

        # ETF shares
        etf_shares = int(notional / etf_price)

        # Futures contracts (usually 1 for small accounts)
        # Notional of 1 ES contract = futures_price * multiplier
        futures_notional = futures_price * pair_config.futures_multiplier
        futures_contracts = max(1, int(notional / futures_notional))

        # Adjust ETF shares to match futures hedge
        # 1 ES contract ~= 500 SPY shares at current prices
        hedge_etf_shares = futures_contracts * pair_config.etf_shares_per_future
        etf_shares = min(etf_shares, hedge_etf_shares)

        return float(etf_shares), float(futures_contracts)

    def _check_max_holding(self, market_state: MarketState) -> bool:
        """Check if position has exceeded max holding time."""
        if market_state.entry_time is None:
            return False

        elapsed = (datetime.now() - market_state.entry_time).total_seconds() / 60
        return elapsed > self.config.max_holding_minutes

    def _should_reset_daily_count(self) -> bool:
        """Check if daily trade count should be reset."""
        if self._last_trade_date is None:
            return True
        return datetime.now().date() > self._last_trade_date

    def get_spread_history(self, pair_id: str, minutes: int = None) -> pd.DataFrame:
        """Get spread history as DataFrame."""
        if pair_id not in self._spread_history:
            return pd.DataFrame()

        history = list(self._spread_history[pair_id])
        if minutes:
            history = history[-minutes:]

        if not history:
            return pd.DataFrame()

        df = pd.DataFrame(history)
        df.set_index("timestamp", inplace=True)
        return df

    def get_z_score_history(self, pair_id: str) -> List[float]:
        """Get z-score history for a pair."""
        history = self._spread_history[pair_id]
        if len(history) < self.config.lookback_minutes:
            return []

        z_scores = []
        spreads = [h["spread"] for h in history]

        for i in range(self.config.lookback_minutes, len(spreads)):
            window = spreads[i - self.config.lookback_minutes:i]
            mean_s = np.mean(window)
            std_s = np.std(window)
            if std_s > 1e-8:
                z = (spreads[i] - mean_s) / std_s
                z_scores.append(z)

        return z_scores

    def get_state(self, pair_id: str) -> Dict[str, Any]:
        """Get current strategy state for a pair."""
        history = self._spread_history.get(pair_id, [])
        position = self._positions.get(pair_id)

        current_z = self._calculate_z_score(pair_id)
        current_spread = history[-1]["spread"] if history else None

        return {
            "pair_id": pair_id,
            "current_spread": current_spread,
            "current_z_score": current_z,
            "history_length": len(history),
            "lookback_minutes": self.config.lookback_minutes,
            "z_entry": self.config.z_entry,
            "z_exit": self.config.z_exit,
            "position_side": position.position_side.value if position else "FLAT",
            "daily_trades": self._daily_trades,
        }


# =============================================================================
# Convenience Function
# =============================================================================

def generate_etf_dislocation_signal(market_state: MarketState,
                                     strategy: Optional[ETFFuturesSpreadStrategy] = None,
                                     config: Optional[StrategyConfig] = None) -> dict:
    """
    Generate ETF dislocation signal from market state.

    This is the main entry point function.

    Args:
        market_state: Current market state with prices and z-score
        strategy: Optional strategy instance (creates new if None)
        config: Optional strategy configuration

    Returns:
        dict with:
        {
            "signal": "LONG" | "SHORT" | "FLAT",
            "symbol_etf": "SPY",
            "symbol_hedge": "ES",
            "size_etf": float,
            "size_hedge": float,
            "reason": str,
            "z_score": float
        }
    """
    if strategy is None:
        strategy = ETFFuturesSpreadStrategy(config=config)

    signal = strategy.generate_signal(market_state)
    return signal.to_dict()


def create_market_state(pair_id: str,
                        etf_price: float,
                        futures_price: float,
                        spread_history: List[float],
                        z_score: float,
                        position_side: str = "FLAT",
                        position_etf_qty: float = 0.0,
                        position_futures_qty: float = 0.0,
                        pairs: Optional[Dict[str, SpreadPairConfig]] = None) -> MarketState:
    """
    Helper function to create MarketState object.

    Args:
        pair_id: Pair identifier
        etf_price: Current ETF price
        futures_price: Current futures price
        spread_history: List of recent spreads
        z_score: Current z-score
        position_side: Current position ("FLAT", "LONG", "SHORT")
        position_etf_qty: ETF position quantity
        position_futures_qty: Futures position quantity
        pairs: Optional pairs configuration

    Returns:
        MarketState object
    """
    pairs = pairs or DEFAULT_PAIRS
    if pair_id not in pairs:
        raise ValueError(f"Unknown pair: {pair_id}")

    config = pairs[pair_id]
    spread = etf_price - config.scaling_factor * futures_price

    position = PositionSide.FLAT
    if position_side == "LONG":
        position = PositionSide.LONG_ETF
    elif position_side == "SHORT":
        position = PositionSide.SHORT_ETF

    return MarketState(
        pair_id=pair_id,
        config=config,
        etf_price=etf_price,
        etf_bid=etf_price - 0.01,
        etf_ask=etf_price + 0.01,
        futures_price=futures_price,
        futures_bid=futures_price - 0.25,
        futures_ask=futures_price + 0.25,
        spread=spread,
        spread_history=spread_history,
        z_score=z_score,
        timestamp=datetime.now(),
        position_side=position,
        position_etf_qty=position_etf_qty,
        position_futures_qty=position_futures_qty,
    )
