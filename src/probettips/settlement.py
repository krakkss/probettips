from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Any

from probettips.history import compute_stats, load_history
from probettips.providers import FootballDataProvider


def settle_pending_tickets(store, api_token: str) -> dict:
    tickets = load_history(store)
    checked_count = 0
    settled_count = 0
    provider = FootballDataProvider(api_token) if api_token else None
    result_cache: dict[tuple[str, str, str, str], dict | None] = {}

    for ticket in tickets:
        if not _needs_settlement_refresh(ticket):
            continue

        picks = _ensure_pick_list(ticket.get("picks"))
        if not picks:
            continue

        checked_count += 1
        ticket_result = _resolve_ticket(ticket, picks, api_token, provider, result_cache)
        if not ticket_result:
            continue

        _persist_settlement(store, ticket, ticket_result["result"], ticket_result["settlement"])
        settled_count += 1

    return {
        "checked_count": checked_count,
        "settled_count": settled_count,
    }


def settle_tickets(store, api_token: str, date_label: str | None = None) -> tuple[list[dict], dict]:
    entries = load_history(store)
    updated: list[dict] = []
    provider = FootballDataProvider(api_token) if api_token else None
    result_cache: dict[tuple[str, str, str, str], dict | None] = {}

    for ticket in entries:
        if not _needs_settlement_refresh(ticket):
            continue
        if date_label and ticket.get("date") != date_label:
            continue

        picks = _ensure_pick_list(ticket.get("picks"))
        if not picks:
            continue

        ticket_result = _resolve_ticket(ticket, picks, api_token, provider, result_cache)
        if not ticket_result:
            continue

        _persist_settlement(store, ticket, ticket_result["result"], ticket_result["settlement"])
        updated.append(
            {
                **ticket,
                "status": "settled",
                "result": ticket_result["result"],
                "settlement": ticket_result["settlement"],
            }
        )

    latest_entries = load_history(store)
    return updated, compute_stats(latest_entries, strategy="official")


def _needs_settlement_refresh(ticket: dict) -> bool:
    status = ticket.get("status")
    if status == "pending":
        return True
    if status == "settled" and not ticket.get("settlement"):
        return True
    return False


def check_match_result(
    pick: dict[str, Any],
    api_token: str,
    provider: FootballDataProvider | None = None,
    result_cache: dict[tuple[str, str, str, str], dict | None] | None = None,
) -> tuple[str, bool | None, dict[str, int] | None]:
    match_id = pick.get("match_id")
    if not match_id:
        return "pending", None, None

    if str(match_id).startswith("flashscore::"):
        return _check_flashscore_match_result(pick, api_token, provider, result_cache)

    url = f"https://api.football-data.org/v4/matches/{match_id}"
    request = urllib.request.Request(url, headers={"X-Auth-Token": api_token}, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return "pending", None, None

    status = data.get("status")
    if status not in {"FINISHED", "AWARDED"}:
        return "pending", None, None

    score = data.get("score", {}).get("fullTime", {})
    home_goals = score.get("home")
    away_goals = score.get("away")
    if home_goals is None or away_goals is None:
        return "pending", None, None

    is_win = evaluate_market(pick.get("market", ""), home_goals, away_goals)
    if is_win is None:
        return "pending", None, None

    return "finished", is_win, {"home": home_goals, "away": away_goals}


def _check_flashscore_match_result(
    pick: dict[str, Any],
    api_token: str,
    provider: FootballDataProvider | None = None,
    result_cache: dict[tuple[str, str, str, str], dict | None] | None = None,
) -> tuple[str, bool | None, dict[str, int] | None]:
    parsed = _parse_flashscore_match_id(str(pick.get("match_id", "")))
    if not parsed:
        return "pending", None, None

    competition_code, date_str, home_team, away_team = parsed
    cache_key = (competition_code, date_str, home_team, away_team)
    if result_cache is not None and cache_key in result_cache:
        result = result_cache[cache_key]
    else:
        active_provider = provider or FootballDataProvider(api_token)
        try:
            result = active_provider.find_match_result(competition_code, date_str, home_team, away_team)
        except Exception:
            return "pending", None, None
        if result_cache is not None:
            result_cache[cache_key] = result

    if not result:
        return "pending", None, None
    if result.get("status") not in {"FINISHED", "AWARDED"}:
        return "pending", None, None

    home_goals = result.get("home")
    away_goals = result.get("away")
    if home_goals is None or away_goals is None:
        return "pending", None, None

    is_win = evaluate_market(pick.get("market", ""), int(home_goals), int(away_goals))
    if is_win is None:
        return "pending", None, None
    return "finished", is_win, {"home": int(home_goals), "away": int(away_goals)}


def evaluate_market(market: str, home_goals: int, away_goals: int) -> bool | None:
    market = (market or "").strip()
    total_goals = home_goals + away_goals

    if market == "1X":
        return home_goals >= away_goals
    if market == "X2":
        return away_goals >= home_goals
    if market == "Gana local":
        return home_goals > away_goals
    if market == "Gana visitante":
        return away_goals > home_goals
    if market in {"Mas de 0.5 goles", "Más de 0.5 goles"}:
        return total_goals >= 1
    if market in {"Mas de 1.5 goles", "Más de 1.5 goles", "Over 1.5"}:
        return total_goals >= 2
    if market == "Over 2.5":
        return total_goals >= 3
    if market.startswith("Bet Builder:"):
        parts = [part.strip() for part in market.replace("Bet Builder:", "", 1).split("+")]
        if not parts:
            return None
        results = [evaluate_market(part, home_goals, away_goals) for part in parts]
        if any(result is None for result in results):
            return None
        return all(results)
    return None


def _resolve_ticket(
    ticket: dict,
    picks: list[dict],
    api_token: str,
    provider: FootballDataProvider | None = None,
    result_cache: dict[tuple[str, str, str, str], dict | None] | None = None,
) -> dict | None:
    all_finished = True
    overall_result = "win"
    leg_results: list[dict[str, Any]] = []

    for pick in picks:
        match_status, is_win, details = check_match_result(pick, api_token, provider, result_cache)
        leg_results.append(
            {
                "match_id": pick.get("match_id"),
                "match_label": pick.get("match_label") or pick.get("match"),
                "market": pick.get("market"),
                "status": match_status,
                "won": is_win,
                "score": details,
            }
        )

        if match_status != "finished":
            all_finished = False
            continue
        if not is_win:
            overall_result = "loss"

    if not all_finished:
        return None

    symbol = "✅" if overall_result == "win" else "❌"
    return {
        "result": overall_result,
        "settlement": {
            "symbol": symbol,
            "legs": leg_results,
        },
    }


def _persist_settlement(store, ticket: dict, result: str, settlement: dict) -> None:
    entry = {
        "date": ticket["date"],
        "strategy": ticket.get("strategy", "official"),
        "source": ticket.get("source", ""),
        "status": "settled",
        "result": result,
        "combined_odds": ticket.get("combined_odds", 1.0),
        "combined_probability": ticket.get("combined_probability", 0.0),
        "recommendation_tier": ticket.get("recommendation_tier"),
        "picks": _ensure_pick_list(ticket.get("picks")),
        "settlement": settlement,
    }
    store.upsert_daily_tip(entry)


def _ensure_pick_list(value: Any) -> list[dict]:
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, list):
        return value
    return []


def _parse_flashscore_match_id(match_id: str) -> tuple[str, str, str, str] | None:
    parts = match_id.split("::", 4)
    if len(parts) != 5:
        return None
    _, competition_code, date_str, home_team, away_team = parts
    return competition_code, date_str, home_team, away_team


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()
