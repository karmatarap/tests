"""
ETF-Futures Spread Dashboard Panel

Streamlit dashboard component for the ETF-Futures spread dislocation strategy.
Displays:
- Live spread chart (ETF vs futures)
- Current z-score
- Current position + PnL
- Trade simulation and execution buttons
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


def generate_mock_spread_data(pair_id: str, minutes: int = 60) -> pd.DataFrame:
    """Generate mock spread data for demonstration."""
    np.random.seed(42)

    # Generate timestamps
    end_time = datetime.now()
    timestamps = [end_time - timedelta(minutes=i) for i in range(minutes, 0, -1)]

    # Base spread with mean reversion
    base_spread = 0.0
    spreads = []
    z_scores = []

    for i in range(minutes):
        # Random walk with mean reversion
        shock = np.random.randn() * 0.05
        reversion = -0.1 * base_spread
        base_spread = base_spread + shock + reversion

        # Occasional larger dislocations
        if np.random.random() < 0.05:
            base_spread += np.random.choice([-1, 1]) * np.random.uniform(0.2, 0.5)

        spreads.append(base_spread)

        # Calculate z-score (rolling)
        if i >= 20:
            window = spreads[max(0, i-20):i]
            z = (base_spread - np.mean(window)) / (np.std(window) + 1e-8)
            z_scores.append(z)
        else:
            z_scores.append(0)

    # Generate ETF and futures prices
    if "SPY" in pair_id:
        etf_base, fut_base = 450.0, 4500.0
    elif "QQQ" in pair_id:
        etf_base, fut_base = 380.0, 15200.0
    else:
        etf_base, fut_base = 200.0, 2000.0

    etf_prices = [etf_base + s + np.random.randn() * 0.1 for s in spreads]
    fut_prices = [fut_base + np.random.randn() for _ in spreads]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "spread": spreads,
        "z_score": z_scores,
        "etf_price": etf_prices,
        "futures_price": fut_prices,
    })
    df.set_index("timestamp", inplace=True)
    return df


def render_spread_chart(pair_id: str, data: pd.DataFrame):
    """Render the spread time series chart."""
    st.subheader(f"Spread: {pair_id}")

    # Create tabs for different views
    tab1, tab2, tab3 = st.tabs(["Spread", "Z-Score", "Prices"])

    with tab1:
        st.line_chart(data["spread"], use_container_width=True)
        st.caption("Spread = ETF - k × Futures")

    with tab2:
        # Z-score with threshold lines
        chart_data = data[["z_score"]].copy()
        chart_data["upper_threshold"] = 2.0
        chart_data["lower_threshold"] = -2.0
        chart_data["zero"] = 0.0

        st.line_chart(chart_data, use_container_width=True)
        st.caption("Z-Score with ±2σ thresholds")

    with tab3:
        # Normalized prices for comparison
        etf_norm = data["etf_price"] / data["etf_price"].iloc[0] * 100
        fut_norm = data["futures_price"] / data["futures_price"].iloc[0] * 100

        price_data = pd.DataFrame({
            "ETF (normalized)": etf_norm,
            "Futures (normalized)": fut_norm,
        })
        st.line_chart(price_data, use_container_width=True)


def render_current_state(pair_id: str, state: dict):
    """Render current z-score and position."""
    col1, col2, col3, col4 = st.columns(4)

    z_score = state.get("z_score", 0)
    z_color = "red" if abs(z_score) > 2 else "orange" if abs(z_score) > 1 else "green"

    with col1:
        st.metric(
            "Current Z-Score",
            f"{z_score:.2f}",
            delta=f"{z_score - state.get('prev_z', z_score):.2f}",
        )
        if abs(z_score) > 2:
            st.markdown(f":{z_color}[**SIGNAL THRESHOLD EXCEEDED**]")

    with col2:
        st.metric(
            "Current Spread",
            f"{state.get('spread', 0):.4f}",
        )

    with col3:
        position = state.get("position", "FLAT")
        pos_color = "blue" if position == "LONG" else "red" if position == "SHORT" else "gray"
        st.markdown(f"**Position:** :{pos_color}[{position}]")

        if position != "FLAT":
            st.write(f"ETF Qty: {state.get('etf_qty', 0):.0f}")
            st.write(f"Futures Qty: {state.get('futures_qty', 0):.0f}")

    with col4:
        pnl = state.get("unrealized_pnl", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        st.metric(
            "Unrealized P&L",
            f"${pnl:+,.2f}",
        )


def render_trade_buttons(pair_id: str, state: dict, on_trade_callback=None):
    """Render trade simulation and execution buttons."""
    st.subheader("Trade Actions")

    col1, col2, col3, col4 = st.columns(4)

    position = state.get("position", "FLAT")
    z_score = state.get("z_score", 0)

    with col1:
        if position == "FLAT":
            if st.button("📈 Simulate LONG", key=f"sim_long_{pair_id}",
                        help="Simulate long ETF / short futures"):
                st.success("Simulated LONG trade executed")
                if on_trade_callback:
                    on_trade_callback("LONG", pair_id, simulated=True)
        else:
            st.button("📈 LONG", key=f"sim_long_{pair_id}", disabled=True)

    with col2:
        if position == "FLAT":
            if st.button("📉 Simulate SHORT", key=f"sim_short_{pair_id}",
                        help="Simulate short ETF / long futures"):
                st.success("Simulated SHORT trade executed")
                if on_trade_callback:
                    on_trade_callback("SHORT", pair_id, simulated=True)
        else:
            st.button("📉 SHORT", key=f"sim_short_{pair_id}", disabled=True)

    with col3:
        if position != "FLAT":
            if st.button("🔄 Simulate CLOSE", key=f"sim_close_{pair_id}",
                        help="Close current position"):
                st.success("Simulated CLOSE executed")
                if on_trade_callback:
                    on_trade_callback("CLOSE", pair_id, simulated=True)
        else:
            st.button("🔄 CLOSE", key=f"sim_close_{pair_id}", disabled=True)

    with col4:
        if EXECUTION_MODE == "live":
            if position == "FLAT" and abs(z_score) > 2:
                action = "LONG" if z_score < -2 else "SHORT"
                if st.button(f"⚡ Execute {action}", key=f"exec_{pair_id}",
                            type="primary",
                            help="Execute LIVE trade"):
                    st.warning(f"LIVE {action} trade executed!")
                    if on_trade_callback:
                        on_trade_callback(action, pair_id, simulated=False)
            elif position != "FLAT":
                if st.button("⚡ Execute CLOSE", key=f"exec_close_{pair_id}",
                            type="primary"):
                    st.warning("LIVE CLOSE executed!")
                    if on_trade_callback:
                        on_trade_callback("CLOSE", pair_id, simulated=False)
            else:
                st.button("⚡ Execute", key=f"exec_{pair_id}", disabled=True,
                         help="No signal - |z| < 2")
        else:
            st.info("🔒 Paper Mode")


def render_strategy_config():
    """Render strategy configuration sidebar."""
    st.sidebar.subheader("Strategy Config")

    z_entry = st.sidebar.slider("Z-Score Entry", 1.0, 4.0, 2.0, 0.1)
    z_exit = st.sidebar.slider("Z-Score Exit", 0.0, 1.5, 0.5, 0.1)
    lookback = st.sidebar.slider("Lookback (min)", 30, 180, 60, 10)
    notional = st.sidebar.number_input("Notional per Leg ($)", 1000, 50000, 5000, 1000)

    st.sidebar.divider()

    st.sidebar.subheader("Pairs")
    spy_es = st.sidebar.checkbox("SPY / ES", value=True)
    qqq_nq = st.sidebar.checkbox("QQQ / NQ", value=True)
    iwm_rty = st.sidebar.checkbox("IWM / RTY", value=False)

    return {
        "z_entry": z_entry,
        "z_exit": z_exit,
        "lookback": lookback,
        "notional": notional,
        "pairs": {
            "SPY_ES": spy_es,
            "QQQ_NQ": qqq_nq,
            "IWM_RTY": iwm_rty,
        },
    }


def render_signal_history(signals: list):
    """Render recent signal history."""
    st.subheader("Recent Signals")

    if not signals:
        st.info("No signals generated yet")
        return

    df = pd.DataFrame(signals)
    df = df[["timestamp", "signal", "symbol_etf", "symbol_hedge", "z_score", "reason"]]
    df.columns = ["Time", "Signal", "ETF", "Hedge", "Z-Score", "Reason"]

    st.dataframe(
        df.style.applymap(
            lambda x: "background-color: #90EE90" if x == "LONG"
            else "background-color: #FFB6C1" if x == "SHORT"
            else "background-color: #FFA500" if x == "CLOSE"
            else "",
            subset=["Signal"]
        ),
        use_container_width=True,
    )


def render_spread_dashboard():
    """Main spread dashboard panel."""
    st.header("ETF-Futures Spread Strategy")

    # Mode indicator
    mode_color = "green" if EXECUTION_MODE == "paper" else "red"
    st.markdown(f"**Mode:** :{mode_color}[{EXECUTION_MODE.upper()}]")

    # Get config from sidebar
    config = render_strategy_config()

    # Select active pair
    active_pairs = [p for p, enabled in config["pairs"].items() if enabled]

    if not active_pairs:
        st.warning("No pairs selected. Enable at least one pair in the sidebar.")
        return

    pair_tabs = st.tabs(active_pairs)

    for i, pair_id in enumerate(active_pairs):
        with pair_tabs[i]:
            # Generate mock data (replace with real data in production)
            data = generate_mock_spread_data(pair_id, minutes=config["lookback"])

            # Current state
            current_state = {
                "z_score": data["z_score"].iloc[-1],
                "prev_z": data["z_score"].iloc[-2] if len(data) > 1 else 0,
                "spread": data["spread"].iloc[-1],
                "position": np.random.choice(["FLAT", "LONG", "SHORT"], p=[0.8, 0.1, 0.1]),
                "etf_qty": np.random.randint(100, 500) if np.random.random() > 0.8 else 0,
                "futures_qty": 1 if np.random.random() > 0.8 else 0,
                "unrealized_pnl": np.random.randn() * 100,
            }

            # Render components
            render_current_state(pair_id, current_state)
            st.divider()
            render_spread_chart(pair_id, data)
            st.divider()
            render_trade_buttons(pair_id, current_state)

    st.divider()

    # Signal history (mock)
    mock_signals = [
        {"timestamp": "14:30:00", "signal": "LONG", "symbol_etf": "SPY", "symbol_hedge": "ES", "z_score": -2.5, "reason": "ETF cheap"},
        {"timestamp": "14:15:00", "signal": "CLOSE", "symbol_etf": "QQQ", "symbol_hedge": "NQ", "z_score": 0.3, "reason": "Mean reversion"},
        {"timestamp": "13:45:00", "signal": "SHORT", "symbol_etf": "SPY", "symbol_hedge": "ES", "z_score": 2.8, "reason": "ETF rich"},
    ]
    render_signal_history(mock_signals)


def main():
    """Standalone dashboard entry point."""
    st.set_page_config(
        page_title="ETF-Futures Spread Strategy",
        page_icon="📊",
        layout="wide",
    )

    render_spread_dashboard()

    # Auto-refresh
    if st.sidebar.checkbox("Auto-refresh", value=True):
        refresh_interval = st.sidebar.slider("Interval (sec)", 5, 60, 10)
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
