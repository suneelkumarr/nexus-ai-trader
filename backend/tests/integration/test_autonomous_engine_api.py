"""Integration tests for autonomous paper-trading engine and AI research API endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from nexus.application.autonomous.engine_service import AutonomousEngineService
from nexus.core.config import Settings
from nexus.main import create_app


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=AutonomousEngineService)
    engine.get_status = AsyncMock(
        return_value={
            "is_running": True,
            "cycle_count": 5,
            "last_cycle_at": "2026-11-12T18:00:00Z",
            "last_cycle_duration_ms": 12.5,
            "arbitrage_trades_count": 2,
            "strategy_trades_count": 1,
            "open_positions_count": 1,
            "kill_switch_active": False,
            "kill_switch_reason": None,
            "cash_balance_inr": 10000.0,
            "initial_capital_inr": 10000.0,
            "last_error": None,
            "latest_ai_research": {
                "macro_regime": "BULLISH_EXPANSION",
                "sentiment_index": 75,
                "sentiment_label": "Greed",
                "top_momentum_sector": "Layer 1",
                "executive_briefing": "Bullish expansion underway.",
                "risk_advisory": "Maintain strict stops.",
                "top_alpha_picks": [],
                "updated_at": "2026-11-12T18:00:00Z",
            },
        }
    )
    engine.toggle = AsyncMock(return_value=False)
    engine.force_full_cycle = AsyncMock(return_value={"status": "OK"})
    engine.latest_ai_research = {
        "macro_regime": "BULLISH_EXPANSION",
        "sentiment_index": 75,
        "sentiment_label": "Greed",
        "top_momentum_sector": "Layer 1",
        "executive_briefing": "Bullish expansion underway.",
        "risk_advisory": "Maintain strict stops.",
        "top_alpha_picks": [],
        "updated_at": "2026-11-12T18:00:00Z",
    }
    engine._refresh_ai_research = AsyncMock(return_value=engine.latest_ai_research)
    return engine


@pytest.fixture
def test_client(mock_engine: MagicMock) -> Any:
    settings = Settings(
        app_env="test",
        api_auth_token="nexus_sec_admin_7f9b8a3e4c1d2e5a6f8b",
        trading_mode="paper",
        live_trading_enabled=False,
        allow_leverage=False,
        allow_withdrawals=False,
    )
    app = create_app(settings)
    app.state.autonomous_engine = mock_engine
    return TestClient(app)


def test_autonomous_status_endpoint(test_client: TestClient) -> None:
    res = test_client.get("/api/v1/autonomous/status")
    assert res.status_code == 200
    data = res.json()
    assert data["is_running"] is True
    assert data["cycle_count"] == 5
    assert data["cash_balance_inr"] == 10000.0
    assert data["latest_ai_research"]["macro_regime"] == "BULLISH_EXPANSION"


def test_autonomous_toggle_and_cycle(test_client: TestClient) -> None:
    headers = {"Authorization": "Bearer nexus_sec_admin_7f9b8a3e4c1d2e5a6f8b"}

    # Toggle
    res = test_client.post("/api/v1/autonomous/toggle", headers=headers)
    assert res.status_code == 200
    assert "is_running" in res.json()

    # Manual cycle
    cycle_res = test_client.post("/api/v1/autonomous/cycle", headers=headers)
    assert cycle_res.status_code == 200

    # Read latest AI research
    ai_res = test_client.get("/api/v1/autonomous/ai-research")
    assert ai_res.status_code == 200
    ai_data = ai_res.json()
    assert ai_data["macro_regime"] == "BULLISH_EXPANSION"
    assert ai_data["sentiment_index"] == 75
