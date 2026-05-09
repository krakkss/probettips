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
:root{
--bg:#0f172a;
--card:#1e293b;
--accent:#3b82f6;
--green:#10b981;
--orange:#f59e0b;
--red:#ef4444;
--text:#e2e8f0;
--muted:#94a3b8;
}

body{
margin:0;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:linear-gradient(180deg,#0f172a 0%,#0b1220 100%);
color:var(--text);
}

.header{
position:sticky;
top:0;
background:rgba(15,23,42,0.95);
backdrop-filter:blur(16px);
padding:18px 20px;
display:flex;
align-items:center;
gap:14px;
border-bottom:1px solid rgba(255,255,255,0.05);
z-index:10;
}

.container{
padding:22px;
max-width:900px;
margin:auto;
}

.section-title{
font-size:13px;
color:var(--muted);
margin:10px 0 6px;
}

.stats{
display:flex;
gap:14px;
flex-wrap:wrap;
margin-bottom:20px;
}

.stat{
background:var(--card);
padding:18px;
border-radius:16px;
flex:1;
min-width:160px;
text-align:center;
box-shadow:0 6px 20px rgba(0,0,0,0.35);
}

.stat-value{
font-size:22px;
font-weight:700;
margin-top:6px;
}

.buttons{
display:flex;
gap:12px;
flex-wrap:wrap;
margin-bottom:20px;
}

button{
padding:12px 16px;
border-radius:14px;
border:none;
font-weight:600;
cursor:pointer;
background:var(--card);
color:var(--text);
}

button.primary{
background:linear-gradient(135deg,#3b82f6,#2563eb);
color:white;
}

.card{
background:var(--card);
padding:20px;
border-radius:18px;
box-shadow:0 10px 30px rgba(0,0,0,0.4);
}

.history-item{
padding:14px;
border-radius:12px;
background:#0f172a;
margin-bottom:12px;
}

.history-top{
display:flex;
justify-content:space-between;
font-size:14px;
}

.footer{
text-align:center;
margin-top:30px;
font-size:11px;
color:var(--muted);
}

@media(max-width:600px){
.stats{flex-direction:column;}
}
</style>

<script>
async function loadHistory(days=null){
document.getElementById("history").innerText="Cargando...";
const res=await fetch("/history");
const data=await res.json();

if(!data.length){
document.getElementById("history").innerText="No hay histórico.";
return;
}

let wins=0;
let losses=0;
let filtered=data.slice().reverse();

if(days){
const cutoff=new Date();
cutoff.setDate(cutoff.getDate()-days);
filtered=filtered.filter(x=>new Date(x.date)>=cutoff);
}

filtered.forEach(x=>{
if(x.status==="won") wins++;
if(x.status==="lost") losses++;
});

const total=wins+losses;
const hitRate=total?Math.round((wins/total)*100):0;
const roi=total?(((wins-losses)/total)*100).toFixed(1):0;

document.getElementById("stat-hit").innerText=hitRate+"%";
document.getElementById("stat-total").innerText=total;
document.getElementById("stat-roi").innerText=roi+"%";

let html="";
filtered.forEach(x=>{
const color=
x.status==="won"?"#10b981":
x.status==="lost"?"#ef4444":"#f59e0b";

html+=`
<div class="history-item">
<div class="history-top">
<strong>${x.date}</strong>
<span style="color:${color};font-weight:700;">
${x.status.toUpperCase()}
</span>
</div>
<div style="font-size:12px;color:var(--muted);margin-top:4px;">
${x.source}
</div>
</div>`;
});

document.getElementById("history").innerHTML=html;
}
</script>

</head>

<body>

<div class="header">
<div>
<div style="font-weight:700;">ProBetTips</div>
<div style="font-size:12px;color:var(--muted);">
Personal Analytics Dashboard
</div>
</div>
</div>

<div class="container">

<div class="section-title">Resumen</div>

<div class="stats">
<div class="stat">
<div>Hit Rate</div>
<div class="stat-value" id="stat-hit">--</div>
</div>
<div class="stat">
<div>Total Picks</div>
<div class="stat-value" id="stat-total">--</div>
</div>
<div class="stat">
<div>ROI Estimado</div>
<div class="stat-value" id="stat-roi">--</div>
</div>
</div>

<div class="section-title">Filtros</div>

<div class="buttons">
<button onclick="loadHistory()">Todo</button>
<button onclick="loadHistory(7)">Últimos 7 días</button>
<button onclick="loadHistory(30)">Últimos 30 días</button>
<button class="primary" onclick="fetch('/generate').then(r=>r.text()).then(t=>alert(t))">
Generar Pick
</button>
</div>

<div class="section-title">Histórico</div>

<div class="card" id="history">
Pulsa un filtro para cargar histórico.
</div>

<div class="footer">
Producto personal · No público
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


@app.get("/history")
def history():
    return load_history(store)
