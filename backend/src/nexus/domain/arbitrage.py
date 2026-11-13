"""Domain models for high-speed multi-market scanning and arbitrage detection."""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

ArbitrageStatus = Literal["ACTIVE", "EXPIRED", "FILTERED"]
FilterReason = Literal[
    "NEGATIVE_NET_EDGE",
    "STALE_QUOTE",
    "INSUFFICIENT_LIQUIDITY",
    "HIGH_SPREAD_DRAG",
    "RISK_LIMIT_EXCEEDED",
]
DislocationDirection = Literal["BUY_DIRECT_SELL_SYNTH", "BUY_SYNTH_SELL_DIRECT", "NEUTRAL"]
MarketSector = Literal[
    "LAYER_1",
    "DEFI",
    "AI_COMPUTE",
    "MEMES",
    "GAMING_METAVERSE",
    "INFRASTRUCTURE",
]


@dataclass(frozen=True)
class MarketTickerItem:
    """Snapshot quote for a single scanned spot pair."""

    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    spread_bps: Decimal
    change_24h_pct: Decimal
    quote_volume_24h: Decimal
    sector: MarketSector
    timestamp: datetime
    is_stale: bool = False

    def model_copy(self, *, update: dict[str, Any] | None = None) -> MarketTickerItem:
        """Pydantic-like compatibility method for frozen dataclass."""
        if update:
            return dataclasses.replace(self, **update)
        return dataclasses.replace(self)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Pydantic-like compatibility method returning dict."""
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ArbitrageLeg:
    """A single trade leg in a triangular or statistical arbitrage path."""

    step: int
    symbol: str
    side: Literal["BUY", "SELL"]
    from_asset: str
    to_asset: str
    rate: Decimal
    fee_bps: Decimal
    slippage_bps: Decimal

    def model_copy(self, *, update: dict[str, Any] | None = None) -> ArbitrageLeg:
        if update:
            return dataclasses.replace(self, **update)
        return dataclasses.replace(self)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class TriangularOpportunity:
    """Evaluated triangular arbitrage loop opportunity."""

    id: str
    path: str  # e.g. "USDT -> BTC -> ETH -> USDT"
    legs: list[ArbitrageLeg]
    gross_edge_bps: Decimal
    total_fee_bps: Decimal
    estimated_slippage_bps: Decimal
    net_edge_bps: Decimal
    expected_profit_usdt: Decimal
    status: ArbitrageStatus
    filter_reason: FilterReason | None
    execution_window_ms: int
    detected_at: datetime
    quality_score: Decimal  # 0.0 to 1.0 (SOTA candidate score)

    def model_copy(self, *, update: dict[str, Any] | None = None) -> TriangularOpportunity:
        if update:
            return dataclasses.replace(self, **update)
        return dataclasses.replace(self)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class SyntheticDislocation:
    """Dislocation between a direct cross pair and its synthetic price."""

    base_asset: str
    quote_asset: str
    direct_symbol: str
    direct_price: Decimal
    synthetic_price: Decimal
    dislocation_bps: Decimal
    z_score: Decimal
    direction: DislocationDirection
    detected_at: datetime

    def model_copy(self, *, update: dict[str, Any] | None = None) -> SyntheticDislocation:
        if update:
            return dataclasses.replace(self, **update)
        return dataclasses.replace(self)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class MultiMarketScanResult:
    """Full snapshot of the 50+ multi-market scanner state."""

    timestamp: datetime
    total_markets: int
    active_markets: int
    avg_spread_bps: Decimal
    top_gainers: list[MarketTickerItem]
    top_spreads: list[MarketTickerItem]
    markets: list[MarketTickerItem]
    triangular_opportunities: list[TriangularOpportunity]
    synthetic_dislocations: list[SyntheticDislocation]

    def model_copy(self, *, update: dict[str, Any] | None = None) -> MultiMarketScanResult:
        if update:
            return dataclasses.replace(self, **update)
        return dataclasses.replace(self)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dataclasses.asdict(self)
