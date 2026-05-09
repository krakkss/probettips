from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from probettips.config import load_env_file, get_env
from probettips.service import generate_daily_picks
from probettips.history import load_history
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
--bg:#0b0f14;
--card:#121a22;
--primary:#00ff88;
--secondary:#00c26e;
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
display:flex;
align-items:center;
gap:14px;
padding:20px;
border-bottom:1px solid #1c2732;
}

.logo{
width:44px;
height:44px;
}

.title{
font-size:20px;
font-weight:700;
color:var(--primary);
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
box-shadow:0 0 20px rgba(0,255,136,0.05);
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
margin-bottom:25px;
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
background:linear-gradient(135deg,var(--primary),var(--secondary));
color:black;
}

button:hover{
transform:translateY(-2px);
}

.card{
background:var(--card);
padding:22px;
border-radius:18px;
border:1px solid #1c2732;
}

.history-item{
padding:14px;
border-radius:12px;
background:#0e141b;
margin-bottom:12px;
border-left:4px solid var(--primary);
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
function drawEquity(data){
const canvas=document.getElementById("equity");
const ctx=canvas.getContext("2d");
ctx.clearRect(0,0,canvas.width,canvas.height);

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
const res=await fetch("/history");
const data=await res.json();
if(!data.length){return;}

let filtered=data.slice().reverse();
if(days){
const cutoff=new Date();
cutoff.setDate(cutoff.getDate()-days);
filtered=filtered.filter(x=>new Date(x.date)>=cutoff);
}

let wins=0;
let losses=0;
let equity=0;
let equityCurve=[];

filtered.forEach(x=>{
if(x.status==="won"){wins++;equity+=1;}
if(x.status==="lost"){losses++;equity-=1;}
equityCurve.push(equity);
});

const total=wins+losses;
const hitRate=total?Math.round((wins/total)*100):0;
const roi=total?(((wins-losses)/total)*100).toFixed(1):0;

document.getElementById("stat-hit").innerText=hitRate+"%";
document.getElementById("stat-total").innerText=total;
document.getElementById("stat-roi").innerText=roi+"%";
document.getElementById("stat-profit").innerText=equity+"u";

drawEquity(equityCurve);

let html="";
filtered.forEach(x=>{
const color=
x.status==="won"?"#00ff88":
x.status==="lost"?"#ff3b3b":"#ffaa00";

html+=`
<div class="history-item" style="border-left:4px solid ${color};">
<div style="display:flex;justify-content:space-between;">
<strong>${x.date}</strong>
<span style="color:${color};font-weight:800;">
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

window.onload=function(){loadHistory();}
</script>

</head>

<body>

<div class="header">
<div class="logo">
<svg viewBox="0 0 512 512">
<rect width="512" height="512" rx="110" fill="#0b0f14"/>
<polyline points="100,340 190,260 270,300 360,180 420,220"
fill="none" stroke="#00ff88" stroke-width="28"
stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="360" cy="180" r="20" fill="#00ff88"/>
</svg>
</div>
<div class="title">ProBetTips</div>
</div>

<div class="container">

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
<div>ROI</div>
<div class="stat-value" id="stat-roi">--</div>
</div>
<div class="stat">
<div>Profit (u)</div>
<div class="stat-value" id="stat-profit">--</div>
</div>
</div>

<div class="buttons">
<button onclick="loadHistory()">Todo</button>
<button onclick="loadHistory(7)">7 días</button>
<button onclick="loadHistory(30)">30 días</button>
<button class="primary" onclick="fetch('/generate').then(r=>r.text()).then(t=>alert(t))">
Generar Pick
</button>
</div>

<canvas id="equity" width="800" height="250"></canvas>

<div class="card" id="history"></div>

<div class="footer">
Modelo privado · Dashboard personal estilo betting
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
