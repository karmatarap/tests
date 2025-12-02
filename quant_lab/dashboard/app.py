"""
Quant Lab Dashboard

Streamlit-based dashboard for monitoring strategies, positions, and performance.

Provides:
- Global portfolio overview
- Per-strategy tabs for detailed monitoring
- Position and PnL tracking
- Trade history
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import EXECUTION_MODE, DASHBOARD_CONFIG, STRATEGY_CONFIG

# Import strategy dashboard panels
from dashboard.spread_panel import render_spread_dashboard
from dashboard.funding_panel import render_funding_dashboard
from dashboard.vol_panel import render_vol_dashboard


# Page configuration
st.set_page_config(
    page_title="Quant Lab Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_mock_data():
    """Generate mock data for demonstration."""
    np.random.seed(int(time.time()) % 1000)

    return {
        "portfolio": {
            "total_value": 100000 + np.random.randn() * 1000,
            "cash": 50000 + np.random.randn() * 500,
            "positions_value": 50000 + np.random.randn() * 500,
            "daily_pnl": np.random.randn() * 500,
            "total_pnl": np.random.randn() * 2000,
        },
        "positions": [
            {"symbol": "SPY", "quantity": 100, "avg_cost": 450.0, "current_price": 451.5, "pnl": 150.0},
            {"symbol": "QQQ", "quantity": 50, "avg_cost": 380.0, "current_price": 378.5, "pnl": -75.0},
            {"symbol": "BTC/USDT", "quantity": 0.5, "avg_cost": 45000, "current_price": 45500, "pnl": 250.0},
        ],
        "strategies": {
            "etf_dislocation": {
                "status": "running",
                "signals_today": 3,
                "last_signal": "BUY SPY",
                "pnl": 150.0,
            },
            "funding_harvest": {
                "status": "running",
                "signals_today": 1,
                "last_signal": "SHORT BTC/USDT",
                "pnl": 50.0,
            },
            "vol_of_vol": {
                "status": "paused",
                "signals_today": 0,
                "last_signal": "-",
                "pnl": 0.0,
            },
        },
        "recent_signals": [
            {"time": "14:30:00", "strategy": "ETF Dislocation", "signal": "BUY", "symbol": "SPY", "strength": 0.8},
            {"time": "14:15:00", "strategy": "Funding Harvest", "signal": "SHORT", "symbol": "BTC/USDT", "strength": 0.6},
            {"time": "13:45:00", "strategy": "ETF Dislocation", "signal": "SELL", "symbol": "QQQ", "strength": 0.7},
        ],
        "recent_trades": [
            {"time": "14:30:05", "symbol": "SPY", "side": "BUY", "quantity": 100, "price": 450.0, "status": "FILLED"},
            {"time": "14:15:10", "symbol": "BTC/USDT", "side": "SELL", "quantity": 0.5, "price": 45000, "status": "FILLED"},
        ],
        "market_data": {
            "SPY": {"price": 451.5, "change_pct": 0.3, "fair_value": 451.2},
            "QQQ": {"price": 378.5, "change_pct": -0.2, "fair_value": 379.0},
            "VIX": {"price": 18.5, "change_pct": 5.2},
            "BTC/USDT": {"price": 45500, "funding_rate": 0.0003},
        },
    }


def render_header():
    """Render dashboard header."""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.title("Quant Lab Dashboard")

    with col2:
        mode_color = "green" if EXECUTION_MODE == "paper" else "red"
        st.markdown(f"### Mode: :{mode_color}[{EXECUTION_MODE.upper()}]")

    with col3:
        st.markdown(f"### {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def render_portfolio_summary(data: dict):
    """Render portfolio summary cards."""
    st.subheader("Portfolio Summary")

    col1, col2, col3, col4, col5 = st.columns(5)

    portfolio = data["portfolio"]

    with col1:
        st.metric(
            "Total Value",
            f"${portfolio['total_value']:,.2f}",
            f"${portfolio['daily_pnl']:+,.2f}",
        )

    with col2:
        st.metric("Cash", f"${portfolio['cash']:,.2f}")

    with col3:
        st.metric("Positions Value", f"${portfolio['positions_value']:,.2f}")

    with col4:
        pnl_color = "normal" if portfolio['total_pnl'] >= 0 else "inverse"
        st.metric(
            "Total P&L",
            f"${portfolio['total_pnl']:+,.2f}",
            delta_color=pnl_color,
        )

    with col5:
        return_pct = (portfolio['total_pnl'] / 100000) * 100
        st.metric("Return", f"{return_pct:+.2f}%")


def render_positions(data: dict):
    """Render positions table."""
    st.subheader("Current Positions")

    positions = data["positions"]

    if not positions:
        st.info("No open positions")
        return

    df = pd.DataFrame(positions)
    df["market_value"] = df["quantity"] * df["current_price"]
    df["pnl_pct"] = (df["current_price"] / df["avg_cost"] - 1) * 100

    # Format columns
    df_display = df[["symbol", "quantity", "avg_cost", "current_price", "market_value", "pnl", "pnl_pct"]]
    df_display.columns = ["Symbol", "Qty", "Avg Cost", "Current", "Value", "P&L $", "P&L %"]

    st.dataframe(
        df_display.style.format({
            "Avg Cost": "${:.2f}",
            "Current": "${:.2f}",
            "Value": "${:,.2f}",
            "P&L $": "${:+,.2f}",
            "P&L %": "{:+.2f}%",
        }).applymap(
            lambda x: "color: green" if isinstance(x, (int, float)) and x > 0 else "color: red" if isinstance(x, (int, float)) and x < 0 else "",
            subset=["P&L $", "P&L %"]
        ),
        use_container_width=True,
    )


def render_strategies(data: dict):
    """Render strategy status."""
    st.subheader("Strategy Status")

    strategies = data["strategies"]

    cols = st.columns(len(strategies))

    for i, (name, info) in enumerate(strategies.items()):
        with cols[i]:
            status_icon = "🟢" if info["status"] == "running" else "🟡" if info["status"] == "paused" else "🔴"
            st.markdown(f"### {status_icon} {name.replace('_', ' ').title()}")
            st.write(f"**Signals Today:** {info['signals_today']}")
            st.write(f"**Last Signal:** {info['last_signal']}")
            st.write(f"**P&L:** ${info['pnl']:+,.2f}")


def render_recent_signals(data: dict):
    """Render recent signals table."""
    st.subheader("Recent Signals")

    signals = data["recent_signals"]

    if not signals:
        st.info("No recent signals")
        return

    df = pd.DataFrame(signals)
    df.columns = ["Time", "Strategy", "Signal", "Symbol", "Strength"]

    st.dataframe(
        df.style.format({"Strength": "{:.1%}"}).applymap(
            lambda x: "background-color: #90EE90" if x == "BUY" else "background-color: #FFB6C1" if x == "SELL" else "",
            subset=["Signal"]
        ),
        use_container_width=True,
    )


def render_recent_trades(data: dict):
    """Render recent trades table."""
    st.subheader("Recent Trades")

    trades = data["recent_trades"]

    if not trades:
        st.info("No recent trades")
        return

    df = pd.DataFrame(trades)
    df["value"] = df["quantity"] * df["price"]
    df_display = df[["time", "symbol", "side", "quantity", "price", "value", "status"]]
    df_display.columns = ["Time", "Symbol", "Side", "Qty", "Price", "Value", "Status"]

    st.dataframe(df_display, use_container_width=True)


def render_market_data(data: dict):
    """Render market data."""
    st.subheader("Market Data")

    market = data["market_data"]

    cols = st.columns(len(market))

    for i, (symbol, info) in enumerate(market.items()):
        with cols[i]:
            price = info["price"]
            change = info.get("change_pct", 0)
            change_color = "green" if change >= 0 else "red"

            st.markdown(f"### {symbol}")
            st.markdown(f"**${price:,.2f}** :{change_color}[{change:+.2f}%]")

            if "fair_value" in info:
                dislocation = ((price - info["fair_value"]) / info["fair_value"]) * 100
                st.write(f"Fair Value: ${info['fair_value']:,.2f}")
                st.write(f"Dislocation: {dislocation:+.3f}%")

            if "funding_rate" in info:
                rate_pct = info["funding_rate"] * 100
                ann_rate = rate_pct * 3 * 365
                st.write(f"Funding: {rate_pct:.4f}%")
                st.write(f"Annualized: {ann_rate:.2f}%")


def render_sidebar():
    """Render sidebar controls."""
    st.sidebar.header("Controls")

    # Execution mode indicator
    st.sidebar.markdown(f"**Execution Mode:** {EXECUTION_MODE}")

    st.sidebar.divider()

    # Strategy toggles
    st.sidebar.subheader("Strategies")

    for strategy_name, config in STRATEGY_CONFIG.items():
        enabled = st.sidebar.checkbox(
            strategy_name.replace("_", " ").title(),
            value=config.get("enabled", True),
            key=f"strategy_{strategy_name}",
        )

    st.sidebar.divider()

    # Refresh controls
    st.sidebar.subheader("Refresh")
    auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
    refresh_interval = st.sidebar.slider("Interval (sec)", 1, 60, 5)

    if st.sidebar.button("Manual Refresh"):
        st.rerun()

    st.sidebar.divider()

    # Actions
    st.sidebar.subheader("Actions")

    if st.sidebar.button("Close All Positions"):
        st.sidebar.warning("This would close all positions (not implemented in demo)")

    if st.sidebar.button("Pause All Strategies"):
        st.sidebar.info("Strategies paused (not implemented in demo)")

    return auto_refresh, refresh_interval


def render_overview_tab(data: dict):
    """Render the overview tab with portfolio summary."""
    # Render portfolio summary
    render_portfolio_summary(data)

    st.divider()

    # Two-column layout for positions and strategies
    col1, col2 = st.columns(2)

    with col1:
        render_positions(data)

    with col2:
        render_strategies(data)

    st.divider()

    # Market data
    render_market_data(data)

    st.divider()

    # Two-column layout for signals and trades
    col1, col2 = st.columns(2)

    with col1:
        render_recent_signals(data)

    with col2:
        render_recent_trades(data)


def main():
    """Main dashboard entry point."""
    # Render header
    render_header()

    # Render sidebar and get controls
    auto_refresh, refresh_interval = render_sidebar()

    st.divider()

    # Create tabs for different views
    tab_overview, tab_spread, tab_funding, tab_vol = st.tabs([
        "📊 Overview",
        "📈 ETF-Futures Spread",
        "💰 Crypto Funding",
        "📉 Vol Mean Reversion"
    ])

    # Get data (mock for demo)
    data = get_mock_data()

    with tab_overview:
        render_overview_tab(data)

    with tab_spread:
        try:
            render_spread_dashboard()
        except Exception as e:
            st.error(f"Error loading spread dashboard: {e}")
            st.info("Use --dashboard spread for standalone spread dashboard")

    with tab_funding:
        try:
            render_funding_dashboard()
        except Exception as e:
            st.error(f"Error loading funding dashboard: {e}")
            st.info("Use --dashboard funding for standalone funding dashboard")

    with tab_vol:
        try:
            render_vol_dashboard()
        except Exception as e:
            st.error(f"Error loading vol dashboard: {e}")
            st.info("Use --dashboard vol for standalone vol dashboard")

    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


def run_dashboard():
    """Run the Streamlit dashboard."""
    main()


if __name__ == "__main__":
    main()
