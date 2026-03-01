"""
Stock Ticks Dashboard

A Streamlit dashboard to visualize real-time stock data from ClickHouse.

Run with:
    streamlit run src/production/dashboard/app.py
"""

import os

import streamlit as st
import clickhouse_connect
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Stock Ticks Dashboard",
    page_icon="📈",
    layout="wide",
)

# =============================================================================
# CLICKHOUSE CONNECTION
# =============================================================================

@st.cache_resource
def get_client():
    """Create a ClickHouse client (cached so we reuse the connection)."""
    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        database="stocks",
    )


def run_query(query: str) -> pd.DataFrame:
    """Run a query and return results as a DataFrame (no caching - always fresh)."""
    client = get_client()
    result = client.query(query)
    return pd.DataFrame(result.result_rows, columns=result.column_names)


def get_total_count() -> int:
    """Get total tick count - always fresh."""
    client = get_client()
    result = client.query("SELECT count() as cnt FROM ticks")
    return result.result_rows[0][0]


# =============================================================================
# DASHBOARD
# =============================================================================

st.title("📈 Stock Ticks Dashboard")
st.caption("Real-time stock data from Kafka → Spark → ClickHouse")

# Sidebar controls
st.sidebar.header("Controls")

# Manual refresh button
if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()

# Auto-refresh interval selector
refresh_interval = st.sidebar.selectbox(
    "Auto-refresh",
    options=[0, 5, 10, 30],
    format_func=lambda x: "Off" if x == 0 else f"Every {x}s",
    index=0,
)

# Apply auto-refresh if enabled
if refresh_interval > 0:
    st_autorefresh(interval=refresh_interval * 1000, key="data_refresh")

# =============================================================================
# METRICS - Latest prices with change
# =============================================================================

st.header("Latest Prices")

# Get latest price for each symbol
latest_query = """
SELECT
    symbol,
    argMax(price, timestamp) as price,
    argMax(volume, timestamp) as volume,
    max(timestamp) as last_update
FROM ticks
GROUP BY symbol
ORDER BY symbol
"""

try:
    df_latest = run_query(latest_query)

    if df_latest.empty:
        st.warning("No data yet. Make sure the producer and consumer are running!")
    else:
        # Display metrics in columns
        cols = st.columns(len(df_latest))
        for i, row in df_latest.iterrows():
            with cols[i]:
                st.metric(
                    label=row["symbol"],
                    value=f"${row['price']:.2f}",
                )
                st.caption(f"Vol: {row['volume']:,}")
                st.caption(f"{row['last_update']}")

except Exception as e:
    st.error(f"Error connecting to ClickHouse: {e}")
    st.info("Make sure ClickHouse is running: `docker-compose up -d clickhouse`")
    st.stop()

# =============================================================================
# CHARTS - Price over time
# =============================================================================

st.header("Price History")

# Symbol selector
symbols = run_query("SELECT DISTINCT symbol FROM ticks ORDER BY symbol")

if symbols.empty:
    st.warning("No symbols found in database")
else:
    selected_symbols = st.multiselect(
        "Select stocks",
        options=symbols["symbol"].tolist(),
        default=symbols["symbol"].tolist(),
    )

    # Time range selector
    time_range = st.selectbox(
        "Time range",
        options=["Last 5 minutes", "Last 1 hour", "Last 24 hours", "All data"],
        index=3,  # Default to "All data"
    )

    time_filter = {
        "Last 5 minutes": "AND timestamp > now() - INTERVAL 5 MINUTE",
        "Last 1 hour": "AND timestamp > now() - INTERVAL 1 HOUR",
        "Last 24 hours": "AND timestamp > now() - INTERVAL 24 HOUR",
        "All data": "",
    }

    if selected_symbols:
        # Format for SQL IN clause
        symbols_str = ", ".join([f"'{s}'" for s in selected_symbols])

        price_history_query = f"""
        SELECT
            timestamp,
            symbol,
            price
        FROM ticks
        WHERE symbol IN ({symbols_str})
          {time_filter[time_range]}
        ORDER BY timestamp
        """

        df_history = run_query(price_history_query)

        if not df_history.empty:
            # Pivot for line chart
            df_pivot = df_history.pivot(index="timestamp", columns="symbol", values="price")
            st.line_chart(df_pivot)
        else:
            st.info(f"No data found for {time_range.lower()}")

# =============================================================================
# TABLE - Recent ticks
# =============================================================================

st.header("Recent Ticks")

recent_query = """
SELECT
    timestamp,
    symbol,
    price,
    volume
FROM ticks
ORDER BY timestamp DESC
LIMIT 20
"""

df_recent = run_query(recent_query)

if not df_recent.empty:
    st.dataframe(
        df_recent,
        use_container_width=True,
        hide_index=True,
    )

# =============================================================================
# STATS - Aggregations
# =============================================================================

st.header("Statistics")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Price Stats by Symbol")

    stats_query = """
    SELECT
        symbol,
        count() as tick_count,
        round(min(price), 2) as min_price,
        round(max(price), 2) as max_price,
        round(avg(price), 2) as avg_price
    FROM ticks
    GROUP BY symbol
    ORDER BY symbol
    """

    df_stats = run_query(stats_query)
    if not df_stats.empty:
        st.dataframe(df_stats, use_container_width=True, hide_index=True)

with col2:
    st.subheader("Volume by Symbol")

    volume_query = """
    SELECT
        symbol,
        sum(volume) as total_volume
    FROM ticks
    GROUP BY symbol
    ORDER BY total_volume DESC
    """

    df_volume = run_query(volume_query)
    if not df_volume.empty:
        st.bar_chart(df_volume.set_index("symbol"))

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
from datetime import datetime
total_count = get_total_count()
st.caption(f"Total ticks in database: {total_count:,} | Last refreshed: {datetime.now().strftime('%H:%M:%S')}")
