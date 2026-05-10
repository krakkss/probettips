from __future__ import annotations

from itertools import combinations

from probettips.analysis import (
    MarketCalibration,
    adjusted_threshold,
    calibrated_probability,
    market_bias,
    market_core_bonus,
    market_needs_extra_evidence,
)
from probettips.models import Pick

BOOKMAKER_ODDS_HAIRCUT = 0.12
OFFICIAL_MIN_LEG_ODDS = 1.14
LOW_VALUE_MARKETS = {"Mas de 0.5 goles", "Más de 0.5 goles"}


def choose_two_picks(
    picks: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None = None,
    min_probability: float = 0.72,
    min_confidence: float = 0.62,
    combined_odds_target: float = 1.60,
    minimum_combined_odds: float = 1.60,
    maximum_combined_odds: float = 1.95,
) -> tuple[list[Pick], str | None]:
    eligible = _eligible_picks(picks, market_calibrations, min_probability, min_confidence)
    eligible.sort(key=lambda item: composite_pick_score(item, market_calibrations), reverse=True)
    if not eligible:
        return [], None
    official_eligible = [
        pick for pick in eligible
        if adjusted_odds_for_bookmaker(pick.odds) >= OFFICIAL_MIN_LEG_ODDS
        and pick.market not in LOW_VALUE_MARKETS
    ]
    if official_eligible:
        eligible = official_eligible

    strong_single = None
    strong_combo: list[Pick] = []
    for allowed_biases in ({"core"}, {"core", "semi_aggressive"}, {"core", "semi_aggressive", "aggressive"}):
        if not strong_single:
            strong_single = _find_best_single(
                eligible,
                market_calibrations=market_calibrations,
                minimum_odds=1.55,
                maximum_odds=1.75,
                target_odds=1.60,
                allowed_biases=allowed_biases,
            )
        if not strong_combo:
            strong_combo = _find_best_pair(
                eligible,
                market_calibrations=market_calibrations,
                combined_odds_target=combined_odds_target,
                minimum_combined_odds=minimum_combined_odds,
                maximum_combined_odds=maximum_combined_odds,
                allowed_biases=allowed_biases,
            )
        if strong_single or strong_combo:
            break

    if strong_single and _single_beats_combo(strong_single, strong_combo, market_calibrations):
        return [strong_single], "strong_single"
    if strong_combo:
        return strong_combo, "strong_combo"
    if strong_single:
        return [strong_single], "strong_single"

    fallback_single = None
    fallback_combo = []
    for allowed_biases in ({"core"}, {"core", "semi_aggressive"}, {"core", "semi_aggressive", "aggressive"}):
        if not fallback_single:
            fallback_single = _find_best_single(
                eligible,
                market_calibrations=market_calibrations,
                minimum_odds=1.40,
                maximum_odds=1.59,
                target_odds=1.48,
                fallback_penalty=0.03,
                allowed_biases=allowed_biases,
            )
        if not fallback_combo:
            fallback_combo = _find_best_pair(
                eligible,
                market_calibrations=market_calibrations,
                combined_odds_target=1.48,
                minimum_combined_odds=1.40,
                maximum_combined_odds=1.59,
                fallback_penalty=0.03,
                allowed_biases=allowed_biases,
            )
        if fallback_single or fallback_combo:
            break

    if fallback_single and _single_beats_combo(fallback_single, fallback_combo, market_calibrations):
        return [fallback_single], "low_edge_single"
    if fallback_combo:
        return fallback_combo, "low_edge_combo"
    if fallback_single:
        return [fallback_single], "low_edge_single"

    return [], None


def choose_shadow_picks(
    picks: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None = None,
    min_probability: float = 0.72,
    min_confidence: float = 0.62,
) -> tuple[list[Pick], str | None]:
    eligible = _eligible_picks(picks, market_calibrations, min_probability, min_confidence)
    eligible.sort(key=lambda item: composite_pick_score(item, market_calibrations), reverse=True)
    if not eligible:
        return [], None

    for allowed_biases, target_odds, min_odds, max_odds, tier in (
        ({"core"}, 1.48, 1.40, 1.70, "shadow_core"),
        ({"core", "semi_aggressive"}, 1.52, 1.40, 1.75, "shadow_mixed"),
        ({"core", "semi_aggressive", "aggressive"}, 1.55, 1.40, 1.80, "shadow_open"),
    ):
        shadow_combo = _find_best_pair(
            eligible,
            market_calibrations=market_calibrations,
            combined_odds_target=target_odds,
            minimum_combined_odds=min_odds,
            maximum_combined_odds=max_odds,
            fallback_penalty=0.01,
            allowed_biases=allowed_biases,
        )
        if shadow_combo:
            return shadow_combo, tier

    return [], None


def _find_best_single(
    eligible: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None,
    minimum_odds: float,
    maximum_odds: float,
    target_odds: float,
    fallback_penalty: float = 0.0,
    allowed_biases: set[str] | None = None,
) -> Pick | None:
    best_pick: Pick | None = None
    best_score = float("-inf")

    for pick in eligible:
        effective_odds = adjusted_odds_for_bookmaker(pick.odds)
        if effective_odds < minimum_odds or effective_odds > maximum_odds:
            continue
        if allowed_biases and market_bias(pick.market) not in allowed_biases:
            continue
        distance = abs(effective_odds - target_odds)
        score = composite_pick_score(pick, market_calibrations) - (distance * 0.18) - fallback_penalty
        if score > best_score:
            best_score = score
            best_pick = pick

    return best_pick


def _find_best_pair(
    eligible: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None,
    combined_odds_target: float,
    minimum_combined_odds: float,
    maximum_combined_odds: float,
    fallback_penalty: float = 0.0,
    allowed_biases: set[str] | None = None,
) -> list[Pick]:
    best_pair: tuple[Pick, Pick] | None = None
    best_score = float("-inf")

    for first, second in combinations(eligible, 2):
        if first.match_id == second.match_id:
            continue
        if allowed_biases and (market_bias(first.market) not in allowed_biases or market_bias(second.market) not in allowed_biases):
            continue

        combined_odds = round(first.odds * second.odds, 2)
        effective_combined_odds = adjusted_odds_for_bookmaker(combined_odds)
        if effective_combined_odds < minimum_combined_odds or effective_combined_odds > maximum_combined_odds:
            continue

        distance = abs(effective_combined_odds - combined_odds_target)
        pair_score = composite_pair_score(first, second, market_calibrations) - (distance * 0.20) - fallback_penalty
        if pair_score > best_score:
            best_score = pair_score
            best_pair = (first, second)

    if not best_pair:
        return []

    return list(best_pair)


def _eligible_picks(
    picks: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None,
    min_probability: float,
    min_confidence: float,
) -> list[Pick]:
    return [
        pick for pick in picks
        if effective_probability(pick, market_calibrations) >= min_probability
        and pick.confidence >= min_confidence
        and effective_probability(pick, market_calibrations) >= effective_threshold(pick, market_calibrations)
        and not should_reject_pick(pick, market_calibrations)
    ]


def composite_pick_score(pick: Pick, market_calibrations: dict[str, MarketCalibration] | None = None) -> float:
    probability = effective_probability(pick, market_calibrations)
    threshold_edge = max(0.0, probability - effective_threshold(pick, market_calibrations))
    core_bonus = market_core_bonus(pick.market)
    value_penalty = _value_penalty(pick)
    calibration = market_calibrations.get(pick.market) if market_calibrations else None
    historical_hit_rate = calibration.posterior_hit_rate if calibration else probability
    volatility_penalty = calibration.volatility_penalty if calibration else 0.0
    reliability_score = calibration.reliability_score if calibration else probability
    return (
        (probability * historical_hit_rate)
        + (reliability_score * 0.38)
        - volatility_penalty
        + (pick.confidence * 0.10)
        + (pick.market_stability * 0.10)
        - (pick.risk_score * 0.18)
        - (pick.context_penalty * 0.45)
        - value_penalty
        + (threshold_edge * 0.12)
        + core_bonus
    )


def composite_pair_score(
    first: Pick,
    second: Pick,
    market_calibrations: dict[str, MarketCalibration] | None = None,
) -> float:
    first_probability = effective_probability(first, market_calibrations)
    second_probability = effective_probability(second, market_calibrations)
    combined_probability = first_probability * second_probability
    combined_confidence = (first.confidence + second.confidence) / 2
    combined_stability = (first.market_stability + second.market_stability) / 2
    combined_risk = (first.risk_score + second.risk_score) / 2
    market_bias_bonus = (market_core_bonus(first.market) + market_core_bonus(second.market)) / 2
    value_penalty = (_value_penalty(first) + _value_penalty(second)) / 2
    first_calibration = market_calibrations.get(first.market) if market_calibrations else None
    second_calibration = market_calibrations.get(second.market) if market_calibrations else None
    historical_hit_rate = (
        ((first_calibration.posterior_hit_rate if first_calibration else first_probability)
        + (second_calibration.posterior_hit_rate if second_calibration else second_probability)) / 2
    )
    volatility_penalty = (
        ((first_calibration.volatility_penalty if first_calibration else 0.0)
        + (second_calibration.volatility_penalty if second_calibration else 0.0)) / 2
    )
    reliability_score = (
        ((first_calibration.reliability_score if first_calibration else first_probability)
        + (second_calibration.reliability_score if second_calibration else second_probability)) / 2
    )
    threshold_edge = (
        (first_probability - effective_threshold(first, market_calibrations))
        + (second_probability - effective_threshold(second, market_calibrations))
    ) / 2
    mixed_bonus = 0.01 if first.bet_type != second.bet_type else 0.0
    return (
        (combined_probability * historical_hit_rate)
        + (reliability_score * 0.34)
        - volatility_penalty
        + (combined_confidence * 0.10)
        + (combined_stability * 0.08)
        - (combined_risk * 0.16)
        - ((first.context_penalty + second.context_penalty) * 0.22)
        - value_penalty
        + (threshold_edge * 0.10)
        + market_bias_bonus
        + mixed_bonus
    )


def _single_beats_combo(
    single_pick: Pick,
    combo_picks: list[Pick],
    market_calibrations: dict[str, MarketCalibration] | None = None,
) -> bool:
    if not combo_picks:
        return True

    single_score = composite_pick_score(single_pick, market_calibrations)
    combo_score = composite_pair_score(combo_picks[0], combo_picks[1], market_calibrations)
    return single_score >= combo_score + 0.08


def effective_probability(pick: Pick, market_calibrations: dict[str, MarketCalibration] | None = None) -> float:
    return calibrated_probability(pick.probability, pick.market, market_calibrations)


def effective_threshold(pick: Pick, market_calibrations: dict[str, MarketCalibration] | None = None) -> float:
    return adjusted_threshold(pick.dynamic_threshold, pick.market, market_calibrations)


def should_reject_pick(pick: Pick, market_calibrations: dict[str, MarketCalibration] | None = None) -> bool:
    calibration = market_calibrations.get(pick.market) if market_calibrations else None
    if calibration and not calibration.enabled:
        return True
    if not market_needs_extra_evidence(pick.market, calibration):
        if calibration and calibration.sample_size_60 >= 6 and calibration.reliability_score < 0.62:
            return True
        if pick.context_penalty >= 0.08:
            return True
        return False

    probability = effective_probability(pick, market_calibrations)
    threshold = effective_threshold(pick, market_calibrations)
    edge = probability - threshold
    volatility_penalty = calibration.volatility_penalty if calibration else 0.0
    return (
        edge < 0.05
        or pick.confidence < 0.82
        or pick.risk_score > 0.12
        or volatility_penalty > 0.10
        or pick.context_penalty >= 0.06
    )


def adjusted_odds_for_bookmaker(estimated_odds: float) -> float:
    if estimated_odds <= 1.0:
        return round(estimated_odds, 2)
    reduced_margin = (estimated_odds - 1.0) * (1 - BOOKMAKER_ODDS_HAIRCUT)
    return round(1.0 + reduced_margin, 2)


def _value_penalty(pick: Pick) -> float:
    effective_odds = adjusted_odds_for_bookmaker(pick.odds)
    penalty = 0.0
    if pick.market in LOW_VALUE_MARKETS:
        penalty += 0.14
    if effective_odds < OFFICIAL_MIN_LEG_ODDS:
        penalty += min(0.10, (OFFICIAL_MIN_LEG_ODDS - effective_odds) * 1.6)
    return penalty
