# NEXUS AI TRADER — System Architecture

## 1. Architectural Vision & Non-Negotiable Invariants

**NEXUS AI TRADER** is a modular, production-grade automated cryptocurrency **paper-trading** platform designed with strict separation between trading core, infrastructure adapters, and the 3D web client.

### Core System Invariants
1. **Paper Trading Only**: Live order placement, real-money transfers, and exchange withdrawals are architecturally impossible. `TradingMode` only permits `PAPER`; configuration validation rejects any attempt to enable live execution.
2. **Spot Markets Only**: Leverage, margin, perpetuals, futures, options, and short-selling beyond spot holdings are explicitly blocked at both configuration and domain risk-guard layers.
3. **Initial Virtual Capital**: Every newly initialized portfolio starts with **INR 10,000.00** (`base_currency = "INR"`, `initial_capital = 10000.00`).
4. **Initial Asset Universe**: Restricted to `BTC/USDT`, `ETH/USDT`, and `SOL/USDT` (configurable via validated environment settings, defaulting strictly to this set).
5. **No Fake Exchange Results**: Market data adapters (`CCXTMarketDataProvider`) fetch real public spot market data from the configured exchange via CCXT and never synthesize or hardcode fake tickers, candles, or order book ticks. Failures propagate explicitly through typed domain exceptions.
6. **Backend / Frontend Independence**: The `frontend` (`React + TypeScript + Three.js`) communicates exclusively over versioned HTTP/REST contracts (`/api/v1/...`) and contains zero trading, pricing, or risk logic.

---

## 2. High-Level Architecture

```
+-----------------------------------------------------------------------+
|                       FRONTEND (Independent)                          |
|   React 18 + TypeScript + Vite + Three.js                             |
|   - 3D Portfolio/Market Telemetry Canvas (NexusScene)                 |
|   - Typed API Client -> HTTP JSON (/api/v1/health, ...)               |
+-----------------------------------+-----------------------------------+
                                    | REST / JSON (CORS-controlled)
                                    v
+-----------------------------------------------------------------------+
|                     BACKEND API LAYER (FastAPI)                       |
|   - Health Probes (/api/v1/health, /health/live, /health/ready)       |
|   - Dependency Injection Container (api/dependencies.py)              |
|   - Request Correlation & Structured Access Logging                   |
+-----------------------------------+-----------------------------------+
                                    | Interfaces (Protocols)
                                    v
+-----------------------------------------------------------------------+
|                    APPLICATION LAYER (Use Cases)                      |
|   - PortfolioService (INR 10,000 init, numpy/pandas valuation)        |
|   - RiskGuard (spot-only, no leverage/withdrawals, pair allowlist)    |
|   - PaperBroker (virtual order matching against live CCXT quotes)     |
|   - StrategyEngine (pandas/numpy signal pipeline)                     |
|   - Worker Scheduler (automated paper-trading loop)                   |
+-------------------+-------------------------------+-------------------+
                    |                               |
                    v                               v
+-----------------------------------+ +---------------------------------+
|         DOMAIN LAYER              | |      INFRASTRUCTURE LAYER       |
| - Pure Python & Pydantic Models   | | - PostgreSQL (SQLAlchemy 2 +    |
| - Enums (PAPER, SPOT, Sides)      | |   asyncpg / Alembic migrations) |
| - Abstract Protocols/Interfaces   | | - CCXT Spot Market Data Adapter |
| - Domain Exceptions               | | - Structlog JSON Logger         |
+-----------------------------------+ +---------------------------------+
```

---

## 3. Repository Structure

```text
nexus/
├── .env.example                 # Template environment variables (zero secrets)
├── .gitignore                   # Git exclusions for venv, node_modules, .env
├── docker-compose.yml           # PostgreSQL, Backend API, Frontend services
├── README.md                    # Project overview and quick start
├── docs/
│   ├── ARCHITECTURE.md          # This architecture specification
│   └── SETUP.md                 # Local, Docker, and DB migration guide
├── backend/
│   ├── Dockerfile               # Multi-stage Python 3.12+ container
│   ├── pyproject.toml           # Python dependencies, pytest, ruff, mypy config
│   ├── alembic.ini              # Alembic configuration
│   ├── alembic/                 # Database schema migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 20261112_0001_initial_schema.py
│   ├── src/nexus/
│   │   ├── main.py              # FastAPI application factory & lifespan
│   │   ├── core/                # Config, exceptions, structured logging
│   │   ├── domain/              # Enums, entities, interface protocols
│   │   ├── application/         # Paper broker, risk guard, portfolio & strategy
│   │   ├── infrastructure/      # DB ORM/session, CCXT read-only spot adapter
│   │   ├── api/                 # FastAPI routers & DI providers
│   │   └── workers/             # Automated trading loop scheduler
│   └── tests/                   # Unit and API integration tests
└── frontend/
    ├── Dockerfile               # Node build + Nginx/static runtime
    ├── package.json             # React, TypeScript, Three.js, Vite
    ├── tsconfig.json            # Strict TypeScript compiler configuration
    ├── vite.config.ts           # Vite bundler & proxy configuration
    └── src/                     # Decoupled UI, API client, Three.js canvas
```

---

## 4. Module Responsibilities

### 4.1 `nexus.core`
- **`config.py`**: Loads environment settings via `pydantic-settings`. Enforces invariants at startup: `trading_mode == "paper"`, `market_type == "spot"`, `live_trading_enabled is False`, `allow_leverage is False`, `allow_futures is False`, `allow_withdrawals is False`, `initial_capital_inr == Decimal("10000.00")`. Credentials (e.g., DB password, optional read-only exchange keys) are never hardcoded.
- **`logging.py`**: Configures `structlog` + stdlib logging bridge. Outputs machine-readable JSON in production and colored key-value logs in local development. Automatically binds `service`, `environment`, `request_id` (via `contextvars`), and redacts sensitive keys (`password`, `secret`, `api_key`, `token`).
- **`exceptions.py`**: Typed hierarchy (`NexusError`, `ConfigurationInvariantError`, `RiskViolationError`, `MarketDataUnavailableError`, `InsufficientBalanceError`, `DatabaseUnavailableError`).

### 4.2 `nexus.domain`
- **`enums.py`**: `TradingMode` (`PAPER` only), `MarketType` (`SPOT` only), `OrderSide` (`BUY`, `SELL`), `OrderType` (`MARKET`, `LIMIT`), `OrderStatus`, `SignalAction`.
- **`models.py`**: Pure domain data models (`TickerQuote`, `OHLCVBar`, `OrderRequest`, `PaperOrder`, `PaperFill`, `PortfolioSnapshot`, `AssetHolding`, `TradingSignal`). Uses `Decimal` for financial precision in ledgers and `pandas`/`numpy` in quantitative analysis.
- **`interfaces.py`**: `typing.Protocol` abstractions enabling Dependency Injection and testability without mocks inside production adapters:
  - `MarketDataProvider`: `fetch_ticker(symbol)`, `fetch_ohlcv(symbol, timeframe, limit)`, `fetch_inr_per_usdt()`, `health_check()`.
  - `RiskGuard`: `validate_order(request, portfolio)`.
  - `PaperExecutionEngine`: `execute_order(request, quote, portfolio)`.
  - `Strategy`: `evaluate(symbol, candles_df)`.
  - `PortfolioRepository` & `OrderRepository`: Persistence contracts.

### 4.3 `nexus.infrastructure`
- **`db/base.py` & `db/session.py`**: Async SQLAlchemy 2.0 engine (`postgresql+asyncpg`), connection pool settings, `check_database_health()` probe for readiness endpoints.
- **`db/models.py`**: Relational schema for:
  - `portfolios`: Tracks virtual account (`name`, `base_currency='INR'`, `initial_capital=10000.00`, `cash_balance_inr`, `trading_mode='paper'`, `market_type='spot'`).
  - `portfolio_balances`: Per-asset spot holdings (`asset`, `free_qty`, `locked_qty`, `avg_entry_price_usdt`).
  - `paper_orders`: Virtual order intents and lifecycle state (`symbol`, `side`, `order_type`, `quantity`, `limit_price_usdt`, `status`, `strategy_name`).
  - `paper_fills`: Simulated execution ledger (`order_id`, `executed_price_usdt`, `executed_qty`, `fee_usdt`, `inr_per_usdt_rate`, `slippage_bps`).
  - `market_snapshots`: Historical real CCXT OHLCV/ticker snapshots persisted for auditability and backtesting.
  - `strategy_runs` & `system_events`: Structured audit trail of automated decisions and risk rejections.
- **`exchange/ccxt_market_data.py`**: Asynchronous CCXT adapter (`ccxt.async_support`) pinned to `defaultType="spot"`. Never creates exchange orders or accesses withdrawal endpoints (`create_order`, `withdraw` are not implemented/exposed). Validates returned ticker/OHLCV payloads and raises `MarketDataUnavailableError` if exchange data is missing or unreachable.

### 4.4 `nexus.application`
- **`risk_guard.py`**: Enforces symbol allowlist (`BTC/USDT`, `ETH/USDT`, `SOL/USDT`), spot-only balance checks (no shorting/leverage), max position allocation, and strict rejection of non-paper/non-spot requests.
- **`paper_broker.py`**: Orchestrates `RiskGuard` + `MarketDataProvider` real quotes + slippage/fee accounting to settle virtual spot fills in-memory or against repositories.
- **`portfolio_service.py`**: Initializes the INR 10,000 portfolio, tracks INR <-> USDT valuation, and computes return/drawdown metrics via `numpy`/`pandas`.
- **`strategy_engine.py`**: Converts validated OHLCV series into `pandas.DataFrame` and computes deterministic indicators using `numpy`/`pandas` (e.g., EMA crossover / RSI framework) to produce `TradingSignal` objects.

### 4.5 `nexus.api`
- **`dependencies.py`**: FastAPI dependency providers wiring `Settings`, async DB sessions, `CCXTMarketDataProvider`, `RiskGuard`, and `PaperBroker`.
- **`v1/health.py`**:
  - `GET /api/v1/health`: Comprehensive service status (app metadata, paper/spot mode assertions, DB & market feed status).
  - `GET /api/v1/health/live`: Liveness probe (process alive, zero external I/O).
  - `GET /api/v1/health/ready`: Readiness probe (verifies PostgreSQL connectivity and configuration invariants; returns HTTP `503` when DB is unavailable).

### 4.6 `nexus.workers`
- **`scheduler.py`**: Automated paper-trading loop runner accepting injected `MarketDataProvider`, `Strategy`, `PaperBroker`, and `PortfolioService`.

### 4.7 `frontend`
- Completely standalone TypeScript SPA (`React + Vite + Three.js`).
- **`services/apiClient.ts`**: Fetches `/api/v1/health` and future portfolio endpoints via `VITE_API_BASE_URL`.
- **`components/NexusScene.tsx`**: Interactive Three.js 3D orbital core visualizing the three initial spot pairs (`BTC`, `ETH`, `SOL`) around the INR 10,000 virtual capital core, reacting cleanly to container resize and WebGL disposal.

---

## 5. Dependency Injection Strategy

All cross-layer dependencies flow inward toward `nexus.domain.interfaces`:
- FastAPI endpoints declare dependencies via `Depends(...)` in `api/dependencies.py`.
- Application services (`PaperBroker`, `StrategyEngine`, `PortfolioService`) receive protocol implementations in `__init__`.
- Unit and integration tests substitute in-memory fakes/stubs at the DI boundary (e.g., `app.dependency_overrides`) without altering or polluting production adapters with fake exchange data.

---

## 6. Security & Configuration Management

- Secrets (`POSTGRES_PASSWORD`, optional read-only exchange keys) live exclusively in `.env` (git-ignored) and environment variables injected at runtime.
- `.env.example` provides safe placeholder defaults for local development.
- `Settings` marks secret fields with `pydantic.SecretStr` and structured logging automatically masks secret keys.
- Production CCXT adapter runs in public read-only spot mode by default (no API keys required to fetch public spot tickers and OHLCV candles).

