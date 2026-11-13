# NEXUS AI TRADER — Setup & Operations Guide

## 1. Prerequisites

- **Docker & Docker Compose** (recommended for full stack with PostgreSQL)
- Or for local bare-metal development:
  - **Python 3.12+**
  - **Node.js 20+** and **npm**
  - **PostgreSQL 16+**

---

## 2. Environment Configuration

Copy `.env.example` to `.env` at the repository root and set a strong `POSTGRES_PASSWORD`:

```bash
cp .env.example .env
```

> **Security Note**: Never commit `.env` or hardcode API secrets. Set a strong `API_AUTH_TOKEN` on the backend and pass the same value as `VITE_API_AUTH_TOKEN` at frontend build time. The frontend intentionally has **no fallback token**. Any token that was previously committed must be treated as compromised and rotated. Public spot market data via CCXT works without exchange API keys.

### Non-Negotiable Safety Settings
The backend fails fast at startup if any of the following are modified away from paper/spot defaults:
- `TRADING_MODE=paper`
- `MARKET_TYPE=spot`
- `LIVE_TRADING_ENABLED=false`
- `ALLOW_LEVERAGE=false`
- `ALLOW_FUTURES=false`
- `ALLOW_WITHDRAWALS=false`
- `INITIAL_CAPITAL_INR=10000.00` (must be positive)
- `ALLOWED_SYMBOLS` must contain valid spot pairs

`PAPER_FUTURES_ENABLED=true` enables only the isolated-margin **futures simulator**. Live futures/leverage remain blocked by `ALLOW_FUTURES=false` and `LIVE_TRADING_ENABLED=false`.

---

## 3. Running with Docker Compose

Build and start PostgreSQL, the FastAPI backend (runs Alembic migrations automatically), and the React + Three.js frontend:

```bash
docker compose up --build -d
```

Verify health endpoints:
- **Liveness**: `http://localhost:8000/api/v1/health/live`
- **Readiness**: `http://localhost:8000/api/v1/health/ready`
- **Full Health Summary**: `http://localhost:8000/api/v1/health`
- **OpenAPI Docs**: `http://localhost:8000/docs`
- **Frontend UI**: `http://localhost:3000`

Stop the stack:
```bash
docker compose down
```

---

## 4. Local Backend Setup (Without Docker)

Python 3.12–3.13 is recommended; 3.14 works but emits upstream asyncio deprecation warnings from test dependencies.

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev]"
```

Run database migrations (ensure PostgreSQL is running and `POSTGRES_HOST=localhost` in `.env`):

```bash
alembic upgrade head
```

Start the FastAPI development server:

```bash
uvicorn nexus.main:app --reload --host 0.0.0.0 --port 8000
```

Run unit & integration tests:

```bash
pytest
```

---

## 5. Local Frontend Setup (Without Docker)

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and communicates independently with `VITE_API_BASE_URL` (default `http://localhost:8000`).

Typecheck and production build:

```bash
npm run typecheck
npm run build
```

