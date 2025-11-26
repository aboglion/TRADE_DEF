import streamlit as st
import asyncio
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time

from CONFIG import Config
from COIN_MODELS.COIN_MAIN import Coin
from COIN_MODELS.database.db_handler import TimescaleDBHandler
from backtest import run_backtest

# ==============================================================================
# PAGE CONFIG & STYLING
# ==============================================================================
st.set_page_config(
    page_title="COIN | Algorithmic Trading Terminal",
    layout="wide",
    page_icon="🪙",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look (Dark/Glassmorphism)
st.markdown("""
<style>
    /* Main Background */
    .stApp {
        background-color: #0e1117;
    }
    
    /* Metrics Cards */
    div[data-testid="stMetric"] {
        background-color: #1e2127;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #2e3138;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div[data-testid="stMetric"] label {
        color: #9ca3af;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #ffffff;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: transparent;
        border-bottom: 2px solid #4f46e5;
        color: #4f46e5;
    }

    /* Buttons */
    .stButton button {
        background-color: #4f46e5;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton button:hover {
        background-color: #4338ca;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }

    /* DataFrame */
    div[data-testid="stDataFrame"] {
        background-color: #1e2127;
        border-radius: 12px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Helper to run async code
def run_async(coro):
    return asyncio.run(coro)

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.title("🪙 COIN Terminal")
    st.caption(f"v2.0 | {datetime.now().strftime('%Y-%m-%d')}")
    st.markdown("---")
    
    st.subheader("⚙️ Global Config")
    
    # Configuration Sliders (Visual only for now, unless we inject them)
    history_min = st.slider("History (Minutes)", 1, 60, Config.HISTORY_TIME_MINUTES)
    threshold = st.slider("Base Threshold", 1.0, 2.0, Config.BASE_THRESHOLD, 0.01)
    
    st.markdown("---")
    auto_refresh = st.checkbox("🔄 Auto-Refresh (every 5s)", value=False)
    
    st.markdown("---")
    st.info("💡 **Tip:** Use the 'Backtest' tab to test different parameters safely.")

# ==============================================================================
# MAIN TABS
# ==============================================================================
tab1, tab2, tab3 = st.tabs(["📊 Live Monitor", "🧪 Backtest Lab", "🧠 Strategy Logic"])

# ==============================================================================
# TAB 1: LIVE MONITOR
# ==============================================================================
with tab1:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown("### 📡 Real-Time Market Data")
    with c2:
        if st.button("🔄 Refresh Data", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    # Initialize refresh counter and data in session state
    if 'refresh_count' not in st.session_state:
        st.session_state.refresh_count = 0
        st.session_state.dashboard_data = []
    
    async def fetch_db_data():
        """Fetches the latest market metrics directly from the database."""
        refresh_id = st.session_state.refresh_count
        metrics = await TimescaleDBHandler.fetch_latest_metrics()
        print(f"Dashboard: Fetched {len(metrics)} metrics from DB (refresh #{refresh_id})")
        
        coins_data = []
        for m in metrics:
            print(f"  - {m['symbol']}: Price={m['price']}, Readiness={m['readiness']}")
            coins_data.append({
                "Symbol": m['symbol'],
                "Price": m['price'],
                "Signal": m['signal'],
                "Volatility": m['volatility'] * 1000, # Scaled
                "Momentum": m['momentum'],
                "Buy Pressure": m['buy_pressure'],
                "Sell Pressure": m['sell_pressure'],
                "Data Ready": m['readiness'] * 100,  # Convert to percentage (0-100)
                "Fallback": False # DB data is considered valid if present
            })
        return coins_data

    # Fetch fresh data and store in session state
    st.session_state.refresh_count += 1
    with st.spinner("Fetching data from DB..."):
        try:
            # Always fetch fresh data
            fresh_data = run_async(fetch_db_data())
            st.session_state.dashboard_data = fresh_data  # Store in session state
            
            # Create DataFrame from session state
            df = pd.DataFrame(st.session_state.dashboard_data)
            
            # Use refresh count as unique key for all components
            unique_key = st.session_state.refresh_count
            
            # Top Metrics Row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Active Assets", len(df))
            m2.metric("Buy Signals", len(df[df['Signal'] == 'BUY']), delta_color="normal")
            m3.metric("Sell Signals", len(df[df['Signal'] == 'SELL']), delta_color="inverse")
            m4.metric("Avg Volatility", f"{df['Volatility'].mean():.2f}")

            # Main Data Table with Styling
            def highlight_signal(val):
                color = ''
                if val == 'BUY': color = 'background-color: rgba(34, 197, 94, 0.2); color: #22c55e'
                elif val == 'SELL': color = 'background-color: rgba(239, 68, 68, 0.2); color: #ef4444'
                return color

            # Fill None values to avoid formatting errors
            df['Price'] = df['Price'].fillna(0.0)
            df['Volatility'] = df['Volatility'].fillna(0.0)
            df['Momentum'] = df['Momentum'].fillna(0.0)
            df['Buy Pressure'] = df['Buy Pressure'].fillna(0.0)
            df['Sell Pressure'] = df['Sell Pressure'].fillna(0.0)

            # Display without cached styling - recreate each time
            st.text(f"Last updated: Refresh #{unique_key}")
            st.dataframe(
                df,
                column_config={
                    "Data Ready": st.column_config.ProgressColumn(
                        "Data Readiness",
                        help="Percentage of historical data collected for indicators",
                        format="%.0f%%",
                        min_value=0,
                        max_value=100,
                    ),
                },
                width="stretch",
                height=400,
                key=f"dataframe_{unique_key}"
            )
            
            # Charts
            st.markdown("### 📉 Market Dynamics")
            ch1, ch2 = st.columns(2)
            
            with ch1:
                fig_mom = px.bar(df, x='Symbol', y='Momentum', title="Momentum by Asset", color='Momentum', color_continuous_scale='RdBu')
                fig_mom.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_mom, width="stretch")
            
            with ch2:
                # Pressure Ratio Chart (Buy vs Sell)
                fig_pres = go.Figure(data=[
                    go.Bar(name='Buy Pressure', x=df['Symbol'], y=df['Buy Pressure'], marker_color='#22c55e'),
                    go.Bar(name='Sell Pressure', x=df['Symbol'], y=df['Sell Pressure'], marker_color='#ef4444')
                ])
                fig_pres.update_layout(barmode='group', title="Order Book Pressure", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                st.plotly_chart(fig_pres, width="stretch")
            
            # Auto-refresh logic
            if auto_refresh:
                time.sleep(5)
                st.rerun()

        except Exception as e:
            st.error(f"Connection Error: {e}")
            st.warning("Ensure you have an active internet connection and the exchanges are accessible.")

# ==============================================================================
# TAB 2: BACKTEST LAB
# ==============================================================================
with tab2:
    st.markdown("### 🧪 Backtest Laboratory")
    
    # Controls
    with st.expander("⚙️ Simulation Settings", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            symbol = st.selectbox("Asset", Config.SYMBOLS)
        with c2:
            start_date = st.date_input("Start Date", datetime.now() - timedelta(days=1))
            start_time = st.time_input("Start Time", datetime.strptime("00:00", "%H:%M").time())
        with c3:
            end_date = st.date_input("End Date", datetime.now())
            end_time = st.time_input("End Time", datetime.strptime("23:59", "%H:%M").time())
        with c4:
            st.write("") # Spacer
            run_btn = st.button("🚀 Run Simulation", width="stretch")

    start_dt = datetime.combine(start_date, start_time).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, end_time).replace(tzinfo=timezone.utc)

    if run_btn:
        with st.spinner(f"Simulating strategy on {symbol}..."):
            try:
                # Create a custom config based on sidebar sliders
                custom_config = Config(
                    HISTORY_TIME_MINUTES=history_min,
                    BASE_THRESHOLD=threshold
                )
                
                result = run_async(run_backtest(symbol, start_dt, end_dt, verbose=False, config=custom_config))
                
                if result and result.get('equity_curve'):
                    st.success("Simulation Complete!")
                    
                    # 1. KPI Metrics
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Net Profit", f"{result['total_profit']:.4f}")
                    k2.metric("ROI", f"{result['total_profit_pct']:.2f}%", delta_color="normal")
                    k3.metric("Trades", result['buy_trades'] + result['sell_trades'])
                    k4.metric("Win Rate", "N/A") # TODO: Calculate if trade log exists

                    # 2. Equity Curve Chart
                    equity_df = pd.DataFrame(result['equity_curve'])
                    if not equity_df.empty:
                        fig_eq = px.line(equity_df, x='time', y='profit', title='Equity Curve (Cumulative Profit)', markers=True)
                        fig_eq.update_traces(line_color='#4f46e5', line_width=3)
                        fig_eq.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white')
                        st.plotly_chart(fig_eq, width="stretch")
                    
                    # 3. Trade Log (Placeholder if empty)
                    if 'trade_log' in result and result['trade_log']:
                        st.subheader("📜 Trade Log")
                        st.dataframe(pd.DataFrame(result['trade_log']), width="stretch")
                    else:
                        st.info("No trades were executed in this period.")
                        
                else:
                    st.warning("No data found for this period. Try a different range.")
                    
            except Exception as e:
                st.error(f"Simulation Failed: {e}")

# ==============================================================================
# TAB 3: STRATEGY LOGIC
# ==============================================================================
with tab3:
    st.markdown("### 🧠 The Algorithm")
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.markdown("""
        #### 1. Dynamic Thresholding
        The core innovation is adjusting the buy/sell threshold based on market conditions.
        
        $$
        T_{dynamic} = T_{base} + \min(Vol \\times 100, 0.5) \\times (1 + |Momentum|)
        $$
        
        *   **Volatility ($Vol$)**: Standard deviation of log returns. High volatility $\\to$ Higher threshold (Safety).
        *   **Momentum**: Trend strength. Strong trend $\\to$ Higher threshold (Confirmation).
        
        #### 2. Multi-Exchange Arbitration
        We don't trust a single source.
        *   **Price**: `Median(Binance, Bybit, OKX)`
        *   **Liquidity**: Aggregated pressure ratios.
        """)
    
    with c2:
        st.info("""
        **Current Settings**
        
        *   **Interval**: 2s
        *   **History**: 7m
        *   **Take Profit**: 1.0%
        *   **Stop Loss**: 0.66%
        """)
