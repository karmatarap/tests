"""
IBKR Client Wrapper

Reusable wrapper for Interactive Brokers API using ib_insync.
Provides market data, historical data, and account information.
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

import pandas as pd
from ib_insync import IB, Stock, Option, Future, Contract, util

import sys
sys.path.insert(0, '..')
from config import IBKR_CONFIG

logger = logging.getLogger(__name__)


class IBKRClient:
    """
    Interactive Brokers client wrapper using ib_insync.

    Provides methods for:
    - Connecting/disconnecting
    - Getting live quotes
    - Fetching historical data
    - Account/portfolio information
    """

    def __init__(self):
        self.ib = IB()
        self._connected = False
        self._subscriptions: Dict[str, Contract] = {}

    @property
    def is_connected(self) -> bool:
        """Check if connected to IBKR."""
        return self._connected and self.ib.isConnected()

    def connect(self) -> bool:
        """
        Connect to IBKR TWS or Gateway.

        Returns:
            bool: True if connection successful
        """
        if self.is_connected:
            logger.info("Already connected to IBKR")
            return True

        try:
            self.ib.connect(
                host=IBKR_CONFIG["host"],
                port=IBKR_CONFIG["port"],
                clientId=IBKR_CONFIG["client_id"],
                timeout=IBKR_CONFIG["timeout"],
                readonly=IBKR_CONFIG["readonly"],
            )
            self._connected = True
            logger.info(f"Connected to IBKR at {IBKR_CONFIG['host']}:{IBKR_CONFIG['port']}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IBKR: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from IBKR."""
        if self.ib.isConnected():
            self.ib.disconnect()
        self._connected = False
        logger.info("Disconnected from IBKR")

    def create_stock_contract(self, symbol: str, exchange: str = "SMART",
                              currency: str = "USD") -> Stock:
        """Create a stock contract."""
        return Stock(symbol, exchange, currency)

    def create_option_contract(self, symbol: str, expiry: str, strike: float,
                               right: str, exchange: str = "SMART",
                               currency: str = "USD") -> Option:
        """
        Create an option contract.

        Args:
            symbol: Underlying symbol
            expiry: Expiration date (YYYYMMDD format)
            strike: Strike price
            right: 'C' for call, 'P' for put
            exchange: Exchange (default SMART)
            currency: Currency (default USD)
        """
        return Option(symbol, expiry, strike, right, exchange, currency=currency)

    def create_future_contract(self, symbol: str, exchange: str = "CME",
                               currency: str = "USD",
                               expiry: str = "") -> Future:
        """
        Create a futures contract.

        Args:
            symbol: Futures symbol (e.g., "ES", "NQ", "RTY")
            exchange: Exchange (default CME for E-mini futures)
            currency: Currency (default USD)
            expiry: Optional expiry (YYYYMM format). If empty, uses front month.

        Returns:
            Future contract object
        """
        if expiry:
            return Future(symbol, expiry, exchange, currency=currency)
        else:
            # Create continuous/front-month contract
            return Future(symbol, exchange=exchange, currency=currency)

    def create_index_contract(self, symbol: str, exchange: str = "CBOE",
                              currency: str = "USD") -> Contract:
        """
        Create an index contract.

        Args:
            symbol: Index symbol (e.g., "SPX", "NDX", "VIX")
            exchange: Exchange (default CBOE)
            currency: Currency (default USD)

        Returns:
            Index contract object
        """
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "IND"
        contract.exchange = exchange
        contract.currency = currency
        return contract

    def get_front_month_future(self, symbol: str, exchange: str = "CME") -> Optional[Future]:
        """
        Get the front-month futures contract for a symbol.

        Args:
            symbol: Futures symbol (e.g., "ES", "NQ")
            exchange: Exchange

        Returns:
            Front-month Future contract
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            # Create a generic future and let IBKR resolve to front month
            future = Future(symbol, exchange=exchange)
            qualified = self.ib.qualifyContracts(future)
            if qualified:
                return qualified[0]
            return None
        except Exception as e:
            logger.error(f"Error getting front month future for {symbol}: {e}")
            return None

    def get_contract_details(self, contract: Contract) -> Optional[Dict[str, Any]]:
        """
        Get detailed contract information.

        Args:
            contract: IBKR contract object

        Returns:
            Dictionary with contract details
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            details = self.ib.reqContractDetails(contract)
            if details:
                d = details[0]
                return {
                    "symbol": d.contract.symbol,
                    "sec_type": d.contract.secType,
                    "exchange": d.contract.exchange,
                    "currency": d.contract.currency,
                    "local_symbol": d.contract.localSymbol,
                    "multiplier": float(d.contract.multiplier) if d.contract.multiplier else 1,
                    "min_tick": d.minTick,
                    "trading_hours": d.tradingHours,
                    "liquid_hours": d.liquidHours,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting contract details: {e}")
            return None

    def get_quote(self, contract: Contract) -> Optional[Dict[str, Any]]:
        """
        Get current quote for a contract.

        Args:
            contract: IBKR contract object

        Returns:
            Dictionary with bid, ask, last, volume, etc.
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract, snapshot=True)
            self.ib.sleep(2)  # Wait for data

            return {
                "symbol": contract.symbol,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last": ticker.last,
                "volume": ticker.volume,
                "high": ticker.high,
                "low": ticker.low,
                "close": ticker.close,
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error getting quote for {contract.symbol}: {e}")
            return None

    def get_quotes_batch(self, contracts: List[Contract]) -> Dict[str, Dict[str, Any]]:
        """
        Get quotes for multiple contracts.

        Args:
            contracts: List of IBKR contract objects

        Returns:
            Dictionary mapping symbols to quote data
        """
        results = {}
        for contract in contracts:
            quote = self.get_quote(contract)
            if quote:
                results[contract.symbol] = quote
        return results

    def get_historical_data(self, contract: Contract, duration: str = "1 D",
                           bar_size: str = "1 min",
                           what_to_show: str = "TRADES") -> Optional[pd.DataFrame]:
        """
        Get historical bar data.

        Args:
            contract: IBKR contract object
            duration: Time span (e.g., "1 D", "1 W", "1 M")
            bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour", "1 day")
            what_to_show: Data type (TRADES, MIDPOINT, BID, ASK)

        Returns:
            DataFrame with OHLCV data
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            self.ib.qualifyContracts(contract)
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=True,
                formatDate=1,
            )

            if not bars:
                return None

            df = util.df(bars)
            df.set_index("date", inplace=True)
            return df

        except Exception as e:
            logger.error(f"Error getting historical data for {contract.symbol}: {e}")
            return None

    def subscribe_market_data(self, contract: Contract,
                              callback: callable) -> Optional[str]:
        """
        Subscribe to streaming market data.

        Args:
            contract: IBKR contract object
            callback: Function to call on data updates

        Returns:
            Subscription ID
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            self.ib.qualifyContracts(contract)
            ticker = self.ib.reqMktData(contract)
            ticker.updateEvent += callback

            sub_id = f"{contract.symbol}_{contract.secType}"
            self._subscriptions[sub_id] = contract

            logger.info(f"Subscribed to market data for {contract.symbol}")
            return sub_id

        except Exception as e:
            logger.error(f"Error subscribing to {contract.symbol}: {e}")
            return None

    def unsubscribe_market_data(self, sub_id: str):
        """Unsubscribe from market data."""
        if sub_id in self._subscriptions:
            contract = self._subscriptions[sub_id]
            self.ib.cancelMktData(contract)
            del self._subscriptions[sub_id]
            logger.info(f"Unsubscribed from {sub_id}")

    def get_account_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get account summary.

        Returns:
            Dictionary with account values (NetLiquidation, TotalCashValue, etc.)
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return None

        try:
            account_values = self.ib.accountSummary()

            summary = {}
            for av in account_values:
                summary[av.tag] = {
                    "value": float(av.value) if av.value else 0,
                    "currency": av.currency,
                }
            return summary

        except Exception as e:
            logger.error(f"Error getting account summary: {e}")
            return None

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return []

        try:
            positions = self.ib.positions()

            result = []
            for pos in positions:
                result.append({
                    "symbol": pos.contract.symbol,
                    "sec_type": pos.contract.secType,
                    "position": pos.position,
                    "avg_cost": pos.avgCost,
                    "market_value": pos.position * pos.avgCost,
                })
            return result

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders."""
        if not self.is_connected:
            logger.error("Not connected to IBKR")
            return []

        try:
            orders = self.ib.openOrders()

            result = []
            for order in orders:
                result.append({
                    "order_id": order.orderId,
                    "symbol": order.contract.symbol if hasattr(order, 'contract') else None,
                    "action": order.action,
                    "quantity": order.totalQuantity,
                    "order_type": order.orderType,
                    "limit_price": order.lmtPrice,
                    "status": order.status if hasattr(order, 'status') else None,
                })
            return result

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
