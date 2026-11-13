"""Unit tests for Binance Futures WebSocket & Official Connector Gateway."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nexus.infrastructure.exchange.binance_gateway import (
    BINANCE_PROD_WS_API,
    BINANCE_TESTNET_WS_API,
    BinanceFuturesGateway,
)


@pytest.mark.asyncio
async def test_binance_gateway_initialization() -> None:
    gateway = BinanceFuturesGateway(
        api_key="test_key",
        api_secret="test_secret",
        use_testnet=True,
    )
    assert gateway.is_configured is True
    assert gateway.is_testnet is True
    assert gateway._ws_url == BINANCE_TESTNET_WS_API

    gateway.update_credentials(api_key="live_key", api_secret="live_secret", use_testnet=False)
    assert gateway.is_testnet is False
    assert gateway._ws_url == BINANCE_PROD_WS_API


@pytest.mark.asyncio
async def test_binance_gateway_test_credentials_safety_lock() -> None:
    gateway = BinanceFuturesGateway()

    mock_account = {
        "canTrade": True,
        "canDeposit": True,
        "canWithdraw": False,  # Strict invariant passed
        "assets": [{"asset": "USDT", "walletBalance": "5000.0", "availableBalance": "4500.0"}],
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.1"}],
    }

    with patch("nexus.infrastructure.exchange.binance_gateway.UMFutures") as mock_um:
        client_instance = MagicMock()
        client_instance.ping.return_value = {}
        client_instance.time.return_value = {"serverTime": 1700000000000}
        client_instance.account.return_value = mock_account
        mock_um.return_value = client_instance

        res = await gateway.test_credentials(
            api_key="key",
            api_secret="secret",
            use_testnet=True,
        )

        assert res["success"] is True
        assert res["can_trade"] is True
        assert res["can_withdraw"] is False
        assert res["safety_lock_passed"] is True
        assert res["wallet_balance_usdt"] == 5000.0
        assert res["available_balance_usdt"] == 4500.0
        assert res["open_positions_count"] == 1


@pytest.mark.asyncio
async def test_binance_gateway_detects_withdrawal_hazard() -> None:
    gateway = BinanceFuturesGateway()

    hazard_account = {
        "canTrade": True,
        "canDeposit": True,
        "canWithdraw": True,  # UNSAFE: Key has withdrawal permissions
        "assets": [],
        "positions": [],
    }

    with patch("nexus.infrastructure.exchange.binance_gateway.UMFutures") as mock_um:
        client_instance = MagicMock()
        client_instance.ping.return_value = {}
        client_instance.time.return_value = {"serverTime": 1700000000000}
        client_instance.account.return_value = hazard_account
        mock_um.return_value = client_instance

        res = await gateway.test_credentials(
            api_key="unsafe_key",
            api_secret="unsafe_secret",
            use_testnet=False,
        )

        assert res["success"] is True
        assert res["can_withdraw"] is True
        assert res["safety_lock_passed"] is False  # Must flag safety failure


@pytest.mark.asyncio
async def test_binance_gateway_order_placement_pretrade_validation() -> None:
    gateway = BinanceFuturesGateway(api_key="k", api_secret="s", use_testnet=True)

    with patch.object(gateway, "_client") as mock_client:
        mock_client.new_order_test.return_value = {}
        mock_client.new_order.return_value = {
            "orderId": 987654321,
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "executedQty": "0.01",
        }

        res = await gateway.place_order(
            symbol="BTC/USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            leverage=2,
            stop_loss_price=Decimal("60000.0"),
            take_profit_price=Decimal("70000.0"),
        )

        assert res.get("orderId") == 987654321
        mock_client.new_order_test.assert_called_once()
        assert mock_client.new_order.call_count >= 1

