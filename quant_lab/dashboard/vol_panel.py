"""
Vol-of-Vol Mean Reversion Dashboard Panel

Streamlit dashboard component for the volatility mean reversion strategy.
Displays:
- VIX price and daily % change with color coding
- Spike/crash detection status
- Current position, P&L
- Trade buttons: "Short Vol", "Long Vol", "Close"
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


def generate_mock_vol_data() -> dict:
    """Generate mock volatility data for demonstration."""
    np.random.seed(int(time.time()) % 1000)

    # VIX with occasional spikes
    vix_prev_close = 18.0 + np.random.randn() * 2

    # 20% chance of spike/crash
    if np.random.random() < 0.2:
        vix_change = np.random.choice([-1, 1]) * np.random.uniform(10, 35)
    else:
        vix_change = np.random.uniform(-5, 5)

    vix_price = max(10, vix_prev_close * (1 + vix_change / 100))

    # Correlated ETF prices
    uvxy_mult = 1 + (vix_change / 100) * 1.5
    svxy_mult = 1 - (vix_change / 100) * 0.5
    vxx_mult = 1 + (vix_change / 100)

    return {
        "vix_price": vix_price,
        "vix_prev_close": vix_prev_close,
        "vix_change_pct": vix_change,
        "uvxy_price": 12.0 * uvxy_mult,
        "svxy_price": 45.0 * svxy_mult,
        "vxx_price": 22.0 * vxx_mult,
        "vix_mean_20d": 18.5,
        "vix_std_20d": 3.2,
        "vix_zscore": (vix_price - 18.5) / 3.2,
        "timestamp": datetime.now(),
    }


def generate_mock_position() -> dict:
    """Generate mock position for demonstration."""
    np.random.seed(42)

    if np.random.random() < 0.4:
        return {
            "instrument": np.random.choice(["SVXY", "UVXY"]),
            "position_type": np.random.choice(["LONG", "SHORT"]),
            "signal_type": np.random.choice(["SHORT_VOL", "LONG_VOL"]),
            "quantity": np.random.uniform(50, 200),
            "entry_price": np.random.uniform(10, 50),
            "entry_vix": np.random.uniform(15, 30),
            "entry_vix_change_pct": np.random.uniform(10, 25),
            "notional_usd": 3000,
            "entry_time": (datetime.now() - timedelta(hours=np.random.uniform(1, 48))).isoformat(),
            "current_pnl_usd": np.random.uniform(-200, 400),
            "current_pnl_pct": np.random.uniform(-10, 15),
            "holding_hours": np.random.uniform(1, 48),
        }
    return None


def get_vix_color(vix_change_pct: float, spike_threshold: float = 15.0, crash_threshold: float = -10.0) -> str:
    """Get color based on VIX change magnitude."""
    if vix_change_pct >= spike_threshold:
        return "red"  # Spike
    elif vix_change_pct <= crash_threshold:
        return "blue"  # Crash
    elif abs(vix_change_pct) >= 10:
        return "orange"
    else:
        return "gray"


def render_vix_status(data: dict, config: dict):
    """Render VIX status with spike/crash detection."""
    st.subheader("VIX Status")

    col1, col2, col3 = st.columns(3)

    vix_price = data["vix_price"]
    vix_change = data["vix_change_pct"]
    spike_threshold = config.get("spike_threshold", 15.0)
    crash_threshold = config.get("crash_threshold", -10.0)
    extreme_threshold = config.get("extreme_threshold", 30.0)

    with col1:
        st.metric(
            "VIX",
            f"{vix_price:.2f}",
            f"{vix_change:+.1f}%",
            delta_color="inverse"  # Red when up, green when down
        )

    with col2:
        # Status indicator
        if vix_change >= extreme_threshold:
            st.error("🔴 EXTREME SPIKE")
            st.caption(f"+{vix_change:.1f}% >= {extreme_threshold}% threshold")
        elif vix_change >= spike_threshold:
            st.warning("🟠 VIX SPIKE")
            st.caption(f"+{vix_change:.1f}% >= {spike_threshold}% threshold")
        elif vix_change <= crash_threshold:
            st.info("🔵 VIX CRASH")
            st.caption(f"{vix_change:.1f}% <= {crash_threshold}% threshold")
        else:
            st.success("🟢 NORMAL")
            st.caption(f"{vix_change:+.1f}% within normal range")

    with col3:
        st.markdown("**Statistics**")
        st.write(f"Previous Close: {data['vix_prev_close']:.2f}")
        if data.get("vix_mean_20d"):
            st.write(f"20D Mean: {data['vix_mean_20d']:.2f}")
        if data.get("vix_zscore"):
            zscore = data["vix_zscore"]
            z_color = "red" if abs(zscore) > 2 else "orange" if abs(zscore) > 1 else "gray"
            st.markdown(f"Z-Score: :{z_color}[{zscore:+.2f}σ]")


def render_vol_instruments(data: dict):
    """Render volatility instrument prices."""
    st.subheader("Volatility Instruments")

    cols = st.columns(3)

    instruments = [
        ("UVXY", data.get("uvxy_price"), "Long Vol (1.5x)"),
        ("SVXY", data.get("svxy_price"), "Short Vol (0.5x)"),
        ("VXX", data.get("vxx_price"), "Long Vol (1x)"),
    ]

    for i, (symbol, price, desc) in enumerate(instruments):
        with cols[i]:
            st.markdown(f"### {symbol}")
            if price:
                st.write(f"**${price:,.2f}**")
                st.caption(desc)
            else:
                st.write("N/A")


def render_position(position: dict, market_data: dict):
    """Render current position."""
    st.subheader("Current Position")

    if not position:
        st.info("No open position")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"### {position['instrument']}")
        st.write(f"**Type:** {position['position_type']}")
        st.write(f"**Signal:** {position['signal_type']}")
        st.write(f"**Quantity:** {position['quantity']:.2f}")

    with col2:
        st.markdown("**Entry**")
        st.write(f"Price: ${position['entry_price']:.2f}")
        st.write(f"VIX: {position['entry_vix']:.2f}")
        st.write(f"VIX Δ: {position['entry_vix_change_pct']:+.1f}%")
        st.write(f"Notional: ${position['notional_usd']:,.0f}")

    with col3:
        st.markdown("**P&L**")
        pnl_usd = position.get("current_pnl_usd", 0)
        pnl_pct = position.get("current_pnl_pct", 0)

        pnl_color = "green" if pnl_usd >= 0 else "red"
        st.markdown(f"**USD:** :{pnl_color}[**${pnl_usd:+,.2f}**]")
        st.markdown(f"**%:** :{pnl_color}[**{pnl_pct:+.2f}%**]")
        st.write(f"Holding: {position['holding_hours']:.1f}h")


def render_trade_buttons(has_position: bool, market_data: dict, on_trade_callback=None):
    """Render trade action buttons."""
    st.subheader("Trade Actions")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Short Vol**")
        if not has_position:
            if st.button("📉 Short Vol", key="short_vol",
                        help="Long SVXY to short volatility"):
                st.success("Opened short vol position (long SVXY)")
                if on_trade_callback:
                    on_trade_callback("SHORT_VOL")
        else:
            st.button("📉 Short Vol", key="short_vol", disabled=True)

    with col2:
        st.markdown("**Long Vol**")
        if not has_position:
            if st.button("📈 Long Vol", key="long_vol",
                        help="Long UVXY to go long volatility"):
                st.success("Opened long vol position (long UVXY)")
                if on_trade_callback:
                    on_trade_callback("LONG_VOL")
        else:
            st.button("📈 Long Vol", key="long_vol", disabled=True)

    with col3:
        st.markdown("**Close**")
        if has_position:
            if st.button("🔄 Close Position", key="close_vol"):
                st.warning("Closed position")
                if on_trade_callback:
                    on_trade_callback("CLOSE")
        else:
            st.button("🔄 Close Position", key="close_vol", disabled=True)

    with col4:
        st.markdown("**Mode**")
        if EXECUTION_MODE == "live":
            st.error("⚡ LIVE MODE")
            st.caption("Trades will execute on IBKR")
        else:
            st.info("🔒 Paper Mode")
            st.caption("All trades simulated")


def render_vix_history(history: list = None):
    """Render VIX history chart."""
    st.subheader("VIX History")

    if not history:
        # Generate mock history
        np.random.seed(123)
        timestamps = [datetime.now() - timedelta(hours=i) for i in range(48, 0, -1)]
        vix_prices = [18.0]
        for _ in range(len(timestamps) - 1):
            change = np.random.uniform(-2, 2)
            vix_prices.append(max(10, vix_prices[-1] + change))

        df = pd.DataFrame({
            "Time": timestamps,
            "VIX": vix_prices,
        })
        df.set_index("Time", inplace=True)
    else:
        df = pd.DataFrame(history)

    # Add threshold lines
    df["Spike Threshold (+15%)"] = df["VIX"].iloc[0] * 1.15
    df["Crash Threshold (-10%)"] = df["VIX"].iloc[0] * 0.90

    st.line_chart(df, use_container_width=True)
    st.caption("VIX price history with threshold levels")


def render_strategy_stats(stats: dict):
    """Render strategy statistics."""
    st.subheader("Strategy Statistics")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Trades", stats.get("total_trades", 0))

    with col2:
        win_rate = stats.get("win_rate_pct", 0)
        st.metric("Win Rate", f"{win_rate:.1f}%")

    with col3:
        st.metric("Winning", stats.get("winning_trades", 0))

    with col4:
        total_pnl = stats.get("total_pnl_usd", 0)
        st.metric(
            "Total P&L",
            f"${total_pnl:+,.2f}",
            delta_color="normal" if total_pnl >= 0 else "inverse"
        )


def render_closed_positions(positions: list):
    """Render recent closed positions."""
    st.subheader("Recent Trades")

    if not positions:
        st.info("No closed positions yet")
        return

    df = pd.DataFrame(positions[-10:])  # Last 10

    # Format columns
    if "pnl_usd" in df.columns:
        df["P&L"] = df["pnl_usd"].apply(lambda x: f"${x:+,.2f}")
    if "pnl_pct" in df.columns:
        df["P&L %"] = df["pnl_pct"].apply(lambda x: f"{x:+.2f}%")
    if "holding_hours" in df.columns:
        df["Duration"] = df["holding_hours"].apply(lambda x: f"{x:.1f}h")

    display_cols = ["instrument", "signal_type", "P&L", "P&L %", "Duration", "exit_reason"]
    display_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


def render_config_sidebar():
    """Render strategy configuration sidebar."""
    st.sidebar.subheader("Vol Strategy Config")

    spike_threshold = st.sidebar.slider("Spike Threshold (%)", 10.0, 40.0, 15.0, 1.0)
    crash_threshold = st.sidebar.slider("Crash Threshold (%)", -20.0, -5.0, -10.0, 1.0)
    extreme_threshold = st.sidebar.slider("Extreme Threshold (%)", 20.0, 50.0, 30.0, 1.0)
    max_holding = st.sidebar.slider("Max Holding (days)", 1, 7, 3, 1)
    stop_loss = st.sidebar.slider("Stop Loss (%)", 5.0, 30.0, 15.0, 1.0)
    notional = st.sidebar.number_input("Notional per Trade ($)", 1000, 20000, 3000, 500)

    st.sidebar.divider()

    st.sidebar.subheader("Instruments")
    short_vol = st.sidebar.selectbox("Short Vol Instrument", ["SVXY", "VXX"], index=0)
    long_vol = st.sidebar.selectbox("Long Vol Instrument", ["UVXY", "VXX"], index=0)

    return {
        "spike_threshold": spike_threshold,
        "crash_threshold": crash_threshold,
        "extreme_threshold": extreme_threshold,
        "max_holding_days": max_holding,
        "stop_loss_pct": stop_loss,
        "notional_usd": notional,
        "preferred_short_vol": short_vol,
        "preferred_long_vol": long_vol,
    }


def render_vol_dashboard():
    """Main vol strategy dashboard panel."""
    st.header("Vol-of-Vol Mean Reversion Strategy")

    # Mode indicator
    mode_color = "green" if EXECUTION_MODE == "paper" else "red"
    st.markdown(f"**Mode:** :{mode_color}[{EXECUTION_MODE.upper()}]")

    # Get config from sidebar
    config = render_config_sidebar()

    # Generate mock data
    market_data = generate_mock_vol_data()
    position = generate_mock_position()
    stats = {
        "total_trades": np.random.randint(0, 20),
        "winning_trades": np.random.randint(0, 15),
        "win_rate_pct": np.random.uniform(40, 70),
        "total_pnl_usd": np.random.uniform(-500, 1000),
    }

    # Render components
    render_vix_status(market_data, config)
    st.divider()

    render_vol_instruments(market_data)
    st.divider()

    render_position(position, market_data)
    st.divider()

    render_trade_buttons(position is not None, market_data)
    st.divider()

    render_strategy_stats(stats)
    st.divider()

    render_vix_history()
    st.divider()

    # Mock closed positions
    closed = []
    if np.random.random() > 0.3:
        for _ in range(np.random.randint(1, 5)):
            closed.append({
                "instrument": np.random.choice(["SVXY", "UVXY"]),
                "signal_type": np.random.choice(["SHORT_VOL", "LONG_VOL"]),
                "pnl_usd": np.random.uniform(-200, 400),
                "pnl_pct": np.random.uniform(-10, 15),
                "holding_hours": np.random.uniform(4, 48),
                "exit_reason": np.random.choice(["Mean reversion", "Stop loss", "Time limit"]),
            })

    render_closed_positions(closed)


def main():
    """Standalone dashboard entry point."""
    st.set_page_config(
        page_title="Vol Mean Reversion",
        page_icon="📊",
        layout="wide",
    )

    render_vol_dashboard()

    # Auto-refresh
    if st.sidebar.checkbox("Auto-refresh", value=True):
        refresh_interval = st.sidebar.slider("Interval (sec)", 10, 120, 30)
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
