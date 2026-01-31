"""
Stock Ticks Dashboard - Web API

A simple FastAPI backend that serves the stock dashboard
and provides API endpoints for ClickHouse data.

Run with:
    uvicorn src.dashboard.web_app:app --reload --port 8502

Or:
    python src/dashboard/web_app.py
"""

import os
from contextlib import asynccontextmanager

import clickhouse_connect
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# =============================================================================
# CLICKHOUSE CONNECTION
# =============================================================================

client = None


def get_client():
    """Get or create ClickHouse client."""
    global client
    if client is None:
        client = clickhouse_connect.get_client(
            host="localhost",
            port=8123,
            database="stocks",
        )
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: initialize client
    get_client()
    yield
    # Shutdown: close client
    global client
    if client:
        client.close()


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Stock Ticks Dashboard API",
    lifespan=lifespan,
)

# Get the directory where this file is located
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DASHBOARD_DIR, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# =============================================================================
# API ENDPOINTS
# =============================================================================


@app.get("/")
async def root():
    """Serve the main dashboard page."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/latest")
async def get_latest_prices():
    """Get latest price for each symbol."""
    query = """
    SELECT
        symbol,
        argMax(price, timestamp) as price,
        argMax(volume, timestamp) as volume,
        max(timestamp) as last_update
    FROM ticks
    GROUP BY symbol
    ORDER BY symbol
    """
    result = get_client().query(query)
    return [
        {
            "symbol": row[0],
            "price": row[1],
            "volume": row[2],
            "last_update": str(row[3]),
        }
        for row in result.result_rows
    ]


@app.get("/api/history")
async def get_price_history(symbols: str = "", minutes: int = 60):
    """Get price history for selected symbols."""
    if not symbols:
        # Get all symbols if none specified
        symbols_result = get_client().query("SELECT DISTINCT symbol FROM ticks")
        symbol_list = [row[0] for row in symbols_result.result_rows]
    else:
        symbol_list = symbols.split(",")

    if not symbol_list:
        return []

    symbols_str = ", ".join([f"'{s}'" for s in symbol_list])
    time_filter = f"AND timestamp > now() - INTERVAL {minutes} MINUTE" if minutes > 0 else ""

    query = f"""
    SELECT
        timestamp,
        symbol,
        price
    FROM ticks
    WHERE symbol IN ({symbols_str})
      {time_filter}
    ORDER BY timestamp
    """
    result = get_client().query(query)
    return [
        {
            "timestamp": str(row[0]),
            "symbol": row[1],
            "price": row[2],
        }
        for row in result.result_rows
    ]


@app.get("/api/recent")
async def get_recent_ticks(limit: int = 20):
    """Get most recent ticks."""
    query = f"""
    SELECT
        timestamp,
        symbol,
        price,
        volume
    FROM ticks
    ORDER BY timestamp DESC
    LIMIT {limit}
    """
    result = get_client().query(query)
    return [
        {
            "timestamp": str(row[0]),
            "symbol": row[1],
            "price": row[2],
            "volume": row[3],
        }
        for row in result.result_rows
    ]


@app.get("/api/stats")
async def get_stats():
    """Get price statistics by symbol."""
    query = """
    SELECT
        symbol,
        count() as tick_count,
        round(min(price), 2) as min_price,
        round(max(price), 2) as max_price,
        round(avg(price), 2) as avg_price,
        sum(volume) as total_volume
    FROM ticks
    GROUP BY symbol
    ORDER BY symbol
    """
    result = get_client().query(query)
    return [
        {
            "symbol": row[0],
            "tick_count": row[1],
            "min_price": row[2],
            "max_price": row[3],
            "avg_price": row[4],
            "total_volume": row[5],
        }
        for row in result.result_rows
    ]


@app.get("/api/count")
async def get_total_count():
    """Get total tick count."""
    result = get_client().query("SELECT count() FROM ticks")
    return {"count": result.result_rows[0][0]}


@app.get("/api/symbols")
async def get_symbols():
    """Get list of all symbols."""
    result = get_client().query("SELECT DISTINCT symbol FROM ticks ORDER BY symbol")
    return [row[0] for row in result.result_rows]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8502)
