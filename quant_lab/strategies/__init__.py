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
from .crypto_funding_harvest import (
    CryptoFundingHarvestStrategy,
    FundingHarvestConfig,
    MarketState as FundingMarketState,
    FundingSignal,
    CarryPosition,
    PositionType,
    generate_funding_harvest_signal,
)
from .funding_runner import FundingHarvestRunner
from .vol_mean_reversion import (
    VolMeanReversionStrategy,
    VolMeanReversionConfig,
    VolMarketState,
    VolSignal,
    VolPosition,
    generate_vol_of_vol_signal,
    create_vol_market_state,
)
from .vol_runner import VolMeanReversionRunner

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
    # Crypto Funding Harvest Strategy
    "CryptoFundingHarvestStrategy",
    "FundingHarvestConfig",
    "FundingMarketState",
    "FundingSignal",
    "CarryPosition",
    "PositionType",
    "generate_funding_harvest_signal",
    "FundingHarvestRunner",
    # Vol Mean Reversion Strategy
    "VolMeanReversionStrategy",
    "VolMeanReversionConfig",
    "VolMarketState",
    "VolSignal",
    "VolPosition",
    "generate_vol_of_vol_signal",
    "create_vol_market_state",
    "VolMeanReversionRunner",
]
