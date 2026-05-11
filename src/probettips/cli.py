from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from probettips.analysis import adjusted_threshold, build_analysis_report, build_market_calibrations, calibrated_probability
from probettips.config import get_env, load_env_file
from probettips.history import compute_stats, load_history, upsert_ticket
from probettips.service import generate_daily_picks
from probettips.settlement import settle_tickets
from probettips.supabase_store import SupabaseStore
from probettips.telegram import format_message, format_settlement_message, send_message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generador de picks diarios de futbol")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview_parser = subparsers.add_parser("preview", help="Muestra los picks sin enviar")
    preview_parser.add_argument("--date", help="Fecha YYYY-MM-DD", default=None)
    preview_parser.add_argument("--save", action="store_true", help="Guarda el pronostico en historial local")
    preview_parser.add_argument("--debug", action="store_true", help="Muestra candidatos internos del algoritmo")
    preview_parser.add_argument("--strategy", choices=["official", "shadow"], default="official", help="Estrategia a generar")

    history_parser = subparsers.add_parser("history", help="Lee el historico guardado en Supabase")
    history_parser.add_argument("--date", help="Fecha YYYY-MM-DD", default=None)
    history_parser.add_argument("--strategy", choices=["official", "shadow"], default=None, help="Filtra por estrategia")

    analyze_parser = subparsers.add_parser("analyze", help="Analiza el historico y la calibracion del modelo")
    analyze_parser.add_argument("--days", type=int, default=60, help="Ventana rolling en dias")

    send_parser = subparsers.add_parser("send", help="Envia los picks a Telegram")
    send_parser.add_argument("--date", help="Fecha YYYY-MM-DD", default=None)

    settle_parser = subparsers.add_parser("settle", help="Liquida pronosticos ya finalizados")
    settle_parser.add_argument("--date", help="Fecha YYYY-MM-DD", default=None)
    settle_parser.add_argument("--notify", action="store_true", help="Envia el resumen de liquidacion a Telegram")

    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    load_env_file()
    parser = build_parser()
    args = parser.parse_args()

    api_token = get_env("FOOTBALL_DATA_API_TOKEN")
    bot_token = get_env("TELEGRAM_BOT_TOKEN")
    chat_id = get_env("TELEGRAM_CHAT_ID")
    supabase_url = get_env("SUPABASE_URL")
    supabase_service_role_key = get_env("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_service_role_key:
        print("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env", file=sys.stderr)
        return 1

    store = SupabaseStore(supabase_url, supabase_service_role_key)

    if args.command == "analyze":
        report = build_analysis_report(load_history(store), rolling_days=args.days)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.command == "history":
        entries = load_history(store)
        if args.date:
            entries = [entry for entry in entries if entry["date"] == args.date]
        if args.strategy:
            entries = [entry for entry in entries if entry.get("strategy", "official") == args.strategy]
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0

    if args.command == "settle":
        settled, stats = settle_tickets(store, api_token, args.date)
        if not settled:
            if args.date:
                entries = load_history(store)
                existing = next(
                    (
                        entry for entry in entries
                        if entry["date"] == args.date
                        and entry.get("status") == "settled"
                        and entry.get("strategy", "official") == "official"
                    ),
                    None,
                )
                if existing:
                    if existing.get("settlement"):
                        print(format_settlement_message(existing, compute_stats(entries, strategy="official")))
                    else:
                        print(json.dumps({"message": "El tip ya estaba liquidado, pero aun no tiene detalle de settlement.", "ticket": existing}, indent=2, ensure_ascii=False))
                    return 0
            print(json.dumps({"message": "No hay pronosticos liquidados todavia", "stats": stats}, indent=2, ensure_ascii=False))
            return 0

        all_entries = load_history(store)
        summaries = [
            format_settlement_message(
                ticket,
                compute_stats(all_entries, strategy=ticket.get("strategy", "official")),
            )
            for ticket in settled
        ]
        output = "\n\n---\n\n".join(summaries)
        print(output)

        if args.notify:
            if not bot_token or not chat_id:
                print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env", file=sys.stderr)
                return 1
            for summary in summaries:
                send_message(bot_token, chat_id, summary)
        return 0

    requested_strategy = getattr(args, "strategy", "official")
    official_reference: list = []
    if requested_strategy == "shadow":
        lookup_date = args.date or date.today().isoformat()
        stored_official = None
        try:
            stored_official = store.get_daily_tip(lookup_date, "official") if hasattr(store, "get_daily_tip") else None
        except Exception:
            stored_official = None
        if stored_official and stored_official.get("picks"):
            official_reference = stored_official["picks"]
        else:
            try:
                _, official_reference, _, _, _ = generate_daily_picks(args.date, api_token, store, strategy="official")
            except Exception:
                official_reference = []
    excluded_for_shadow = None
    if requested_strategy == "shadow" and official_reference:
        # Excluir solo el mismo pick exacto (match_id + market), no todo el partido
        excluded_for_shadow = {
            (
                pick["match_id"] if isinstance(pick, dict) else pick.match_id,
                pick["market"] if isinstance(pick, dict) else pick.market,
            )
            for pick in official_reference
        }

    date_label, picks, source, recommendation_tier, calibration_candidates = generate_daily_picks(
        args.date,
        api_token,
        store,
        excluded_match_ids=excluded_for_shadow,
        strategy=requested_strategy,
    )
    if not picks:
        no_picks_payload = {"date": date_label, "source": source, "message": "No hay picks disponibles"}
        if args.command == "send":
            if not bot_token or not chat_id:
                print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env", file=sys.stderr)
                return 1
            no_picks_message = (
                f"Pronosticos del dia {date_label}\n\n"
                "Hoy no hay picks disponibles para las ligas configuradas."
            )
            response = send_message(bot_token, chat_id, no_picks_message)
            print(json.dumps({"notice": no_picks_payload, "telegram": response}, indent=2, ensure_ascii=False))
            return 0

        print(json.dumps(no_picks_payload, indent=2))
        return 0

    message = format_message(date_label, picks, recommendation_tier)

    if args.command == "preview":
        if args.save:
            upsert_ticket(store, date_label, source, picks, requested_strategy, recommendation_tier, calibration_candidates)
        if requested_strategy == "shadow":
            print("Shadow Pick")
            print("")
        print(message)
        print("")
        print(f"Fuente de datos: {source}")
        if args.debug:
            try:
                calibrations = build_market_calibrations(load_history(store))
            except Exception:
                calibrations = {}
            print("")
            print("Candidatos internos:")
            for candidate in calibration_candidates:
                effective_prob = calibrated_probability(candidate.probability, candidate.market, calibrations)
                effective_thr = adjusted_threshold(candidate.dynamic_threshold, candidate.market, calibrations)
                edge = effective_prob - effective_thr
                market_calibration = calibrations.get(candidate.market)
                sample_size = market_calibration.sample_size_60 if market_calibration else 0
                calibration_factor = market_calibration.calibration_factor if market_calibration else 1.0
                volatility_penalty = market_calibration.volatility_penalty if market_calibration else 0.0
                print(
                    f"- {candidate.match_label} | {candidate.market} | prob={candidate.probability:.3f} "
                    f"| prob_cal={effective_prob:.3f} "
                    f"| conf={candidate.confidence:.3f} | risk={candidate.risk_score:.3f} "
                    f"| stability={candidate.market_stability:.3f} | threshold={candidate.dynamic_threshold:.3f} "
                    f"| threshold_cal={effective_thr:.3f} | edge={edge:.3f} | samples60={sample_size} "
                    f"| factor={calibration_factor:.3f} | vol_pen={volatility_penalty:.3f}"
                )
        return 0

    if args.command == "send":
        if requested_strategy != "official":
            print("Solo se puede enviar por Telegram la estrategia official", file=sys.stderr)
            return 1
        upsert_ticket(store, date_label, source, picks, "official", recommendation_tier, calibration_candidates)
        if not bot_token or not chat_id:
            print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env", file=sys.stderr)
            return 1

        response = send_message(bot_token, chat_id, message)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0

    if not bot_token or not chat_id:
        print("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
