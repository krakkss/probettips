from __future__ import annotations

from fastapi import Body, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

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


@app.get("/logo.png")
def get_logo():
    return FileResponse("logo.png")


@app.get("/favicon.ico")
def get_favicon():
    return FileResponse("logo.png")


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>ProBetTipsIA</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/png" href="/favicon.ico">
<style>
body{background:#0b0f14;color:#e6edf3;font-family:Inter,Segoe UI,Arial,sans-serif;margin:0}
.hero{display:flex;align-items:center;gap:18px;padding:30px 24px 18px;border-bottom:1px solid #1e2936}
.hero-logo{width:72px;height:72px;border-radius:14px;background:#10161d;border:1px solid #1e2936;object-fit:cover;box-shadow:0 0 0 1px rgba(0,255,136,.08),0 14px 30px rgba(0,0,0,.25)}
.hero-title{font-size:30px;font-weight:800;line-height:1.05;color:#00ff88;margin:0}
.hero-subtitle{margin:8px 0 0;color:#94a3b8;font-size:14px}
.page{padding:24px}
.card{background:#121a22;padding:18px;border-radius:16px;margin-bottom:20px;border:1px solid #1b2632}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.stat{text-align:center;padding:18px 12px;background:#141d27;border-radius:14px;border:1px solid #1f2b37}
.stat-label{font-size:13px;color:#9fb3c8;margin-bottom:10px}
.stat-value{font-size:26px;font-weight:800;color:#00ff88}
button{margin:5px;padding:10px 14px;border-radius:8px;border:none;background:#1c2732;color:white;cursor:pointer}
button.primary{background:#00ff88;color:black}
button.secondary{background:#1f6feb}
button:disabled{opacity:.45;cursor:not-allowed}
.history-item{background:#0e141b;padding:16px;border-radius:12px;margin-bottom:12px;border:1px solid #18222c}
.pick-line{font-size:13px;margin-top:6px}
.toolbar{margin:20px 0 14px}
.status{margin-top:10px;color:#9fb3c8;font-size:13px}
.warning{color:#ffaa00;margin-top:8px}
.strategy-tag{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;background:#1f2937;font-size:11px;color:#9fb3c8}
h3{font-size:22px;margin:28px 0 14px}
@media (max-width: 900px){
  .page{padding:16px}
  .hero{padding:20px 16px 14px}
  .hero-logo{width:58px;height:58px}
  .hero-title{font-size:22px}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
<script>
let lastGeneratedData = null
let activeFilterDays = null

function renderPickCard(data){
  if(!data || !data.picks || data.picks.length === 0){
    return "<div class='history-item'><strong>No hay picks disponibles.</strong></div>"
  }

  let html = "<div class='history-item'>"
  html += `<strong>${data.date}</strong>`
  html += `<span class='strategy-tag'>${data.strategy || "official"}</span><br>`

  if(data.warning){
    html += `<div class='warning'>Aviso: ${data.warning}</div>`
  }

  let total = 1
  data.picks.forEach(p => {
    total *= parseFloat(p.odds || 1)
    html += `<div class='pick-line'><strong>${p.match_label || p.match || ""}</strong><br>${p.league || ""} - ${p.market || ""} - Cuota: ${Number(p.odds || 1).toFixed(2)}</div>`
  })

  if(data.picks.length > 1){
    html += `<div class='pick-line' style='color:#00ff88;font-weight:700'>Cuota total: ${total.toFixed(2)}</div>`
  }

  html += "</div>"
  return html
}

function setStatus(message){
  document.getElementById("status").innerText = message || ""
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
  document.getElementById("stat-total").innerText = total
  document.getElementById("stat-roi").innerText = roi + "%"
  document.getElementById("stat-profit").innerText = equity + "u"

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
    const result = x.result === "win" ? "✅" : (x.result === "loss" ? "❌" : "⏳")
    html += `<div class='history-item'><strong>${tipDate}</strong><span class='strategy-tag'>${strategy}</span><span class='strategy-tag'>${result}</span>${picksHtml}</div>`
  })

  document.getElementById("history").innerHTML = html || "<div class='history-item'>Sin historico todavia.</div>"
}

window.onload = function(){ loadHistory() }
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
  <div class="stats">
    <div class="stat"><div class="stat-label">Hit Rate</div><div class="stat-value" id="stat-hit">--</div></div>
    <div class="stat"><div class="stat-label">Total Picks</div><div class="stat-value" id="stat-total">--</div></div>
    <div class="stat"><div class="stat-label">ROI</div><div class="stat-value" id="stat-roi">--</div></div>
    <div class="stat"><div class="stat-label">Profit (u)</div><div class="stat-value" id="stat-profit">--</div></div>
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

<div id="pickResult" class="card"></div>
<div id="status" class="status"></div>

<h3>Historico</h3>
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
