"""Trading strategies for Quant Lab."""

from .base_strategy import BaseStrategy, Signal, SignalType
from .etf_dislocation import ETFDislocationStrategy
from .funding_harvest import FundingHarvestStrategy
from .vol_of_vol import VolOfVolStrategy
from .etf_futures_spread import (
    ETFFuturesSpreadStrategy,
    SpreadPairConfig,
    StrategyConfig,
    MarketState,
    TradeSignal,
    PositionSide,
    generate_etf_dislocation_signal,
    create_market_state,
    DEFAULT_PAIRS,
)

__all__ = [
    "BaseStrategy",
    "Signal",
    "SignalType",
    "ETFDislocationStrategy",
    "FundingHarvestStrategy",
    "VolOfVolStrategy",
    # ETF-Futures Spread Strategy
    "ETFFuturesSpreadStrategy",
    "SpreadPairConfig",
    "StrategyConfig",
    "MarketState",
    "TradeSignal",
    "PositionSide",
    "generate_etf_dislocation_signal",
    "create_market_state",
    "DEFAULT_PAIRS",
]
