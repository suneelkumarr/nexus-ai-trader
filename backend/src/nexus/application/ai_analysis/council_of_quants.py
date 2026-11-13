"""Council of Quants: Multi-Agent Debate Architecture for Institutional AI Decision-Making.

Orchestrates 3 specialized agents:
1. MomentumBullAgent (Upside drivers & alpha generation)
2. RiskSkepticBearAgent (Devil's advocate & liquidity trap detection)
3. ChiefArbitratorAgent (Debate synthesis, conviction score, and binding verdict)
"""

from datetime import UTC, datetime
from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field


class AgentArgument(BaseModel):
    category: str
    point: str
    impact: Literal["HIGH", "MEDIUM", "LOW"]
    is_supporting: bool


class BullThesis(BaseModel):
    agent_name: str = "Momentum Bull Agent"
    score: int = Field(ge=0, le=100)
    key_drivers: list[str]
    arguments: list[AgentArgument]
    recommended_action: Literal["STRONG_BUY", "BUY", "ACCUMULATE"]


class BearThesis(BaseModel):
    agent_name: str = "Risk Skeptic Bear Agent"
    skepticism_score: int = Field(ge=0, le=100)
    red_flags: list[str]
    counter_arguments: list[AgentArgument]
    threat_level: Literal["CRITICAL", "ELEVATED", "CONTAINED"]


class CouncilDebateResult(BaseModel):
    debate_id: str
    symbol: str
    timeframe: str
    timestamp: datetime
    bull_thesis: BullThesis
    bear_thesis: BearThesis
    consensus_conviction_pct: int = Field(ge=0, le=100)
    verdict: Literal["APPROVED", "CONDITIONAL", "VETOED"]
    verdict_rationale: str
    suggested_sizing_multiplier: float
    recommended_stop_adjustment: str


class CouncilOfQuantsEngine:
    """Evaluates market state through multi-agent debate synthesis."""

    def evaluate_debate(
        self,
        symbol: str,
        timeframe: str = "15m",
        *,
        last_price: float = 65000.0,
        fast_ema: float | None = None,
        slow_ema: float | None = None,
        rsi: float | None = None,
        volume_ratio: float | None = None,
        market_breadth_pct: float = 58.0,
    ) -> CouncilDebateResult:
        """Run debate between Momentum Bull, Risk Skeptic, and Chief Arbitrator."""
        now_utc = datetime.now(UTC)
        debate_id = str(uuid.uuid4())[:8]

        f_ema = fast_ema if fast_ema is not None else last_price * 1.008
        s_ema = slow_ema if slow_ema is not None else last_price * 0.995
        cur_rsi = rsi if rsi is not None else 56.4
        vol_ratio = volume_ratio if volume_ratio is not None else 1.45

        # -------------------------------------------------------------
        # 1. Momentum Bull Agent Analysis
        # -------------------------------------------------------------
        bull_score = 50
        bull_drivers: list[str] = []
        bull_args: list[AgentArgument] = []

        if f_ema > s_ema:
            ema_spread = ((f_ema - s_ema) / s_ema) * 100
            bull_score += 18
            bull_drivers.append(f"Golden EMA20/50 alignment (+{ema_spread:.2f}% positive slope)")
            bull_args.append(
                AgentArgument(
                    category="Trend Structure",
                    point=f"Fast EMA ({f_ema:,.1f}) comfortably riding above Slow EMA ({s_ema:,.1f}), confirming upward structural momentum.",
                    impact="HIGH",
                    is_supporting=True,
                )
            )
        else:
            bull_args.append(
                AgentArgument(
                    category="Trend Structure",
                    point="EMA crossover negative; trend requires confirmation before aggressive longing.",
                    impact="MEDIUM",
                    is_supporting=False,
                )
            )

        if 48 <= cur_rsi <= 68:
            bull_score += 15
            bull_drivers.append(f"RSI in optimal acceleration zone ({cur_rsi:.1f})")
            bull_args.append(
                AgentArgument(
                    category="Momentum Oscillator",
                    point=f"RSI ({cur_rsi:.1f}) indicates clean directional buying pressure without reaching overbought exhaustion.",
                    impact="HIGH",
                    is_supporting=True,
                )
            )
        elif cur_rsi < 35:
            bull_score += 12
            bull_drivers.append(f"Oversold mean-reversion spring ({cur_rsi:.1f})")
            bull_args.append(
                AgentArgument(
                    category="Momentum Oscillator",
                    point=f"RSI ({cur_rsi:.1f}) deeply depressed; mean-reverting bounce probability elevated.",
                    impact="MEDIUM",
                    is_supporting=True,
                )
            )

        if vol_ratio >= 1.2:
            bull_score += 12
            bull_drivers.append(f"Volume surge confirmation ({vol_ratio:.2f}x 20MA)")
            bull_args.append(
                AgentArgument(
                    category="Liquidity & Volume",
                    point=f"Trade volume is {vol_ratio:.2f}x above baseline moving average, confirming institutional participation.",
                    impact="MEDIUM",
                    is_supporting=True,
                )
            )

        if market_breadth_pct >= 55:
            bull_score += 5
            bull_drivers.append(f"Broad market tailwind ({market_breadth_pct:.1f}% green pairs)")

        bull_score = min(max(bull_score, 15), 95)
        bull_action: Literal["STRONG_BUY", "BUY", "ACCUMULATE"] = (
            "STRONG_BUY" if bull_score >= 80 else "BUY" if bull_score >= 65 else "ACCUMULATE"
        )

        bull_thesis = BullThesis(
            score=bull_score,
            key_drivers=bull_drivers or ["Base structural support intact"],
            arguments=bull_args,
            recommended_action=bull_action,
        )

        # -------------------------------------------------------------
        # 2. Risk Skeptic Bear Agent Analysis (Devil's Advocate)
        # -------------------------------------------------------------
        bear_score = 30
        bear_red_flags: list[str] = []
        bear_args: list[AgentArgument] = []

        if cur_rsi >= 68:
            bear_score += 25
            bear_red_flags.append(f"Extended RSI ({cur_rsi:.1f}) vulnerable to sharp mean-reversion")
            bear_args.append(
                AgentArgument(
                    category="Exhaustion Risk",
                    point=f"RSI at {cur_rsi:.1f} approaches the upper volatility boundary; high probability of long squeeze or liquidity flush.",
                    impact="HIGH",
                    is_supporting=True,
                )
            )

        if vol_ratio < 1.0:
            bear_score += 20
            bear_red_flags.append(f"Declining volume divergence ({vol_ratio:.2f}x MA)")
            bear_args.append(
                AgentArgument(
                    category="Liquidity Trap",
                    point="Price advancing on below-average volume creates liquidity vacuum wick risk.",
                    impact="HIGH",
                    is_supporting=True,
                )
            )

        if market_breadth_pct < 45:
            bear_score += 15
            bear_red_flags.append(f"Weak market breadth ({market_breadth_pct:.1f}% positive)")
            bear_args.append(
                AgentArgument(
                    category="Macro Drag",
                    point="Altcoin sector liquidity contracting; adverse market correlation threatens idiosyncratic alpha.",
                    impact="MEDIUM",
                    is_supporting=True,
                )
            )
        else:
            bear_args.append(
                AgentArgument(
                    category="Macro Drag",
                    point=f"Market breadth is healthy ({market_breadth_pct:.1f}% green); systemic downside drag is currently subdued.",
                    impact="LOW",
                    is_supporting=False,
                )
            )

        bear_score = min(max(bear_score, 10), 92)
        threat: Literal["CRITICAL", "ELEVATED", "CONTAINED"] = (
            "CRITICAL" if bear_score >= 70 else "ELEVATED" if bear_score >= 45 else "CONTAINED"
        )

        bear_thesis = BearThesis(
            skepticism_score=bear_score,
            red_flags=bear_red_flags or ["No catastrophic red flags detected on current timeframe"],
            counter_arguments=bear_args,
            threat_level=threat,
        )

        # -------------------------------------------------------------
        # 3. Chief Arbitrator Synthesis & Binding Verdict
        # -------------------------------------------------------------
        # Net conviction weighted formula: 60% Bull Score + 40% (100 - Bear Score)
        net_conviction = int(round(0.60 * bull_score + 0.40 * (100 - bear_score)))

        if net_conviction >= 72 and threat != "CRITICAL":
            verdict: Literal["APPROVED", "CONDITIONAL", "VETOED"] = "APPROVED"
            rationale = (
                f"Council consensus reached ({net_conviction}% Conviction). Momentum Bull drivers "
                f"({', '.join(bull_drivers[:2])}) clearly outweigh Risk Skeptic objections. Full size authorized."
            )
            sizing = 1.0
            stop_adj = "Standard 1.5x ATR Trailing Stop"
        elif net_conviction >= 58 and threat != "CRITICAL":
            verdict = "CONDITIONAL"
            rationale = (
                f"Conditional authorization ({net_conviction}% Conviction). Bullish trend confirmed, but "
                f"Risk Skeptic notes {bear_red_flags[0] if bear_red_flags else 'moderate volatility'}. "
                "Recommend scaled 0.6x position size with tightened stops."
            )
            sizing = 0.6
            stop_adj = "Tightened 1.0x ATR Stop Loss"
        else:
            verdict = "VETOED"
            rationale = (
                f"Council VETO engaged ({net_conviction}% Conviction). Risk Skeptic threat is {threat} "
                f"with red flags ({', '.join(bear_red_flags[:2])}). Standing down to preserve capital."
            )
            sizing = 0.0
            stop_adj = "Entry Rejected · Capital Safeguarded"

        return CouncilDebateResult(
            debate_id=debate_id,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now_utc,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            consensus_conviction_pct=net_conviction,
            verdict=verdict,
            verdict_rationale=rationale,
            suggested_sizing_multiplier=sizing,
            recommended_stop_adjustment=stop_adj,
        )

