from __future__ import annotations

from fastapi import Body, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from probettips.config import get_env, load_env_file
from probettips.history import load_history, upsert_ticket
from probettips.models import Pick
from probettips.service import generate_daily_picks
from probettips.supabase_store import SupabaseStore
from probettips.telegram import format_message, send_message

load_env_file()

app = FastAPI(title="ProBetTips API")

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = get_env("SUPABASE_SERVICE_ROLE_KEY")
FOOTBALL_DATA_API_TOKEN = get_env("FOOTBALL_DATA_API_TOKEN")
TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

FAVICON_SVG = """
<svg width="64" height="64" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00ff88"/>
      <stop offset="100%" stop-color="#7fffe0"/>
    </linearGradient>
  </defs>
  <circle cx="256" cy="256" r="256" fill="#0b0f14"/>
  <g stroke="url(#brandGrad)" stroke-width="18" stroke-linecap="round" fill="none">
    <path d="M130 322a150 150 0 0 1 120-188"/>
    <path d="M182 382a178 178 0 0 1-7-228"/>
    <path d="M333 135a171 171 0 0 1 47 17"/>
    <path d="M397 176a180 180 0 0 1 5 163"/>
    <path d="M190 412a175 175 0 0 0 80 19"/>
    <path d="M271 402v46"/>
  </g>
  <g fill="url(#brandGrad)">
    <circle cx="129" cy="323" r="18"/>
    <circle cx="174" cy="155" r="18"/>
    <circle cx="332" cy="133" r="18"/>
    <circle cx="396" cy="175" r="18"/>
    <circle cx="189" cy="412" r="18"/>
    <circle cx="271" cy="448" r="18"/>
  </g>
  <circle cx="256" cy="256" r="118" fill="url(#brandGrad)"/>
  <g fill="#0b0f14">
    <polygon points="256,180 291,204 291,248 256,272 221,248 221,204"/>
    <polygon points="186,228 219,248 213,292 173,309 148,270 161,236"/>
    <polygon points="326,248 359,228 384,236 397,270 372,309 332,292"/>
    <polygon points="235,302 277,302 297,338 276,377 236,377 215,338"/>
  </g>
  <circle cx="256" cy="256" r="118" fill="none" stroke="#0b0f14" stroke-width="12"/>
</svg>
""".strip()


@app.get("/logo.png")
def get_logo():
    return FileResponse("logo.png")


@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("logo.png")


@app.get("/favicon.svg")
def get_favicon_svg():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>ProBetTipsIA</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/svg+xml" href="/favicon.svg?v=2">
<link rel="shortcut icon" href="/favicon.svg?v=2">
<link rel="apple-touch-icon" href="/logo.png">
<style>
body{background:#0b0f14;color:#e6edf3;font-family:Inter,Segoe UI,Arial,sans-serif;margin:0}
.hero{display:flex;align-items:center;gap:18px;padding:30px 24px 18px;border-bottom:1px solid #1e2936}
.hero-logo{width:72px;height:72px;border-radius:14px;background:#10161d;border:1px solid #1e2936;object-fit:cover;box-shadow:0 0 0 1px rgba(0,255,136,.08),0 14px 30px rgba(0,0,0,.25)}
.hero-title{font-size:30px;font-weight:800;line-height:1.05;color:#00ff88;margin:0}
.hero-subtitle{margin:8px 0 0;color:#94a3b8;font-size:14px}
.page{padding:24px}
.card{background:#121a22;padding:18px;border-radius:16px;margin-bottom:20px;border:1px solid #1b2632}
.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 12px}
.section-title h3{font-size:22px;margin:0}
.section-note{font-size:12px;color:#7f93a8}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.stat{text-align:center;padding:18px 12px;background:#141d27;border-radius:14px;border:1px solid #1f2b37}
.stat-label{font-size:13px;color:#9fb3c8;margin-bottom:10px}
.stat-value{font-size:26px;font-weight:800;color:#00ff88}
.stat-subvalue{font-size:12px;color:#7f93a8;margin-top:6px}
button{margin:5px;padding:10px 14px;border-radius:8px;border:none;background:#1c2732;color:white;cursor:pointer}
button.primary{background:#00ff88;color:black}
button.secondary{background:#1f6feb}
button:disabled{opacity:.45;cursor:not-allowed}
.feature-grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(320px,.7fr);gap:18px;align-items:start;margin-top:18px}
.daily-card{position:relative;overflow:hidden;background:linear-gradient(180deg,#121a22 0%,#0f151c 100%)}
.daily-card:before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:4px;background:linear-gradient(90deg,#00ff88 0%,#12b5ff 100%)}
.daily-empty{padding:22px 0;color:#8fa4b8}
.daily-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0 8px}
.daily-summary-box{background:#111922;border:1px solid #1b2a36;border-radius:12px;padding:12px}
.daily-summary-label{font-size:11px;color:#7f93a8;text-transform:uppercase;letter-spacing:.06em}
.daily-summary-value{font-size:20px;font-weight:800;color:#f8fafc;margin-top:4px}
.toolbar{margin:20px 0 14px;display:flex;flex-wrap:wrap;gap:8px}
.history-item{background:#0e141b;padding:16px;border-radius:12px;margin-bottom:12px;border:1px solid #18222c}
.history-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}
.history-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.history-date{font-size:19px;font-weight:800}
.history-summary{font-size:12px;color:#8fa4b8}
.pick-line{font-size:13px;margin-top:6px}
.pick-line strong{display:block;font-size:14px;color:#f8fafc}
.status{margin-top:10px;color:#9fb3c8;font-size:13px}
.warning{color:#ffaa00;margin-top:8px}
.status-banner{margin:12px 0 0;padding:12px 14px;border-radius:12px;border:1px solid #1a3342;background:#0d1a24;color:#c7d8e5;font-size:13px}
.status-banner.alt{border-color:#564400;background:#241f0a;color:#f4e7ad}
.status-banner.success{border-color:#1f5f43;background:#0d2b1d;color:#a7f3d0}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.02em}
.badge.result-win{background:#133122;color:#79f2a7}
.badge.result-loss{background:#35171b;color:#ff9eaa}
.badge.result-pending{background:#1e293b;color:#cbd5e1}
.badge.alt{background:#3a2f07;color:#f4e7ad}
@media (max-width: 900px){
  .page{padding:16px}
  .hero{padding:20px 16px 14px}
  .hero-logo{width:58px;height:58px}
  .hero-title{font-size:22px}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .feature-grid{grid-template-columns:1fr}
  .daily-summary{grid-template-columns:1fr}
}
</style>
<script>
let lastGeneratedData = null
let activeFilterDays = null

function isOfficialStrategy(strategy){
  return !strategy || strategy === "official"
}

function getResultBadge(result){
  if(result === "win"){
    return "<span class='badge result-win'>✅ Acertado</span>"
  }
  if(result === "loss"){
    return "<span class='badge result-loss'>❌ Fallado</span>"
  }
  return "<span class='badge result-pending'>⏳ Pendiente</span>"
}

function getAlternativeNotice(strategy){
  if(isOfficialStrategy(strategy)){
    return ""
  }
  return "<div class='status-banner alt'>Apuesta alternativa con valor. No es la recomendada oficial del dia, pero se guarda para comparar rendimiento.</div>"
}

function getTierLabel(data){
  if(!data || !data.picks || data.picks.length === 0){
    return "Sin pick"
  }
  return isOfficialStrategy(data.strategy) ? "Oficial" : "Alternativa"
}

function renderPickCard(data){
  if(!data || !data.picks || data.picks.length === 0){
    return "<div class='daily-empty'><strong>No hay picks disponibles.</strong><div class='status-banner'>Hoy el algoritmo no ha encontrado una recomendacion suficientemente fuerte.</div></div>"
  }

  let html = "<div class='history-item daily-card'>"
  html += "<div class='history-header'>"
  html += `<div><div class='history-date'>${data.date}</div><div class='history-summary'>Pick del dia</div></div>`
  html += `<div class='history-meta'><span class='badge result-pending'>${getTierLabel(data)}</span></div>`
  html += "</div>"

  if(data.warning){
    html += `<div class='status-banner'>Aviso: ${data.warning}</div>`
  }

  html += getAlternativeNotice(data.strategy)

  let total = 1
  data.picks.forEach(p => {
    total *= parseFloat(p.odds || 1)
    html += `<div class='pick-line'><strong>${p.match_label || p.match || ""}</strong><br>${p.league || ""} - ${p.market || ""} - Cuota: ${Number(p.odds || 1).toFixed(2)}</div>`
  })

  html += "<div class='daily-summary'>"
  html += `<div class='daily-summary-box'><div class='daily-summary-label'>Selecciones</div><div class='daily-summary-value'>${data.picks.length}</div></div>`
  html += `<div class='daily-summary-box'><div class='daily-summary-label'>Cuota total</div><div class='daily-summary-value'>${total.toFixed(2)}</div></div>`
  html += `<div class='daily-summary-box'><div class='daily-summary-label'>Estado</div><div class='daily-summary-value'>Pendiente</div></div>`
  html += "</div>"

  if(data.picks.length > 1){
    html += `<div class='pick-line' style='color:#00ff88;font-weight:700'>Cuota total: ${total.toFixed(2)}</div>`
  }

  html += "</div>"
  return html
}

function setStatus(message){
  const target = document.getElementById("status")
  if(!message){
    target.innerHTML = ""
    return
  }
  target.innerHTML = `<div class='status-banner success'>${message}</div>`
}

async function generatePick(){
  setStatus("Generando pick...")
  const res = await fetch("/generate")
  const data = await res.json()
  lastGeneratedData = data && data.picks && data.picks.length ? data : null
  document.getElementById("pickResult").innerHTML = renderPickCard(data)
  document.getElementById("sendButton").disabled = !lastGeneratedData
  setStatus(lastGeneratedData ? "Pick generado. Ya puedes enviarlo a Telegram." : "No hay picks disponibles para hoy.")
}

async function initializeDashboard(){
  setStatus("Cargando pick del dia...")
  await Promise.all([
    loadHistory(),
    generatePick(),
  ])
}

async function sendPick(){
  if(!lastGeneratedData){
    setStatus("Genera un pick antes de enviarlo.")
    return
  }

  setStatus("Enviando pick a Telegram y guardando en la base de datos...")
  const res = await fetch("/send", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(lastGeneratedData),
  })
  const data = await res.json()

  if(!res.ok){
    setStatus(data.detail || "No se pudo enviar el pick.")
    return
  }

  setStatus("Pick enviado correctamente.")
  await loadHistory(activeFilterDays)
}

async function settleResults(){
  setStatus("Actualizando resultados...")
  const res = await fetch("/settle", {method:"POST"})
  const data = await res.json()

  if(!res.ok){
    setStatus(data.detail || "No se pudieron actualizar resultados.")
    return
  }

  const settled = data.settled_count || 0
  setStatus(settled ? `Resultados actualizados. Tips liquidados: ${settled}.` : "No habia tips nuevos para liquidar.")
  await loadHistory(activeFilterDays)
}

async function loadHistory(days=null){
  activeFilterDays = days
  const res = await fetch("/history")
  const data = await res.json()

  let filtered = [...data].reverse()
  if(days){
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - days)
    filtered = filtered.filter(x => {
      const tipDate = x.tip_date || x.date
      return tipDate && new Date(tipDate) >= cutoff
    })
  }

  let wins = 0
  let losses = 0
  let equity = 0

  filtered.forEach(x => {
    if(x.status === "settled"){
      if(x.result === "win"){wins++; equity += 1}
      if(x.result === "loss"){losses++; equity -= 1}
    }
  })

  const total = filtered.length
  const resolved = wins + losses
  const hit = resolved ? Math.round((wins / resolved) * 100) : 0
  const roi = total ? (((wins - losses) / total) * 100).toFixed(1) : 0

  document.getElementById("stat-hit").innerText = hit + "%"
  document.getElementById("stat-hit-sub").innerText = `${wins} aciertos / ${resolved || 0} resueltos`
  document.getElementById("stat-total").innerText = total
  document.getElementById("stat-total-sub").innerText = `${filtered.filter(x => (x.strategy || "official") === "official").length} oficiales en rango`
  document.getElementById("stat-roi").innerText = roi + "%"
  document.getElementById("stat-roi-sub").innerText = "Balance del historico visible"
  document.getElementById("stat-profit").innerText = equity + "u"
  document.getElementById("stat-profit-sub").innerText = "Unidades netas del tramo"

  let html = ""
  filtered.forEach(x => {
    let picksHtml = ""
    let totalOdds = 1
    const parsed = Array.isArray(x.picks) ? x.picks : []
    parsed.forEach(p => {
      totalOdds *= parseFloat(p.odds || 1)
      const match = p.match_label || p.match || p.fixture || ""
      picksHtml += `<div class='pick-line'><strong>${match}</strong><br>${p.league || ""} - ${p.market || ""} - Cuota: ${Number(p.odds || 1).toFixed(2)}</div>`
    })
    if(parsed.length > 1){
      picksHtml += `<div class='pick-line' style='color:#00ff88;font-weight:700'>Cuota total: ${totalOdds.toFixed(2)}</div>`
    }

    const tipDate = x.tip_date || x.date || ""
    const strategy = x.strategy || "official"
    const badge = getResultBadge(x.result)
    const title = isOfficialStrategy(strategy) ? "Pick oficial" : "Pick alternativo"
    html += "<div class='history-item'>"
    html += "<div class='history-header'>"
    html += `<div><div class='history-date'>${tipDate}</div><div class='history-summary'>${title}</div></div>`
    html += `<div class='history-meta'>${!isOfficialStrategy(strategy) ? "<span class='badge alt'>Con valor</span>" : ""}${badge}</div>`
    html += "</div>"
    html += getAlternativeNotice(strategy)
    html += picksHtml
    html += "</div>"
  })

  document.getElementById("history").innerHTML = html || "<div class='history-item'>Sin historico todavia.</div>"
}

window.onload = function(){ initializeDashboard() }
</script>
</head>
<body>

<div class="hero">
  <img class="hero-logo" src="/logo.png" alt="ProBetTipsIA logo">
  <div>
    <h1 class="hero-title">ProBetTipsIA</h1>
    <p class="hero-subtitle">Quant Betting Engine</p>
  </div>
</div>

<div class="page">
<div class="card">
  <div class="section-title">
    <h3>Panel diario</h3>
    <div class="section-note">Seguimiento rapido del rendimiento y del pick actual</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-label">Hit Rate</div><div class="stat-value" id="stat-hit">--</div><div class="stat-subvalue" id="stat-hit-sub">--</div></div>
    <div class="stat"><div class="stat-label">Total Picks</div><div class="stat-value" id="stat-total">--</div><div class="stat-subvalue" id="stat-total-sub">--</div></div>
    <div class="stat"><div class="stat-label">ROI</div><div class="stat-value" id="stat-roi">--</div><div class="stat-subvalue" id="stat-roi-sub">--</div></div>
    <div class="stat"><div class="stat-label">Profit (u)</div><div class="stat-value" id="stat-profit">--</div><div class="stat-subvalue" id="stat-profit-sub">--</div></div>
  </div>
</div>

<div class="toolbar">
  <button onclick="loadHistory()">Todo</button>
  <button onclick="loadHistory(7)">7 dias</button>
  <button onclick="loadHistory(30)">30 dias</button>
  <button class="primary" onclick="generatePick()">Generar Pick</button>
  <button id="sendButton" class="secondary" onclick="sendPick()" disabled>Enviar a Telegram</button>
  <button onclick="settleResults()">Actualizar Resultados</button>
</div>

<div id="status" class="status"></div>

<div class="feature-grid">
  <div class="card">
    <div class="section-title">
      <h3>Pick del dia</h3>
      <div class="section-note">Vista previa antes de publicar en Telegram</div>
    </div>
    <div id="pickResult"></div>
  </div>

  <div class="card">
    <div class="section-title">
      <h3>Operacion</h3>
      <div class="section-note">Flujo recomendado</div>
    </div>
    <div class="status-banner">1. Genera el pick del dia para revisar la salida del algoritmo.</div>
    <div class="status-banner">2. Si te convence, pulsa enviar y lo guardaremos en BD y Telegram.</div>
    <div class="status-banner">3. Mas tarde, actualiza resultados para liquidar los picks cerrados.</div>
  </div>
</div>

<div class="section-title">
  <h3>Historico</h3>
  <div class="section-note">Comparativa de picks oficiales y alternativas con valor</div>
</div>
<div id="history"></div>
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
        return JSONResponse(
            {
                "date": date_label,
                "strategy": "official",
                "tier": tier,
                "source": source,
                "picks": [],
                "warning": None,
            }
        )

    warning = source if source and "aviso" in source.lower() else None
    return JSONResponse(
        {
            "date": date_label,
            "strategy": "official",
            "tier": tier,
            "source": source,
            "warning": warning,
            "picks": [_pick_to_dict(pick) for pick in picks],
            "candidates": [_pick_to_dict(candidate) for candidate in candidates or []],
        }
    )


@app.get("/history")
def history():
    return load_history(store)


@app.post("/send")
def send(payload: dict = Body(...)):
    picks = [_dict_to_pick(item) for item in payload.get("picks", [])]
    candidates = [_dict_to_pick(item) for item in payload.get("candidates", [])]
    date_label = payload.get("date")
    source = payload.get("source", "visor-web")
    tier = payload.get("tier")
    strategy = payload.get("strategy", "official")

    if not date_label:
        return JSONResponse({"detail": "Falta la fecha del tip."}, status_code=400)

    if not picks:
        return JSONResponse({"detail": "No hay picks validos para enviar."}, status_code=400)

    upsert_ticket(store, date_label, source, picks, strategy, tier, candidates)
    message = format_message(date_label, picks, tier)
    send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)

    return {
        "status": "ok",
        "date": date_label,
        "strategy": strategy,
        "pick_count": len(picks),
    }


@app.post("/settle")
def settle_pending():
    from probettips.settlement import settle_pending_tickets

    summary = settle_pending_tickets(store=store, api_token=FOOTBALL_DATA_API_TOKEN)
    return {"status": "ok", **summary}


def _pick_to_dict(pick: Pick) -> dict:
    return {
        "match_id": pick.match_id,
        "competition_code": pick.competition_code,
        "league": pick.league,
        "match_label": pick.match_label,
        "kickoff": pick.kickoff,
        "bet_type": pick.bet_type,
        "market": pick.market,
        "probability": pick.probability,
        "odds": pick.odds,
        "confidence": pick.confidence,
        "risk_score": pick.risk_score,
        "market_stability": pick.market_stability,
        "dynamic_threshold": pick.dynamic_threshold,
        "rationale": pick.rationale,
    }


def _dict_to_pick(data: dict) -> Pick:
    return Pick(
        match_id=data["match_id"],
        competition_code=data.get("competition_code", ""),
        league=data.get("league", ""),
        match_label=data.get("match_label") or data.get("match") or "",
        kickoff=data.get("kickoff", ""),
        bet_type=data.get("bet_type", "single"),
        market=data.get("market", ""),
        probability=float(data.get("probability", 0.0)),
        odds=float(data.get("odds", 1.0)),
        confidence=float(data.get("confidence", 0.0)),
        risk_score=float(data.get("risk_score", 0.0)),
        market_stability=float(data.get("market_stability", 0.0)),
        dynamic_threshold=float(data.get("dynamic_threshold", 0.0)),
        rationale=data.get("rationale", ""),
    )
