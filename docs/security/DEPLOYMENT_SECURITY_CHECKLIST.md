# NEXUS AI TRADER — Deployment & Production Security Checklist

**Current Release Gate Status:** **BLOCKED — NOT READY FOR LIVE TRADING**  
**Permitted Scope Today:** Local, isolated developer workstation use in **PAPER-ONLY** mode (`TRADING_MODE=paper`, `LIVE_TRADING_ENABLED=false`).

Every gate below MUST be satisfied and verified with recorded evidence before advancing to staged network deployment or ever considering live financial operation.

---

## 1. Financial Safety & Trading Mode Gates (Non-Negotiable)

- [x] `TRADING_MODE=paper`, `MARKET_TYPE=spot`, `LIVE_TRADING_ENABLED=false`, `ALLOW_LEVERAGE=false`, `ALLOW_FUTURES=false`, `ALLOW_WITHDRAWALS=false` verified in `.env.example` and `config.py`.
- [x] Zero calls to CCXT `create_order`, `create_market`, `create_limit`, `withdraw`, `fetch_balance`, or private exchange API keys anywhere in `backend/src`.
- [x] Atomic single-transaction paper settlement (`commit_order_settlement`) with `with_for_update()` locking on PostgreSQL and real `find_duplicate_signal_order(...)` lookup verified.
- [x] `PersistentPaperBroker.execute_strategy_signal` rejects entries on `MarketDataUnavailableError` and records an audit trail.
- [x] AI analysis module (`ai_analysis/`) is strictly read-only/advisory with Pydantic schema validation and zero execution authority.
- [ ] **BLOCKER (`SEC-003`):** Wire autonomous execution loop (`workers/scheduler.py`) and persist `NexusStrategyV1` candle/signal checkpoints in PostgreSQL so restarts cannot replay or skip signals.
- [ ] **BLOCKER (`SEC-007`):** Remove `datetime.now(UTC)` fallback in `parse_ticker_payload` when exchange timestamps are missing; block new entries whenever held open-position MTM quotes are missing.

---

## 2. Authentication, Authorization & API Security Gates

- [ ] **BLOCKER (`SEC-002`):** Implement authentication and RBAC separation (`viewer` vs `operator`) on `/api/v1/terminal/*`, `/api/v1/analysis/*`, and `/api/v1/ws/stream`.
- [ ] **BLOCKER (`SEC-002`):** Enforce rate limiting, request body size limits, and WebSocket handshake origin + token validation.
- [x] Database health check (`DatabaseManager.check_health()`) returns sanitized errors without leaking raw connection exceptions (`SEC-004`).
- [ ] **OPEN (`SEC-008`):** Replace `allow_headers=["*"]` with explicit header allowlists while `allow_credentials=True` is set in `backend/src/nexus/main.py`.

---

## 3. Infrastructure, Container & Network Hardening Gates

- [ ] **BLOCKER (`SEC-006`):** Add non-root `USER` directives to `backend/Dockerfile` and `frontend/Dockerfile`.
- [ ] **BLOCKER (`SEC-006`):** Remove direct host port bindings for PostgreSQL (`5432:5432`) and backend (`8000:8000`) in `docker-compose.yml`; keep DB and API on an internal bridge network behind TLS termination.
- [ ] **BLOCKER (`SEC-006`):** Add `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true`, and memory/CPU resource limits to `docker-compose.yml` services.
- [ ] **BLOCKER (`SEC-006`):** Enable HTTPS/WSS TLS, `server_tokens off`, `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer` in `frontend/nginx.conf`.

---

## 4. Secrets, Logging & Frontend Security Gates

- [x] `.env.example` contains placeholder credentials only (`POSTGRES_PASSWORD=change_me_in_local_env`, empty `AI__API_KEY=`); no `.env` or secret material present on disk.
- [x] `.gitignore` excludes `.env`, `.env.local`, `.env.*.local`, `*.pem`, `*.key`, `postgres_data/`, and `*.db`.
- [x] Structlog scrubber (`logging.py`) redacts secret field names as well as embedded DSN credentials (`_DSN_CRED_RE`), bearer tokens (`_BEARER_RE`), and API key prefixes (`_SK_TOKEN_RE`) inside string values (`SEC-004`).
- [x] Frontend `src/` contains zero `dangerouslySetInnerHTML`, `innerHTML`, `localStorage`, `sessionStorage`, `eval(`, `Function(`, or `document.write`; backtest HTML reports escape dynamic text via `html.escape()`.

---

## 5. Supply Chain, Testing & Release Sign-Off Gates

- [ ] **OPEN (`SEC-009`):** Initialize Git VCS (`git init`), pin reproducible Python dependency lockfiles with hashes, and switch `frontend/Dockerfile` from `npm install` to `npm ci`.
- [ ] **OPEN (`SEC-009`):** Install and pass `pip-audit`, `bandit`, `semgrep`, `trivy`, `gitleaks`, and `osv-scanner` with zero unmitigated Critical/High findings.
- [ ] **OPEN (`SEC-010`):** Run Alembic migrations and concurrent locking/idempotency tests against live `postgres:16-alpine`.
- [ ] **OPEN (`SEC-010`):** Execute Playwright browser E2E suite verifying paper-trading banner, kill switch, and live WebSocket rendering.
- [ ] **LIVE TRADING GATE (DISABLED BY DESIGN):** Explicit dual-control architecture review, dedicated read/trade-scoped exchange API keys (strictly zero withdrawal permissions, IP allowlisted, KMS/Vault-backed), reconciled accounting audit, and human operator sign-off required before `LIVE_TRADING_ENABLED` may ever be reconsidered.

