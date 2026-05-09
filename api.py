# ✅ Versión restaurada con:
# - Filtros Todo / 7 días / 30 días
# - Cálculo Hit Rate / ROI / Profit
# - Histórico con título
# - Generate en JSON estructurado
# - Warning visual
# - Sin romper nada existente

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from probettips.config import load_env_file, get_env
from probettips.service import generate_daily_picks
from probettips.history import load_history, upsert_ticket
from probettips.supabase_store import SupabaseStore
from probettips.telegram import send_message, format_message
from probettips.settlement import settle_pending_tickets

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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>ProBetTipsIA</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{background:#0b0f14;color:#e6edf3;font-family:sans-serif;margin:0;padding:20px}
.card{background:#121a22;padding:18px;border-radius:12px;margin-bottom:20px}
.stat{display:inline-block;width:22%;text-align:center}
button{margin:5px;padding:10px 14px;border-radius:8px;border:none;background:#1c2732;color:white}
button.primary{background:#00ff88;color:black}
.history-item{background:#0e141b;padding:12px;border-radius:10px;margin-bottom:10px}
.pick-line{font-size:13px;margin-top:6px}
</style>
<script>

let lastGeneratedData=null

async function generatePick(){
const res=await fetch("/generate")
const data=await res.json()
if(!data.picks || data.picks.length===0)return

let html="<div class='history-item'>"
html+=`<strong>${data.date}</strong><br>`

if(data.warning){
html+=`<div style="color:#ffaa00;margin-top:8px">⚠️ ${data.warning}</div>`
}

let total=1
data.picks.forEach(p=>{
total*=parseFloat(p.odds||1)
html+=`<div class='pick-line'><strong>${p.match}</strong><br>${p.league} · ${p.market} · Cuota: ${p.odds}</div>`
})

if(data.picks.length>1){
html+=`<div class='pick-line' style="color:#00ff88;font-weight:700">Cuota total: ${total.toFixed(2)}</div>`
}

html+="</div>"
document.getElementById("pickResult").innerHTML=html
}

async function loadHistory(days=null){
const res=await fetch("/history")
const data=await res.json()

let filtered=[...data].reverse()
if(days){
const cutoff=new Date()
cutoff.setDate(cutoff.getDate()-days)
filtered=filtered.filter(x=>new Date(x.tip_date)>=cutoff)
}

let wins=0,losses=0,equity=0

filtered.forEach(x=>{
if(x.status==="settled"){
if(x.result==="win"){wins++;equity+=1}
if(x.result==="loss"){losses++;equity-=1}
}
})

const total=filtered.length
const resolved=wins+losses
const hit=resolved?Math.round((wins/resolved)*100):0
const roi=total?(((wins-losses)/total)*100).toFixed(1):0

document.getElementById("stat-hit").innerText=hit+"%"
document.getElementById("stat-total").innerText=total
document.getElementById("stat-roi").innerText=roi+"%"
document.getElementById("stat-profit").innerText=equity+"u"

let html=""
filtered.forEach(x=>{
let picksHtml=""
let totalOdds=1
let parsed=typeof x.picks==="string"?JSON.parse(x.picks):x.picks
parsed.forEach(p=>{
totalOdds*=parseFloat(p.odds||1)
const match=p.match_label||p.match||p.fixture||""
picksHtml+=`<div class='pick-line'><strong>${match}</strong><br>${p.league} · ${p.market} · Cuota: ${p.odds}</div>`
})
if(parsed.length>1){
picksHtml+=`<div class='pick-line' style="color:#00ff88;font-weight:700">Cuota total: ${totalOdds.toFixed(2)}</div>`
}
html+=`<div class='history-item'><strong>${x.tip_date}</strong>${picksHtml}</div>`
})

document.getElementById("history").innerHTML=html
}

window.onload=function(){loadHistory()}
</script>
</head>
<body>

<h2>ProBetTipsIA</h2>

<div class="card">
<div class="stat"><div>Hit Rate</div><div id="stat-hit">--</div></div>
<div class="stat"><div>Total Picks</div><div id="stat-total">--</div></div>
<div class="stat"><div>ROI</div><div id="stat-roi">--</div></div>
<div class="stat"><div>Profit</div><div id="stat-profit">--</div></div>
</div>

<button onclick="loadHistory()">Todo</button>
<button onclick="loadHistory(7)">7 días</button>
<button onclick="loadHistory(30)">30 días</button>
<button class="primary" onclick="generatePick()">Generar Pick</button>

<div id="pickResult" class="card"></div>

<h3>📊 Histórico</h3>
<div id="history"></div>

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
        return JSONResponse({"picks": []})

    structured=[]
    for p in picks:
        structured.append({
            "match": getattr(p,"match_label",None) or getattr(p,"match",None) or "",
            "league": getattr(p,"league",None),
            "market": getattr(p,"market",None),
            "odds": getattr(p,"odds",None),
        })

    warning=None
    if source and "aviso" in source.lower():
        warning=source

    return JSONResponse({
        "date":date_label,
        "tier":tier,
        "picks":structured,
        "warning":warning
    })


@app.get("/history")
def history():
    return load_history(store)


@app.get("/send")
def send():
    date_label, picks, source, tier, candidates = generate_daily_picks(
        None,
        FOOTBALL_DATA_API_TOKEN,
        store,
        strategy="official",
    )

    upsert_ticket(store,date_label,source,picks,"official",tier,candidates)
    message=format_message(date_label,picks,tier)
    send_message(TELEGRAM_BOT_TOKEN,TELEGRAM_CHAT_ID,message)

    return "OK"


@app.get("/settle")
def settle_pending():
    settle_pending_tickets(store=store, api_token=FOOTBALL_DATA_API_TOKEN)
    return {"status": "ok"}
