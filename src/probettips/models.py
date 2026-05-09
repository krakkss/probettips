from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Match:
    match_id: str
    competition_code: str
    league: str
    home_team: str
    away_team: str
    kickoff: str
    home_rank: int
    away_rank: int
    home_ppg: float
    away_ppg: float
    home_goal_diff: int
    away_goal_diff: int


@dataclass(slots=True)
class Pick:
    match_id: str
    competition_code: str
    league: str
    match_label: str
    kickoff: str
    bet_type: str
    market: str
    probability: float
    odds: float
    confidence: float
    risk_score: float
    market_stability: float
    dynamic_threshold: float
    rationale: str
    context_penalty: float = 0.0
    context_alerts: list[str] = field(default_factory=list)
    context_source: str = ""
