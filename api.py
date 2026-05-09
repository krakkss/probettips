from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from probettips.config import load_env_file, get_env
from probettips.service import generate_daily_picks
from probettips.history import load_history
from probettips.supabase_store import SupabaseStore
from probettips.telegram import format_message

load_env_file()

app = FastAPI(title="ProBetTips API")

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = get_env("SUPABASE_SERVICE_ROLE_KEY")
FOOTBALL_DATA_API_TOKEN = get_env("FOOTBALL_DATA_API_TOKEN")

store = SupabaseStore(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<title>ProBetTipsIA</title>
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
background:linear-gradient(135deg,var(--primary),#00c26e);
color:black;
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
document.getElementById("history").innerText="No hay datos en base de datos.";
return;
}

let filtered=[...data].reverse();

if(days){
const cutoff=new Date();
cutoff.setDate(cutoff.getDate()-days);
filtered=filtered.filter(x=>{
if(!x.date) return false;
return new Date(x.date)>=cutoff;
});
}

let wins=0;
let losses=0;
let equity=0;
let equityCurve=[];

filtered.forEach(x=>{
// Normalizamos estados y resultado
const status = (x.status || "").toLowerCase();
const result = (x.result || "").toLowerCase();

// Si está settled miramos el result real
if(status==="settled"){
if(result==="win"){wins++;equity+=1;}
if(result==="loss"){losses++;equity-=1;}
}

// Compatibilidad si algún día guardas directamente won/lost
if(status==="won"){wins++;equity+=1;}
if(status==="lost"){losses++;equity-=1;}

equityCurve.push(equity);
});

// Total picks ahora cuenta todos los registros (incluye pending / settled)
const total=filtered.length;

// Hit rate solo sobre picks resueltos (won/lost)
const resolved=wins+losses;
const hitRate=resolved?Math.round((wins/resolved)*100):0;

// ROI sobre total histórico visible
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
else{
label="Finalizada";
color="#00c26e";
}
}
else if(rawStatus==="pending"){
label="Pendiente";
color="#ffaa00";
}
else if(rawStatus==="won"){
label="Ganada";
color="#00ff88";
}
else if(rawStatus==="lost"){
label="Perdida";
color="#ff3b3b";
}

/* Formateamos el pick de forma legible */
let pickText = "Sin detalle";

if (x.picks) {
try {
let parsed = typeof x.picks === "string" ? JSON.parse(x.picks) : x.picks;

if (Array.isArray(parsed) && parsed.length > 0) {

pickText = parsed.map(p => `
<div style="margin-bottom:4px;">
<strong>${p.league || ""}</strong> · 
${p.market || ""} · 
Cuota: ${p.odds || ""}
</div>
`).join("");

} else if (typeof parsed === "object") {

pickText = `
<div>
<strong>${parsed.league || ""}</strong> · 
${parsed.market || ""} · 
Cuota: ${parsed.odds || ""}
</div>
`;
}
} catch(e) {
pickText = x.source || "Sin detalle";
}
} else {
pickText = x.source || "Sin detalle";
}

html+=`
<div class="history-item">
<div style="display:flex;justify-content:space-between;">
<strong>${x.date || "-"}</strong>
<span style="color:${color};font-weight:800;">
${label}
</span>
</div>
<div style="font-size:13px;margin-top:6px;color:#cfd8dc;">
${pickText}
</div>
</div>`;
});

document.getElementById("history").innerHTML=html;

}catch(err){
resetStats();
document.getElementById("history").innerText="Error cargando datos.";
}
}

window.onload=function(){loadHistory();}
</script>

</head>

<body>

<div class="header">
ProBetTipsIA · Quant Betting Engine
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


@app.get("/history")
def history():
    return load_history(store)
