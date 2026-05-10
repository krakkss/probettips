from __future__ import annotations

import json
from datetime import date, timedelta
import html
import re
import ssl
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Iterable

from probettips.models import Match


COMPETITIONS = {
    "PD": "La Liga",
    "SD": "Segunda Division",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
    "PL": "Premier League",
    "PPL": "Primeira Liga",
}

DEFAULT_COMPETITIONS = ["PD", "SD", "BL1", "SA", "FL1", "PL", "PPL"]


class FootballDataProvider:
    base_url = "https://api.football-data.org/v4"

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        self._competition_match_cache: dict[tuple[str, str], dict] = {}

    def get_matches_for_date(self, date_str: str, competitions: Iterable[str]) -> list[Match]:
        matches: list[Match] = []
        standings_cache: dict[str, dict[str, dict[str, float | int]]] = {}
        next_day = (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()

        for code in competitions:
            try:
                standings_cache[code] = self._get_competition_strength_table(code)
                payload = self._get_json(
                    f"/competitions/{code}/matches",
                    {"dateFrom": date_str, "dateTo": next_day},
                )
            except Exception:
                continue
            for item in payload.get("matches", []):
                if item.get("status") not in {"SCHEDULED", "TIMED"}:
                    continue
                home_name = item["homeTeam"]["name"]
                away_name = item["awayTeam"]["name"]
                table = standings_cache[code]
                home_data = table.get(home_name, self._fallback_strength())
                away_data = table.get(away_name, self._fallback_strength())
                matches.append(
                    Match(
                        match_id=str(item["id"]),
                        competition_code=code,
                        league=COMPETITIONS.get(code, code),
                        home_team=home_name,
                        away_team=away_name,
                        kickoff=item["utcDate"].replace("T", " ").replace("Z", " UTC"),
                        home_rank=int(home_data["rank"]),
                        away_rank=int(away_data["rank"]),
                        home_ppg=float(home_data["ppg"]),
                        away_ppg=float(away_data["ppg"]),
                        home_goal_diff=int(home_data["goal_diff"]),
                        away_goal_diff=int(away_data["goal_diff"]),
                    )
                )
        return matches

    def get_match_result(self, match_id: str) -> dict:
        payload = self._get_json(f"/matches/{match_id}")
        score = payload.get("score", {})
        full_time = score.get("fullTime", {}) or {}
        return {
            "status": payload.get("status"),
            "home": full_time.get("home"),
            "away": full_time.get("away"),
            "home_team": payload.get("homeTeam", {}).get("name"),
            "away_team": payload.get("awayTeam", {}).get("name"),
        }

    def find_match_result(self, competition_code: str, date_str: str, home_team: str, away_team: str) -> dict | None:
        payload = self._get_competition_matches_for_date(competition_code, date_str)
        target_home_variants = build_name_variants(home_team)
        target_away_variants = build_name_variants(away_team)

        for item in payload.get("matches", []):
            candidate_home = item.get("homeTeam", {}).get("name", "")
            candidate_away = item.get("awayTeam", {}).get("name", "")
            if not names_match(target_home_variants, candidate_home):
                continue
            if not names_match(target_away_variants, candidate_away):
                continue

            score = item.get("score", {})
            full_time = score.get("fullTime", {}) or {}
            return {
                "status": item.get("status"),
                "home": full_time.get("home"),
                "away": full_time.get("away"),
                "home_team": candidate_home,
                "away_team": candidate_away,
            }
        return None

    def _get_competition_matches_for_date(self, competition_code: str, date_str: str) -> dict:
        cache_key = (competition_code, date_str)
        if cache_key in self._competition_match_cache:
            return self._competition_match_cache[cache_key]

        next_day = (date.fromisoformat(date_str) + timedelta(days=1)).isoformat()
        payload = self._get_json(
            f"/competitions/{competition_code}/matches",
            {"dateFrom": date_str, "dateTo": next_day},
        )
        self._competition_match_cache[cache_key] = payload
        return payload

    def _get_competition_strength_table(self, code: str) -> dict[str, dict[str, float | int]]:
        payload = self._get_json(f"/competitions/{code}/standings")
        table: dict[str, dict[str, float | int]] = {}
        standings = payload.get("standings", [])
        if not standings:
            return table

        rows = standings[0].get("table", [])
        for row in rows:
            team_name = row["team"]["name"]
            played = max(row.get("playedGames", 0), 1)
            points = row.get("points", 0)
            won = row.get("won", 0)
            drawn = row.get("draw", 0)
            lost = row.get("lost", 0)
            scored = row.get("goalsFor", 0)
            conceded = row.get("goalsAgainst", 0)
            table[team_name] = {
                "rank": row.get("position", 10),
                "ppg": round(points / played, 3),
                "goal_diff": scored - conceded,
                "wins": won,
                "draws": drawn,
                "losses": lost,
            }
        return table

    def get_competition_strength_table(self, code: str) -> dict[str, dict[str, float | int]]:
        return self._get_competition_strength_table(code)

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict:
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            self.base_url + path + query,
            headers={"X-Auth-Token": self.api_token},
        )
        with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _fallback_strength() -> dict[str, float | int]:
        return {"rank": 10, "ppg": 1.2, "goal_diff": 0}


FLASHSCORE_LEAGUES = {
    "PD": {
        "league": "La Liga",
        "url": "https://www.flashscore.es/futbol/espana/laliga-ea-sports/",
    },
    "SD": {
        "league": "Segunda Division",
        "url": "https://www.flashscore.es/futbol/espana/laliga-hypermotion/",
    },
    "BL1": {
        "league": "Bundesliga",
        "url": "https://www.flashscore.es/futbol/alemania/bundesliga/",
    },
    "SA": {
        "league": "Serie A",
        "url": "https://www.flashscore.es/futbol/italia/serie-a/",
    },
    "FL1": {
        "league": "Ligue 1",
        "url": "https://www.flashscore.es/futbol/francia/ligue-1/",
    },
    "PL": {
        "league": "Premier League",
        "url": "https://www.flashscore.es/futbol/inglaterra/premier-league/",
    },
    "PPL": {
        "league": "Primeira Liga",
        "url": "https://www.flashscore.es/futbol/portugal/liga-portugal-betclic/",
    },
}


class FlashscoreScheduleProvider:
    def __init__(self, strength_provider: FootballDataProvider | None = None) -> None:
        self.strength_provider = strength_provider

    def get_matches_for_date(self, date_str: str, competitions: Iterable[str]) -> list[Match]:
        matches: list[Match] = []
        date_token = self._to_flashscore_date(date_str)

        for code in competitions:
            league_config = FLASHSCORE_LEAGUES.get(code)
            if not league_config:
                continue

            page_text = self._fetch_page_text(league_config["url"])
            pairings = self._extract_pairings_for_date(page_text, date_token)
            if not pairings:
                continue

            strength_table = self._get_strength_table(code)
            normalized_strength_table = build_normalized_strength_table(strength_table)
            for home_team, away_team in pairings:
                home_data = resolve_strength_data(home_team, strength_table, normalized_strength_table)
                away_data = resolve_strength_data(away_team, strength_table, normalized_strength_table)
                matches.append(
                    Match(
                        match_id=f"flashscore::{code}::{date_str}::{home_team}::{away_team}",
                        competition_code=code,
                        league=str(league_config["league"]),
                        home_team=home_team,
                        away_team=away_team,
                        kickoff=date_str,
                        home_rank=int(home_data["rank"]),
                        away_rank=int(away_data["rank"]),
                        home_ppg=float(home_data["ppg"]),
                        away_ppg=float(away_data["ppg"]),
                        home_goal_diff=int(home_data["goal_diff"]),
                        away_goal_diff=int(away_data["goal_diff"]),
                    )
                )

        return matches

    def _get_strength_table(self, code: str) -> dict[str, dict[str, float | int]]:
        if not self.strength_provider:
            return {}
        try:
            return self.strength_provider.get_competition_strength_table(code)
        except Exception:
            return {}

    def _fetch_page_text(self, url: str) -> str:
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
            raw_html = response.read().decode("utf-8", errors="ignore")

        no_scripts = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        no_styles = re.sub(r"<style.*?</style>", " ", no_scripts, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", no_styles)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _extract_pairings_for_date(self, page_text: str, date_token: str) -> list[tuple[str, str]]:
        day_segment_match = re.search(
            rf"{re.escape(date_token)}\.\s*(.*?)(?=(?:\d{{2}}\.\d{{2}}\.)|$)",
            page_text,
        )
        if not day_segment_match:
            return []

        pairings: list[tuple[str, str]] = []
        day_segment = day_segment_match.group(1)
        for item in day_segment.split(","):
            if " - " not in item and " – " not in item:
                continue
            separator = " - " if " - " in item else " – "
            home_team, away_team = item.split(separator, 1)
            clean_home = self._clean_team_name(home_team)
            clean_away = self._clean_team_name(away_team)
            if clean_home and clean_away:
                pairings.append((clean_home, clean_away))
        return pairings

    @staticmethod
    def _to_flashscore_date(date_str: str) -> str:
        parsed = date.fromisoformat(date_str)
        return parsed.strftime("%d.%m")

    @staticmethod
    def _clean_team_name(name: str) -> str:
        cleaned = re.sub(r"\s+", " ", name).strip(" ,.-")
        return cleaned

    @staticmethod
    def _fallback_strength() -> dict[str, float | int]:
        return {"rank": 10, "ppg": 1.2, "goal_diff": 0}


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()


TEAM_ALIASES = {
    "real madrid": "Real Madrid CF",
    "atletico de madrid": "Club Atlético de Madrid",
    "celta de vigo": "RC Celta de Vigo",
    "real sociedad": "Real Sociedad de Fútbol",
    "betis": "Real Betis Balompié",
    "real betis": "Real Betis Balompié",
    "espanyol": "RCD Espanyol",
    "barcelona": "FC Barcelona",
    "deportivo de la coruna": "Deportivo de La Coruña",
    "deportivo la coruna": "Deportivo de La Coruña",
    "eintracht francfort": "Eintracht Frankfurt",
    "francfort": "Eintracht Frankfurt",
    "bayern munich": "FC Bayern München",
    "leverkusen": "Bayer 04 Leverkusen",
    "stuttgart": "VfB Stuttgart",
    "hoffenheim": "TSG 1899 Hoffenheim",
    "friburgo": "SC Freiburg",
    "mainz": "1. FSV Mainz 05",
    "inter": "FC Internazionale Milano",
    "napoles": "SSC Napoli",
    "juventus": "Juventus FC",
    "sassuolo": "US Sassuolo Calcio",
    "atalanta": "Atalanta BC",
    "lazio": "SS Lazio",
    "roma": "AS Roma",
    "psg": "Paris Saint-Germain FC",
    "lens": "Racing Club de Lens",
    "lyon": "Olympique Lyonnais",
    "marsella": "Olympique de Marseille",
    "estraburgo": "RC Strasbourg Alsace",
    "monaco": "AS Monaco FC",
    "niza": "OGC Nice",
}


GENERIC_TEAM_TOKENS = {
    "fc",
    "cf",
    "ac",
    "as",
    "rc",
    "sc",
    "tsg",
    "ssc",
    "vfb",
    "fsv",
    "us",
    "club",
    "de",
    "del",
    "la",
    "balompie",
    "calcio",
    "futbol",
    "football",
    "1901",
    "1907",
    "1909",
    "04",
    "05",
}


def build_normalized_strength_table(
    strength_table: dict[str, dict[str, float | int]],
) -> dict[str, dict[str, float | int]]:
    normalized: dict[str, dict[str, float | int]] = {}
    for official_name, data in strength_table.items():
        for variant in build_name_variants(official_name):
            normalized.setdefault(variant, data)
    return normalized


def resolve_strength_data(
    team_name: str,
    strength_table: dict[str, dict[str, float | int]],
    normalized_strength_table: dict[str, dict[str, float | int]],
) -> dict[str, float | int]:
    if team_name in strength_table:
        return strength_table[team_name]

    for variant in build_name_variants(team_name):
        alias_target = TEAM_ALIASES.get(variant)
        if alias_target and alias_target in strength_table:
            return strength_table[alias_target]
        if variant in normalized_strength_table:
            return normalized_strength_table[variant]

    return FlashscoreScheduleProvider._fallback_strength()


def build_name_variants(name: str) -> set[str]:
    normalized = normalize_team_name(name)
    stripped = strip_generic_tokens(normalized)
    return {normalized, stripped} - {""}


def names_match(expected_variants: set[str], candidate_name: str) -> bool:
    candidate_variants = build_name_variants(candidate_name)
    if expected_variants & candidate_variants:
        return True
    for variant in expected_variants:
        alias_target = TEAM_ALIASES.get(variant)
        if alias_target and build_name_variants(alias_target) & candidate_variants:
            return True
    return False


def normalize_team_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", ascii_name).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_generic_tokens(name: str) -> str:
    tokens = [token for token in name.split() if token not in GENERIC_TEAM_TOKENS]
    return " ".join(tokens)
