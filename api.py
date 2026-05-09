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
            <title>ProBetTips Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: radial-gradient(circle at 20% 20%, #1e293b, #0f172a 60%);
                    color: #e2e8f0;
                    margin: 0;
                    padding: 0;
                }
                .container {
                    max-width: 900px;
                    margin: auto;
                    padding: 40px 20px;
                }
                h1 {
                    font-size: 42px;
                    margin-bottom: 5px;
                    letter-spacing: -1px;
                }
                .subtitle {
                    opacity: 0.6;
                    margin-bottom: 35px;
                    font-size: 15px;
                }
                .buttons {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                    gap: 15px;
                    margin-bottom: 30px;
                }
                button {
                    padding: 15px;
                    border-radius: 12px;
                    border: none;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: 0.2s ease;
                    backdrop-filter: blur(10px);
                }

                .primary { background: linear-gradient(135deg,#3b82f6,#2563eb); }
                .success { background: linear-gradient(135deg,#10b981,#059669); }
                .warning { background: linear-gradient(135deg,#f59e0b,#d97706); }
                .neutral { background: #334155; }

                button:hover {
                    transform: translateY(-3px);
                    box-shadow: 0 8px 20px rgba(0,0,0,0.4);
                }

                .card {
                    background: rgba(30,41,59,0.9);
                    border-radius: 16px;
                    padding: 25px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.4);
                    min-height: 180px;
                    white-space: pre-wrap;
                    font-size: 14px;
                    line-height: 1.5;
                }

                .loading {
                    opacity: 0.5;
                }

                .footer {
                    margin-top: 40px;
                    text-align: center;
                    font-size: 12px;
                    opacity: 0.5;
                }
            </style>
            <script>
                async function callEndpoint(endpoint) {
                    const output = document.getElementById("output");
                    output.innerText = "Cargando...";
                    output.classList.add("loading");
                    try {
                        const res = await fetch(endpoint);
                        const text = await res.text();
                        try {
                            const json = JSON.parse(text);
                            output.innerText = JSON.stringify(json, null, 2);
                        } catch {
                            output.innerText = text;
                        }
                    } catch (err) {
                        output.innerText = "Error: " + err;
                    }
                    output.classList.remove("loading");
                }
            </script>
        </head>
        <body>
            <div class="container">
                <h1>ProBetTips</h1>
                <div class="subtitle">AI Betting Dashboard</div>

                <div class="buttons">
                    <button class="primary" onclick="callEndpoint('/generate')">
                        Generar Pick Diario
                    </button>
                    <button class="success" onclick="callEndpoint('/save')">
                        Guardar en BD
                    </button>
                    <button class="warning" onclick="callEndpoint('/send')">
                        Enviar a Telegram
                    </button>
                    <button class="neutral" onclick="callEndpoint('/history')">
                        Ver Histórico
                    </button>
                </div>

                <div class="card" id="output">
                    Sistema listo. Pulsa "Generar Pick Diario".
                </div>

                <div class="footer">
                    ProBetTips AI • Engine v2 • Cloud Deployment
                </div>
            </div>
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
