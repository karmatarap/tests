"""
Quant Lab Configuration

Central configuration for execution mode, API credentials, and symbol settings.
"""

import os
from typing import Literal

# =============================================================================
# EXECUTION MODE
# =============================================================================
# "paper" -> paper_executor only records hypothetical trades
# "live"  -> IBKR / Coinbase executors actually send orders
EXECUTION_MODE: Literal["paper", "live"] = os.getenv("EXECUTION_MODE", "paper")

# =============================================================================
# IBKR Configuration
# =============================================================================
IBKR_CONFIG = {
    "host": os.getenv("IBKR_HOST", "127.0.0.1"),
    "port": int(os.getenv("IBKR_PORT", "7497")),  # 7497 for TWS paper, 7496 for live
    "client_id": int(os.getenv("IBKR_CLIENT_ID", "1")),
    "timeout": int(os.getenv("IBKR_TIMEOUT", "30")),
    "readonly": EXECUTION_MODE == "paper",  # Read-only in paper mode
}

# =============================================================================
# Crypto Exchange Configuration (CCXT)
# =============================================================================
COINBASE_CONFIG = {
    "api_key": os.getenv("COINBASE_API_KEY", ""),
    "api_secret": os.getenv("COINBASE_API_SECRET", ""),
    "sandbox": EXECUTION_MODE == "paper",
}

BINANCE_CONFIG = {
    "api_key": os.getenv("BINANCE_API_KEY", ""),
    "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    "sandbox": EXECUTION_MODE == "paper",
    "options": {
        "defaultType": "future",  # For funding rates
    },
}

# =============================================================================
# Symbol Configuration
# =============================================================================
# ETF Dislocation Strategy Symbols
ETF_SYMBOLS = {
    "SPY": {"underlying": "SPY", "type": "ETF"},
    "QQQ": {"underlying": "QQQ", "type": "ETF"},
    "IWM": {"underlying": "IWM", "type": "ETF"},
    "DIA": {"underlying": "DIA", "type": "ETF"},
}

# Crypto Symbols for Funding Harvest
CRYPTO_SYMBOLS = {
    "BTC/USDT": {"exchange": "binance", "type": "perpetual"},
    "ETH/USDT": {"exchange": "binance", "type": "perpetual"},
    "BTC/USD": {"exchange": "coinbase", "type": "spot"},
    "ETH/USD": {"exchange": "coinbase", "type": "spot"},
}

# Vol of Vol Strategy Symbols
VOL_SYMBOLS = {
    "VIX": {"underlying": "VIX", "type": "index"},
    "UVXY": {"underlying": "UVXY", "type": "ETF"},
    "SVXY": {"underlying": "SVXY", "type": "ETF"},
}

# =============================================================================
# Strategy Configuration
# =============================================================================
STRATEGY_CONFIG = {
    "etf_dislocation": {
        "enabled": True,
        "schedule_interval_seconds": 60,
        "dislocation_threshold_pct": 0.1,  # 0.1% dislocation threshold
        "max_position_size": 100,  # shares
    },
    "funding_harvest": {
        "enabled": True,
        "schedule_interval_seconds": 300,  # 5 minutes
        "min_funding_rate_pct": 0.01,  # Minimum 0.01% funding rate
        "max_position_size_usd": 10000,
    },
    "vol_of_vol": {
        "enabled": True,
        "schedule_interval_seconds": 60,
        "vol_spike_threshold": 2.0,  # 2 std devs
        "lookback_periods": 20,
    },
}

# =============================================================================
# ETF-Futures Spread Strategy Configuration
# =============================================================================
ETF_FUTURES_SPREAD_CONFIG = {
    "enabled": True,

    # Z-score thresholds for entry/exit
    "z_entry": float(os.getenv("SPREAD_Z_ENTRY", "2.0")),  # Enter when |z| > z_entry
    "z_exit": float(os.getenv("SPREAD_Z_EXIT", "0.5")),    # Exit when |z| < z_exit
    "stop_loss_z": float(os.getenv("SPREAD_STOP_LOSS_Z", "4.0")),  # Emergency stop

    # Lookback for z-score calculation
    "lookback_minutes": int(os.getenv("SPREAD_LOOKBACK", "60")),

    # Position sizing
    "notional_per_leg_usd": float(os.getenv("SPREAD_NOTIONAL", "5000.0")),
    "max_position_pct": 0.01,  # Max 1% of portfolio per position

    # Execution
    "update_interval_seconds": int(os.getenv("SPREAD_UPDATE_INTERVAL", "60")),

    # Risk limits
    "max_daily_trades": 20,
    "max_holding_minutes": 240,  # 4 hours max holding

    # Active pairs
    "pairs": {
        "SPY_ES": {
            "enabled": True,
            "etf_symbol": "SPY",
            "futures_symbol": "ES",
            "futures_exchange": "CME",
            "futures_multiplier": 50.0,
            "scaling_factor": 0.1,  # SPY ~= ES / 10
            "etf_shares_per_future": 500,
        },
        "QQQ_NQ": {
            "enabled": True,
            "etf_symbol": "QQQ",
            "futures_symbol": "NQ",
            "futures_exchange": "CME",
            "futures_multiplier": 20.0,
            "scaling_factor": 0.025,  # QQQ ~= NQ / 40
            "etf_shares_per_future": 400,
        },
        "IWM_RTY": {
            "enabled": False,  # Disabled by default
            "etf_symbol": "IWM",
            "futures_symbol": "RTY",
            "futures_exchange": "CME",
            "futures_multiplier": 50.0,
            "scaling_factor": 0.5,
            "etf_shares_per_future": 500,
        },
    },
}

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": os.getenv("LOG_FILE", "quant_lab.log"),
}

# =============================================================================
# Dashboard Configuration
# =============================================================================
DASHBOARD_CONFIG = {
    "host": os.getenv("DASHBOARD_HOST", "0.0.0.0"),
    "port": int(os.getenv("DASHBOARD_PORT", "8501")),
    "refresh_interval_seconds": 5,
}

# =============================================================================
# Risk Management
# =============================================================================
RISK_CONFIG = {
    "max_daily_loss_pct": 2.0,  # Stop trading if daily loss exceeds 2%
    "max_position_value_pct": 10.0,  # Max 10% of portfolio in single position
    "max_total_exposure_pct": 100.0,  # Max 100% gross exposure
}


def get_executor_class():
    """Returns the appropriate executor class based on EXECUTION_MODE."""
    if EXECUTION_MODE == "paper":
        from execution.paper_executor import PaperExecutor
        return PaperExecutor
    else:
        # In live mode, return a router that selects the right executor
        return None  # Will be handled by execution router


def validate_config():
    """Validate configuration settings."""
    errors = []

    if EXECUTION_MODE not in ("paper", "live"):
        errors.append(f"Invalid EXECUTION_MODE: {EXECUTION_MODE}")

    if EXECUTION_MODE == "live":
        if not COINBASE_CONFIG["api_key"]:
            errors.append("COINBASE_API_KEY required for live trading")
        if not BINANCE_CONFIG["api_key"]:
            errors.append("BINANCE_API_KEY required for live trading")

    if errors:
        raise ValueError(f"Configuration errors: {errors}")

    return True
