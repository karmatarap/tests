"""
Crypto Client Wrapper

Reusable wrapper for cryptocurrency exchanges using CCXT.
Supports Coinbase and Binance for spot prices and funding rates.
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

import ccxt
import pandas as pd

import sys
sys.path.insert(0, '..')
from config import COINBASE_CONFIG, BINANCE_CONFIG

logger = logging.getLogger(__name__)


class CryptoClient:
    """
    Cryptocurrency exchange client wrapper using CCXT.

    Provides methods for:
    - Getting spot prices from Coinbase
    - Getting perpetual funding rates from Binance
    - Fetching historical OHLCV data
    """

    def __init__(self):
        self._coinbase: Optional[ccxt.Exchange] = None
        self._binance: Optional[ccxt.Exchange] = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize exchange connections.

        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize Coinbase
            self._coinbase = ccxt.coinbase({
                "apiKey": COINBASE_CONFIG["api_key"],
                "secret": COINBASE_CONFIG["api_secret"],
                "sandbox": COINBASE_CONFIG["sandbox"],
                "enableRateLimit": True,
            })

            # Initialize Binance (futures for funding rates)
            self._binance = ccxt.binance({
                "apiKey": BINANCE_CONFIG["api_key"],
                "secret": BINANCE_CONFIG["api_secret"],
                "sandbox": BINANCE_CONFIG["sandbox"],
                "enableRateLimit": True,
                "options": BINANCE_CONFIG["options"],
            })

            self._initialized = True
            logger.info("Crypto exchanges initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize crypto exchanges: {e}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if exchanges are initialized."""
        return self._initialized

    def get_coinbase_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current ticker from Coinbase.

        Args:
            symbol: Trading pair (e.g., "BTC/USD")

        Returns:
            Dictionary with ticker data
        """
        if not self._coinbase:
            logger.error("Coinbase not initialized")
            return None

        try:
            ticker = self._coinbase.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "last": ticker.get("last"),
                "volume": ticker.get("baseVolume"),
                "high": ticker.get("high"),
                "low": ticker.get("low"),
                "change_pct": ticker.get("percentage"),
                "timestamp": datetime.fromtimestamp(ticker["timestamp"] / 1000)
                    if ticker.get("timestamp") else datetime.now(),
                "exchange": "coinbase",
            }
        except Exception as e:
            logger.error(f"Error getting Coinbase ticker for {symbol}: {e}")
            return None

    def get_binance_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current ticker from Binance Futures.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")

        Returns:
            Dictionary with ticker data
        """
        if not self._binance:
            logger.error("Binance not initialized")
            return None

        try:
            ticker = self._binance.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "last": ticker.get("last"),
                "volume": ticker.get("baseVolume"),
                "high": ticker.get("high"),
                "low": ticker.get("low"),
                "change_pct": ticker.get("percentage"),
                "timestamp": datetime.fromtimestamp(ticker["timestamp"] / 1000)
                    if ticker.get("timestamp") else datetime.now(),
                "exchange": "binance",
            }
        except Exception as e:
            logger.error(f"Error getting Binance ticker for {symbol}: {e}")
            return None

    def get_funding_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current funding rate from Binance perpetual futures.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")

        Returns:
            Dictionary with funding rate data
        """
        if not self._binance:
            logger.error("Binance not initialized")
            return None

        try:
            # Fetch funding rate
            funding_info = self._binance.fetch_funding_rate(symbol)

            return {
                "symbol": symbol,
                "funding_rate": funding_info.get("fundingRate"),
                "funding_rate_pct": funding_info.get("fundingRate", 0) * 100,
                "next_funding_time": funding_info.get("fundingTimestamp"),
                "mark_price": funding_info.get("markPrice"),
                "index_price": funding_info.get("indexPrice"),
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error getting funding rate for {symbol}: {e}")
            return None

    def get_funding_rates_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get funding rates for multiple symbols.

        Args:
            symbols: List of trading pairs

        Returns:
            Dictionary mapping symbols to funding rate data
        """
        results = {}
        for symbol in symbols:
            rate = self.get_funding_rate(symbol)
            if rate:
                results[symbol] = rate
        return results

    def get_historical_funding_rates(self, symbol: str,
                                     limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get historical funding rates from Binance.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            limit: Number of records to fetch

        Returns:
            DataFrame with historical funding rates
        """
        if not self._binance:
            logger.error("Binance not initialized")
            return None

        try:
            # Binance-specific funding rate history
            funding_history = self._binance.fetch_funding_rate_history(
                symbol,
                limit=limit,
            )

            if not funding_history:
                return None

            df = pd.DataFrame(funding_history)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error getting funding rate history for {symbol}: {e}")
            return None

    def get_ohlcv(self, exchange: str, symbol: str,
                  timeframe: str = "1h",
                  limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Get OHLCV candlestick data.

        Args:
            exchange: "coinbase" or "binance"
            symbol: Trading pair
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles

        Returns:
            DataFrame with OHLCV data
        """
        try:
            if exchange == "coinbase":
                client = self._coinbase
            elif exchange == "binance":
                client = self._binance
            else:
                logger.error(f"Unknown exchange: {exchange}")
                return None

            if not client:
                logger.error(f"{exchange} not initialized")
                return None

            ohlcv = client.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not ohlcv:
                return None

            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error getting OHLCV for {symbol} on {exchange}: {e}")
            return None

    def get_order_book(self, exchange: str, symbol: str,
                       limit: int = 20) -> Optional[Dict[str, Any]]:
        """
        Get order book data.

        Args:
            exchange: "coinbase" or "binance"
            symbol: Trading pair
            limit: Depth of order book

        Returns:
            Dictionary with bids and asks
        """
        try:
            if exchange == "coinbase":
                client = self._coinbase
            elif exchange == "binance":
                client = self._binance
            else:
                logger.error(f"Unknown exchange: {exchange}")
                return None

            if not client:
                logger.error(f"{exchange} not initialized")
                return None

            order_book = client.fetch_order_book(symbol, limit)

            return {
                "symbol": symbol,
                "exchange": exchange,
                "bids": order_book["bids"][:limit],
                "asks": order_book["asks"][:limit],
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting order book for {symbol} on {exchange}: {e}")
            return None

    def get_balance(self, exchange: str) -> Optional[Dict[str, Any]]:
        """
        Get account balance.

        Args:
            exchange: "coinbase" or "binance"

        Returns:
            Dictionary with balances by currency
        """
        try:
            if exchange == "coinbase":
                client = self._coinbase
            elif exchange == "binance":
                client = self._binance
            else:
                logger.error(f"Unknown exchange: {exchange}")
                return None

            if not client:
                logger.error(f"{exchange} not initialized")
                return None

            balance = client.fetch_balance()

            return {
                "total": balance.get("total", {}),
                "free": balance.get("free", {}),
                "used": balance.get("used", {}),
                "exchange": exchange,
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting balance from {exchange}: {e}")
            return None

    def get_open_positions(self, exchange: str = "binance") -> List[Dict[str, Any]]:
        """
        Get open positions from futures exchange.

        Args:
            exchange: Exchange name (primarily binance for futures)

        Returns:
            List of position dictionaries
        """
        if exchange != "binance":
            logger.warning(f"Positions only supported for binance futures")
            return []

        if not self._binance:
            logger.error("Binance not initialized")
            return []

        try:
            positions = self._binance.fetch_positions()

            result = []
            for pos in positions:
                if float(pos.get("contracts", 0)) != 0:
                    result.append({
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),
                        "contracts": pos.get("contracts"),
                        "entry_price": pos.get("entryPrice"),
                        "mark_price": pos.get("markPrice"),
                        "unrealized_pnl": pos.get("unrealizedPnl"),
                        "leverage": pos.get("leverage"),
                    })
            return result

        except Exception as e:
            logger.error(f"Error getting positions from {exchange}: {e}")
            return []

    def get_funding_info_detailed(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed funding information including next funding time.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")

        Returns:
            Dictionary with detailed funding info
        """
        if not self._binance:
            logger.error("Binance not initialized")
            return None

        try:
            # Get current funding rate
            funding = self._binance.fetch_funding_rate(symbol)

            # Get ticker for mark price
            ticker = self._binance.fetch_ticker(symbol)

            # Calculate time to next funding
            next_funding_ts = funding.get("fundingTimestamp")
            time_to_funding = None
            if next_funding_ts:
                next_funding_dt = datetime.fromtimestamp(next_funding_ts / 1000)
                time_to_funding = (next_funding_dt - datetime.now()).total_seconds()

            funding_rate = funding.get("fundingRate", 0)

            return {
                "symbol": symbol,
                "funding_rate": funding_rate,
                "funding_rate_pct": funding_rate * 100,
                "funding_rate_8h_pct": funding_rate * 100,  # Already 8h rate
                "annualized_rate_pct": funding_rate * 100 * 3 * 365,  # 3 fundings/day * 365
                "next_funding_time": datetime.fromtimestamp(next_funding_ts / 1000) if next_funding_ts else None,
                "time_to_funding_seconds": time_to_funding,
                "mark_price": funding.get("markPrice") or ticker.get("last"),
                "index_price": funding.get("indexPrice"),
                "last_price": ticker.get("last"),
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting detailed funding info for {symbol}: {e}")
            return None

    def get_spot_and_perp_prices(self, asset: str) -> Optional[Dict[str, Any]]:
        """
        Get both spot (Coinbase) and perp (Binance) prices for an asset.

        Args:
            asset: Asset symbol (e.g., "BTC" or "ETH")

        Returns:
            Dictionary with spot and perp prices
        """
        spot_symbol = f"{asset}/USD"
        perp_symbol = f"{asset}/USDT"

        try:
            spot_ticker = self.get_coinbase_ticker(spot_symbol)
            perp_ticker = self.get_binance_ticker(perp_symbol)
            funding_info = self.get_funding_info_detailed(perp_symbol)

            if not spot_ticker and not perp_ticker:
                return None

            spot_price = spot_ticker.get("last") if spot_ticker else None
            perp_price = perp_ticker.get("last") if perp_ticker else None

            # Calculate basis (perp premium/discount to spot)
            basis = None
            basis_pct = None
            if spot_price and perp_price:
                basis = perp_price - spot_price
                basis_pct = (basis / spot_price) * 100

            return {
                "asset": asset,
                "spot_symbol": spot_symbol,
                "perp_symbol": perp_symbol,
                "spot_price": spot_price,
                "perp_price": perp_price,
                "mark_price": funding_info.get("mark_price") if funding_info else None,
                "basis": basis,
                "basis_pct": basis_pct,
                "funding_rate": funding_info.get("funding_rate") if funding_info else None,
                "funding_rate_pct": funding_info.get("funding_rate_pct") if funding_info else None,
                "annualized_funding_pct": funding_info.get("annualized_rate_pct") if funding_info else None,
                "next_funding_time": funding_info.get("next_funding_time") if funding_info else None,
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting spot and perp prices for {asset}: {e}")
            return None

    def close(self):
        """Close exchange connections."""
        self._coinbase = None
        self._binance = None
        self._initialized = False
        logger.info("Crypto exchanges closed")

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
