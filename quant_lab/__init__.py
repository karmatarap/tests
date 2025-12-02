"""
Quant Lab - Quantitative Trading Framework

A Python framework for:
- Pulling live data from IBKR and crypto exchanges
- Running strategy logic on a schedule
- Web dashboard via Streamlit
- Paper and live execution modes
"""

__version__ = "0.1.0"

from .config import EXECUTION_MODE, validate_config

__all__ = ["EXECUTION_MODE", "validate_config"]
