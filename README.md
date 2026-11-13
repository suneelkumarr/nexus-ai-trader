# NEXUS AI TRADER

Production-quality, modular cryptocurrency **paper-trading** platform starting with a virtual **INR 10,000.00** portfolio. The default trading universe is `BTC/USDT`, `ETH/USDT`, and `SOL/USDT`; the market scanner covers a configurable 54-pair Binance spot universe.

## Guarantees
- **Paper Trading Only** — Zero live order placement, zero real-money execution.
- **No Live Derivatives** — Real leverage, margin, futures, and withdrawals are blocked by configuration invariants. The optional futures desk is an isolated-margin **simulation** controlled by `PAPER_FUTURES_ENABLED` and never routes orders to an exchange.
- **Real Market Data Only** — Public CCXT spot feeds. Chart candles are only served from verified stored or downloaded history; unavailable history returns an empty series rather than synthetic prices.
- **Decoupled Architecture** — Independent FastAPI trading backend and React + TypeScript + Three.js frontend connected via REST API and Dependency Injection.
- **Credential Hygiene** — No API token is embedded in source. Set `API_AUTH_TOKEN` on the backend and `VITE_API_AUTH_TOKEN` at frontend build time; rotate any token that was ever committed.

## Documentation
- [System Architecture & Module Responsibilities](docs/ARCHITECTURE.md)
- [Setup & Operations Guide](docs/SETUP.md)

## Quick Start
```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env
docker compose up --build -d
```

