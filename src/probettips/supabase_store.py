from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request


class SupabaseStore:
    def __init__(self, url: str, service_role_key: str, schema: str = "probettips") -> None:
        self.url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.schema = schema

    def list_daily_tips(self) -> list[dict]:
        rows = self._request(
            method="GET",
            path="/rest/v1/daily_tips",
            query={
                "select": "*",
                "order": "tip_date.asc,strategy.asc",
            },
            profile_header="Accept-Profile",
        )
        return [self._map_daily_tip(row) for row in rows]

    def list_candidate_picks(self, tip_date: str, strategy: str = "official") -> list[dict]:
        return self._request(
            method="GET",
            path="/rest/v1/candidate_picks",
            query={
                "select": "*",
                "tip_date": f"eq.{tip_date}",
                "strategy": f"eq.{strategy}",
                "order": "candidate_rank.asc",
            },
            profile_header="Accept-Profile",
        )

    def get_daily_tip(self, tip_date: str, strategy: str = "official") -> dict | None:
        rows = self._request(
            method="GET",
            path="/rest/v1/daily_tips",
            query={
                "select": "*",
                "tip_date": f"eq.{tip_date}",
                "strategy": f"eq.{strategy}",
                "limit": "1",
            },
            profile_header="Accept-Profile",
        )
        if not rows:
            return None
        return self._map_daily_tip(rows[0])

    def upsert_daily_tip(self, ticket: dict) -> dict:
        strategy = ticket.get("strategy", "official")
        payload = {
            "tip_date": ticket["date"],
            "strategy": strategy,
            "source": ticket["source"],
            "status": ticket["status"],
            "result": ticket["result"],
            "combined_odds": ticket["combined_odds"],
            "combined_probability": ticket["combined_probability"],
            "recommendation_tier": ticket.get("recommendation_tier"),
            "selected_picks_json": ticket["picks"],
            "settlement_json": ticket.get("settlement"),
        }
        try:
            rows = self._request(
                method="POST",
                path="/rest/v1/daily_tips",
                query={"on_conflict": "tip_date,strategy"},
                body=[payload],
                profile_header="Content-Profile",
                extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            )
        except Exception:
            if strategy != "official":
                raise RuntimeError("La base de datos todavia no tiene activado el soporte multi-estrategia. Ejecuta supabase/probettips_strategy_migration.sql y vuelve a intentarlo.")
            legacy_payload = dict(payload)
            legacy_payload.pop("strategy", None)
            rows = self._request(
                method="POST",
                path="/rest/v1/daily_tips",
                query={"on_conflict": "tip_date"},
                body=[legacy_payload],
                profile_header="Content-Profile",
                extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            )
        return self._map_daily_tip(rows[0])

    def replace_candidate_picks(
        self,
        tip_date: str,
        strategy: str,
        candidates: list[dict],
        selected_keys: set[tuple[str, str, str]],
    ) -> None:
        payload = []
        for index, candidate in enumerate(candidates, start=1):
            key = (candidate["match_id"], candidate["market"], candidate["bet_type"])
            payload.append(
                {
                    "tip_date": tip_date,
                    "strategy": strategy,
                    "candidate_rank": index,
                    "selected": key in selected_keys,
                    "match_id": candidate["match_id"],
                    "competition_code": candidate["competition_code"],
                    "league": candidate["league"],
                    "match_label": candidate["match_label"],
                    "kickoff": candidate["kickoff"],
                    "bet_type": candidate["bet_type"],
                    "market": candidate["market"],
                    "probability": candidate["probability"],
                    "odds": candidate["odds"],
                    "confidence": candidate["confidence"],
                    "risk_score": candidate["risk_score"],
                    "market_stability": candidate["market_stability"],
                    "dynamic_threshold": candidate["dynamic_threshold"],
                    "rationale": candidate["rationale"],
                }
            )

        try:
            self._request(
                method="DELETE",
                path="/rest/v1/candidate_picks",
                query={
                    "tip_date": f"eq.{tip_date}",
                    "strategy": f"eq.{strategy}",
                },
                profile_header="Content-Profile",
            )
            if not candidates:
                return
            self._request(
                method="POST",
                path="/rest/v1/candidate_picks",
                body=payload,
                profile_header="Content-Profile",
                extra_headers={"Prefer": "return=minimal"},
            )
        except Exception:
            if strategy != "official":
                raise RuntimeError("La base de datos todavia no tiene activado el soporte multi-estrategia. Ejecuta supabase/probettips_strategy_migration.sql y vuelve a intentarlo.")
            if not candidates:
                self._request(
                    method="DELETE",
                    path="/rest/v1/candidate_picks",
                    query={"tip_date": f"eq.{tip_date}"},
                    profile_header="Content-Profile",
                )
                return
            legacy_payload = []
            for item in payload:
                legacy_item = dict(item)
                legacy_item.pop("strategy", None)
                legacy_payload.append(legacy_item)
            self._request(
                method="DELETE",
                path="/rest/v1/candidate_picks",
                query={"tip_date": f"eq.{tip_date}"},
                profile_header="Content-Profile",
            )
            self._request(
                method="POST",
                path="/rest/v1/candidate_picks",
                body=legacy_payload,
                profile_header="Content-Profile",
                extra_headers={"Prefer": "return=minimal"},
            )

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        body: list[dict] | None = None,
        profile_header: str = "Content-Profile",
        extra_headers: dict[str, str] | None = None,
    ) -> list[dict]:
        query_string = ""
        if query:
            query_string = "?" + urllib.parse.urlencode(query)
        url = f"{self.url}{path}{query_string}"

        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            profile_header: self.schema,
        }
        if extra_headers:
            headers.update(extra_headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, data=data, method=method, headers=headers)
                with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
                    raw = response.read().decode("utf-8")
                    if not raw.strip():
                        return []
                    return json.loads(raw)
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(0.8 * (attempt + 1))
        if last_error:
            raise last_error
        return []

    @staticmethod
    def _map_daily_tip(row: dict) -> dict:
        return {
            "date": row["tip_date"],
            "strategy": row.get("strategy", "official"),
            "source": _safe_text(row["source"]),
            "status": row["status"],
            "result": row.get("result"),
            "combined_odds": float(row["combined_odds"]),
            "combined_probability": float(row["combined_probability"]),
            "recommendation_tier": row.get("recommendation_tier"),
            "picks": _safe_json_value(row.get("selected_picks_json") or []),
            "settlement": _safe_json_value(row.get("settlement_json")),
        }


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()


def _safe_json_value(value):
    if isinstance(value, dict):
        return {key: _safe_json_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _safe_text(value: str) -> str:
    if "?" in value or "â" in value:
        return value
    return value
