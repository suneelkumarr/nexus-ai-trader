# NEXUS AI TRADER

Production-quality, modular cryptocurrency **spot paper-trading** platform starting with a virtual **INR 10,000.00** portfolio across `BTC/USDT`, `ETH/USDT`, and `SOL/USDT`.

## Guarantees
- **Paper Trading Only** — Zero live order placement, zero real-money execution.
- **Spot Only** — No leverage, margin, futures, or withdrawals.
- **Real Market Data Only** — Public CCXT spot feeds without fabricated/fake exchange results.
- **Decoupled Architecture** — Independent FastAPI trading backend and React + TypeScript + Three.js frontend connected via REST API and Dependency Injection.

## Documentation
- [System Architecture & Module Responsibilities](docs/ARCHITECTURE.md)
- [Setup & Operations Guide](docs/SETUP.md)

## Quick Start
```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env
docker compose up --build -d
```

