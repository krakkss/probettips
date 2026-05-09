from __future__ import annotations

from probettips.history import compute_stats, load_history
from probettips.providers import FootballDataProvider
from probettips.sample_data import SAMPLE_RESULTS
from probettips.supabase_store import SupabaseStore


def settle_tickets(store: SupabaseStore, api_token: str, date_label: str | None = None) -> tuple[list[dict], dict]:
    entries = load_history(store)
    provider = FootballDataProvider(api_token) if api_token else None
    updated: list[dict] = []

    for entry in entries:
        if entry.get("status") == "settled":
            continue
        if date_label and entry["date"] != date_label:
            continue

        leg_results = []
        pending = False
        for pick in entry["picks"]:
            result = resolve_pick_result(provider, pick)
            if result["status"] != "FINISHED":
                pending = True
                break
            leg_results.append(result)

        if pending or len(leg_results) != len(entry["picks"]):
            continue

        is_win = all(item["won"] for item in leg_results)
        entry["status"] = "settled"
        entry["result"] = "win" if is_win else "loss"
        entry["settlement"] = {
            "legs": leg_results,
            "symbol": "✅" if is_win else "❌",
        }
        updated.append(entry)

    for entry in updated:
        store.upsert_daily_tip(entry)
    return updated, compute_stats(entries, strategy="official")


def resolve_pick_result(provider: FootballDataProvider | None, pick: dict) -> dict:
    match_id = pick["match_id"]
    if provider:
        try:
            match_result = provider.get_match_result(match_id)
        except Exception:
            match_result = SAMPLE_RESULTS.get(match_id, {"status": "PENDING", "home": None, "away": None})
    else:
        match_result = SAMPLE_RESULTS.get(match_id, {"status": "PENDING", "home": None, "away": None})

    won = evaluate_market(pick["market"], match_result.get("home"), match_result.get("away"))
    return {
        "match_label": pick["match_label"],
        "bet_type": pick.get("bet_type", "simple"),
        "market": pick["market"],
        "status": match_result.get("status"),
        "home": match_result.get("home"),
        "away": match_result.get("away"),
        "won": won,
    }


def evaluate_market(market: str, home_goals: int | None, away_goals: int | None) -> bool:
    if home_goals is None or away_goals is None:
        return False
    if market.startswith("Bet Builder: "):
        builder_parts = market.removeprefix("Bet Builder: ").split(" + ")
        return all(evaluate_market(part, home_goals, away_goals) for part in builder_parts)
    if market == "1X":
        return home_goals >= away_goals
    if market == "X2":
        return away_goals >= home_goals
    if market == "Mas de 0.5 goles":
        return (home_goals + away_goals) >= 1
    if market == "Mas de 1.5 goles":
        return (home_goals + away_goals) >= 2
    if market == "Gana local":
        return home_goals > away_goals
    if market == "Gana visitante":
        return away_goals > home_goals
    return False
