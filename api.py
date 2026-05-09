from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
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

button:disabled{
opacity:0.6;
cursor:not-allowed;
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

let lastGeneratedMessage = null;
let alreadySent = false;

async function generatePick(){
const resultDiv = document.getElementById("pickResult");
const sendBtn = document.getElementById("sendBtn");

resultDiv.style.display="block";
resultDiv.innerHTML="Generando pick... ⏳";
sendBtn.style.display="none";
sendBtn.disabled=false;
alreadySent=false;

try{
const res = await fetch("/generate");
const text = await res.text();

lastGeneratedMessage = text;

resultDiv.innerHTML = "<pre style='white-space:pre-wrap'>" + text + "</pre>";
sendBtn.style.display="inline-block";
}catch{
resultDiv.innerHTML="Error generando pick.";
}
}

async function sendToTelegram(){
if(!lastGeneratedMessage || alreadySent) return;

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

function drawEquity(data){
const canvas=document.getElementById("equity");
const ctx=canvas.getContext("2d");
ctx.clearRect(0,0,canvas.width,canvas.height);

if(data.length<2){return;}

ctx.strokeStyle="#00ff88";
ctx.lineWidth=2;
ctx.beginPath();

const min=Math.min(...data);
const max=Math.max(...data);
const range=max-min||1;

data.forEach((val,i)=>{
const x=i*(canvas.width/(data.length-1));
const y=canvas.height-((val-min)/range)*canvas.height;
if(i===0)ctx.moveTo(x,y);
else ctx.lineTo(x,y);
});
ctx.stroke();
}

async function loadHistory(days=null){
try{
const res=await fetch("/history");
const data=await res.json();

if(!Array.isArray(data) || data.length===0){
resetStats();
document.getElementById("history").innerText="No hay datos.";
return;
}

let filtered=[...data].reverse();

if(days){
const cutoff=new Date();
cutoff.setDate(cutoff.getDate()-days);
filtered=filtered.filter(x=>{
const d = x.tip_date || x.date;
if(!d) return false;
return new Date(d) >= cutoff;
});
}

let wins=0;
let losses=0;
let equity=0;
let equityCurve=[];

filtered.forEach(x=>{
const status = (x.status || "").toLowerCase();
const result = (x.result || "").toLowerCase();

if(status==="settled"){
if(result==="win"){wins++;equity+=1;}
if(result==="loss"){losses++;equity-=1;}
}

equityCurve.push(equity);
});

const total=filtered.length;
const resolved=wins+losses;
const hitRate=resolved?Math.round((wins/resolved)*100):0;
const roi=total?(((wins-losses)/total)*100).toFixed(1):0;

document.getElementById("stat-hit").innerText=hitRate+"%";
document.getElementById("stat-total").innerText=total;
document.getElementById("stat-roi").innerText=roi+"%";
document.getElementById("stat-profit").innerText=equity+"u";

drawEquity(equityCurve);

let html="";
filtered.forEach(x=>{
const rawStatus=(x.status || "").toLowerCase();
let label="Pendiente";
let color="#ffaa00";

if(rawStatus==="settled"){
if((x.result || "").toLowerCase()==="win"){
label="Ganada";
color="#00ff88";
}
else if((x.result || "").toLowerCase()==="loss"){
label="Perdida";
color="#ff3b3b";
}
}

let picksHtml="";
let totalOdds=1;

if(x.picks){
try{
let parsed=typeof x.picks==="string"?JSON.parse(x.picks):x.picks;

if(Array.isArray(parsed)){
parsed.forEach(p=>{
const odd=parseFloat(p.odds||1);
if(!isNaN(odd)){ totalOdds*=odd; }

const match = p.match || p.game || p.fixture || (p.home && p.away ? p.home + " vs " + p.away : "");

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
}catch{}
}

html+=`
<div class="history-item">
<div style="display:flex;justify-content:space-between;">
<strong>${x.tip_date || x.date || "-"}</strong>
<span style="color:${color};font-weight:800;">${label}</span>
</div>
${picksHtml}
</div>`;
});

document.getElementById("history").innerHTML=html;

}catch{
resetStats();
document.getElementById("history").innerText="Error cargando datos.";
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
<button onclick="loadHistory()">Todo</button>
<button onclick="loadHistory(7)">7 días</button>
<button onclick="loadHistory(30)">30 días</button>
<button class="primary" onclick="generatePick()">Generar Pick</button>
<button id="sendBtn" style="display:none;" onclick="sendToTelegram()">Enviar a Telegram</button>
</div>

<div class="card" id="pickResult" style="display:none;"></div>

<canvas id="equity" width="800" height="250"></canvas>

<div class="card" id="history"></div>

<div class="footer">
Motor cuantitativo · Dashboard personal
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
