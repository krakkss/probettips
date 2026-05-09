from __future__ import annotations

from probettips.models import Match


SAMPLE_MATCHES = [
    Match(
        match_id="sample-001",
        competition_code="PD",
        league="La Liga",
        home_team="Real Madrid",
        away_team="Getafe",
        kickoff="2026-05-08 21:00",
        home_rank=1,
        away_rank=14,
        home_ppg=2.35,
        away_ppg=1.02,
        home_goal_diff=41,
        away_goal_diff=-9,
    ),
    Match(
        match_id="sample-002",
        competition_code="PL",
        league="Premier League",
        home_team="Manchester City",
        away_team="Wolves",
        kickoff="2026-05-08 20:30",
        home_rank=2,
        away_rank=13,
        home_ppg=2.22,
        away_ppg=1.08,
        home_goal_diff=36,
        away_goal_diff=-11,
    ),
    Match(
        match_id="sample-003",
        competition_code="SA",
        league="Serie A",
        home_team="Inter",
        away_team="Empoli",
        kickoff="2026-05-08 18:30",
        home_rank=1,
        away_rank=16,
        home_ppg=2.28,
        away_ppg=0.94,
        home_goal_diff=33,
        away_goal_diff=-14,
    ),
]


SAMPLE_RESULTS = {
    "sample-001": {"status": "FINISHED", "home": 2, "away": 0},
    "sample-002": {"status": "FINISHED", "home": 2, "away": 1},
    "sample-003": {"status": "FINISHED", "home": 1, "away": 0},
}
