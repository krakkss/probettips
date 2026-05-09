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

*{box-sizing:border-box;}

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

.logo{width:40px;height:40px;}

.title{font-size:20px;font-weight:700;}
.subtitle{font-size:12px;color:var(--muted);}

.container{
padding:22px;
max-width:900px;
margin:auto;
}

.stats{
display:flex;
gap:14px;
overflow-x:auto;
margin-bottom:22px;
}

.stat-card{
background:var(--card);
padding:20px;
border-radius:18px;
min-width:170px;
text-align:center;
box-shadow:0 8px 24px rgba(0,0,0,0.4);
}

.stat-title{font-size:11px;color:var(--muted);}
.stat-value{font-size:22px;font-weight:700;margin-top:6px;}

.gauge{
width:90px;
height:90px;
margin:10px auto 0;
border-radius:50%;
display:flex;
align-items:center;
justify-content:center;
font-weight:700;
font-size:18px;
color:white;
background:conic-gradient(var(--green) 0deg, var(--green) 0deg, #1e293b 0deg);
}

.buttons{
display:grid;
grid-template-columns:1fr 1fr;
gap:14px;
margin-bottom:24px;
}

button{
padding:16px;
border-radius:16px;
border:none;
font-weight:700;
font-size:14px;
cursor:pointer;
transition:all 0.15s ease;
box-shadow:0 6px 18px rgba(0,0,0,0.35);
}

.primary{background:linear-gradient(135deg,#3b82f6,#2563eb);color:white;}
.success{background:linear-gradient(135deg,#10b981,#059669);color:white;}
.warning{background:linear-gradient(135deg,#f59e0b,#d97706);color:white;}
.neutral{background:var(--card);color:var(--text);}

button:hover{transform:translateY(-2px);}
button:active{transform:scale(0.96);}

.card{
background:var(--card);
padding:22px;
border-radius:20px;
min-height:160px;
box-shadow:0 10px 30px rgba(0,0,0,0.45);
animation:fadeIn .3s ease;
}

@keyframes fadeIn{
from{opacity:0;transform:translateY(6px);}
to{opacity:1;transform:translateY(0);}
}

.spinner{
border:3px solid rgba(255,255,255,0.1);
border-top:3px solid var(--accent);
border-radius:50%;
width:26px;height:26px;
animation:spin .8s linear infinite;
margin:auto;
}

@keyframes spin{to{transform:rotate(360deg);}}

.footer{
text-align:center;
margin-top:36px;
font-size:11px;
color:var(--muted);
}

canvas{margin-top:10px;}

@media(max-width:600px){
.buttons{grid-template-columns:1fr;}
}
</style>

<script>
function showSpinner(){
document.getElementById("output").innerHTML="<div class='spinner'></div>";
}

function updateGauge(percent){
const gauge=document.getElementById("gauge");
const deg=percent*3.6;
gauge.style.background=`conic-gradient(var(--green) 0deg ${deg}deg,#1e293b ${deg}deg 360deg)`;
gauge.innerText=percent+"%";
}

function drawSparkline(data){
const canvas=document.getElementById("spark");
const ctx=canvas.getContext("2d");
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.strokeStyle="#3b82f6";
ctx.lineWidth=2;
ctx.beginPath();
const step=canvas.width/(data.length-1);
data.forEach((val,i)=>{
const x=i*step;
const y=canvas.height-(val*canvas.height);
if(i===0)ctx.moveTo(x,y);
else ctx.lineTo(x,y);
});
ctx.stroke();
}

async function loadHistory(){
showSpinner();
try{
const res=await fetch("/history");
const data=await res.json();
if(!data.length){
document.getElementById("output").innerText="No hay histórico.";
return;
}

let wins=0;
let losses=0;
let performance=[];

data.forEach(item=>{
if(item.status==="won"){wins++;performance.push(1);}
if(item.status==="lost"){losses++;performance.push(0);}
});

const total=wins+losses;
const hitRate=total?Math.round((wins/total)*100):0;

updateGauge(hitRate);
drawSparkline(performance);

document.getElementById("output").innerText="Histórico cargado correctamente.";

}catch{
document.getElementById("output").innerText="Error cargando historial.";
}
}
</script>

</head>

<body>

<div class="header">
<div class="logo">
<svg viewBox="0 0 512 512">
<rect width="512" height="512" rx="110" fill="#0f172a"/>
<polyline points="100,340 190,260 270,300 360,180 420,220"
fill="none" stroke="#3b82f6" stroke-width="28"
stroke-linecap="round" stroke-linejoin="round"/>
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
<div class="stat-title">Hit Rate</div>
<div class="gauge" id="gauge">--</div>
</div>

<div class="stat-card">
<div class="stat-title">Performance</div>
<canvas id="spark" width="120" height="60"></canvas>
</div>

</div>

<div class="buttons">
<button class="primary" onclick="fetch('/generate').then(r=>r.text()).then(t=>document.getElementById('output').innerText=t)">🎯 Generar Pick</button>
<button class="success" onclick="fetch('/save').then(r=>r.text()).then(t=>document.getElementById('output').innerText=t)">💾 Guardar</button>
<button class="warning" onclick="fetch('/send').then(r=>r.text()).then(t=>document.getElementById('output').innerText=t)">📩 Telegram</button>
<button class="neutral" onclick="loadHistory()">📊 Analizar</button>
</div>

<div class="card" id="output">
Sistema listo. Pulsa Analizar para cargar métricas avanzadas.
</div>

<div class="footer">
© ProBetTips AI · Advanced Analytics Dashboard
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
    return "Pick guardado correctamente"


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
