from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from probettips.config import load_env_file, get_env
from probettips.service import generate_daily_picks
from probettips.history import load_history, upsert_ticket
from probettips.supabase_store import SupabaseStore
from probettips.telegram import send_message, format_message
import json

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
<link rel="icon" type="image/png" href="/logo.png">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<style>
:root{
--bg:#0b0f14;
--card:#121a22;
--primary:#00ff88;
--danger:#ff3b3b;
--text:#e6edf3;
--muted:#7d8b99;
}

body{
margin:0;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:linear-gradient(180deg,#0b0f14 0%,#0f1720 100%);
color:var(--text);
}

.header{
padding:22px;
border-bottom:1px solid #1c2732;
font-weight:800;
font-size:20px;
color:var(--primary);
display:flex;
align-items:center;
gap:20px;
}

.header img{
height:140px;
}

.container{
padding:24px;
max-width:1000px;
margin:auto;
}

.stats{
display:flex;
gap:18px;
flex-wrap:wrap;
margin-bottom:25px;
}

.stat{
background:var(--card);
padding:22px;
border-radius:16px;
flex:1;
min-width:180px;
text-align:center;
border:1px solid #1c2732;
}

.stat-value{
font-size:26px;
font-weight:800;
margin-top:8px;
color:var(--primary);
}

.buttons{
display:flex;
gap:14px;
flex-wrap:wrap;
margin-bottom:20px;
}

button{
padding:12px 18px;
border-radius:14px;
border:none;
font-weight:700;
cursor:pointer;
background:var(--card);
color:var(--text);
border:1px solid #1c2732;
}

button.primary{
background:linear-gradient(135deg,var(--primary),#00c26e);
color:black;
}

button.secondary{
background:#1c2732;
}

.card{
background:var(--card);
padding:22px;
border-radius:18px;
border:1px solid #1c2732;
margin-bottom:20px;
}

.history-item{
padding:14px;
border-radius:12px;
background:#0e141b;
margin-bottom:12px;
}

.pick-line{
margin-top:6px;
font-size:13px;
color:#cfd8dc;
}

.badge-success{
margin-top:12px;
padding:10px;
border-radius:10px;
background:#003d24;
color:#00ff88;
font-weight:700;
}

.footer{
text-align:center;
margin-top:30px;
font-size:12px;
color:var(--muted);
}

canvas{
width:100%;
max-width:800px;
margin-top:15px;
}
</style>

<script>

let lastGeneratedData = null;
let alreadySent = false;

async function generatePick(){
const resultDiv = document.getElementById("pickResult");
const sendBtn = document.getElementById("sendBtn");

resultDiv.style.display="block";
resultDiv.innerHTML="Generando pick... ⏳";
sendBtn.style.display="none";
alreadySent=false;

try{
const res = await fetch("/generate");
const data = await res.json();

if(!data.picks || data.picks.length === 0){
resultDiv.innerHTML="No hay picks disponibles hoy";
return;
}

lastGeneratedData = data;

let html = `
<div class="history-item">
<div style="display:flex;justify-content:space-between;">
<strong>${data.date}</strong>
<span style="color:#00ff88;font-weight:800;">${data.tier || ""}</span>
</div>
`;

if(data.warning){
html+=`
<div style="margin-top:10px;padding:10px;border-radius:8px;background:#2a1a00;color:#ffaa00;font-size:13px;">
⚠️ ${data.warning}
</div>`;
}

let totalOdds = 1;

data.picks.forEach(p=>{
const odd=parseFloat(p.odds||1);
if(!isNaN(odd)){ totalOdds*=odd; }

html+=`
<div class="pick-line">
<strong>${p.match}</strong><br>
${p.league} · ${p.market} · Cuota: ${p.odds}
</div>`;
});

if(data.picks.length>1){
html+=`
<div class="pick-line" style="margin-top:8px;font-weight:700;color:#00ff88;">
Cuota total: ${totalOdds.toFixed(2)}
</div>`;
}

html+="</div>";

resultDiv.innerHTML = html;
sendBtn.style.display="inline-block";

}catch{
resultDiv.innerHTML="Error generando pick.";
}
}

async function runSettlement(){
const resultDiv = document.getElementById("pickResult");
resultDiv.style.display="block";
resultDiv.innerHTML="Actualizando resultados... ⏳";

try{
await fetch("/settle");
resultDiv.innerHTML="<div class='badge-success'>✅ Resultados actualizados correctamente</div>";
loadHistory();
}catch{
resultDiv.innerHTML="Error actualizando resultados.";
}
}

async function sendToTelegram(){
if(!lastGeneratedData || alreadySent) return;

const sendBtn = document.getElementById("sendBtn");
const resultDiv = document.getElementById("pickResult");

sendBtn.disabled=true;
sendBtn.innerText="Enviando...";

await fetch("/send");

alreadySent=true;
sendBtn.innerText="Enviado ✅";

resultDiv.innerHTML += "<div class='badge-success'>✅ Pick guardado en BD y enviado a Telegram</div>";

loadHistory();
}

function resetStats(){
document.getElementById("stat-hit").innerText="0%";
document.getElementById("stat-total").innerText="0";
document.getElementById("stat-roi").innerText="0%";
document.getElementById("stat-profit").innerText="0u";
}

async function loadHistory(){
try{
const res=await fetch("/history");
const data=await res.json();

if(!Array.isArray(data) || data.length===0){
resetStats();
document.getElementById("history").innerText="No hay datos.";
return;
}

let html="";
data.slice().reverse().forEach(x=>{
let picksHtml="";
let totalOdds=1;

if(x.picks){
let parsed=typeof x.picks==="string"?JSON.parse(x.picks):x.picks;

parsed.forEach(p=>{
const odd=parseFloat(p.odds||1);
if(!isNaN(odd)){ totalOdds*=odd; }

const match =
    p.match_label ||
    p.match ||
    p.game ||
    p.fixture ||
    (p.home && p.away ? p.home + " vs " + p.away : "");

picksHtml+=`
<div class="pick-line">
<strong>${match}</strong><br>
${p.league} · ${p.market} · Cuota: ${p.odds}
</div>`;
});

if(parsed.length>1){
picksHtml+=`
<div class="pick-line" style="margin-top:8px;font-weight:700;color:#00ff88;">
Cuota total: ${totalOdds.toFixed(2)}
</div>`;
}
}

html+=`
<div class="history-item">
<strong>${x.tip_date || x.date}</strong>
${picksHtml}
</div>`;
});

document.getElementById("history").innerHTML=html;

}catch{
resetStats();
}
}

window.onload=function(){loadHistory();}
</script>
</head>

<body>

<div class="header">
<img src="/logo.png" alt="Logo">
<div>ProBetTipsIA · Quant Betting Engine</div>
</div>

<div class="container">

<div class="stats">
<div class="stat"><div>Hit Rate</div><div class="stat-value" id="stat-hit">--</div></div>
<div class="stat"><div>Total Picks</div><div class="stat-value" id="stat-total">--</div></div>
<div class="stat"><div>ROI</div><div class="stat-value" id="stat-roi">--</div></div>
<div class="stat"><div>Profit (u)</div><div class="stat-value" id="stat-profit">--</div></div>
</div>

<div class="buttons">
<button class="primary" onclick="generatePick()">Generar Pick</button>
<button class="secondary" onclick="runSettlement()">Actualizar Resultados</button>
<button id="sendBtn" style="display:none;" onclick="sendToTelegram()">Enviar a Telegram</button>
</div>

<div class="card" id="pickResult" style="display:none;"></div>
<div class="card" id="history"></div>

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
        return JSONResponse({"picks": []})

    structured = []
    for p in picks:
        structured.append(
            {
                "match": p.get("match_label")
                or p.get("match")
                or p.get("fixture")
                or "",
                "league": p.get("league"),
                "market": p.get("market"),
                "odds": p.get("odds"),
            }
        )

    warning_message = None

    if source and isinstance(source, str) and "aviso" in source.lower():
        warning_message = source

    return JSONResponse(
        {
            "date": date_label,
            "tier": tier,
            "picks": structured,
            "warning": warning_message,
        }
    )


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

    upsert_ticket(
        store,
        date_label,
        source,
        picks,
        "official",
        tier,
        candidates,
    )

    message = format_message(date_label, picks, tier)
    send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)

    return "OK"


@app.get("/history")
def history():
    return load_history(store)


@app.get("/settle")
def settle_pending():
    from probettips.settlement import settle_pending_tickets

    settle_pending_tickets(
        store=store,
        api_token=FOOTBALL_DATA_API_TOKEN,
    )

    return {"status": "settlement executed"}
