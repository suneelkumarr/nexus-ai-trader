"""Quantitative Arbitrage & Synthetic Mispricing Detection Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from nexus.domain.arbitrage import (
    ArbitrageLeg,
    ArbitrageStatus,
    DislocationDirection,
    FilterReason,
    MarketTickerItem,
    MultiMarketScanResult,
    SyntheticDislocation,
    TriangularOpportunity,
)


class ArbitrageDetector:
    """Detects spatial triangular arbitrage and statistical cross dislocations."""

    def __init__(
        self,
        paper_fee_bps_per_leg: Decimal = Decimal("10.0"),  # 0.10% taker fee per leg
        paper_slippage_bps_per_leg: Decimal = Decimal("5.0"),  # 0.05% slippage per leg
        standard_clip_usdt: Decimal = Decimal("100.0"),  # ₹8,300 virtual execution clip
    ) -> None:
        self._fee_bps = paper_fee_bps_per_leg
        self._slippage_bps = paper_slippage_bps_per_leg
        self._clip_usdt = standard_clip_usdt

    def evaluate(self, tickers: dict[str, MarketTickerItem]) -> MultiMarketScanResult:
        """Scan all tickers for triangular loops and synthetic dislocations."""
        utc_now = datetime.now(UTC)

        triangular_opps = self._evaluate_triangles(tickers, utc_now)
        synthetic_dislocations = self._evaluate_synthetic_crosses(tickers, utc_now)

        market_list = list(tickers.values())
        total_markets = len(market_list)
        active_markets = sum(1 for m in market_list if not m.is_stale)

        spread_sum = sum((m.spread_bps for m in market_list), Decimal("0.0"))
        avg_spread = (spread_sum / Decimal(str(max(total_markets, 1)))).quantize(Decimal("0.01"))

        # Top gainers and top spreads
        sorted_gainers = sorted(market_list, key=lambda m: m.change_24h_pct, reverse=True)[:5]
        sorted_spreads = sorted(market_list, key=lambda m: m.spread_bps, reverse=True)[:5]

        return MultiMarketScanResult(
            timestamp=utc_now,
            total_markets=total_markets,
            active_markets=active_markets,
            avg_spread_bps=avg_spread,
            top_gainers=sorted_gainers,
            top_spreads=sorted_spreads,
            markets=market_list,
            triangular_opportunities=triangular_opps,
            synthetic_dislocations=synthetic_dislocations,
        )

    def _evaluate_triangles(
        self, tickers: dict[str, MarketTickerItem], utc_now: datetime
    ) -> list[TriangularOpportunity]:
        """Evaluate canonical triangular loops (Forward and Reverse)."""
        opportunities: list[TriangularOpportunity] = []

        triangles = [
            ("BTC", "ETH", "BTC/USDT", "ETH/USDT", "ETH/BTC"),
            ("BTC", "SOL", "BTC/USDT", "SOL/USDT", "SOL/BTC"),
            ("BTC", "BNB", "BTC/USDT", "BNB/USDT", "BNB/BTC"),
            ("ETH", "SOL", "ETH/USDT", "SOL/USDT", "SOL/ETH"),
        ]

        total_roundtrip_fees_bps = self._fee_bps * Decimal("3.0")
        total_roundtrip_slippage_bps = self._slippage_bps * Decimal("3.0")

        for idx, (asset_a, asset_b, pair_a_usdt, pair_b_usdt, pair_cross) in enumerate(triangles):
            t_a = tickers.get(pair_a_usdt)
            t_b = tickers.get(pair_b_usdt)
            t_cross = tickers.get(pair_cross)

            if not t_a or not t_b or not t_cross:
                continue

            # FORWARD: USDT -> AssetA -> AssetB -> USDT
            mult_fwd = (Decimal("1.0") / t_a.ask) / t_cross.ask * t_b.bid
            fwd_calc = (mult_fwd - Decimal("1.0")) * Decimal("10000")
            gross_edge_bps_fwd = fwd_calc.quantize(Decimal("0.01"))
            net_edge_bps_fwd = (
                gross_edge_bps_fwd - total_roundtrip_fees_bps - total_roundtrip_slippage_bps
            )
            fwd_profit_calc = self._clip_usdt * (net_edge_bps_fwd / Decimal("10000"))
            expected_profit_fwd = fwd_profit_calc.quantize(Decimal("0.01"))

            status_fwd: ArbitrageStatus = "ACTIVE" if net_edge_bps_fwd > 0 else "FILTERED"
            reason_fwd: FilterReason | None = None if net_edge_bps_fwd > 0 else "NEGATIVE_NET_EDGE"

            raw_score_fwd = float(gross_edge_bps_fwd + Decimal("15.0")) / 30.0
            quality_fwd = Decimal(str(max(0.700, min(0.999, round(raw_score_fwd, 3)))))

            opportunities.append(
                TriangularOpportunity(
                    id=f"ARB-TRI-{idx * 2 + 1:02d}",
                    path=f"USDT -> {asset_a} -> {asset_b} -> USDT",
                    legs=[
                        ArbitrageLeg(
                            1, pair_a_usdt, "BUY", "USDT", asset_a, t_a.ask,
                            self._fee_bps, self._slippage_bps,
                        ),
                        ArbitrageLeg(
                            2, pair_cross, "BUY", asset_a, asset_b, t_cross.ask,
                            self._fee_bps, self._slippage_bps,
                        ),
                        ArbitrageLeg(
                            3, pair_b_usdt, "SELL", asset_b, "USDT", t_b.bid,
                            self._fee_bps, self._slippage_bps,
                        ),
                    ],
                    gross_edge_bps=gross_edge_bps_fwd,
                    total_fee_bps=total_roundtrip_fees_bps,
                    estimated_slippage_bps=total_roundtrip_slippage_bps,
                    net_edge_bps=net_edge_bps_fwd,
                    expected_profit_usdt=expected_profit_fwd,
                    status=status_fwd,
                    filter_reason=reason_fwd,
                    execution_window_ms=3200,
                    detected_at=utc_now,
                    quality_score=quality_fwd,
                )
            )

            # REVERSE: USDT -> AssetB -> AssetA -> USDT
            mult_rev = (Decimal("1.0") / t_b.ask) * t_cross.bid * t_a.bid
            rev_calc = (mult_rev - Decimal("1.0")) * Decimal("10000")
            gross_edge_bps_rev = rev_calc.quantize(Decimal("0.01"))
            net_edge_bps_rev = (
                gross_edge_bps_rev - total_roundtrip_fees_bps - total_roundtrip_slippage_bps
            )
            rev_profit_calc = self._clip_usdt * (net_edge_bps_rev / Decimal("10000"))
            expected_profit_rev = rev_profit_calc.quantize(Decimal("0.01"))

            status_rev: ArbitrageStatus = "ACTIVE" if net_edge_bps_rev > 0 else "FILTERED"
            reason_rev: FilterReason | None = None if net_edge_bps_rev > 0 else "NEGATIVE_NET_EDGE"

            raw_score_rev = float(gross_edge_bps_rev + Decimal("15.0")) / 30.0
            quality_rev = Decimal(str(max(0.700, min(0.999, round(raw_score_rev, 3)))))

            opportunities.append(
                TriangularOpportunity(
                    id=f"ARB-TRI-{idx * 2 + 2:02d}",
                    path=f"USDT -> {asset_b} -> {asset_a} -> USDT",
                    legs=[
                        ArbitrageLeg(
                            1, pair_b_usdt, "BUY", "USDT", asset_b, t_b.ask,
                            self._fee_bps, self._slippage_bps,
                        ),
                        ArbitrageLeg(
                            2, pair_cross, "SELL", asset_b, asset_a, t_cross.bid,
                            self._fee_bps, self._slippage_bps,
                        ),
                        ArbitrageLeg(
                            3, pair_a_usdt, "SELL", asset_a, "USDT", t_a.bid,
                            self._fee_bps, self._slippage_bps,
                        ),
                    ],
                    gross_edge_bps=gross_edge_bps_rev,
                    total_fee_bps=total_roundtrip_fees_bps,
                    estimated_slippage_bps=total_roundtrip_slippage_bps,
                    net_edge_bps=net_edge_bps_rev,
                    expected_profit_usdt=expected_profit_rev,
                    status=status_rev,
                    filter_reason=reason_rev,
                    execution_window_ms=2800,
                    detected_at=utc_now,
                    quality_score=quality_rev,
                )
            )

        return sorted(opportunities, key=lambda o: o.gross_edge_bps, reverse=True)

    def _evaluate_synthetic_crosses(
        self, tickers: dict[str, MarketTickerItem], utc_now: datetime
    ) -> list[SyntheticDislocation]:
        """Evaluate statistical dislocations between direct cross pairs and synthetic ratios."""
        dislocations: list[SyntheticDislocation] = []

        crosses = [
            ("ETH", "BTC", "ETH/BTC", "ETH/USDT", "BTC/USDT"),
            ("SOL", "BTC", "SOL/BTC", "SOL/USDT", "BTC/USDT"),
            ("BNB", "BTC", "BNB/BTC", "BNB/USDT", "BTC/USDT"),
            ("SOL", "ETH", "SOL/ETH", "SOL/USDT", "ETH/USDT"),
        ]

        for base, quote, direct_symbol, base_usdt, quote_usdt in crosses:
            t_direct = tickers.get(direct_symbol)
            t_base = tickers.get(base_usdt)
            t_quote = tickers.get(quote_usdt)

            if not t_direct or not t_base or not t_quote:
                continue

            direct_mid = (t_direct.bid + t_direct.ask) / Decimal("2.0")
            base_mid = (t_base.bid + t_base.ask) / Decimal("2.0")
            quote_mid = (t_quote.bid + t_quote.ask) / Decimal("2.0")

            synthetic_mid = base_mid / quote_mid
            disloc_calc = (direct_mid - synthetic_mid) / synthetic_mid * Decimal("10000")
            dislocation_bps = disloc_calc.quantize(Decimal("0.01"))
            z_score = (dislocation_bps / Decimal("6.5")).quantize(Decimal("0.01"))

            direction: DislocationDirection = "NEUTRAL"
            if dislocation_bps > Decimal("10.0"):
                direction = "BUY_SYNTH_SELL_DIRECT"
            elif dislocation_bps < Decimal("-10.0"):
                direction = "BUY_DIRECT_SELL_SYNTH"

            dislocations.append(
                SyntheticDislocation(
                    base_asset=base,
                    quote_asset=quote,
                    direct_symbol=direct_symbol,
                    direct_price=direct_mid,
                    synthetic_price=synthetic_mid.quantize(Decimal("0.000001")),
                    dislocation_bps=dislocation_bps,
                    z_score=z_score,
                    direction=direction,
                    detected_at=utc_now,
                )
            )

        return dislocations
