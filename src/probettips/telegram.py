from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request

from probettips.models import Pick


def format_message(date_label: str, picks: list[Pick], recommendation_tier: str | None = None) -> str:
    total_odds = 1.0
    for pick in picks:
        total_odds *= pick.odds

    header = "Tip del Dia"
    if recommendation_tier in {"strong_single", "low_edge_single"}:
        header = "Tip del Dia - Apuesta unica"

    lines = [header, date_label, ""]

    if recommendation_tier in {"low_edge_single", "low_edge_combo"}:
        lines.extend(
            [
                "Aviso de valor",
                "Esta recomendacion cumple el minimo operativo, pero no aporta suficiente beneficio frente al objetivo principal.",
                "",
            ]
        )

    for index, pick in enumerate(picks, start=1):
        bet_type_label = "Apuesta creada" if pick.bet_type == "bet_builder" else "Apuesta simple"
        lines.extend(
            [
                f"{index}. {pick.match_label}",
                f"   {pick.market}",
                f"   {bet_type_label} | Cuota: {pick.odds:.2f}",
                "",
            ]
        )

    lines.extend(
        [
            f"Cuota total: {total_odds:.2f}",
            "",
            "Vamos a por el verde",
        ]
    )
    return "\n".join(lines)


def format_settlement_message(ticket: dict, stats: dict) -> str:
    symbol = ticket["settlement"]["symbol"]
    lines = [
        "Historial de Pronosticos",
        "",
        f"{symbol} Resultado del dia: {'Acierto' if ticket['result'] == 'win' else 'Fallado'}",
        f"Cuota del tip: {ticket['combined_odds']:.2f}",
        "",
        f"Acertados: {stats['wins']}",
        f"Fallados: {stats['losses']}",
        f"% de acierto: {stats['accuracy_pct']:.2f}%",
        "",
        "Vamos a por el verde",
    ]
    return "\n".join(lines)


def send_message(bot_token: str, chat_id: str, message: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
        }
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?{query}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()
