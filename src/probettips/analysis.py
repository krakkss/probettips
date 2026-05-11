from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev


MARKET_PRIORS: dict[str, tuple[float, float]] = {
    "1X": (16.0, 4.0),
    "X2": (16.0, 4.0),
    "Mas de 0.5 goles": (23.0, 2.0),
    "Mas de 1.5 goles": (18.0, 6.0),
    "Gana local": (12.0, 8.0),
    "Gana visitante": (11.0, 9.0),
    "Bet Builder: 1X + Mas de 1.5 goles": (14.0, 6.0),
    "Bet Builder: X2 + Mas de 1.5 goles": (14.0, 6.0),
    "Bet Builder: Gana local + Mas de 1.5 goles": (11.0, 9.0),
}

CORE_MARKETS = {
    "1X",
    "X2",
    "Mas de 0.5 goles",
    "Mas de 1.5 goles",
}

AGGRESSIVE_MARKETS = {
    "Gana local",
    "Gana visitante",
    "Bet Builder: Gana local + Mas de 1.5 goles",
}

SEMI_AGGRESSIVE_MARKETS = {
    "Bet Builder: 1X + Mas de 1.5 goles",
    "Bet Builder: X2 + Mas de 1.5 goles",
}

CALIBRATION_WINDOW_DAYS = 60
VOLATILITY_WINDOW_DAYS = 30
BLOCK_MARKET_MIN_SAMPLE_30 = 8
BLOCK_MARKET_MIN_SAMPLE_60 = 12
BLOCK_MARKET_MIN_HIT_RATE = 0.65

STRATEGY_LEARNING_WEIGHTS = {
    "official": 1.0,
    "shadow_auto_v1": 0.8,
    "shadow_algo_v2": 0.8,
    "shadow_manual": 0.65,
}


@dataclass(slots=True)
class MarketCalibration:
    market: str
    market_bias: str
    sample_size_total: int
    sample_size_60: int
    sample_size_30: int
    wins_total: int
    wins_60: int
    wins_30: int
    weighted_sample_60: float
    weighted_sample_30: float
    weighted_wins_60: float
    weighted_wins_30: float
    avg_model_probability_60: float
    avg_model_probability_30: float
    hit_rate_60: float | None
    hit_rate_30: float | None
    prior_mean: float
    posterior_hit_rate: float
    calibration_factor: float
    volatility: float
    volatility_penalty: float
    threshold_delta: float
    robustness_penalty: float
    reliability_score: float
    enabled: bool
    disable_reason: str | None


def build_market_calibrations(entries: list[dict]) -> dict[str, MarketCalibration]:
    learning_entries = _entries_for_learning(entries)
    settled_legs = flatten_settled_legs([entry for entry in learning_entries if entry.get("status") == "settled"])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for leg in settled_legs:
        grouped[leg["market"]].append(leg)

    calibrations: dict[str, MarketCalibration] = {}
    for market, prior in MARKET_PRIORS.items():
        all_legs = grouped.get(market, [])
        rolling_60 = _filter_legs_by_days(all_legs, CALIBRATION_WINDOW_DAYS)
        rolling_30 = _filter_legs_by_days(all_legs, VOLATILITY_WINDOW_DAYS)

        prior_alpha, prior_beta = prior
        prior_mean = prior_alpha / (prior_alpha + prior_beta)

        sample_total = len(all_legs)
        sample_60 = len(rolling_60)
        sample_30 = len(rolling_30)
        wins_total = sum(1 for leg in all_legs if leg["won"])
        wins_60 = sum(1 for leg in rolling_60 if leg["won"])
        wins_30 = sum(1 for leg in rolling_30 if leg["won"])
        weighted_sample_60 = sum(float(leg.get("learning_weight", 1.0)) for leg in rolling_60)
        weighted_sample_30 = sum(float(leg.get("learning_weight", 1.0)) for leg in rolling_30)
        weighted_wins_60 = sum(float(leg.get("learning_weight", 1.0)) for leg in rolling_60 if leg["won"])
        weighted_wins_30 = sum(float(leg.get("learning_weight", 1.0)) for leg in rolling_30 if leg["won"])

        avg_pred_60 = weighted_mean(rolling_60, "probability", prior_mean)
        avg_pred_30 = weighted_mean(rolling_30, "probability", avg_pred_60)
        hit_rate_60 = (weighted_wins_60 / weighted_sample_60) if weighted_sample_60 else None
        hit_rate_30 = (weighted_wins_30 / weighted_sample_30) if weighted_sample_30 else None

        posterior = (prior_alpha + weighted_wins_60) / (prior_alpha + prior_beta + weighted_sample_60)
        raw_factor = posterior / max(avg_pred_60, 0.01)
        factor_weight = min(0.8, weighted_sample_60 / (weighted_sample_60 + 18.0)) if weighted_sample_60 else 0.0
        calibration_factor = 1.0 + ((raw_factor - 1.0) * factor_weight)
        calibration_factor = max(0.92, min(1.08, calibration_factor))

        volatility = pstdev([1.0 if leg["won"] else 0.0 for leg in rolling_30]) if sample_30 > 1 else 0.0
        volatility_penalty = min(0.12, volatility * 0.4)
        robustness_penalty = _market_robustness_penalty(market, sample_60)
        factor_pressure = max(0.0, 1.0 - calibration_factor) * 0.18
        threshold_delta = min(0.08, robustness_penalty + factor_pressure + (volatility_penalty * 0.6))

        enabled, disable_reason = _market_enabled(sample_30, hit_rate_30, sample_60, hit_rate_60)
        reliability_base = (posterior if sample_60 else prior_mean) * calibration_factor
        reliability_score = max(0.0, min(1.0, reliability_base - volatility_penalty))

        calibrations[market] = MarketCalibration(
            market=market,
            market_bias=_market_bias(market),
            sample_size_total=sample_total,
            sample_size_60=sample_60,
            sample_size_30=sample_30,
            wins_total=wins_total,
            wins_60=wins_60,
            wins_30=wins_30,
            weighted_sample_60=round(weighted_sample_60, 4),
            weighted_sample_30=round(weighted_sample_30, 4),
            weighted_wins_60=round(weighted_wins_60, 4),
            weighted_wins_30=round(weighted_wins_30, 4),
            avg_model_probability_60=round(avg_pred_60, 4),
            avg_model_probability_30=round(avg_pred_30, 4),
            hit_rate_60=round(hit_rate_60, 4) if hit_rate_60 is not None else None,
            hit_rate_30=round(hit_rate_30, 4) if hit_rate_30 is not None else None,
            prior_mean=round(prior_mean, 4),
            posterior_hit_rate=round(posterior, 4),
            calibration_factor=round(calibration_factor, 4),
            volatility=round(volatility, 4),
            volatility_penalty=round(volatility_penalty, 4),
            threshold_delta=round(threshold_delta, 4),
            robustness_penalty=round(robustness_penalty, 4),
            reliability_score=round(reliability_score, 4),
            enabled=enabled,
            disable_reason=disable_reason,
        )
    return calibrations


def _entries_for_learning(entries: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for entry in entries:
        strategy = entry.get("strategy", "official")
        source = str(entry.get("source", "")).lower()
        recommendation_tier = str(entry.get("recommendation_tier", "")).lower()
        if "manual_entry" in source and strategy == "shadow_manual":
            continue
        if recommendation_tier == "shadow_manual" and "manual_entry" in source:
            continue
        filtered.append(entry)
    return filtered


def calibrated_probability(raw_probability: float, market: str, calibrations: dict[str, MarketCalibration] | None) -> float:
    if not calibrations:
        return raw_probability
    calibration = calibrations.get(market)
    if not calibration:
        return raw_probability

    adjusted = raw_probability * calibration.calibration_factor
    adjusted -= calibration.volatility_penalty
    if calibration.sample_size_60 >= 6:
        adjusted = (adjusted * 0.8) + (calibration.posterior_hit_rate * 0.2)
    return round(max(0.01, min(0.99, adjusted)), 4)


def adjusted_threshold(raw_threshold: float, market: str, calibrations: dict[str, MarketCalibration] | None) -> float:
    if not calibrations:
        return raw_threshold
    calibration = calibrations.get(market)
    if not calibration:
        return raw_threshold
    return round(max(0.58, min(0.94, raw_threshold + calibration.threshold_delta)), 4)


def build_analysis_report(entries: list[dict], rolling_days: int = CALIBRATION_WINDOW_DAYS) -> dict:
    settled_entries = [entry for entry in entries if entry.get("status") == "settled"]
    settled_legs = flatten_settled_legs(settled_entries)
    calibrations = build_market_calibrations(settled_entries)
    alternative_entries = [entry for entry in settled_entries if entry.get("strategy", "official") != "official"]

    return {
        "overall": _build_tip_summary(settled_entries),
        "official": _build_tip_summary([entry for entry in settled_entries if entry.get("strategy", "official") == "official"]),
        "shadow": _build_tip_summary(alternative_entries),
        "rolling_60_days": _build_tip_summary(_filter_entries_by_days(settled_entries, CALIBRATION_WINDOW_DAYS)),
        "rolling_30_days": _build_tip_summary(_filter_entries_by_days(settled_entries, VOLATILITY_WINDOW_DAYS)),
        "rolling_custom_days": _build_tip_summary(_filter_entries_by_days(settled_entries, rolling_days)),
        "legs_overall": _build_leg_summary(settled_legs),
        "legs_rolling_60_days": _build_leg_summary(_filter_legs_by_days(settled_legs, CALIBRATION_WINDOW_DAYS)),
        "legs_rolling_30_days": _build_leg_summary(_filter_legs_by_days(settled_legs, VOLATILITY_WINDOW_DAYS)),
        "market_breakdown": _build_market_breakdown(settled_entries, calibrations),
    }


def flatten_settled_legs(entries: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for entry in entries:
        if entry.get("status") != "settled":
            continue
        picks = entry.get("picks") or []
        legs = (entry.get("settlement") or {}).get("legs") or []
        for pick, leg in zip(picks, legs):
            flattened.append(
                {
                    "date": entry["date"],
                    "strategy": entry.get("strategy", "official"),
                    "market": pick["market"],
                    "bet_type": pick.get("bet_type", "simple"),
                    "probability": float(pick.get("probability", 0.0)),
                    "confidence": float(pick.get("confidence", 0.0)),
                    "risk_score": float(pick.get("risk_score", 0.0)),
                    "dynamic_threshold": float(pick.get("dynamic_threshold", 0.0)),
                    "won": bool(leg.get("won")),
                    "learning_weight": strategy_learning_weight(entry.get("strategy", "official")),
                }
            )
    return flattened


def strategy_learning_weight(strategy: str) -> float:
    return STRATEGY_LEARNING_WEIGHTS.get(strategy, 0.75 if strategy != "official" else 1.0)


def weighted_mean(legs: list[dict], field_name: str, default: float) -> float:
    if not legs:
        return default
    total_weight = sum(float(leg.get("learning_weight", 1.0)) for leg in legs)
    if total_weight <= 0:
        return default
    return sum(float(leg.get(field_name, 0.0)) * float(leg.get("learning_weight", 1.0)) for leg in legs) / total_weight


def market_bias(market: str) -> str:
    return _market_bias(market)


def market_core_bonus(market: str) -> float:
    bias = _market_bias(market)
    if bias == "core":
        return 0.03
    if bias == "semi_aggressive":
        return -0.025
    if bias == "aggressive":
        return -0.07
    return 0.0


def market_needs_extra_evidence(market: str, calibration: MarketCalibration | None) -> bool:
    bias = _market_bias(market)
    if bias == "aggressive":
        return calibration is None or calibration.sample_size_60 < 10
    if bias == "semi_aggressive":
        return calibration is None or calibration.sample_size_60 < 6
    return False


def _build_tip_summary(entries: list[dict]) -> dict:
    total = len(entries)
    wins = sum(1 for entry in entries if entry.get("result") == "win")
    losses = sum(1 for entry in entries if entry.get("result") == "loss")
    return {
        "tips": total,
        "wins": wins,
        "losses": losses,
        "hit_rate": round((wins / total), 4) if total else 0.0,
    }


def _build_leg_summary(legs: list[dict]) -> dict:
    total = len(legs)
    wins = sum(1 for leg in legs if leg["won"])
    losses = total - wins
    avg_probability = mean([leg["probability"] for leg in legs]) if legs else 0.0
    avg_confidence = mean([leg["confidence"] for leg in legs]) if legs else 0.0
    return {
        "legs": total,
        "wins": wins,
        "losses": losses,
        "hit_rate": round((wins / total), 4) if total else 0.0,
        "avg_model_probability": round(avg_probability, 4),
        "avg_confidence": round(avg_confidence, 4),
    }


def _build_market_breakdown(entries: list[dict], calibrations: dict[str, MarketCalibration]) -> list[dict]:
    rows: list[dict] = []
    for market, calibration in calibrations.items():
        rows.append(
            {
                "market": market,
                "market_bias": calibration.market_bias,
                "sample_size_total": calibration.sample_size_total,
                "sample_size_60": calibration.sample_size_60,
                "sample_size_30": calibration.sample_size_30,
                "hit_rate_60": calibration.hit_rate_60,
                "hit_rate_30": calibration.hit_rate_30,
                "avg_model_probability_60": calibration.avg_model_probability_60,
                "avg_model_probability_30": calibration.avg_model_probability_30,
                "posterior_hit_rate": calibration.posterior_hit_rate,
                "calibration_factor": calibration.calibration_factor,
                "volatility": calibration.volatility,
                "volatility_penalty": calibration.volatility_penalty,
                "threshold_delta": calibration.threshold_delta,
                "reliability_score": calibration.reliability_score,
                "enabled": calibration.enabled,
                "disable_reason": calibration.disable_reason,
            }
        )
    rows.sort(key=lambda row: (-row["sample_size_60"], -(row["reliability_score"] or 0.0), row["market"]))
    return rows


def _filter_entries_by_days(entries: list[dict], rolling_days: int) -> list[dict]:
    if not entries:
        return []
    latest_date = max(date.fromisoformat(entry["date"]) for entry in entries)
    cutoff = latest_date - timedelta(days=max(rolling_days - 1, 0))
    return [entry for entry in entries if date.fromisoformat(entry["date"]) >= cutoff]


def _filter_legs_by_days(legs: list[dict], rolling_days: int) -> list[dict]:
    if not legs:
        return []
    latest_date = max(date.fromisoformat(leg["date"]) for leg in legs)
    cutoff = latest_date - timedelta(days=max(rolling_days - 1, 0))
    return [leg for leg in legs if date.fromisoformat(leg["date"]) >= cutoff]


def _market_bias(market: str) -> str:
    if market in CORE_MARKETS:
        return "core"
    if market in SEMI_AGGRESSIVE_MARKETS:
        return "semi_aggressive"
    if market in AGGRESSIVE_MARKETS:
        return "aggressive"
    return "neutral"


def _market_robustness_penalty(market: str, sample_size_60: int) -> float:
    bias = _market_bias(market)
    if bias == "core":
        return 0.0 if sample_size_60 >= 5 else 0.004
    if bias == "semi_aggressive":
        if sample_size_60 >= 10:
            return 0.006
        if sample_size_60 >= 6:
            return 0.014
        return 0.022
    if bias == "aggressive":
        if sample_size_60 >= 12:
            return 0.014
        if sample_size_60 >= 8:
            return 0.024
        return 0.036
    return 0.0


def _market_enabled(
    sample_size_30: int,
    hit_rate_30: float | None,
    sample_size_60: int,
    hit_rate_60: float | None,
) -> tuple[bool, str | None]:
    if sample_size_30 >= BLOCK_MARKET_MIN_SAMPLE_30 and hit_rate_30 is not None and hit_rate_30 < BLOCK_MARKET_MIN_HIT_RATE:
        return False, "rolling_30_below_min_hit_rate"
    if sample_size_60 >= BLOCK_MARKET_MIN_SAMPLE_60 and hit_rate_60 is not None and hit_rate_60 < BLOCK_MARKET_MIN_HIT_RATE:
        return False, "rolling_60_below_min_hit_rate"
    return True, None
