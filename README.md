# ExpiryFlow

A fullstack platform for downloading, visualizing, and backtesting historical F&O options data from Dhan. Built for systematic options strategy research.

## Features

- **Data Download** — Fetch historical OHLCV data for expired option contracts (rolling options) from Dhan API with rate limiting, chunked downloads, and duplicate detection
- **ATM Straddle Visualization** — Intraday combined CE+PE premium chart and table with date/expiry selectors, spot overlay toggle
- **Dynamic Straddle Backtester** — Backtest ATM straddle rolling strategy with bar-by-bar equity curve, drawdown, trade log, daily P&L, and full metrics
- **Editable Commissions** — Slab-based turnover commission structure (verified against Zerodha F&O Options) with configurable lot sizes per symbol
- **IST Timestamps** — All data stored in IST for natural market-hours queries

## Stack

- **Backend**: FastAPI, SQLite (config/commissions), DuckDB (market data), httpx
- **Frontend**: React, Vite, TypeScript, ShadCN UI, Zustand, TradingView Lightweight Charts
- **Data**: DuckDB for high-performance time-series storage and backtesting

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
fastapi dev main.py
```

Runs on http://localhost:8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on http://localhost:5173

## Usage

1. Open http://localhost:5173
2. Enter your Dhan Client ID, API Key, and API Secret
3. Login with your PIN and TOTP code
4. **Dashboard** — Download historical options data (multi-expiry, multi-strike, date chunking)
5. **Straddle** — Visualize intraday ATM straddle premium with interactive chart
6. **Backtest** — Run dynamic straddle strategy backtests with configurable capital, lot sizing, and commission slabs
7. **Commissions** — Edit turnover-based commission slabs and lot sizes

## Pages

| Route | Description |
|-------|-------------|
| `/dashboard` | Download controls, progress tracking, download history |
| `/straddle` | ATM straddle intraday chart + data table |
| `/backtest` | Dynamic straddle backtester with equity/drawdown curves |
| `/commissions` | Editable commission slabs and lot sizes |

## Project Structure

```
backend/
  main.py              # FastAPI app entrypoint
  config.py            # Underlying metadata, lot sizes, margin/commission constants
  database.py          # SQLite setup + seed defaults
  duckdb_manager.py    # DuckDB schema + migrations
  models.py            # ORM models (ApiConfig, Session, CommissionSlab, LotSize)
  schemas.py           # Pydantic request/response models
  dependencies.py      # Rate limiter, auth deps
  routers/
    auth_router.py     # Login, session, logout
    config_router.py   # API config CRUD
    download_router.py # Download jobs + active/history
    straddle_router.py # ATM straddle data queries
    backtest_router.py # Backtest execution
    commissions_router.py # Commission slabs + lot sizes CRUD
    health_router.py   # Health check, underlyings metadata
  services/
    dhan_auth_service.py   # Dhan OAuth
    dhan_data_service.py   # Dhan rolling options API (IST timestamps)
    download_service.py    # Job orchestration, duplicate detection
    backtest_service.py    # Dynamic straddle backtesting engine
    session_service.py     # Session validation

frontend/
  src/
    api/               # Backend API clients (auth, config, downloads, straddle, backtest)
    store/             # Zustand state (auth, config, download with localStorage persistence)
    pages/             # Dashboard, Straddle, Backtest, Commissions, Setup, Login
    components/        # Download controls/progress, global download indicator, UI
    layouts/           # Auth & Dashboard layouts with navigation
```

## Backtester Strategy

The dynamic straddle backtester implements:
- **Entry**: Sell ATM CE + PE at market open (nearest strike to spot)
- **Roll**: If spot moves to a new ATM strike, exit current straddle and sell new ATM
- **Exit**: Close all positions at last bar of each day (no overnight carry)
- **Sizing**: Fixed lots, fixed money allocation, or fixed % of capital
- **Commissions**: Slab-based (brokerage, STT, exchange txn, GST, SEBI, stamp duty)
- **Margin**: 11.33% of spot x lot_size x lots

## Commission Structure (Default — Zerodha F&O Options)

| Component | Slab 1 (≤1L) | Slab 2 (≤10L) | Slab 3 (≤1Cr) |
|-----------|--------------|---------------|----------------|
| Brokerage | ₹20/order | ₹20/order | ₹20/order |
| STT (sell) | 0.1% | 0.1% | 0.1% |
| Exchange Txn | 0.03553% | 0.03553% | 0.03553% |
| GST | 18% | 18% | 18% |
| SEBI | ₹10/Cr | ₹10/Cr | ₹10/Cr |
| Stamp Duty (buy) | 0.004% | 0.003% | 0.003% |

GST base = brokerage + exchange txn + SEBI charges

## License

MIT
