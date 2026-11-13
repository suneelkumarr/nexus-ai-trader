# NEXUS AI TRADER — Dependency & Supply Chain Audit

**Audit Date:** 2026-11-12  
**Workspace:** `d:\Nexus`  
**VCS Status:** Not a Git repository (`git status` exited `1`: `fatal: not a git repository`)

---

## 1. Executive Summary

- **Frontend (`npm audit --json`):** Executed cleanly with exit code `0`. **0 vulnerabilities** reported across `170` total audited packages (`38` production, `51` development, `82` optional).
- **Backend Python Environment:** Installed versions were verified via `pip list --format=json`. Automated Python/container/SAST/secret vulnerability scanners (`pip-audit`, `bandit`, `semgrep`, `trivy`, `gitleaks`, `osv-scanner`) are **NOT installed** in this environment and therefore were **NOT EXECUTED** (`SEC-009`).
- **Build & Packaging Risks:** `backend/pyproject.toml` specifies open `<major+1` upper bounds without a committed lockfile, and `frontend/Dockerfile` uses `npm install` rather than deterministic `npm ci`.

---

## 2. Backend Python Dependency Inventory

Observed declared constraints in `backend/pyproject.toml` (`requires-python = ">=3.12"`) vs. exact installed versions in `backend/.venv` (from `pip list --format=json`):

| Package | Declared Range (`pyproject.toml`) | Installed Version (`.venv`) | Role |
| :--- | :--- | :--- | :--- |
| `fastapi` | `>=0.115.0,<1.0.0` | `0.162.5` | Web / API framework |
| `starlette` | *(transitive via fastapi)* | `1.10.0` | ASGI toolkit |
| `uvicorn[standard]` | `>=0.32.0,<1.0.0` | `0.54.0` | ASGI server |
| `pydantic` | `>=2.9.0,<3.0.0` | `2.14.3` | Schema & runtime validation |
| `pydantic_core` | *(transitive via pydantic)* | `2.50.4` | Core validation engine |
| `pydantic-settings` | `>=2.6.0,<3.0.0` | `2.16.2` | Environment configuration |
| `SQLAlchemy[asyncio]` | `>=2.0.35,<3.0.0` | `2.1.8` | ORM & async DB sessions |
| `alembic` | `>=1.14.0,<2.0.0` | `1.20.1` | Schema migrations |
| `asyncpg` | `>=0.30.0,<1.0.0` | `0.32.0` | Async PostgreSQL driver |
| `psycopg[binary]` | `>=3.2.0,<4.0.0` | `3.3.9` | PostgreSQL driver |
| `aiosqlite` | *(dev/test async SQLite)* | `0.22.1` | In-memory/test SQLite driver |
| `ccxt` | `>=4.4.0,<5.0.0` | `4.5.92` | Exchange public market data SDK |
| `httpx` | `>=0.27.0,<1.0.0` | `0.28.1` | Async HTTP client (AI & API) |
| `httpcore` | *(transitive)* | `1.0.9` | HTTP transport |
| `aiohttp` | *(transitive via ccxt)* | `3.14.5` | Async HTTP transport |
| `requests` | *(transitive)* | `2.34.2` | Sync HTTP client |
| `urllib3` | *(transitive)* | `2.8.0` | HTTP connection pool |
| `cryptography` | *(transitive)* | `50.0.2` | TLS/crypto primitives |
| `certifi` | *(transitive)* | `2026.10.23` | CA root bundle |
| `pandas` | `>=2.2.0,<3.0.0` | `2.3.3` | Market data & indicator frames |
| `numpy` | `>=2.1.0,<3.0.0` | `2.5.4` | Numeric indicator computations |
| `structlog` | `>=24.4.0,<26.0.0` | `25.5.0` | Structured JSON logging |
| `orjson` | *(runtime JSON)* | `3.13.0` | Fast JSON serialization |
| `pytest` | *(dev)* | `8.4.2` | Test runner |
| `pytest-asyncio` | *(dev)* | `0.26.0` | Async test harness |
| `pytest-cov` | *(dev)* | `6.3.0` | Coverage plugin |
| `mypy` | *(dev)* | `1.20.2` | Static type checker |
| `ruff` | *(dev)* | `0.17.4` | Linter & formatter |

### Python Supply Chain Observations
1. **Unpinned Lockfile (`SEC-009`):** `pyproject.toml` permits minor/patch drift across rebuilds. Generate and commit a hash-verified lockfile (`uv.lock` or `requirements.lock` via `pip-compile --generate-hashes`) before staging or production builds.
2. **High-Sensitivity Packages:** `ccxt` (`4.5.92`), `aiohttp` (`3.14.5`), `cryptography` (`50.0.2`), `starlette` (`1.10.0`), `fastapi` (`0.162.5`), and `urllib3` (`2.8.0`) sit directly on external network or parsing boundaries and require continuous CVE monitoring via `pip-audit` / `osv-scanner`.

---

## 3. Frontend Dependency Audit (`frontend/package.json` & `npm audit`)

Declared core packages in `frontend/package.json`:
- `react`: `^18.3.1`
- `three`: `^0.170.0`
- `tailwindcss`: `^4.3.5`
- `lucide-react`: `^1.72.0`
- `vite`: `^6.0.1`
- `typescript`: `^5.6.3`

Observed `npm audit --json` output (run in `d:\Nexus\frontend`):
- **Exit Code:** `0`
- **Total Vulnerabilities:** `0` (Critical: `0`, High: `0`, Moderate: `0`, Low: `0`, Info: `0`)
- **Audited Package Counts:** `prod: 38`, `dev: 51`, `optional: 82`, `total: 170`

### Frontend Build Reproducibility Note
- `frontend/Dockerfile` invokes `npm install` rather than `npm ci`, allowing lockfile drift if `package-lock.json` differs from `package.json`. Replace with `npm ci --omit=dev` (or build-stage `npm ci`) for reproducible container builds (`SEC-009`).

---

## 4. Security Scanner Execution Status

To maintain strict audit accuracy, tools missing from both system `PATH` and `backend/.venv` were **not** approximated or simulated:

| Tool | Category | Availability (`PATH` / `.venv`) | Execution Status | Required Follow-Up |
| :--- | :--- | :--- | :--- | :--- |
| `npm audit --json` | JS SCA / CVE check | Installed | **EXECUTED** (exit `0`, `0` vulns / `170` pkgs) | Maintain in CI PR checks |
| `pip-audit` | Python SCA / CVE check | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Install & run against locked `.venv` / requirements |
| `osv-scanner` | Multi-ecosystem SCA | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Run in CI against repo & lockfiles |
| `bandit` | Python SAST | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Run `bandit -r backend/src` in CI |
| `semgrep` | Multi-language SAST | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Run OWASP + Python + TS rulesets in CI |
| `trivy` | Container / IaC / FS CVE scan | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Scan `backend`, `frontend`, and `postgres:16-alpine` images |
| `gitleaks` | Secret history scanner | Not installed (`path=False venv=False`) | **NOT EXECUTED** | Initialize Git & enable pre-commit + CI secret scan |

