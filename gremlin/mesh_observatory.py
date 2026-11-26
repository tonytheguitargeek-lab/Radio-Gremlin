# Mesh Observatory V1.7 — part of Radio Gremlin
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Locally hosted dashboard: polls the Mesh Command API, keeps a persistent SQLite history of packets
# and node positions, and serves System Health, RF Watch, Mesh Radar, RF Signal Analysis and Node
# Directory views. Listens on 127.0.0.1 by default.
#
# The database stores other mesh users' node IDs, names, signal reports and reported positions.
# Keep it private; never publish observatory.db.
#
# The map uses Leaflet (BSD-2-Clause, loaded from unpkg.com) and OpenStreetMap tiles
# (data (c) OpenStreetMap contributors, ODbL; please respect the OSM tile usage policy).
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License version 3. It is distributed WITHOUT ANY WARRANTY. See LICENSE.

import json
import sqlite3
import subprocess
import re
import time
import threading
import os
import shutil
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gremlin_settings

SETTINGS = gremlin_settings.load()
API = SETTINGS.api_url
DB = SETTINGS.database

def database():
    return sqlite3.connect(DB, timeout=10)

with database() as db:
    db.execute("""CREATE TABLE IF NOT EXISTS packets (
        id TEXT PRIMARY KEY, timestamp INTEGER,
        sender TEXT, node TEXT, type TEXT,
        route TEXT, rssi REAL, snr REAL, hops INTEGER
    )""")

with database() as db:
    columns = [r[1] for r in db.execute("PRAGMA table_info(packets)")]
    if "relay" not in columns:
        db.execute("ALTER TABLE packets ADD COLUMN relay TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS rf_idx ON packets(route,timestamp)")

with database() as db:
    db.execute("""CREATE TABLE IF NOT EXISTS node_positions (
        node TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        position_time INTEGER,
        first_seen INTEGER,
        last_seen INTEGER
    )""")

position_lock = threading.Lock()

def save_positions(nodes):
    now = int(time.time())
    with database() as db:
        for n in nodes:
            pos = n.get("position")
            node = n.get("id")
            if not pos or not node:
                continue
            lat = pos.get("latitude")
            lon = pos.get("longitude")
            if not isinstance(lat, (int, float)):
                continue
            if not isinstance(lon, (int, float)):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            if lat == 0 and lon == 0:
                continue
            stamp = pos.get("position_time") or 0
            db.execute("""
                INSERT INTO node_positions
                (node,data,position_time,first_seen,last_seen)
                VALUES (?,?,?,?,?)
                ON CONFLICT(node) DO UPDATE SET
                    data=excluded.data,
                    position_time=excluded.position_time,
                    last_seen=excluded.last_seen
                WHERE excluded.position_time >=
                      node_positions.position_time
            """, (node,json.dumps(n),stamp,now,now))

def fetch_positions():
    with urllib.request.urlopen(
        API + "/mapnodes", timeout=5
    ) as r:
        data = json.load(r)
    return data["nodes"]

health_times = {"traffic": 0, "gps": 0}
observatory_started = time.time()

def collect_positions():
    while True:
        try:
            with position_lock:
                save_positions(fetch_positions())
                health_times["gps"] = time.time()
        except Exception as e:
            print("GPS collector:", e, flush=True)
        time.sleep(30)

def persistent_map():
    online = False
    live = []
    try:
        with position_lock:
            live = fetch_positions()
            save_positions(live)
        online = True
    except Exception:
        pass

    now = int(time.time())
    nodes = {n["id"]: n for n in live if n.get("id")}

    for n in nodes.values():
        n["historical"] = False

    with database() as db:
        rows = db.execute(
            "SELECT node,data,last_seen FROM node_positions"
        ).fetchall()

    for node, raw, last_seen in rows:
        current = nodes.get(node)
        if current and current.get("position"):
            continue
        n = json.loads(raw)
        if current:
            n.update({
                k:v for k,v in current.items()
                if k != "position"
            })
        else:
            n["age"] = (
                max(0, now - n["last_heard"])
                if n.get("last_heard") else None
            )
        n["historical"] = True
        n["position_cached_at"] = last_seen
        nodes[node] = n

    return {
        "nodes": list(nodes.values()),
        "count": len(nodes),
        "api_online": online,
        "saved_positions": len(rows)
    }

def collect():
    while True:
        try:
            with urllib.request.urlopen(API + "/traffic", timeout=4) as r:
                events = json.load(r)["events"]
            with database() as db:
                for e in events:
                    key = f'{e["timestamp"]}:{e["seq"]}:{e["sender_id"]}'
                    db.execute(
                        "INSERT OR IGNORE INTO packets (id,timestamp,sender,node,type,route,rssi,snr,hops,relay) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (key, e["timestamp"], e["sender"],
                         e["sender_id"], e["type"], e["route"],
                         e["rssi"], e["snr"], e["hops"], e.get("relay"))
                    )
            health_times["traffic"] = time.time()
        except Exception as e:
            print("Collector:", e, flush=True)
        time.sleep(2)

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Mesh Observatory</title>
<style>
body{background:#10151b;color:#ddd;font:16px monospace;margin:30px}
h1{color:#51df95} small{color:#82949e}
.cards{display:flex;gap:15px;flex-wrap:wrap}
.card{background:#1c2630;padding:20px;border-radius:8px;min-width:120px}
strong{display:block;font-size:32px;color:#51df95}
table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:10px;border-bottom:1px solid #33404c}
th{color:#51df95}
canvas{width:100%;height:220px;background:#151e26}
input{background:#202c36;color:white;padding:10px;border:1px solid #53636e}
#radar{height:500px;border-radius:8px}
select,button{background:#202c36;color:white;
padding:10px;border:1px solid #53636e;
border-radius:4px;margin:5px}

.rfscroll {
    max-height: 440px;
    overflow: auto;
    border: 1px solid #33404c;
    border-radius: 6px;
}
#rftraffic th {
    position: sticky;
    top: 0;
    background: #1c2630;
    z-index: 2;
}
#rftraffic td {
    white-space: nowrap;
}
#rftraffic tbody tr:hover {
    background: #202c36;
}

#radar .leaflet-tile-pane {
    filter: invert(100%) hue-rotate(180deg)
            brightness(85%) contrast(90%)
            saturate(35%);
}
#radar {
    background: #151e26;
}

.healthstrip {
 display:grid;
 grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
 gap:10px;
}
.healthbox {
 background:#1c2630;
 border:1px solid #33404c;
 border-radius:7px;
 padding:14px;
}
.healthlabel {
 font-size:12px;
 color:#9aabb5;
 margin-bottom:8px;
}
.healthvalue {
 font-size:16px;
 font-weight:bold;
}
.healthgood {color:#51df95}
.healthbad {color:#ff6666}
#healthDetails {
 font-size:13px;
 line-height:1.8;
 color:#9aabb5;
}
</style>

<link rel="stylesheet"
href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head><body>
<h1>RADIO GREMLIN / MESH OBSERVATORY</h1>
<h2>SYSTEM HEALTH / V1.7</h2>
<div id="healthStrip" class="healthstrip"></div>
<p id="healthDetails">Checking services...</p>
<p id="status">Connecting...</p>
<div class="cards" id="cards"></div>
<h2>RF WATCH / V1.2.1</h2>
<div class="cards" id="rfcards"></div>
<p id="rfstatus">Waiting for RF data...</p>
<button id="rfsound">Enable discovery sound</button>
<h3>RF NODE DIRECTORY</h3>
<div style="overflow-x:auto">
<table id="rfnodes"></table>
</div>
<h3>RF PACKET HISTORY</h3>
<div class="rfscroll">
<table id="rftraffic"></table>
</div>
<h2>MESH RADAR / V1.5.1</h2>
<div>
<select id="radius">
<option value="25">25 miles</option>
<option value="50" selected>50 miles</option>
<option value="100">100 miles</option>
<option value="250">250 miles</option>
<option value="0">All nodes</option>
</select>
<select id="source">
<option value="ALL">All sources</option>
<option value="RF">RF only</option>
<option value="MQTT">MQTT only</option>
</select>
<button id="center">Center on Gremlin</button>
<button id="fitNodes">Fit Nodes</button>
</div>
<p id="radarstatus">Waiting for GPS data...</p>
<div id="radar"></div>
<p>
<span style="color:#51df95">● Direct RF</span> |
<span style="color:#f2a34b">● Relayed RF</span> |
<span style="color:#5da8ff">● MQTT</span> |
<span style="color:#ffffff">● Gremlin</span> |
<span style="color:#aaaaaa">● Unknown</span>
</p>
<h2>RF SIGNAL ANALYSIS / V1.7</h2>
<div>
<select id="signalRange">
<option value="3600">Last hour</option>
<option value="21600">Last 6 hours</option>
<option value="86400" selected>Last 24 hours</option>
<option value="604800">Last 7 days</option>
<option value="0">All history</option>
</select>
<select id="signalNode">
<option value="ALL">All RF nodes</option>
</select>
</div>
<p id="signalStatus">Loading RF history...</p>
<p style="color:#51df95">RSSI / dBm</p>
<canvas id="rssiGraph" width="1200" height="260"></canvas>
<p style="color:#51df95">SNR / dB</p>
<canvas id="snrGraph" width="1200" height="260"></canvas>
<p>
<span style="color:#51df95">● Direct RF</span> |
<span style="color:#f2a34b">● Relayed RF</span> |
<span style="color:#aaaaaa">● Unknown route</span>
</p>
<p id="signalHover">Hover over a packet for details.</p>
<h2>NODE DIRECTORY / V1.4</h2>
<div>
<select id="directoryFilter">
<option value="RF" selected>RF ONLY</option>
<option value="MQTT">MQTT ONLY</option>
<option value="ALL">ALL NODES</option>
</select>
<input id="directorySearch" placeholder="Search node name or ID">
</div>
<p id="directoryStatus">Loading directory...</p>
<table id="nodes"></table>
<h2>PACKET HISTORY</h2>
<input id="search" placeholder="Search traffic">
<table id="traffic"></table>
<script>
async function refreshHealth(){
 const strip=document.getElementById('healthStrip');
 const details=document.getElementById('healthDetails');

 try{
  const response=await fetch('/health');
  if(!response.ok)throw Error('Health unavailable');
  const d=await response.json();

  const services=[
   ['GREMLIN API',d.gremlin,'ONLINE'],
   ['RADIO LINK',d.radio_tcp,'CONNECTED'],
   ['WATCHDOG',d.watchdog,'RUNNING'],
   ['COLLECTOR',d.collector,'ACTIVE'],
   ['DATABASE',d.database,'READABLE'],
   ['GPS COLLECTOR',d.gps_collector,'ACTIVE']
  ];

  strip.replaceChildren();

  for(const [name,ok,goodLabel] of services){
   const box=document.createElement('div');
   box.className='healthbox';

   const label=document.createElement('div');
   label.className='healthlabel';
   label.textContent=name;

   const value=document.createElement('div');
   value.className='healthvalue '+(ok?'healthgood':'healthbad');
   value.textContent=ok?'● '+goodLabel:'● CHECK';

   box.append(label,value);
   strip.appendChild(box);
  }

  const duration=t=>{
   if(t===null||t===undefined)return '--';
   const h=Math.floor(t/3600);
   const m=Math.floor((t%3600)/60);
   const sec=Math.floor(t%60);
   return h+'h '+m+'m '+sec+'s';
  };

  details.textContent=
   'Gremlin uptime: '+duration(d.gremlin_uptime)+
   ' | Observatory: '+duration(d.observatory_uptime)+
   ' | Recovery attempts: '+(d.recovery_count??'--')+
   ' | Database: '+(d.database_bytes/1048576).toFixed(2)+' MB'+
   ' | Last traffic collection: '+(d.traffic_age??'--')+'s'+
   ' | Last GPS collection: '+(d.gps_age??'--')+'s';

 }catch(e){
  strip.replaceChildren();
  details.textContent='SYSTEM HEALTH UNAVAILABLE - RETRYING';
 }
}

refreshHealth();
setInterval(refreshHealth,10000);

let packets=[];
let directoryNodes=[];

function renderDirectory(){
 const mode=document.getElementById('directoryFilter').value;
 const query=document.getElementById('directorySearch').value.toLowerCase();

 const nodes=directoryNodes.filter(n=>{
  if(mode==='RF'&&!n.rf_count)return false;
  if(mode==='MQTT'&&!n.mqtt_count)return false;
  return ((n.sender||'')+' '+n.node).toLowerCase().includes(query);
 });

 const date=t=>t?new Date(t*1000).toLocaleString():'--';

 if(mode==='RF'){
  nodes.sort((a,b)=>b.rf_last-a.rf_last);
  table('nodes',
   ['Node','ID','Last RF heard','RSSI','SNR','Hops','RF packets'],
   nodes.map(n=>[
    n.sender,n.node,date(n.rf_last),
    n.rf_rssi,n.rf_snr,n.rf_hops,n.rf_count
   ]));
 }else if(mode==='MQTT'){
  nodes.sort((a,b)=>b.mqtt_last-a.mqtt_last);
  table('nodes',
   ['Node','ID','First MQTT','Last MQTT','MQTT packets'],
   nodes.map(n=>[
    n.sender,n.node,date(n.mqtt_first),
    date(n.mqtt_last),n.mqtt_count
   ]));
 }else{
  nodes.sort((a,b)=>b.last-a.last);
  table('nodes',
   ['Node','ID','First seen','Last seen','Source','Packets'],
   nodes.map(n=>[
    n.sender,n.node,date(n.first),date(n.last),
    n.rf_count&&n.mqtt_count?'RF + MQTT':
    n.rf_count?'RF':n.mqtt_count?'MQTT':'OTHER',
    n.count
   ]));
 }

 document.getElementById('directoryStatus').textContent=
  nodes.length+' matching nodes | '+
  directoryNodes.length+' total discovered';
}

async function refreshDirectory(){
 try{
  const r=await fetch('/directory');
  if(!r.ok)throw Error('Directory unavailable');
  directoryNodes=(await r.json()).nodes;
  renderDirectory();
 }catch(e){
  document.getElementById('directoryStatus').textContent=
   'Directory unavailable - retrying';
 }
}

document.getElementById('directoryFilter').onchange=renderDirectory;
document.getElementById('directorySearch').oninput=renderDirectory;

refreshDirectory();
setInterval(refreshDirectory,10000);

function table(id,heads,rows){
 let t=document.getElementById(id);t.replaceChildren();
 let h=t.insertRow();
 heads.forEach(v=>{let c=document.createElement('th');c.textContent=v;h.append(c)});
 rows.forEach(r=>{let tr=t.insertRow();r.forEach(v=>tr.insertCell().textContent=v??'--')});
}
function traffic(){
 let q=document.getElementById('search').value.toLowerCase();
 table('traffic',['Time','Node','Type','Route','RSSI','SNR','Hops'],
 packets.filter(p=>JSON.stringify(p).toLowerCase().includes(q))
 .map(p=>[new Date(p.timestamp*1000).toLocaleString(),p.sender,p.type,p.route,p.rssi,p.snr,p.hops]));
}
document.getElementById('search').oninput=traffic;
async function refresh(){
 try{
 let d=await(await fetch('/data')).json();packets=d.packets;
 document.getElementById('status').textContent='DATABASE ONLINE | '+new Date().toLocaleTimeString();
 document.getElementById('cards').innerHTML='';
 for(let [k,v] of Object.entries(d.stats)){
 let c=document.createElement('div');c.className='card';
 c.textContent=k;let s=document.createElement('strong');s.textContent=v;c.append(s);
 document.getElementById('cards').append(c);
 }
 traffic();
 }catch(e){document.getElementById('status').textContent='Dashboard connection error'}
}
let rfSeen=null;
let audio=null;

document.getElementById('rfsound').onclick=async()=>{
 if(!audio){
  audio=new (window.AudioContext||window.webkitAudioContext)();
  await audio.resume();
  document.getElementById('rfsound').textContent='Discovery sound ON';
 }else{
  await audio.close();
  audio=null;
  document.getElementById('rfsound').textContent='Enable discovery sound';
 }
};

function rfBeep(){
 if(!audio)return;
 const o=audio.createOscillator();
 const g=audio.createGain();
 o.frequency.value=880;
 g.gain.value=0.12;
 o.connect(g);g.connect(audio.destination);
 o.start();o.stop(audio.currentTime+0.25);
}

function rfTime(t){
 return t?new Date(t*1000).toLocaleString():'--';
}

async function refreshRF(){
 try{
  const response=await fetch('/rfdata');
  if(!response.ok)throw Error('RF API');
  const d=await response.json();
  const current=new Set(d.nodes.map(n=>n.node));
  if(rfSeen&&[...current].some(n=>!rfSeen.has(n)))rfBeep();
  rfSeen=current;

  const cards=document.getElementById('rfcards');
  cards.replaceChildren();
  for(const [k,v] of Object.entries(d.stats)){
   const c=document.createElement('div');
   c.className='card';c.textContent=k;
   const value=document.createElement('strong');
   value.textContent=v;c.append(value);cards.append(c);
  }

  table('rfnodes',
   ['Node','ID','First RF','Last RF','Packets','Best RSSI','Best SNR','Latest RSSI','Latest SNR','Last TX ID'],
   d.nodes.map(n=>[
    n.sender,n.node,rfTime(n.first),rfTime(n.last),
    n.count,n.best_rssi,n.best_snr,
    n.latest_rssi,n.latest_snr,n.relay
   ]));

  table('rftraffic',
   ['Time','Node','ID','Route','Type','RSSI','SNR','Hops','Last TX ID'],
   d.packets.map(p=>[
    rfTime(p.timestamp),p.sender,p.node,p.route,
    p.type,p.rssi,p.snr,p.hops,p.relay
   ]));

  document.getElementById('rfstatus').textContent=
   'RF HISTORY ONLINE | '+new Date().toLocaleTimeString();
 }catch(e){
  document.getElementById('rfstatus').textContent='RF history unavailable';
 }
}

refreshRF();setInterval(refreshRF,3000);
refresh();setInterval(refresh,3000);

let signalData=[];
let signalStart=0;
let signalEnd=0;
let signalBusy=false;

function drawSignal(id,key,low,high,step){
 const canvas=document.getElementById(id);
 const g=canvas.getContext('2d');
 const w=canvas.width,h=canvas.height;
 const left=65,right=w-25,top=18,bottom=h-40;

 g.clearRect(0,0,w,h);
 g.font='14px monospace';

 const span=Math.max(1,signalEnd-signalStart);

 const x=t=>left+(t-signalStart)/span*(right-left);
 const y=v=>bottom-(v-low)/(high-low)*(bottom-top);

 for(let v=low;v<=high;v+=step){
  const yy=y(v);
  g.strokeStyle='#33404c';
  g.beginPath();
  g.moveTo(left,yy);
  g.lineTo(right,yy);
  g.stroke();
  g.fillStyle='#aab5bd';
  g.fillText(v,8,yy+5);
 }

 for(let i=0;i<=4;i++){
  const t=signalStart+span*i/4;
  const xx=x(t);
  const date=new Date(t*1000);
  const label=span>86400?
   date.toLocaleDateString():
   date.toLocaleTimeString([],{
    hour:'2-digit',minute:'2-digit'
   });

  g.strokeStyle='#33404c';
  g.beginPath();
  g.moveTo(xx,top);
  g.lineTo(xx,bottom);
  g.stroke();

  g.fillStyle='#aab5bd';
  g.textAlign=i===0?'left':i===4?'right':'center';
  g.fillText(label,xx,h-12);
 }
 g.textAlign='left';

 const points=[];

 for(const p of signalData){
  if(p[key]===null||p[key]===undefined)continue;
  if(p.timestamp<signalStart||p.timestamp>signalEnd)continue;

  const xx=x(p.timestamp);
  const yy=y(p[key]);

  g.fillStyle={
   DIRECT:'#51df95',
   RELAYED:'#f2a34b',
   'RF UNKNOWN':'#aaaaaa'
  }[p.route]||'#aaaaaa';

  g.beginPath();
  g.arc(xx,yy,4,0,Math.PI*2);
  g.fill();

  points.push({x:xx,y:yy,packet:p});
 }

 if(!points.length){
  g.fillStyle='#aab5bd';
  g.fillText('No RF measurements in this range',left+20,top+30);
 }

 canvas.onmousemove=e=>{
  const r=canvas.getBoundingClientRect();
  const mx=(e.clientX-r.left)*w/r.width;
  const my=(e.clientY-r.top)*h/r.height;

  let nearest=null,best=18;

  for(const point of points){
   const d=Math.hypot(point.x-mx,point.y-my);
   if(d<best){best=d;nearest=point.packet}
  }

  if(nearest){
   document.getElementById('signalHover').textContent=
    (nearest.sender||nearest.node)+' | '+
    new Date(nearest.timestamp*1000).toLocaleString()+
    ' | '+nearest.route+
    ' | RSSI: '+(nearest.rssi??'--')+' dBm'+
    ' | SNR: '+(nearest.snr??'--')+' dB'+
    ' | Hops: '+(nearest.hops??'--');
  }
 };
}

async function refreshSignal(){
 if(signalBusy)return;
 signalBusy=true;

 try{
  const range=document.getElementById('signalRange').value;
  const selector=document.getElementById('signalNode');
  const selected=selector.value;

  const response=await fetch(
   '/signals?range='+range+
   '&node='+encodeURIComponent(selected)
  );

  if(!response.ok)throw Error('Signal API unavailable');

  const d=await response.json();

  signalData=d.packets;
  signalStart=d.start;
  signalEnd=d.end;

  selector.replaceChildren(new Option('All RF nodes','ALL'));

  for(const n of d.nodes){
   selector.add(new Option(
    (n.sender||n.node)+' / '+n.node,n.node
   ));
  }

  selector.value=selected;
  if(!selector.value)selector.value='ALL';

  const rssis=signalData.map(p=>p.rssi).filter(Number.isFinite);
  const snrs=signalData.map(p=>p.snr).filter(Number.isFinite);

  let rLow=-140,rHigh=-20,sLow=-25,sHigh=15;

  for(const v of rssis){
   rLow=Math.min(rLow,Math.floor(v/20)*20);
   rHigh=Math.max(rHigh,Math.ceil(v/20)*20);
  }

  for(const v of snrs){
   sLow=Math.min(sLow,Math.floor(v/5)*5);
   sHigh=Math.max(sHigh,Math.ceil(v/5)*5);
  }

  drawSignal('rssiGraph','rssi',rLow,rHigh,20);
  drawSignal('snrGraph','snr',sLow,sHigh,5);

  document.getElementById('signalStatus').textContent=
   d.packets.length+' RF packets plotted / '+d.total+
   ' matching records'+
   (d.total>d.packets.length?' | Display limit reached':'');

 }catch(e){
  document.getElementById('signalStatus').textContent=
   'Signal history unavailable - retrying';
 }finally{
  signalBusy=false;
 }
}

document.getElementById('signalRange').onchange=refreshSignal;
document.getElementById('signalNode').onchange=refreshSignal;

refreshSignal();
setInterval(refreshSignal,10000);

if(typeof L !== 'undefined'){
const radar=L.map('radar').setView([41.23,-85.82],9);

L.tileLayer(
'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
{attribution:'&copy; OpenStreetMap contributors',
maxZoom:19}).addTo(radar);

const markers=L.layerGroup().addTo(radar);
let home=null, centered=false;
let displayedPoints=[];
let rangeCircle=null;
const nodeMarkers=new Map();

function fitRadius(){
 const radius=Number(document.getElementById('radius').value);
 if(home&&radius){
  const bounds=L.circle(
   [home.latitude,home.longitude],
   {radius:radius*1609.344}
  ).getBounds();
  radar.fitBounds(bounds,{padding:[20,20],maxZoom:13});
 }else{
  fitDisplayed();
 }
}

function fitDisplayed(){
 if(displayedPoints.length){
  radar.fitBounds(L.latLngBounds(displayedPoints),
   {padding:[30,30],maxZoom:13});
 }
}

document.getElementById('fitNodes').onclick=fitDisplayed;

function distance(a,b){
 const r=Math.PI/180;
 const dlat=(b.latitude-a.latitude)*r;
 const dlon=(b.longitude-a.longitude)*r;
 const h=Math.sin(dlat/2)**2+
 Math.cos(a.latitude*r)*Math.cos(b.latitude*r)*
 Math.sin(dlon/2)**2;
 return 3958.76*2*Math.asin(Math.sqrt(Math.min(1,h)));
}

document.getElementById('center').onclick=()=>{
 if(home)fitRadius();
};

async function updateRadar(){
 try{
 const response=await fetch('/mapdata');
 if(!response.ok)throw Error('API unavailable');
 const data=await response.json();
 const nodes=data.nodes;
 const local=nodes.find(n=>n.local&&n.position);
 home=local?local.position:null;

 if(home&&!centered){
 centered=true;
 fitRadius();
 }

 const radius=Number(document.getElementById('radius').value);
 const filter=document.getElementById('source').value;
 displayedPoints=[];
 const visibleIds=new Set();

 const routes={};
 for(const p of packets){
 if(!routes[p.node]&&
 ['DIRECT','RELAYED','MQTT','RF UNKNOWN'].includes(p.route))
 routes[p.node]=p.route;
 }

 let shown=0;
 for(const n of nodes){
 if(!n.position)continue;
 const pos=n.position;
 const miles=home?distance(home,pos):null;
 const route=n.local?'LOCAL':(routes[n.id]||'UNKNOWN');

 if(!n.local){
 if(radius&&miles!==null&&miles>radius)continue;
 if(filter==='MQTT'&&route!=='MQTT')continue;
 if(filter==='RF'&&!['DIRECT','RELAYED','RF UNKNOWN'].includes(route))continue;
 }

 const color={
 LOCAL:'#ffffff',DIRECT:'#51df95',
 RELAYED:'#f2a34b',MQTT:'#5da8ff'
 }[route]||'#aaaaaa';

 const coords=[pos.latitude,pos.longitude];
 const style={
  radius:n.local?9:6,
  color:color,
  fillColor:color,
  fillOpacity:n.historical?0.25:0.85,
  opacity:n.historical?0.5:1,
  weight:2,
  dashArray:n.historical?'3 3':null
 };

 visibleIds.add(n.id);
 displayedPoints.push(coords);

 let marker=nodeMarkers.get(n.id);

 if(marker){
  marker.setLatLng(coords);
  marker.setStyle(style);
  marker.setRadius(style.radius);
 }else{
  marker=L.circleMarker(coords,style).addTo(markers);
  nodeMarkers.set(n.id,marker);
 }

 const info=document.createElement('div');
 const lines=[
 n.long_name||n.short_name||n.id,
 n.id,
 'Source: '+route,
 'Position: '+(n.historical?'Historical / cached':'Radio database'),
 'GPS time: '+(pos.position_time?
 new Date(pos.position_time*1000).toLocaleString():'Unknown'),
 'Distance: '+(miles===null?'Unknown':miles.toFixed(1)+' mi'),
 'Hardware: '+n.hardware,
 'Last heard: '+(n.age===null?'Unknown':n.age+' sec ago')
 ];

 for(const line of lines){
 const div=document.createElement('div');
 div.textContent=line;
 info.appendChild(div);
 }

 if(marker.getPopup()){
 marker.setPopupContent(info);
 }else{
 marker.bindPopup(info);
 }
 shown++;
 }

 for(const [id,marker] of nodeMarkers){
  if(!visibleIds.has(id)){
   markers.removeLayer(marker);
   nodeMarkers.delete(id);
  }
 }

 if(home&&radius){
  if(rangeCircle){
   rangeCircle.setLatLng([home.latitude,home.longitude]);
   rangeCircle.setRadius(radius*1609.344);
  }else{
   rangeCircle=L.circle(
    [home.latitude,home.longitude],
    {radius:radius*1609.344,color:'#51df95',
     weight:1,fill:false,dashArray:'5 8'}
   ).addTo(radar);
  }
 }else if(rangeCircle){
  radar.removeLayer(rangeCircle);
  rangeCircle=null;
 }

 document.getElementById('radarstatus').textContent=
 (data.api_online?'API ONLINE':'API OFFLINE / CACHED')+' | '+
 data.saved_positions+' saved positions | '+
 nodes.length+' known nodes | '+shown+' mapped | '+
 (home?'Gremlin position available':'No Gremlin position; distance filter unavailable');

 }catch(e){
 document.getElementById('radarstatus').textContent=
 'Radar API unavailable — retrying';
 }
}

document.getElementById('radius').onchange=async()=>{
 await updateRadar();
 fitRadius();
};
document.getElementById('source').onchange=updateRadar;
updateRadar();
setInterval(updateRadar,5000);

}else{
document.getElementById('radarstatus').textContent=
'Map library unavailable — check internet connection';
}
</script></body></html>"""

def process_ids(pattern):
    try:
        result = subprocess.run(
            ["/usr/bin/pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=3
        )
        return [
            int(x) for x in result.stdout.split()
            if x.isdigit()
        ]
    except Exception:
        return []

def system_health():
    now = time.time()

    # Only this installation's processes, via the pid files the watchdog writes
    bot = gremlin_settings.pid_alive(SETTINGS.pid_file("gremlin"))
    watchdog = gremlin_settings.pid_alive(SETTINGS.pid_file("watchdog"))
    bots = [bot] if bot else []
    watchdogs = [watchdog] if watchdog else []

    tcp = gremlin_settings.radio_connected(SETTINGS, bot)

    api = False
    gremlin_uptime = None

    try:
        with urllib.request.urlopen(
            API + "/status", timeout=3
        ) as r:
            status = json.load(r)
        api = bool(status.get("api_online"))
        gremlin_uptime = status.get("uptime")
    except Exception:
        pass

    database_ok = False
    packet_count = 0
    gps_count = 0
    db_size = 0

    try:
        with database() as db:
            packet_count = db.execute(
                "SELECT COUNT(*) FROM packets"
            ).fetchone()[0]
            gps_count = db.execute(
                "SELECT COUNT(*) FROM node_positions"
            ).fetchone()[0]
        db_size = DB.stat().st_size
        database_ok = True
    except Exception:
        pass

    recovery_count = None

    try:
        logfile = SETTINGS.root / "watchdog-live.log"
        history = logfile.read_text(errors="replace")
        recovery_count = history.count(
            "Recovery retry in 30 seconds"
        )
    except Exception:
        pass

    traffic_age = (
        int(now-health_times["traffic"])
        if health_times["traffic"] else None
    )

    gps_age = (
        int(now-health_times["gps"])
        if health_times["gps"] else None
    )

    return {
        "gremlin": bool(bots) and api,
        "radio_tcp": tcp,
        "watchdog": bool(watchdogs),
        "collector": traffic_age is not None and traffic_age < 15,
        "database": database_ok,
        "gps_collector": gps_age is not None and gps_age < 75,
        "traffic_age": traffic_age,
        "gps_age": gps_age,
        "gremlin_uptime": gremlin_uptime,
        "observatory_uptime": int(now-observatory_started),
        "recovery_count": recovery_count,
        "database_bytes": db_size,
        "packet_count": packet_count,
        "gps_count": gps_count
    }

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = HTML.encode()
            content = "text/html; charset=utf-8"
        elif self.path.startswith("/signals?"):
            from urllib.parse import urlsplit, parse_qs

            args = parse_qs(urlsplit(self.path).query)

            try:
                seconds = int(args.get("range", ["86400"])[0])
            except ValueError:
                seconds = 86400

            if seconds not in (0,3600,21600,86400,604800):
                seconds = 86400

            node = args.get("node", ["ALL"])[0]
            now = int(time.time())

            rf = "route IN ('DIRECT','RELAYED','RF UNKNOWN')"
            where = rf
            params = []

            if seconds:
                where += " AND timestamp >= ?"
                params.append(now-seconds)

            if node != "ALL":
                where += " AND node = ?"
                params.append(node)

            with database() as db:
                db.row_factory = sqlite3.Row

                total = db.execute(
                    f"SELECT COUNT(*) FROM packets WHERE {where}",
                    params
                ).fetchone()[0]

                packets = [dict(r) for r in db.execute(
                    f"SELECT timestamp,sender,node,route,rssi,snr,hops "
                    f"FROM packets WHERE {where} "
                    "ORDER BY timestamp DESC,rowid DESC LIMIT 20000",
                    params
                )]

                nodes = [dict(r) for r in db.execute(f"""
                    SELECT p.node,p.sender FROM packets p
                    JOIN (
                        SELECT node,MAX(rowid) AS rid
                        FROM packets WHERE {rf}
                        AND node LIKE '!%' AND length(node)=9
                        GROUP BY node
                    ) latest ON p.rowid=latest.rid
                    ORDER BY p.sender
                """)]

                earliest = db.execute(
                    f"SELECT MIN(timestamp) FROM packets WHERE {where}",
                    params
                ).fetchone()[0]

            start = now-seconds if seconds else (
                earliest or now-3600
            )

            body = json.dumps(dict(
                packets=packets,
                nodes=nodes,
                start=min(start,now-1),
                end=now,
                total=total
            )).encode()

            content = "application/json"

        elif self.path == "/health":
            body = json.dumps(system_health()).encode()
            content = "application/json"

        elif self.path == "/mapdata":
            body = json.dumps(persistent_map()).encode()
            content = "application/json"
        elif self.path == "/directory":
            with database() as db:
                db.row_factory = sqlite3.Row
                db.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "directory_idx ON packets(node,timestamp)"
                )
                rf = "route IN ('DIRECT','RELAYED','RF UNKNOWN')"

                nodes = []
                for row in db.execute(f"""
                    SELECT node,
                    MIN(timestamp) AS first,
                    MAX(timestamp) AS last,
                    COUNT(*) AS count,
                    SUM(CASE WHEN {rf} THEN 1 ELSE 0 END) AS rf_count,
                    SUM(CASE WHEN route='MQTT' THEN 1 ELSE 0 END) AS mqtt_count,
                    MAX(CASE WHEN {rf} THEN timestamp END) AS rf_last,
                    MIN(CASE WHEN route='MQTT' THEN timestamp END) AS mqtt_first,
                    MAX(CASE WHEN route='MQTT' THEN timestamp END) AS mqtt_last
                    FROM packets
                    WHERE node LIKE '!%' AND length(node)=9
                    GROUP BY node
                """):
                    n = dict(row)

                    latest = db.execute(
                        "SELECT sender FROM packets WHERE node=? "
                        "ORDER BY timestamp DESC,rowid DESC LIMIT 1",
                        (n["node"],)
                    ).fetchone()

                    n["sender"] = latest["sender"] or n["node"]

                    last_rf = db.execute(
                        f"SELECT rssi,snr,hops FROM packets "
                        f"WHERE node=? AND {rf} "
                        "ORDER BY timestamp DESC,rowid DESC LIMIT 1",
                        (n["node"],)
                    ).fetchone()

                    n["rf_rssi"] = last_rf["rssi"] if last_rf else None
                    n["rf_snr"] = last_rf["snr"] if last_rf else None
                    n["rf_hops"] = last_rf["hops"] if last_rf else None

                    nodes.append(n)

            body = json.dumps(dict(nodes=nodes)).encode()
            content = "application/json"

        elif self.path == "/rfdata":
            with database() as db:
                db.row_factory = sqlite3.Row
                rf = "route IN ('DIRECT','RELAYED','RF UNKNOWN')"
                valid = "node LIKE '!%' AND length(node)=9"
                packets = [dict(r) for r in db.execute(
                    f"SELECT * FROM packets WHERE {rf} "
                    "ORDER BY timestamp DESC,rowid DESC LIMIT 100")]
                nodes = []
                for r in db.execute(
                    f"SELECT node,MIN(timestamp) AS first,"
                    f"MAX(timestamp) AS last,COUNT(*) AS count,"
                    f"MAX(rssi) AS best_rssi,MAX(snr) AS best_snr "
                    f"FROM packets WHERE {rf} AND {valid} "
                    "GROUP BY node ORDER BY last DESC"):
                    n = dict(r)
                    latest = db.execute(
                        f"SELECT sender,rssi,snr,relay FROM packets "
                        f"WHERE {rf} AND node=? "
                        "ORDER BY timestamp DESC,rowid DESC LIMIT 1",
                        (n["node"],)).fetchone()
                    n.update(sender=latest["sender"],
                             latest_rssi=latest["rssi"],
                             latest_snr=latest["snr"],
                             relay=latest["relay"])
                    nodes.append(n)
                stats = {
                    "RF NODE IDs": len(nodes),
                    "RF PACKETS": db.execute(
                        f"SELECT COUNT(*) FROM packets WHERE {rf}"
                    ).fetchone()[0],
                    "DIRECT": db.execute(
                        "SELECT COUNT(*) FROM packets WHERE route='DIRECT'"
                    ).fetchone()[0],
                    "RELAYED": db.execute(
                        "SELECT COUNT(*) FROM packets WHERE route='RELAYED'"
                    ).fetchone()[0]
                }
            body = json.dumps(dict(
                packets=packets,nodes=nodes,stats=stats)).encode()
            content = "application/json"
        elif self.path == "/data":
            with database() as db:
                db.row_factory = sqlite3.Row
                packets = [dict(r) for r in db.execute(
                    "SELECT * FROM packets ORDER BY timestamp DESC,rowid DESC LIMIT 500")]
                nodes = [dict(r) for r in db.execute(
                    """SELECT sender,node,MIN(timestamp) AS first,
                    MAX(timestamp) AS last,COUNT(*) AS count
                    FROM packets GROUP BY node ORDER BY last DESC""")]
                stats = {
                    "NODES": db.execute(
                        "SELECT COUNT(DISTINCT node) FROM packets "
                        "WHERE node LIKE '!%' AND length(node)=9"
                    ).fetchone()[0],
                    "MQTT": db.execute(
                        "SELECT COUNT(*) FROM packets WHERE route='MQTT'"
                    ).fetchone()[0],
                    "PACKETS": db.execute("SELECT COUNT(*) FROM packets").fetchone()[0],
                    "DIRECT": db.execute("SELECT COUNT(*) FROM packets WHERE route='DIRECT'").fetchone()[0],
                    "RELAYED": db.execute("SELECT COUNT(*) FROM packets WHERE route='RELAYED'").fetchone()[0]
                }
            body = json.dumps(dict(packets=packets,nodes=nodes,stats=stats)).encode()
            content = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

threading.Thread(target=collect, daemon=True).start()
threading.Thread(target=collect_positions, daemon=True).start()
SETTINGS.pid_file("observatory").write_text(str(os.getpid()))
print("MESH OBSERVATORY ONLINE: http://%s:%d" % (SETTINGS.obs_bind, SETTINGS.obs_port), flush=True)
try:
    ThreadingHTTPServer((SETTINGS.obs_bind, SETTINGS.obs_port), Handler).serve_forever()
finally:
    SETTINGS.pid_file("observatory").unlink(missing_ok=True)
