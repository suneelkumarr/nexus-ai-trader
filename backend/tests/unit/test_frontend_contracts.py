"""Guards against silent drift between backend response models and frontend types."""

from __future__ import annotations

import re
from pathlib import Path

from nexus.api.v1.health import HealthResponse
from nexus.api.v1.terminal import (
    EngineHealthSummary,
    SanitizedSettingsResponse,
    TerminalRiskSummary,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_TYPES = REPO_ROOT / "frontend" / "src" / "types" / "system.ts"


def _frontend_interface_fields(name: str) -> set[str]:
    source = SYSTEM_TYPES.read_text(encoding="utf-8")
    match = re.search(
        rf"export interface {name} \{{(.*?)\n\}}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"Frontend interface {name} not found in {SYSTEM_TYPES}"
    body = match.group(1)
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", body, flags=re.MULTILINE))


def _assert_contract(model: type, interface_name: str) -> None:
    backend_fields = set(model.model_fields)
    frontend_fields = _frontend_interface_fields(interface_name)
    assert backend_fields == frontend_fields, (
        f"{model.__name__} and frontend {interface_name} drifted. "
        f"Backend-only: {sorted(backend_fields - frontend_fields)}; "
        f"Frontend-only: {sorted(frontend_fields - backend_fields)}"
    )


def test_terminal_snapshot_contracts_match_frontend_types() -> None:
    _assert_contract(EngineHealthSummary, "EngineHealthSummary")
    _assert_contract(TerminalRiskSummary, "TerminalRiskSummary")
    _assert_contract(SanitizedSettingsResponse, "SanitizedSettingsResponse")


def test_health_contract_matches_frontend_type() -> None:
    _assert_contract(HealthResponse, "HealthResponse")
