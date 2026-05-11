from __future__ import annotations

from dataclasses import asdict

from probettips.models import Pick
from probettips.supabase_store import SupabaseStore


def load_history(store: SupabaseStore) -> list[dict]:
    return store.list_daily_tips()


def save_history(_: list[dict]) -> None:
    return None


def upsert_ticket(
    store: SupabaseStore,
    date_label: str,
    source: str,
    picks: list[Pick],
    strategy: str = "official",
    recommendation_tier: str | None = None,
    calibration_candidates: list[Pick] | None = None,
) -> dict:
    ticket = build_ticket(date_label, source, picks, strategy, recommendation_tier, calibration_candidates or [])
    saved = store.upsert_daily_tip(ticket)
    selected_keys = {(pick.match_id, pick.market, pick.bet_type) for pick in picks}
    store.replace_candidate_picks(
        tip_date=date_label,
        strategy=strategy,
        candidates=[asdict(pick) for pick in calibration_candidates or []],
        selected_keys=selected_keys,
    )
    return saved


def build_ticket(
    date_label: str,
    source: str,
    picks: list[Pick],
    strategy: str = "official",
    recommendation_tier: str | None = None,
    calibration_candidates: list[Pick] | None = None,
) -> dict:
    combined_odds = round(product([pick.odds for pick in picks]), 2)
    combined_probability = round(product([pick.probability for pick in picks]), 4)
    return {
        "date": date_label,
        "strategy": strategy,
        "source": source,
        "status": "pending",
        "result": None,
        "combined_odds": combined_odds,
        "combined_probability": combined_probability,
        "recommendation_tier": recommendation_tier,
        "picks": [asdict(pick) for pick in picks],
        "calibration_candidates": [asdict(pick) for pick in calibration_candidates or []],
        "settlement": None,
    }


def product(values: list[float]) -> float:
    total = 1.0
    for value in values:
        total *= value
    return total


def compute_stats(entries: list[dict], strategy: str | None = "official") -> dict:
    settled = [
        entry for entry in entries
        if entry.get("status") == "settled"
        and (strategy is None or entry.get("strategy", "official") == strategy)
    ]
    wins = sum(1 for entry in settled if entry.get("result") == "win")
    losses = sum(1 for entry in settled if entry.get("result") == "loss")
    total = len(settled)
    accuracy = round((wins / total) * 100, 2) if total else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "accuracy_pct": accuracy,
    }


def strategy_bucket(strategy: str | None) -> str:
    normalized = (strategy or "official").strip().lower()
    if normalized == "official":
        return "official"
    if normalized == "shadow_manual":
        return "shadow_manual"
    if normalized.startswith("shadow"):
        return "shadow_auto"
    return "other"


def compute_strategy_metrics(entries: list[dict]) -> dict[str, dict]:
    buckets = {
        "official": [],
        "shadow_auto": [],
        "shadow_manual": [],
        "other": [],
    }
    for entry in entries:
        buckets[strategy_bucket(entry.get("strategy"))].append(entry)

    metrics: dict[str, dict] = {}
    for bucket_name, bucket_entries in buckets.items():
        settled = [entry for entry in bucket_entries if entry.get("status") == "settled"]
        wins = sum(1 for entry in settled if entry.get("result") == "win")
        losses = sum(1 for entry in settled if entry.get("result") == "loss")
        total = len(bucket_entries)
        resolved = len(settled)
        profit_units = wins - losses
        hit_rate = round((wins / resolved) * 100, 2) if resolved else 0.0
        roi_pct = round((profit_units / total) * 100, 2) if total else 0.0
        metrics[bucket_name] = {
            "total": total,
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "hit_rate_pct": hit_rate,
            "profit_units": profit_units,
            "roi_pct": roi_pct,
        }
    return metrics
