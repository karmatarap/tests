"""
Crypto Funding Harvest Dashboard Panel

Streamlit dashboard component for the funding harvest strategy.
Displays:
- Current funding rates (BTC, ETH) with colour-coded thresholds
- Current simulated position, accrued funding, net PnL
- Buttons: "Open Simulated Trade", "Close Simulated Trade"
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

from config import EXECUTION_MODE


def generate_mock_funding_data() -> dict:
    """Generate mock funding data for demonstration."""
    np.random.seed(int(time.time()) % 1000)

    def mock_asset(asset: str, base_price: float) -> dict:
        spot_price = base_price + np.random.randn() * 50
        perp_price = spot_price + np.random.randn() * 10

        # Occasionally generate extreme funding
        if np.random.random() < 0.3:
            funding_pct = np.random.choice([-1, 1]) * np.random.uniform(0.08, 0.25)
        else:
            funding_pct = np.random.uniform(-0.05, 0.05)

        return {
            "asset": asset,
            "spot_price": spot_price,
            "perp_price": perp_price,
            "funding_rate_pct": funding_pct,
            "annualized_pct": funding_pct * 3 * 365,
            "basis_pct": ((perp_price - spot_price) / spot_price) * 100,
            "next_funding": datetime.now() + timedelta(hours=np.random.uniform(0.5, 8)),
        }

    return {
        "BTC": mock_asset("BTC", 45000),
        "ETH": mock_asset("ETH", 2500),
    }


def generate_mock_positions() -> dict:
    """Generate mock positions for demonstration."""
    np.random.seed(42)

    if np.random.random() < 0.4:
        return {
            "BTC": {
                "asset": "BTC",
                "position_type": "LONG_CARRY",
                "notional_usd": 5000,
                "entry_time": (datetime.now() - timedelta(hours=np.random.uniform(1, 48))).isoformat(),
                "entry_spot_price": 44500,
                "entry_perp_price": 44550,
                "spot_quantity": 0.112,
                "perp_quantity": 0.112,
                "accrued_funding_usd": np.random.uniform(5, 50),
                "funding_payments": np.random.randint(1, 10),
                "spot_pnl_usd": np.random.uniform(-100, 200),
                "perp_pnl_usd": np.random.uniform(-100, 200),
                "total_pnl_usd": np.random.uniform(-50, 150),
                "holding_hours": np.random.uniform(1, 48),
            }
        }
    return {}


def get_funding_color(funding_pct: float, threshold: float = 0.10) -> str:
    """Get color based on funding rate magnitude."""
    if abs(funding_pct) >= threshold:
        return "green" if funding_pct > 0 else "red"
    elif abs(funding_pct) >= threshold / 2:
        return "orange"
    else:
        return "gray"


def render_funding_rates(data: dict):
    """Render current funding rates with color coding."""
    st.subheader("Current Funding Rates")

    cols = st.columns(len(data))

    for i, (asset, info) in enumerate(data.items()):
        with cols[i]:
            funding_pct = info["funding_rate_pct"]
            annualized = info["annualized_pct"]
            color = get_funding_color(funding_pct)

            st.markdown(f"### {asset}")

            # Funding rate with color
            if funding_pct >= 0.10:
                st.markdown(f"**Funding:** :green[**{funding_pct:+.4f}%**] (8h)")
                st.success(f"High positive - collect by shorting perp!")
            elif funding_pct <= -0.10:
                st.markdown(f"**Funding:** :red[**{funding_pct:+.4f}%**] (8h)")
                st.error(f"High negative - collect by longing perp!")
            elif abs(funding_pct) >= 0.05:
                st.markdown(f"**Funding:** :orange[**{funding_pct:+.4f}%**] (8h)")
            else:
                st.markdown(f"**Funding:** {funding_pct:+.4f}% (8h)")

            # Annualized
            ann_color = "green" if annualized > 20 else "red" if annualized < -20 else "gray"
            st.markdown(f"**Annualized:** :{ann_color}[{annualized:+.1f}%]")

            # Prices
            st.write(f"**Spot:** ${info['spot_price']:,.2f}")
            st.write(f"**Perp:** ${info['perp_price']:,.2f}")
            st.write(f"**Basis:** {info['basis_pct']:+.3f}%")

            # Next funding
            next_funding = info["next_funding"]
            time_to = (next_funding - datetime.now()).total_seconds() / 3600
            st.write(f"**Next funding:** {time_to:.1f}h")


def render_positions(positions: dict, market_data: dict):
    """Render current positions."""
    st.subheader("Current Positions")

    if not positions:
        st.info("No open positions")
        return

    for asset, pos in positions.items():
        with st.expander(f"📊 {asset} - {pos['position_type']}", expanded=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Entry**")
                st.write(f"Notional: ${pos['notional_usd']:,.0f}")
                st.write(f"Spot: ${pos['entry_spot_price']:,.2f}")
                st.write(f"Perp: ${pos['entry_perp_price']:,.2f}")
                st.write(f"Qty: {pos['spot_quantity']:.6f}")

            with col2:
                st.markdown("**Current**")
                current = market_data.get(asset, {})
                st.write(f"Spot: ${current.get('spot_price', 0):,.2f}")
                st.write(f"Perp: ${current.get('perp_price', 0):,.2f}")
                st.write(f"Holding: {pos['holding_hours']:.1f}h")
                st.write(f"Fundings: {pos['funding_payments']}")

            with col3:
                st.markdown("**P&L**")
                funding_pnl = pos['accrued_funding_usd']
                spot_pnl = pos.get('spot_pnl_usd', 0)
                perp_pnl = pos.get('perp_pnl_usd', 0)
                total_pnl = pos.get('total_pnl_usd', funding_pnl + spot_pnl + perp_pnl)

                funding_color = "green" if funding_pnl >= 0 else "red"
                total_color = "green" if total_pnl >= 0 else "red"

                st.markdown(f"Funding: :{funding_color}[${funding_pnl:+.2f}]")
                st.write(f"Spot: ${spot_pnl:+.2f}")
                st.write(f"Perp: ${perp_pnl:+.2f}")
                st.markdown(f"**Total:** :{total_color}[**${total_pnl:+.2f}**]")


def render_trade_buttons(positions: dict, market_data: dict, on_trade_callback=None):
    """Render trade action buttons."""
    st.subheader("Trade Actions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**BTC**")
        btc_has_pos = "BTC" in positions
        btc_funding = market_data.get("BTC", {}).get("funding_rate_pct", 0)

        if not btc_has_pos:
            if st.button("📈 Open BTC", key="open_btc",
                        help="Open BTC carry position"):
                st.success("Opened simulated BTC carry position")
                if on_trade_callback:
                    on_trade_callback("OPEN", "BTC")
        else:
            st.button("📈 Open BTC", key="open_btc", disabled=True)

        if btc_has_pos:
            if st.button("📉 Close BTC", key="close_btc",
                        help="Close BTC carry position"):
                st.warning("Closed BTC position")
                if on_trade_callback:
                    on_trade_callback("CLOSE", "BTC")
        else:
            st.button("📉 Close BTC", key="close_btc", disabled=True)

    with col2:
        st.markdown("**ETH**")
        eth_has_pos = "ETH" in positions
        eth_funding = market_data.get("ETH", {}).get("funding_rate_pct", 0)

        if not eth_has_pos:
            if st.button("📈 Open ETH", key="open_eth",
                        help="Open ETH carry position"):
                st.success("Opened simulated ETH carry position")
                if on_trade_callback:
                    on_trade_callback("OPEN", "ETH")
        else:
            st.button("📈 Open ETH", key="open_eth", disabled=True)

        if eth_has_pos:
            if st.button("📉 Close ETH", key="close_eth",
                        help="Close ETH carry position"):
                st.warning("Closed ETH position")
                if on_trade_callback:
                    on_trade_callback("CLOSE", "ETH")
        else:
            st.button("📉 Close ETH", key="close_eth", disabled=True)

    with col3:
        st.markdown("**All Positions**")
        if positions:
            if st.button("🔄 Close All", key="close_all", type="secondary"):
                st.warning("Closed all positions")
        else:
            st.button("🔄 Close All", key="close_all", disabled=True)

    with col4:
        st.markdown("**Mode**")
        if EXECUTION_MODE == "live":
            st.error("⚡ LIVE MODE")
            st.caption("Spot trades will execute on Coinbase")
        else:
            st.info("🔒 Paper Mode")
            st.caption("All trades simulated")


def render_funding_history(history: list):
    """Render funding rate history chart."""
    st.subheader("Funding Rate History")

    if not history:
        # Generate mock history
        timestamps = [datetime.now() - timedelta(hours=i*8) for i in range(20, 0, -1)]
        btc_rates = [np.random.uniform(-0.05, 0.15) for _ in timestamps]
        eth_rates = [np.random.uniform(-0.05, 0.15) for _ in timestamps]

        df = pd.DataFrame({
            "Time": timestamps,
            "BTC": btc_rates,
            "ETH": eth_rates,
        })
        df.set_index("Time", inplace=True)
    else:
        df = pd.DataFrame(history)

    # Add threshold lines
    df["Upper Threshold"] = 0.10
    df["Lower Threshold"] = -0.10
    df["Zero"] = 0.0

    st.line_chart(df, use_container_width=True)
    st.caption("Funding rates (%) - 8-hour settlements")


def render_strategy_stats(stats: dict):
    """Render strategy statistics."""
    st.subheader("Strategy Statistics")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Open Positions", stats.get("open_positions", 0))

    with col2:
        st.metric("Closed Trades", stats.get("closed_positions", 0))

    with col3:
        total_funding = stats.get("total_funding_earned", 0)
        st.metric("Funding Earned", f"${total_funding:,.2f}")

    with col4:
        total_pnl = stats.get("total_pnl", 0)
        st.metric("Total P&L", f"${total_pnl:+,.2f}",
                 delta_color="normal" if total_pnl >= 0 else "inverse")


def render_config_sidebar():
    """Render strategy configuration sidebar."""
    st.sidebar.subheader("Funding Harvest Config")

    entry_threshold = st.sidebar.slider("Entry Threshold (%)", 0.05, 0.30, 0.10, 0.01)
    exit_threshold = st.sidebar.slider("Exit Threshold (%)", 0.01, 0.10, 0.05, 0.01)
    notional = st.sidebar.number_input("Notional per Trade ($)", 1000, 50000, 5000, 1000)
    max_holding = st.sidebar.slider("Max Holding (hours)", 12, 168, 72, 12)

    st.sidebar.divider()

    st.sidebar.subheader("Assets")
    btc_enabled = st.sidebar.checkbox("BTC", value=True)
    eth_enabled = st.sidebar.checkbox("ETH", value=True)

    return {
        "entry_threshold": entry_threshold,
        "exit_threshold": exit_threshold,
        "notional": notional,
        "max_holding": max_holding,
        "assets": {
            "BTC": btc_enabled,
            "ETH": eth_enabled,
        },
    }


def render_funding_dashboard():
    """Main funding dashboard panel."""
    st.header("Crypto Funding Harvest Strategy")

    # Mode indicator
    mode_color = "green" if EXECUTION_MODE == "paper" else "red"
    st.markdown(f"**Mode:** :{mode_color}[{EXECUTION_MODE.upper()}]")

    # Get config from sidebar
    config = render_config_sidebar()

    # Generate mock data
    market_data = generate_mock_funding_data()
    positions = generate_mock_positions()
    stats = {
        "open_positions": len(positions),
        "closed_positions": np.random.randint(0, 10),
        "total_funding_earned": np.random.uniform(50, 500),
        "total_pnl": np.random.uniform(-100, 400),
    }

    # Render components
    render_funding_rates(market_data)
    st.divider()

    render_positions(positions, market_data)
    st.divider()

    render_trade_buttons(positions, market_data)
    st.divider()

    render_strategy_stats(stats)
    st.divider()

    render_funding_history([])


def main():
    """Standalone dashboard entry point."""
    st.set_page_config(
        page_title="Crypto Funding Harvest",
        page_icon="💰",
        layout="wide",
    )

    render_funding_dashboard()

    # Auto-refresh
    if st.sidebar.checkbox("Auto-refresh", value=True):
        refresh_interval = st.sidebar.slider("Interval (sec)", 10, 120, 30)
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
