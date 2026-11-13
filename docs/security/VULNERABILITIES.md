# NEXUS AI TRADER — Prioritized Vulnerability Report & Remediation Ledger

This report documents the verification and remediation status of all 10 security findings grounded in repository inspection and automated test execution.

---

### Finding ID: SEC-001
- **Title:** Non-Atomic Multi-Transaction Order Settlement and Missing Concurrent Row Locking
- **Severity:** **Critical** (CVSS v4.0 Estimated Vector: Financial Ledger Integrity / High impact on local consistency)
- **Affected component:** `backend/src/nexus/application/persistent_paper_broker.py`, `backend/src/nexus/infrastructure/db/paper_repository.py`, `backend/src/nexus/domain/interfaces.py`
- **Root cause:** Lack of single `session.begin()` transaction boundary across order, balance, position, ledger, and risk tables.
- **Remediation:** Implemented `commit_order_settlement` inside a single `async with self._session_factory() as session, session.begin():` transaction with PostgreSQL `with_for_update()` locking on `PortfolioORM` and `RiskStateORM`.
- **Verification:** Verified by fault-injection test `test_invariant_atomic_settlement_rolls_back_completely_on_db_fault` in `backend/tests/security/test_financial_safety_invariants.py`.
- **Status:** **Fixed**

---

### Finding ID: SEC-002
- **Title:** Missing Authentication, Authorization, and Rate Limiting on FastAPI Control, Settings, and WebSocket Endpoints
- **Severity:** **High** (OWASP API2:2023 Broken Authentication, API5:2023 Broken Function Level Authorization, API4:2023 Unrestricted Resource Consumption)
- **Affected component:** `backend/src/nexus/core/security.py`, `backend/src/nexus/api/v1/terminal.py`, `backend/src/nexus/api/v1/analysis.py`, `frontend/src/services/apiClient.ts`
- **Root cause:** Initial development phases omitted operator authentication dependencies and reverse-proxy/in-memory rate limiters.
- **Remediation:** Implemented `require_admin_auth` (constant-time Bearer JWT / `X-Nexus-API-Key` verification), WebSocket token query verification, in-memory sliding-window IP rate limiter (`SecurityRateLimitMiddleware`), and 2MB payload size cap (`413 Payload Too Large`).
- **Verification:** Verified by `test_protected_routes_enforce_authentication` and `test_oversized_payload_rejected_with_413` in `tests/security/test_api_security.py`.
- **Status:** **Fixed**

---

### Finding ID: SEC-003
- **Title:** Unwired Runtime Trading Orchestrator & Volatile In-Memory Signal Deduplication Across Restarts
- **Severity:** **High** (CWE-362 / CWE-841 Improper Enforcement of Behavioral Workflow)
- **Affected component:** `backend/src/nexus/workers/scheduler.py`, `backend/src/nexus/application/strategy/v1_engine.py`
- **Root cause:** Autonomous cycle runner was not connected to `PersistentPaperBroker` and strategy deduplication resided only in volatile RAM.
- **Remediation:** Implemented `AutonomousPaperTradingOrchestrator` directly wiring `MarketDataService`, `NexusStrategyV1`, and `PersistentPaperBroker` with kill-switch gating; added `export_checkpoints()` and `import_checkpoints()` to `NexusStrategyV1`.
- **Verification:** Verified by `test_orchestrator_halts_cleanly_when_kill_switch_active` in `tests/unit/test_scheduler_orchestrator.py`.
- **Status:** **Fixed**

---

### Finding ID: SEC-004
- **Title:** Unscrubbed String Exception Values in Structured Logs & Raw DB Exception Exposure on Unauthenticated Health Endpoints
- **Severity:** **Medium** (CWE-209 Generation of Error Message Containing Sensitive Information, CWE-532)
- **Affected component:** `backend/src/nexus/core/logging.py`, `backend/src/nexus/infrastructure/db/session.py` (`check_health`)
- **Root cause:** Pattern-based regex value scrubbing was omitted from `logging.py`, and raw exception messages were returned in health probes.
- **Remediation:** Added regex scrubbing (`_DSN_CRED_RE`, `_BEARER_RE`, `_SK_TOKEN_RE`) in `logging.py`, and updated `DatabaseManager.check_health()` to return sanitized `"Database connectivity check failed"`.
- **Verification:** Verified by `test_invariant_log_scrubbing_and_sanitized_db_health_error` in `tests/security/test_financial_safety_invariants.py`.
- **Status:** **Fixed**

---

### Finding ID: SEC-005
- **Title:** Synchronous Event-Loop Blocking in `POST /api/v1/terminal/backtest` & Missing `client_order_id` Guard on Direct `submit_order`
- **Severity:** **Medium** (OWASP API4:2023 Unrestricted Resource Consumption / CWE-362)
- **Affected component:** `backend/src/nexus/api/v1/terminal.py`, `backend/src/nexus/application/persistent_paper_broker.py`
- **Root cause:** Missing `asyncio.to_thread` offload and optional `None` persistence of `client_order_id`.
- **Remediation:** Wrapped `OutOfSampleBacktestRunner().run_suite` in `await asyncio.to_thread(...)`, enforced automatic `ord:<order_id>` idempotency key assignment in `PersistentPaperBroker.submit_order`, and handled `MarketDataUnavailableError` inside `execute_strategy_signal`.
- **Verification:** Verified by `test_terminal_backtest_validation_and_execution` and `test_invariant_mandatory_idempotency_key_and_outage_halting`.
- **Status:** **Fixed**

---

### Finding ID: SEC-006
- **Title:** Container Least-Privilege Deficits, Missing Nginx Security Headers (CSP / Frame / MIME), and Plaintext Port Exposure
- **Severity:** **Medium** (CWE-250 Execution with Unnecessary Privileges, CWE-693 Protection Mechanism Failure)
- **Affected component:** `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`
- **Root cause:** Development Compose/Docker setup lacked non-root user directives and defense-in-depth headers.
- **Remediation:** Added dedicated non-root `appuser` (UID 10001) in `backend/Dockerfile`, switched frontend to deterministic `npm ci`, configured strict Nginx CSP, clickjacking (`X-Frame-Options: DENY`), MIME sniffing (`nosniff`), and `server_tokens off`, and restricted Docker Compose port bindings to `127.0.0.1` loopback with `cap_drop: [ALL]`.
- **Status:** **Fixed**

---

### Finding ID: SEC-007
- **Title:** Market Feed Freshness Masking on Missing Exchange Timestamp & Silent MTM Cost-Basis Fallback
- **Severity:** **Medium** (Trading Safety / Stale Data Risk)
- **Affected component:** `backend/src/nexus/infrastructure/exchange/ccxt_client.py`, `backend/src/nexus/application/risk_manager.py`
- **Root cause:** Fallback assigned local `datetime.now(UTC)` when CCXT omitted exchange timestamps, and missing open-position quotes defaulted to entry cost.
- **Remediation:** Rejected missing or non-positive exchange ticker timestamps with `MarketDataUnavailableError`, and updated `IndependentRiskManager.check_global_entry_gates` to halt new entries if market quotes for open positions are unavailable.
- **Verification:** Verified by `test_parse_ticker_payload_requires_verified_timestamp` in `tests/unit/test_ccxt_public_client.py`.
- **Status:** **Fixed**

---

### Finding ID: SEC-008
- **Title:** Permissive CORS `allow_headers=["*"]` & Default Fixed `inr_per_usdt=85.00` in API Backtest Endpoint
- **Severity:** **Low** (CWE-942 / Data Fidelity)
- **Affected component:** `backend/src/nexus/main.py`, `backend/src/nexus/api/v1/terminal.py`
- **Root cause:** Broad development CORS header wildcard and default constant FX parameter.
- **Remediation:** Restricted `allow_headers` to explicit allowlist (`["Authorization", "Content-Type", "Accept", "X-Request-ID", "X-Nexus-API-Key"]`) and wired live dynamic INR/USDT FX conversion rate fetching into terminal backtest execution.
- **Verification:** Verified by `test_terminal_backtest_validation_and_execution`.
- **Status:** **Fixed**

---

### Finding ID: SEC-009
- **Title:** Open Python Dependency Ranges, Absent Git VCS, and Missing Lockfiles
- **Severity:** **Medium** (OWASP A06:2021 / Software Supply Chain)
- **Affected component:** `backend/requirements.lock`, `backend/Dockerfile`, `.git`
- **Root cause:** Initial local setup lacked version control and frozen dependency manifests.
- **Remediation:** Initialized Git repository with validated `.gitignore` excluding `.env`, generated hash lockfile `requirements.lock`, and pinned container installation to exact lockfile versions.
- **Status:** **Fixed**

---

### Finding ID: SEC-010
- **Title:** Absence of Live PostgreSQL Execution Verification
- **Severity:** **Medium** (Assurance Gap)
- **Affected component:** `backend/tests/security/test_financial_safety_invariants.py`, `alembic`
- **Root cause:** Previous automated test runs were restricted to in-memory SQLite.
- **Remediation:** Successfully ran Alembic migrations against live Aiven PostgreSQL (`defaultdb`), verified connectivity, and added automated live PostgreSQL test in `test_financial_safety_invariants.py`.
- **Verification:** Verified by `test_invariant_live_postgresql_schema_when_configured` (PASSED).
- **Status:** **Fixed**
