from __future__ import annotations

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
<!DOCTYPE html>
<html>
<head>
    <title>ProBetTips</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --accent: #3b82f6;
            --green: #10b981;
            --orange: #f59e0b;
            --text: #e2e8f0;
            --muted: #94a3b8;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(180deg, #0f172a 0%, #0b1220 100%);
            color: var(--text);
        }

        .header {
            position: sticky;
            top: 0;
            background: rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(12px);
            padding: 16px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            z-index: 10;
        }

        .logo {
            width: 36px;
            height: 36px;
        }

        .title {
            font-size: 18px;
            font-weight: 600;
        }

        .subtitle {
            font-size: 12px;
            color: var(--muted);
        }

        .container {
            padding: 20px;
            max-width: 900px;
            margin: auto;
        }

        .stats {
            display: flex;
            gap: 12px;
            overflow-x: auto;
            margin-bottom: 20px;
        }

        .stat-card {
            background: var(--card);
            padding: 16px;
            border-radius: 14px;
            min-width: 140px;
            text-align: center;
        }

        .stat-title {
            font-size: 11px;
            color: var(--muted);
        }

        .stat-value {
            font-size: 16px;
            font-weight: 600;
        }

        .buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
        }

        button {
            padding: 14px;
            border-radius: 14px;
            border: none;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: 0.2s ease;
        }

        .primary { background: var(--accent); color: white; }
        .success { background: var(--green); color: white; }
        .warning { background: var(--orange); color: white; }
        .neutral { background: var(--card); color: var(--text); }

        button:active { transform: scale(0.96); }

        .card {
            background: var(--card);
            padding: 20px;
            border-radius: 16px;
            min-height: 150px;
            white-space: pre-wrap;
            line-height: 1.6;
        }

        .footer {
            text-align: center;
            margin-top: 30px;
            font-size: 11px;
            color: var(--muted);
        }

        @media (max-width: 600px) {
            .buttons { grid-template-columns: 1fr; }
        }
    </style>

    <script>
        async function callEndpoint(endpoint) {
            const output = document.getElementById("output");
            output.innerText = "Cargando...";
            try {
                const res = await fetch(endpoint);
                const text = await res.text();
                try {
                    const json = JSON.parse(text);
                    output.innerText = JSON.stringify(json, null, 2);
                } catch {
                    output.innerText = text;
                }
            } catch {
                output.innerText = "Error al ejecutar la acción.";
            }
        }

        async function loadHistory() {
            const output = document.getElementById("output");
            output.innerText = "Cargando historial...";
            try {
                const res = await fetch("/history");
                const data = await res.json();

                if (!data.length) {
                    output.innerText = "No hay histórico disponible.";
                    return;
                }

                let html = "";
                data.slice().reverse().forEach(item => {
                    const color =
                        item.status === "won" ? "#10b981" :
                        item.status === "lost" ? "#ef4444" :
                        "#f59e0b";

                    html += `
                        <div style="margin-bottom:15px; padding:15px; background:#0f172a; border-radius:12px;">
                            <div style="display:flex; justify-content:space-between;">
                                <strong>${item.date}</strong>
                                <span style="color:${color}; font-weight:600;">
                                    ${item.status.toUpperCase()}
                                </span>
                            </div>
                            <div style="font-size:12px; opacity:0.7; margin-top:6px;">
                                ${item.source}
                            </div>
                        </div>
                    `;
                });

                output.innerHTML = html;
            } catch {
                output.innerText = "Error cargando historial.";
            }
        }
    </script>
</head>

<body>

    <div class="header">
        <div class="logo">
            <svg viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
                <rect width="512" height="512" rx="110" fill="#0f172a"/>
                <polyline 
                    points="100,340 190,260 270,300 360,180 420,220" 
                    fill="none" 
                    stroke="#3b82f6" 
                    stroke-width="28" 
                    stroke-linecap="round" 
                    stroke-linejoin="round"/>
                <circle cx="360" cy="180" r="20" fill="#10b981"/>
            </svg>
        </div>
        <div>
            <div class="title">ProBetTips</div>
            <div class="subtitle">AI Betting Intelligence</div>
        </div>
    </div>

    <div class="container">

        <div class="stats">
            <div class="stat-card">
                <div class="stat-title">Estado</div>
                <div class="stat-value">Online</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Estrategia</div>
                <div class="stat-value">Official</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Modo</div>
                <div class="stat-value">Producción</div>
            </div>
        </div>

        <div class="buttons">
            <button class="primary" onclick="callEndpoint('/generate')">🎯 Generar Pick</button>
            <button class="success" onclick="callEndpoint('/save')">💾 Guardar</button>
            <button class="warning" onclick="callEndpoint('/send')">📩 Telegram</button>
            <button class="neutral" onclick="loadHistory()">📊 Historial</button>
        </div>

        <div class="card" id="output">
            Sistema listo. Genera el pick del día.
        </div>

        <div class="footer">
            © ProBetTips AI · Statistical Engine v2
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
    return format_message(date_label, picks, tier)


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
    return load_history(store)
