from __future__ import annotations

from dataclasses import dataclass
import html
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from probettips.models import Match, Pick

RSS_BASE_URL = "https://news.google.com/rss/search"
MAX_HEADLINES_PER_TEAM = 5

AVAILABILITY_KEYWORDS = (
    "injury",
    "injuries",
    "injured",
    "lesion",
    "lesionado",
    "suspended",
    "suspension",
    "ban",
    "banned",
    "missing",
    "absence",
    "absent",
    "out",
    "doubtful",
    "duda",
    "unavailable",
    "without",
    "ruled out",
    "fitness test",
    "miss out",
    "set to miss",
)

ROTATION_KEYWORDS = (
    "rotation",
    "rotated",
    "rested",
    "bench",
    "changes",
    "second string",
    "reserve side",
    "lineup",
    "line-up",
    "starting xi",
    "team news",
)

INSTABILITY_KEYWORDS = (
    "manager",
    "coach",
    "caretaker",
    "sacked",
    "crisis",
    "turmoil",
)

SEVERE_AVAILABILITY_KEYWORDS = (
    "ruled out",
    "set to miss",
    "without",
    "major doubt",
)


@dataclass(slots=True)
class MatchContext:
    match_id: str
    penalty: float
    alerts: list[str]
    source: str


class TeamNewsContextProvider:
    def __init__(self) -> None:
        self._team_cache: dict[str, tuple[float, list[str]]] = {}

    def build_match_contexts(self, matches: list[Match]) -> dict[str, MatchContext]:
        contexts: dict[str, MatchContext] = {}
        for match in matches:
            home_penalty, home_alerts = self._team_context(match.home_team)
            away_penalty, away_alerts = self._team_context(match.away_team)
            penalty = min(0.10, home_penalty + away_penalty)
            alerts = home_alerts + away_alerts
            contexts[match.match_id] = MatchContext(
                match_id=match.match_id,
                penalty=round(penalty, 4),
                alerts=alerts[:4],
                source="Google News RSS" if alerts else "",
            )
        return contexts

    def _team_context(self, team_name: str) -> tuple[float, list[str]]:
        cache_key = team_name.strip().lower()
        if cache_key in self._team_cache:
            return self._team_cache[cache_key]

        try:
            titles = self._fetch_team_headlines(team_name)
        except Exception:
            titles = []

        availability_hits = 0
        rotation_hits = 0
        instability_hits = 0
        severe_availability_hits = 0
        for title in titles:
            normalized_title = normalize_text(title)
            if any(keyword in normalized_title for keyword in AVAILABILITY_KEYWORDS):
                availability_hits += 1
            if any(keyword in normalized_title for keyword in SEVERE_AVAILABILITY_KEYWORDS):
                severe_availability_hits += 1
            if any(keyword in normalized_title for keyword in ROTATION_KEYWORDS):
                rotation_hits += 1
            if any(keyword in normalized_title for keyword in INSTABILITY_KEYWORDS):
                instability_hits += 1

        penalty = min(
            0.08,
            (availability_hits * 0.02)
            + (severe_availability_hits * 0.01)
            + (rotation_hits * 0.012)
            + (instability_hits * 0.008),
        )

        alerts: list[str] = []
        if availability_hits:
            alerts.append(f"{team_name}: las noticias recientes mencionan bajas o dudas de disponibilidad.")
        if severe_availability_hits:
            alerts.append(f"{team_name}: hay indicios de bajas importantes o jugadores que podrían perderse el partido.")
        if rotation_hits:
            alerts.append(f"{team_name}: hay señales recientes de posibles rotaciones, cambios de once o descanso.")
        if instability_hits:
            alerts.append(f"{team_name}: el contexto reciente apunta a cierta inestabilidad deportiva.")

        result = (round(penalty, 4), alerts[:4])
        self._team_cache[cache_key] = result
        return result

    def _fetch_team_headlines(self, team_name: str) -> list[str]:
        query = f'"{team_name}" football OR soccer injury suspension lineup rotation'
        url = f"{RSS_BASE_URL}?{urllib.parse.urlencode({'q': query, 'hl': 'en-GB', 'gl': 'GB', 'ceid': 'GB:en'})}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
            payload = response.read().decode("utf-8", errors="ignore")

        root = ET.fromstring(payload)
        titles: list[str] = []
        for item in root.findall(".//item/title"):
            if not item.text:
                continue
            cleaned_title = clean_headline(item.text)
            if cleaned_title:
                titles.append(cleaned_title)
            if len(titles) >= MAX_HEADLINES_PER_TEAM:
                break
        return titles


def apply_match_context_to_picks(picks: list[Pick], match_contexts: dict[str, MatchContext]) -> list[Pick]:
    adjusted: list[Pick] = []
    for pick in picks:
        context = match_contexts.get(pick.match_id)
        if not context or context.penalty <= 0 or not context.alerts:
            adjusted.append(pick)
            continue

        adjusted_probability = max(0.01, min(0.99, pick.probability - (context.penalty * 0.55)))
        adjusted_confidence = max(0.35, min(0.99, pick.confidence - (context.penalty * 0.85)))
        adjusted_risk = min(0.99, pick.risk_score + (context.penalty * 0.90))
        adjusted_threshold = min(0.98, pick.dynamic_threshold + (context.penalty * 0.35))
        adjusted_rationale = f"{pick.rationale} Contexto reciente detectado: {' '.join(context.alerts)}"

        adjusted.append(
            Pick(
                match_id=pick.match_id,
                competition_code=pick.competition_code,
                league=pick.league,
                match_label=pick.match_label,
                kickoff=pick.kickoff,
                bet_type=pick.bet_type,
                market=pick.market,
                probability=round(adjusted_probability, 4),
                odds=pick.odds,
                confidence=round(adjusted_confidence, 4),
                risk_score=round(adjusted_risk, 4),
                market_stability=pick.market_stability,
                dynamic_threshold=round(adjusted_threshold, 4),
                rationale=adjusted_rationale,
                context_penalty=context.penalty,
                context_alerts=context.alerts,
                context_source=context.source,
            )
        )
    return adjusted


def clean_headline(title: str) -> str:
    cleaned = html.unescape(title)
    cleaned = re.sub(r"\s*-\s*Google News\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()
