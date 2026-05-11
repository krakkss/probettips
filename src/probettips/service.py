from __future__ import annotations

from datetime import date

from probettips.analysis import build_market_calibrations
from probettips.context import TeamNewsContextProvider, apply_match_context_to_picks
from probettips.engine import build_candidate_picks
from probettips.models import Pick
from probettips.providers import DEFAULT_COMPETITIONS, FlashscoreScheduleProvider, FootballDataProvider
from probettips.sample_data import SAMPLE_MATCHES
from probettips.selector import choose_shadow_picks, choose_two_picks, composite_pick_score
from probettips.supabase_store import SupabaseStore

def generate_daily_picks(
    target_date: str | None,
    api_token: str,
    store: SupabaseStore | None = None,
    excluded_match_ids: set[str] | None = None,
    strategy: str = "official",
) -> tuple[str, list[Pick], str, str | None, list[Pick]]:
    date_label = target_date or date.today().isoformat()

    if api_token:
        strength_provider = FootballDataProvider(api_token)
        schedule_provider = FlashscoreScheduleProvider(strength_provider)
        matches = schedule_provider.get_matches_for_date(date_label, DEFAULT_COMPETITIONS)
        leagues_with_matches = sorted({match.league for match in matches})
        source = "flashscore.es + soccerway.com + football-data.org"
        if leagues_with_matches:
            source = f"flashscore.es + soccerway.com + football-data.org ({', '.join(leagues_with_matches)})"
        if not matches:
            matches = strength_provider.get_matches_for_date(date_label, DEFAULT_COMPETITIONS)
            leagues_with_matches = sorted({match.league for match in matches})
            source = "football-data.org"
            if leagues_with_matches:
                source = f"football-data.org ({', '.join(leagues_with_matches)})"
    else:
        matches = SAMPLE_MATCHES
        source = "sample_data"

    candidates = build_candidate_picks(matches)
    context_applied = False
    if api_token and matches:
        try:
            context_provider = TeamNewsContextProvider()
            match_contexts = context_provider.build_match_contexts(matches)
            if any(context.penalty > 0 and context.alerts for context in match_contexts.values()):
                candidates = apply_match_context_to_picks(candidates, match_contexts)
                context_applied = True
        except Exception:
            context_applied = False
    if excluded_match_ids:
        candidates = [candidate for candidate in candidates if candidate.match_id not in excluded_match_ids]
    calibrations = {}
    if store:
        try:
            calibrations = build_market_calibrations(store.list_daily_tips())
        except Exception:
            calibrations = {}
    if strategy == "shadow":
        selected, recommendation_tier = choose_shadow_picks(candidates, market_calibrations=calibrations)
    else:
        selected, recommendation_tier = choose_two_picks(candidates, market_calibrations=calibrations)
    ranked_candidates = sorted(
        candidates,
        key=lambda pick: composite_pick_score(pick, calibrations),
        reverse=True,
    )[:12]
    if context_applied:
        source = f"{source} + contexto ultima hora"
    return date_label, selected, source, recommendation_tier, ranked_candidates
