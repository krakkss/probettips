from __future__ import annotations

from math import exp

from probettips.models import Match, Pick


MARKET_STABILITY = {
    "1X": 0.90,
    "X2": 0.90,
    "Mas de 0.5 goles": 0.96,
    "Mas de 1.5 goles": 0.79,
    "Gana local": 0.62,
    "Bet Builder: 1X + Mas de 1.5 goles": 0.73,
    "Bet Builder: X2 + Mas de 1.5 goles": 0.72,
}

BASE_THRESHOLD = {
    "1X": 0.74,
    "X2": 0.74,
    "Mas de 0.5 goles": 0.83,
    "Mas de 1.5 goles": 0.76,
    "Gana local": 0.68,
    "Bet Builder: 1X + Mas de 1.5 goles": 0.73,
    "Bet Builder: X2 + Mas de 1.5 goles": 0.73,
}

MIN_CONFIDENCE_BY_MARKET = {
    "1X": 0.64,
    "X2": 0.64,
    "Mas de 0.5 goles": 0.68,
    "Mas de 1.5 goles": 0.66,
    "Gana local": 0.80,
    "Bet Builder: 1X + Mas de 1.5 goles": 0.76,
    "Bet Builder: X2 + Mas de 1.5 goles": 0.76,
}


def build_candidate_picks(matches: list[Match]) -> list[Pick]:
    picks: list[Pick] = []
    for match in matches:
        home_strength = score_team(match.home_rank, match.home_ppg, match.home_goal_diff, home_bonus=True)
        away_strength = score_team(match.away_rank, match.away_ppg, match.away_goal_diff, home_bonus=False)
        delta = home_strength - away_strength
        confidence = estimate_confidence(match)
        risk_score = estimate_risk_score(match, delta)

        home_win_prob = logistic(delta)
        away_win_prob = logistic(-delta - 0.2)
        draw_prob = max(0.10, 1.0 - home_win_prob - away_win_prob)

        one_x_prob = min(0.94, home_win_prob + draw_prob)
        x_two_prob = min(0.94, away_win_prob + draw_prob)
        over_05_prob = min(0.97, 0.78 + abs(delta) * 0.06 + (match.home_ppg + match.away_ppg) * 0.03)
        over_15_prob = min(0.92, 0.58 + abs(delta) * 0.12 + (match.home_ppg + match.away_ppg) * 0.05)
        away_not_lose_and_over_15_prob = min(0.84, max(0.45, x_two_prob * over_15_prob * 1.01))

        match_label = f"{match.home_team} vs {match.away_team}"
        rationale = (
            f"{match.home_team} llega con PPG {match.home_ppg:.2f} y diff {match.home_goal_diff}; "
            f"{match.away_team} con PPG {match.away_ppg:.2f} y diff {match.away_goal_diff}."
        )

        candidates = [
            ("simple", "1X", one_x_prob, confidence, rationale),
            ("simple", "X2", x_two_prob, confidence, rationale),
            ("simple", "Mas de 0.5 goles", over_05_prob, min(0.95, confidence + 0.02), rationale),
            ("simple", "Mas de 1.5 goles", over_15_prob, confidence, rationale),
        ]

        if home_win_prob >= 0.66 and confidence >= 0.82 and risk_score <= 0.14:
            candidates.append(
                ("simple", "Gana local", home_win_prob, max(0.62, confidence - 0.04), f"{rationale} Mercado agresivo permitido solo por superioridad local muy clara.")
            )
        if away_not_lose_and_over_15_prob >= 0.64 and confidence >= 0.78 and risk_score <= 0.16:
            candidates.append(
                ("bet_builder", "Bet Builder: X2 + Mas de 1.5 goles", away_not_lose_and_over_15_prob, max(0.57, confidence - 0.04), f"{rationale} Builder conservador orientado a bet365.")
            )

        builder_pick = build_builder_pick(
            match=match,
            match_label=match_label,
            delta=delta,
            one_x_prob=one_x_prob,
            x_two_prob=x_two_prob,
            over_15_prob=over_15_prob,
            confidence=confidence,
            risk_score=risk_score,
            rationale=rationale,
        )
        if builder_pick:
            picks.append(builder_pick)

        for bet_type, market, probability, market_confidence, market_rationale in candidates:
            maybe_pick = build_pick(
                match=match,
                match_label=match_label,
                bet_type=bet_type,
                market=market,
                probability=probability,
                confidence=market_confidence,
                risk_score=risk_score,
                rationale=market_rationale,
            )
            if maybe_pick:
                picks.append(maybe_pick)

    return picks


def build_pick(
    match: Match,
    match_label: str,
    bet_type: str,
    market: str,
    probability: float,
    confidence: float,
    risk_score: float,
    rationale: str,
) -> Pick | None:
    market_stability = MARKET_STABILITY[market]
    dynamic_threshold = compute_dynamic_threshold(market, risk_score, market_stability, confidence)
    minimum_confidence = MIN_CONFIDENCE_BY_MARKET[market]
    if probability < dynamic_threshold or confidence < minimum_confidence:
        return None

    return Pick(
        match_id=match.match_id,
        competition_code=match.competition_code,
        league=match.league,
        match_label=match_label,
        kickoff=match.kickoff,
        bet_type=bet_type,
        market=market,
        probability=probability,
        odds=estimate_market_odds(market, probability),
        confidence=confidence,
        risk_score=risk_score,
        market_stability=market_stability,
        dynamic_threshold=dynamic_threshold,
        rationale=rationale,
    )


def score_team(rank: int, ppg: float, goal_diff: int, home_bonus: bool) -> float:
    rank_score = max(0.0, (22 - rank) / 22)
    ppg_score = min(ppg / 3.0, 1.0)
    gd_score = max(min((goal_diff + 30) / 60, 1.0), 0.0)
    home_score = 0.10 if home_bonus else 0.0
    return rank_score * 0.35 + ppg_score * 0.45 + gd_score * 0.20 + home_score


def logistic(value: float) -> float:
    return 1 / (1 + exp(-4 * value))


def estimate_market_odds(market: str, probability: float) -> float:
    fair_odds = 1 / max(probability, 0.01)

    if market in {"1X", "X2"}:
        return round(min(1.38, max(1.12, fair_odds + 0.05)), 2)
    if market == "Mas de 0.5 goles":
        return round(min(1.22, max(1.05, fair_odds + 0.03)), 2)
    if market == "Mas de 1.5 goles":
        return round(min(1.55, max(1.18, fair_odds + 0.08)), 2)
    if market == "Gana local":
        return round(min(1.95, max(1.45, fair_odds + 0.12)), 2)
    if market == "Bet Builder: 1X + Mas de 1.5 goles":
        return round(min(1.72, max(1.40, fair_odds + 0.10)), 2)
    if market == "Bet Builder: X2 + Mas de 1.5 goles":
        return round(min(1.75, max(1.42, fair_odds + 0.10)), 2)
    return round(fair_odds, 2)


def build_builder_pick(
    match: Match,
    match_label: str,
    delta: float,
    one_x_prob: float,
    x_two_prob: float,
    over_15_prob: float,
    confidence: float,
    risk_score: float,
    rationale: str,
) -> Pick | None:
    builder_market: str | None = None
    anchor_probability = 0.0

    if delta >= 0.10 and one_x_prob >= 0.78 and over_15_prob >= 0.74:
        builder_market = "Bet Builder: 1X + Mas de 1.5 goles"
        anchor_probability = one_x_prob
    elif delta <= -0.10 and x_two_prob >= 0.78 and over_15_prob >= 0.74:
        builder_market = "Bet Builder: X2 + Mas de 1.5 goles"
        anchor_probability = x_two_prob
    else:
        return None

    builder_probability = min(0.86, max(0.68, anchor_probability * over_15_prob * 1.03))
    return build_pick(
        match=match,
        match_label=match_label,
        bet_type="bet_builder",
        market=builder_market,
        probability=builder_probability,
        confidence=max(0.55, confidence - 0.04),
        risk_score=risk_score,
        rationale=f"{rationale} Builder conservador orientado a bet365.",
    )


def estimate_confidence(match: Match) -> float:
    base_confidence = 0.55
    rank_signal = 0.10 if match.home_rank != 10 or match.away_rank != 10 else 0.0
    ppg_signal = min((match.home_ppg + match.away_ppg) / 6.0, 0.18)
    gd_signal = min((abs(match.home_goal_diff) + abs(match.away_goal_diff)) / 120.0, 0.12)
    return min(0.92, base_confidence + rank_signal + ppg_signal + gd_signal)


def estimate_risk_score(match: Match, delta: float) -> float:
    parity_risk = max(0.0, 0.28 - abs(delta)) * 1.4
    data_risk = 0.12 if _looks_like_fallback(match.home_rank, match.home_ppg, match.home_goal_diff) else 0.0
    data_risk += 0.12 if _looks_like_fallback(match.away_rank, match.away_ppg, match.away_goal_diff) else 0.0
    low_scoring_risk = max(0.0, 2.4 - (match.home_ppg + match.away_ppg)) * 0.05
    rank_risk = 0.06 if abs(match.home_rank - match.away_rank) <= 2 else 0.0
    return min(0.38, parity_risk + data_risk + low_scoring_risk + rank_risk)


def compute_dynamic_threshold(
    market: str,
    risk_score: float,
    market_stability: float,
    confidence: float,
) -> float:
    base = BASE_THRESHOLD[market]
    risk_penalty = risk_score * (0.55 if market_stability >= 0.85 else 0.70 if market_stability >= 0.70 else 0.82)
    confidence_relief = max(0.0, confidence - 0.78) * 0.18
    stability_relief = max(0.0, market_stability - 0.80) * 0.12
    return min(0.92, max(0.58, base + risk_penalty - confidence_relief - stability_relief))


def _looks_like_fallback(rank: int, ppg: float, goal_diff: int) -> bool:
    return rank == 10 and abs(ppg - 1.2) < 0.001 and goal_diff == 0
