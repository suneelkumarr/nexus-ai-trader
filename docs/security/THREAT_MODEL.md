# NEXUS AI TRADER — Threat Model

## 1. System Assets
1. **Virtual Capital & Ledger Integrity:** INR 10,000.00 virtual balance, `portfolios`, `portfolio_balances`, `paper_orders`, `paper_fills`, `paper_positions`, `trade_ledger`, `risk_states`.
2. **Future-Proof Paper/Live Isolation Invariant:** Guarantees that paper mode can never touch real exchange accounts or private order APIs.
3. **Secrets & Credentials:** `POSTGRES_PASSWORD`, `AI__API_KEY`, `DATABASE_URL_OVERRIDE`.
4. **System Availability & Audit Logs:** FastAPI API server, WebSocket telemetry stream, structured logs, historical candle database (`market_snapshots`).
5. **Market Decision Integrity:** Closed UTC candles, Strategy Engine V1 indicators/signals, Advisory AI JSON assessments.

---

## 2. Trust Boundaries & Data Flows

```
[Public Exchange REST/WS] --(Untrusted External Market Data)--> [TB-1: CCXTPublicExchangeClient + CandleValidator]
[Frankfurter FX API]      --(Untrusted External FX Rate)   --> [TB-1: httpx.AsyncClient]
                                                                       |
                                                                       v
[OpenAI-Compatible LLM]   <--(Validated JSON Features Only)--- [TB-2: MarketAnalysisService + AIResponseValidator]
                                                                       | (Advisory Read-Only JSON)
                                                                       v
[PostgreSQL 16 DB]        <--(Parameterized SQLAlchemy ORM)--- [TB-3: FastAPI Backend / PersistentPaperBroker / IndependentRiskManager]
                                                                       ^
                                                                       | HTTP / WebSocket (JSON)
[Nginx Reverse Proxy]     <--(TLS Missing / Port 3000 HTTP)--- [TB-4: React SPA + Three.js Browser Client]
                                                                       ^
                                                                       |
                                                            [Untrusted Network / Operator Browser]
```

### Trust Boundary Summary
- **TB-1 (External Exchange & FX Feeds):** Unauthenticated public REST/WS responses are **untrusted input** susceptible to malformed payloads, stale/incomplete bars, negative values, or outages. Mitigated by `CandleValidator`, `to_positive_decimal`, and `MarketDataUnavailableError` fail-closed rejections.
- **TB-2 (External LLM / AI Provider):** AI model output is **untrusted** and susceptible to prompt injection (e.g., crafted market commentary or compromised upstream LLM returning execution directives or spoofed prices). Mitigated by `AIResponseValidator` strict 7-key schema, invented-price bounds check, regex execution-directive blocking, and zero Python module coupling to broker/risk/exchange layers.
- **TB-3 (Backend API <-> PostgreSQL):** Multi-table financial state updates require ACID atomicity and row locks. Previously split across 4–5 commits; remediated via `commit_order_settlement` inside `session.begin()`.
- **TB-4 (Client Browser <-> Nginx <-> FastAPI):** Currently an **UNAUTHENTICATED** trust boundary (`SEC-002`). Any network peer able to reach `localhost:3000` or `0.0.0.0:8000` can invoke state-changing `POST /api/v1/terminal/emergency-stop` or heavy compute `POST /api/v1/terminal/backtest`.

---

## 3. STRIDE Threat Matrix

| Threat Category | Concrete Threat | Affected Boundary | Existing Control | Residual Gap |
|---|---|---|---|---|
| **Spoofing** | Forged operator triggers emergency stop or connects to WS stream | TB-4 | None | **SEC-002 (High):** No operator auth/JWT/RBAC |
| **Tampering** | Race condition or mid-flight DB crash splits order fill from cash deduction | TB-3 | Check constraints + `commit_order_settlement` (Fixed) | Needs multi-worker concurrency integration test under live Postgres |
| **Tampering (AI)** | LLM prompt injection embeds order-execution or risk-override command | TB-2 | `AIResponseValidator` regex + `executable_signal=False` | Covered by `test_financial_safety_invariants.py` |
| **Repudiation** | Missing audit order record or untracked manual action | TB-3 | `paper_orders`, `trade_ledger`, `request_id` logs | Local stdout logs; no remote immutable log shipping |
| **Information Disclosure** | Embedded DB password or bearer key leaked via exception `error=str(exc)` | TB-3 | Key + regex value scrubbing in `logging.py`, sanitized `session.py` health (Fixed) | `/terminal/settings` & `/health` remain unauthenticated on network |
| **Denial of Service** | Repeated `POST /terminal/backtest` (2,000 bars) stalls FastAPI asyncio loop | TB-4 | Offloaded via `asyncio.to_thread` (Fixed) | **SEC-002/SEC-005:** No API rate limiting or auth |
| **Elevation of Privilege** | Container escape runs as `root` inside `nexus-backend` or `nexus-frontend` | Infra | None | **SEC-006 (Medium):** Non-root `USER`, `cap_drop`, `read_only` missing |

