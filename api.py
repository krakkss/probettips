from __future__ import annotations

import os
from datetime import date
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from probettips.config import load_env_file, get_env
from probettips.service import generate_daily_picks
from probettips.history import upsert_ticket, load_history
from probettips.supabase_store import SupabaseStore
from probettips.telegram import send_message, format_message

load_env_file()

app = FastAPI(title="ProBetTips API")

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = get_env("SUPABASE_SERVICE_ROLE_KEY")
FOOTBALL_DATA_API_TOKEN = get_env("FOOTBALL_DATA_API_TOKEN")
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>ProBetTips Control Panel</title>
        </head>
        <body style="font-family: Arial; padding:40px;">
            <h1>ProBetTips</h1>
            <button onclick="fetch('/generate').then(r=>r.text()).then(t=>document.getElementById('out').innerText=t)">
                Generar Pick Diario
            </button>
            <button onclick="fetch('/save').then(r=>r.text()).then(t=>document.getElementById('out').innerText=t)">
                Guardar en BD
            </button>
            <button onclick="fetch('/send').then(r=>r.text()).then(t=>document.getElementById('out').innerText=t)">
                Enviar a Telegram
            </button>
            <button onclick="fetch('/history').then(r=>r.text()).then(t=>document.getElementById('out').innerText=t)">
                Ver Histórico
            </button>
            <pre id="out" style="margin-top:20px; background:#f4f4f4; padding:20px;"></pre>
        </body>
    </html>
    """


@app.get("/generate")
def generate():
    date_label, picks, source, tier, candidates = generate_daily_picks(
        None,
        FOOTBALL_DATA_API_TOKEN,
        store,
        strategy="official",
    )
    if not picks:
        return "No hay picks disponibles hoy"
    message = format_message(date_label, picks, tier)
    return message


@app.get("/save")
def save():
    date_label, picks, source, tier, candidates = generate_daily_picks(
        None,
        FOOTBALL_DATA_API_TOKEN,
        store,
        strategy="official",
    )
    if not picks:
        return "No hay picks para guardar"
    upsert_ticket(store, date_label, source, picks, "official", tier, candidates)
    return "Pick guardado en Supabase correctamente"


@app.get("/send")
def send():
    date_label, picks, source, tier, candidates = generate_daily_picks(
        None,
        FOOTBALL_DATA_API_TOKEN,
        store,
        strategy="official",
    )
    if not picks:
        return "No hay picks para enviar"
    message = format_message(date_label, picks, tier)
    send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
    return "Pick enviado a Telegram"


@app.get("/history")
def history():
    entries = load_history(store)
    return entries
