"""Strict response validation preventing schema drift, invented prices, and unsafe claims."""

import json
import math
import re

from pydantic import ValidationError

from nexus.core.exceptions import AIResponseValidationError
from nexus.domain.models import MarketAnalysisInput, MarketAnalysisOutput

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL | re.IGNORECASE)

_CURRENCY_OR_PRICE_RE = re.compile(
    r"(?:"
    r"(?:\$|USD\s+|USDT\s+|INR\s+)(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?)\s*(?:USDT|USD|INR)\b"
    r"|\b(?:price|entry|stop|stop-loss|target|support|resistance|breakout|rally to|drop to)"
    r"(?:\s+(?:of|at|near|around))?\s+\$?(\d[\d,]*(?:\.\d+)?)"
    r")",
    re.IGNORECASE,
)

_NUMBER_TOKEN_RE = re.compile(r"(?<![\w:/-])(\d[\d,]*(?:\.\d+)?)(?![\w:-])")
_ISO_DATE_FRAGMENT_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?")

_PROFIT_PROBABILITY_RE = re.compile(
    r"(?:"
    r"\bprobability\s+of\s+(?:a\s+)?profit(?:able|ability)?\b"
    r"|\bprofit(?:able)?\s+probability\b"
    r"|\bchance\s+of\s+(?:a\s+)?profit(?:able|ing)?\b"
    r"|\bwin(?:ning)?\s+probability\b"
    r"|\bguaranteed\s+(?:profit|returns?|gains?)\b"
    r"|\bconfidence\s*(?:=|of|is)\s*\d+(?:\.\d+)?%\s*(?:chance|probability)\b"
    r")",
    re.IGNORECASE,
)

_EXECUTION_DIRECTIVE_RE = re.compile(
    r"(?:"
    r"\bbypass\s+(?:the\s+)?risk\s*(?:manager|guard|limits?)\b"
    r"|\boverride\s+(?:the\s+)?(?:risk|stop[- ]?loss|kill[- ]?switch)\b"
    r"|\bdisable\s+(?:the\s+)?kill[- ]?switch\b"
    r"|\bplace\s+(?:a\s+)?(?:live|market|limit|spot)\s+order\b"
    r"|\bexecute\s+(?:trade|order)\s+directly\b"
    r")",
    re.IGNORECASE,
)


def _extract_json_object(raw_response: str) -> dict[str, object]:
    """Parse strict JSON object from model output, rejecting non-JSON content."""
    text = raw_response.strip()
    fence_match = _CODE_FENCE_RE.match(text)
    if fence_match is not None:
        text = fence_match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIResponseValidationError(f"AI response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise AIResponseValidationError(
            f"AI response JSON root must be an object, got {type(parsed).__name__}."
        )
    return parsed


def _collect_verified_values(
    source_input: MarketAnalysisInput,
) -> tuple[list[float], list[float]]:
    """Return (verified_prices_and_levels, all_verified_numbers) from validated inputs."""
    ind = source_input.indicators
    hist = source_input.historical_features

    prices: list[float] = [
        float(ind.close_usdt),
        float(ind.ema_fast),
        float(ind.ema_slow),
        float(ind.atr),
        float(hist.range_high_usdt),
        float(hist.range_low_usdt),
    ]
    for sig in source_input.strategy_signals:
        prices.append(float(sig.entry_price))
        prices.append(float(sig.stop_price))

    extras: list[float] = [
        float(ind.volume),
        float(ind.volume_sma),
        float(ind.rsi),
        float(ind.atr_pct),
        float(ind.volume_ratio),
        float(ind.ema_fast_period),
        float(ind.ema_slow_period),
        float(ind.rsi_period),
        float(ind.atr_period),
        float(ind.volume_sma_period),
        float(hist.lookback_bars),
        float(hist.return_1_bar_pct),
        float(hist.return_5_bar_pct),
        float(hist.return_20_bar_pct),
        float(hist.realized_volatility_pct),
        float(hist.atr_percentile),
        float(hist.volume_zscore),
        float(hist.gap_count),
    ]
    for comp in source_input.strategy_comparisons:
        prices.append(abs(float(comp.net_pnl_inr)))
        extras.extend(
            [
                float(comp.trades_count),
                float(comp.win_rate_pct),
                float(comp.max_drawdown_pct),
                float(comp.avg_return_pct),
            ]
        )
        if comp.profit_factor is not None:
            extras.append(float(comp.profit_factor))

    verified_prices = [v for v in prices if math.isfinite(v) and v >= 0.0]
    all_numbers = [abs(v) for v in [*verified_prices, *extras] if math.isfinite(v)]
    return verified_prices, all_numbers


def _matches_any(candidate: float, references: list[float], tolerance_pct: float) -> bool:
    """Check whether candidate matches a verified reference value within tolerance."""
    tol_ratio = max(0.0, tolerance_pct) / 100.0
    for ref in references:
        allowed_diff = max(abs(ref) * tol_ratio, 1e-4)
        if abs(candidate - ref) <= allowed_diff:
            return True
    return False


def _collect_text_fields(output: MarketAnalysisOutput) -> list[str]:
    texts = [
        output.explanation,
        *output.risk_observations,
        output.strategy_assessment.performance_comparison,
        *output.strategy_assessment.unusual_conditions,
    ]
    for sig_exp in output.strategy_assessment.signal_explanations:
        texts.append(sig_exp.rationale)
        texts.append(sig_exp.regime_alignment)
    return texts


class AIResponseValidator:
    """Validates AI responses against strict schema, price grounding, and safety rules."""

    def __init__(self, *, price_tolerance_pct: float = 0.5) -> None:
        self._price_tolerance_pct = price_tolerance_pct

    def validate(
        self,
        raw_response: str,
        *,
        source_input: MarketAnalysisInput,
    ) -> MarketAnalysisOutput:
        """Parse and validate AI JSON response against schema, prices, and safety policies."""
        payload = _extract_json_object(raw_response)

        try:
            output = MarketAnalysisOutput.model_validate(payload)
        except ValidationError as exc:
            raise AIResponseValidationError(
                f"AI response failed strict schema validation: {exc}"
            ) from exc

        self.validate_no_invented_prices(output, source_input=source_input)
        self.validate_safety_constraints(output)
        return output

    def validate_no_invented_prices(
        self,
        output: MarketAnalysisOutput,
        *,
        source_input: MarketAnalysisInput,
    ) -> None:
        """Reject responses that cite currency/price figures absent from validated inputs."""
        verified_prices, all_verified = _collect_verified_values(source_input)

        for text in _collect_text_fields(output):
            sanitized_text = _ISO_DATE_FRAGMENT_RE.sub(" ", text)

            for match in _CURRENCY_OR_PRICE_RE.finditer(sanitized_text):
                raw_num = next((g for g in match.groups() if g is not None), None)
                if raw_num is None:
                    continue
                value = float(raw_num.replace(",", ""))
                if not _matches_any(value, verified_prices, self._price_tolerance_pct):
                    raise AIResponseValidationError(
                        f"AI response cited unverified price/currency figure '{raw_num}'."
                    )

            for match in _NUMBER_TOKEN_RE.finditer(sanitized_text):
                raw_num = match.group(1)
                suffix = sanitized_text[match.end() : match.end() + 12].lstrip().lower()
                if suffix.startswith("%") or suffix.startswith("percent") or suffix.startswith(
                    "bar"
                ):
                    continue
                value = float(raw_num.replace(",", ""))
                if value >= 100.0 and not _matches_any(
                    value, all_verified, self._price_tolerance_pct
                ):
                    raise AIResponseValidationError(
                        f"AI response cited unverified large numeric figure '{raw_num}'."
                    )

    def validate_safety_constraints(self, output: MarketAnalysisOutput) -> None:
        """Reject profit-probability claims and direct execution / risk-bypass directives."""
        for text in _collect_text_fields(output):
            if _PROFIT_PROBABILITY_RE.search(text):
                raise AIResponseValidationError(
                    "AI response attempted to express confidence as probability of profit."
                )
            if _EXECUTION_DIRECTIVE_RE.search(text):
                raise AIResponseValidationError(
                    "AI response attempted unauthorized order execution or risk-bypass guidance."
                )

