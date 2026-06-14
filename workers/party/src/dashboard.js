/**
 * dashboard.js — DEBUG_KEY-gated usage dashboard for the tldps-party worker.
 *
 * Exported handlers (wired by index.js):
 *   handleDashboard(request, env)      GET /dashboard?key=…   → self-contained HTML page
 *   handleDashboardJson(request, env)  GET /dashboard.json?key=… → aggregated JSON
 *
 * Auth: both routes are gated on env.DEBUG_KEY exactly like /rooms and /party/<code>/debug.
 *   - DEBUG_KEY unset      → 404  (fail-closed / invisible)
 *   - DEBUG_KEY set, wrong → 403
 *   - Correct key          → 200
 *
 * KV bindings used (same as existing routes):
 *   env.ROOMS_KV    (id c28515495a524a2bbe2e7fc7c02d78f5)
 *   env.FEEDBACK_KV (id a61e7c1245a14bcc9c96b3cec7da6318)
 *
 * D1 analytics aggregation is delegated to dashboard_analytics.js (pure + unit-tested).
 */

import { buildAnalyticsBlock } from "./dashboard_analytics.js";

// ---------------------------------------------------------------------------
// Auth helper — mirrors /rooms and /party/<code>/debug gates exactly.
// ---------------------------------------------------------------------------
function checkKey(env, url) {
  if (!env.DEBUG_KEY) return new Response("not found", { status: 404 });
  if (url.searchParams.get("key") !== env.DEBUG_KEY) {
    return new Response("forbidden", { status: 403 });
  }
  return null; // authorized
}

// ---------------------------------------------------------------------------
// GET /dashboard.json?key=…
//   { generated_at, live_rooms[], history[], feedback[], analytics{} }
// ---------------------------------------------------------------------------
export async function handleDashboardJson(request, env) {
  const url = new URL(request.url);
  const gate = checkKey(env, url);
  if (gate) return gate;

  const generated_at = Date.now();

  // --- live_rooms: reuse the exact /rooms aggregation logic ---
  let live_rooms = [];
  if (env.ROOMS_KV) {
    try {
      const { keys } = await env.ROOMS_KV.list({ prefix: "room:" });
      live_rooms = keys
        .map((k) => ({ code: k.name.slice(5), ...(k.metadata || {}) }))
        .sort((a, b) => (b.last_activity || 0) - (a.last_activity || 0));
    } catch (_) {}
  }

  // --- history: reuse the exact /rooms/history aggregation logic ---
  let history = [];
  if (env.ROOMS_KV) {
    try {
      const { keys } = await env.ROOMS_KV.list({ prefix: "hist:" });
      history = keys
        .map((k) => k.metadata || { ts: Number(k.name.slice(5)) || 0, active_rooms: null })
        .sort((a, b) => (a.ts || 0) - (b.ts || 0));
    } catch (_) {}
  }

  // --- feedback: list all fb: keys from FEEDBACK_KV ---
  let feedback = [];
  if (env.FEEDBACK_KV) {
    try {
      const { keys } = await env.FEEDBACK_KV.list({ prefix: "fb:" });
      const values = await Promise.all(
        keys.map(async (k) => {
          try {
            return (await env.FEEDBACK_KV.get(k.name, { type: "json" })) || null;
          } catch (_) {
            return null;
          }
        })
      );
      feedback = values.filter(Boolean).reverse();
    } catch (_) {}
  }

  // --- analytics: D1 cross-encounter aggregates (additive; null if binding/queries unavailable) ---
  let analytics = null;
  try { analytics = await buildAnalyticsBlock(env, generated_at); } catch (_) { analytics = null; }

  const body = JSON.stringify({ generated_at, live_rooms, history, feedback, analytics }, null, 2);
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

// ---------------------------------------------------------------------------
// GET /dashboard?key=…  — self-contained HTML page (no CDN, no libs).
// ---------------------------------------------------------------------------
export function handleDashboard(request, env) {
  const url = new URL(request.url);
  const gate = checkKey(env, url);
  if (gate) return gate;

  return new Response(buildDashboardHtml(url.origin), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

// ---------------------------------------------------------------------------
// HTML builder — full self-contained page. Refined Dev-Dark, bento + drill-down,
// inline zero-dependency SVG charts. Exported so a preview harness can render it.
// ---------------------------------------------------------------------------
export function buildDashboardHtml(origin) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>STOOP · Party Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d1117; --surface: #161b22; --surface2: #21262d; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff; --green: #3fb950;
    --yellow: #d29922; --red: #f85149; --orange: #db6d28; --purple: #bc8cff;
    font-size: 14px;
  }
  body { background: var(--bg); color: var(--text); font-family: ui-monospace,SFMono-Regular,Consolas,monospace; min-height: 100vh; }

  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  header h1 { font-size: 1rem; color: var(--accent); letter-spacing: .04em; flex: 1 1 auto; font-weight: 700; }
  #status-bar { font-size: .8rem; color: var(--muted); }
  #status-bar .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); margin-right: 5px; vertical-align: middle; }
  #status-bar.ok .dot { background: var(--green); } #status-bar.err .dot { background: var(--red); }
  #refresh-btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text); padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: .8rem; }
  #refresh-btn:hover { border-color: var(--accent); }

  nav.tabs { background: var(--surface); border-bottom: 1px solid var(--border); display: flex; gap: 0; padding: 0 20px; flex-wrap: wrap; }
  nav.tabs button { background: none; border: none; border-bottom: 2px solid transparent; color: var(--muted); cursor: pointer; padding: 10px 16px; font-size: .875rem; transition: color .15s, border-color .15s; }
  nav.tabs button:hover { color: var(--text); }
  nav.tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }

  main { padding: 20px; max-width: 1200px; margin: 0 auto; }
  .panel { display: none; } .panel.active { display: block; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .card h2 { font-size: .8rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 12px; }

  /* KPI strip */
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 10px; margin-bottom: 14px; }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
  .kpi .label { font-size: .7rem; color: var(--muted); letter-spacing: .04em; }
  .kpi .value { font-size: 1.6rem; font-weight: 700; color: var(--accent); margin-top: 2px; }
  .kpi .value.purple { color: var(--purple); }

  /* bento grid */
  .bento { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; }
  .tile { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px; cursor: pointer; transition: border-color .15s; min-height: 110px; }
  .tile:hover { border-color: var(--accent); }
  .tile .t-head { font-size: .72rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 8px; }
  .tile .t-tag { font-size: .64rem; font-weight: 700; }
  .tag-growth { color: var(--accent); } .tag-game { color: var(--orange); } .tag-ops { color: var(--green); } .tag-fb { color: var(--purple); }
  .tile.span2 { grid-row: span 2; }
  .tile.pending { opacity: .5; border-style: dashed; cursor: default; }
  .tile.pending:hover { border-color: var(--border); }
  @media (max-width: 760px) { .bento { grid-template-columns: 1fr 1fr; } .tile.span2 { grid-row: auto; grid-column: span 2; } }

  /* charts */
  .chart { width: 100%; height: auto; display: block; }
  .chart-donut { width: 96px; height: 96px; display: block; margin: 0 auto; }
  .spark-line { fill: none; stroke: var(--accent); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .spark-area { fill: rgba(88,166,255,.13); stroke: none; }
  .bar { fill: #1f6feb; } .bar-h { fill: var(--orange); }
  .svg-axis { fill: var(--muted); font-size: 8px; font-family: ui-monospace,monospace; }
  .svg-label-l { fill: var(--text); font-size: 10px; font-family: ui-monospace,monospace; }
  .svg-val { fill: var(--muted); font-size: 9px; font-family: ui-monospace,monospace; }
  .svg-empty { fill: var(--muted); font-size: 11px; font-style: italic; }

  .qline { font-size: .8rem; margin: 3px 0; } .qline b { float: right; }
  .mini { font-size: .72rem; color: var(--text); margin: 3px 0; } .mini code { color: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: .8rem; }
  th { color: var(--muted); text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
  td { padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tr:last-child td { border-bottom: none; } tr:hover td { background: var(--surface2); }
  .age-ok { color: var(--green); font-weight: 600; } .age-warn { color: var(--yellow); font-weight: 600; } .age-stale { color: var(--red); font-weight: 600; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: .7rem; }
  .badge-bug { background: #451e1e; color: var(--red); } .badge-idea { background: #1a2e1a; color: var(--green); } .badge-fb { background: #1e2240; color: var(--accent); }
  .note { font-size: .75rem; color: var(--yellow); margin-top: 8px; padding: 6px 10px; background: #2a2100; border-left: 3px solid var(--yellow); border-radius: 0 4px 4px 0; }
  .empty { color: var(--muted); font-style: italic; padding: 16px 0; text-align: center; }
  .feedback-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 10px; }
  .feedback-card .meta { font-size: .75rem; color: var(--muted); margin-bottom: 6px; display: flex; gap: 10px; flex-wrap: wrap; }
  .feedback-card .msg { white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; } @media (max-width:760px){ .grid2{ grid-template-columns:1fr; } }
</style>
</head>
<body>

<header>
  <h1>&#9670; STOOP · Party Dashboard</h1>
  <span id="status-bar"><span class="dot"></span><span id="status-text">Loading…</span></span>
  <button id="refresh-btn" onclick="load()">&#8635; Refresh</button>
</header>

<nav class="tabs">
  <button class="active" data-tab="overview" onclick="showTab('overview',this)">Overview</button>
  <button data-tab="growth" onclick="showTab('growth',this)">Growth</button>
  <button data-tab="gameplay" onclick="showTab('gameplay',this)">Gameplay</button>
  <button data-tab="rooms" onclick="showTab('rooms',this)">Live Rooms</button>
  <button data-tab="feedback" onclick="showTab('feedback',this)">Feedback</button>
</nav>

<main>
  <div id="tab-overview" class="panel active">
    <div class="kpis" id="kpis"></div>
    <div class="bento" id="bento"></div>
  </div>
  <div id="tab-growth" class="panel"><div id="growth"></div></div>
  <div id="tab-gameplay" class="panel"><div id="gameplay"></div></div>

  <div id="tab-rooms" class="panel">
    <div class="note">
      &#9888;&#65039; <strong>online_count</strong> is cached and can be stale. <strong>Trust last-activity age</strong> as the primary signal.
      Use <code>/party/&lt;CODE&gt;/debug</code> for a live socket count.
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Live Parties (<span id="rooms-count">0</span>)</h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Code</th><th>Members</th><th>Online*</th><th>Leader</th><th>Active Boss</th><th>Last Activity</th></tr></thead>
        <tbody id="rooms-tbody"></tbody>
      </table></div>
    </div>
  </div>

  <div id="tab-feedback" class="panel">
    <div class="card"><h2>Feedback Reports (<span id="fb-count">0</span>)</h2><div id="fb-list"></div></div>
  </div>
</main>

<script>
(function() {
  'use strict';
  const KEY = new URL(location.href).searchParams.get('key') || '';
  const REFRESH_MS = 30_000;
  let refreshTimer = null;
  let ghDownloads = null;

  window.showTab = function(id, btn) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + id).classList.add('active');
    if (btn) btn.classList.add('active');
    else { const t = document.querySelector('nav.tabs button[data-tab="'+id+'"]'); if (t) t.classList.add('active'); }
  };

  function setStatus(ok, text) {
    document.getElementById('status-bar').className = ok ? 'ok' : 'err';
    document.getElementById('status-text').textContent = text;
  }

  // ---------- inline zero-dep SVG chart toolkit ----------
  const SVGChart = {
    _empty(w, h) { return '<svg viewBox="0 0 '+w+' '+h+'" class="chart"><text x="'+(w/2)+'" y="'+(h/2)+'" class="svg-empty" text-anchor="middle">no data</text></svg>'; },
    sparkline(points) {
      const W=300,H=80,P=4; if(!points||!points.length) return this._empty(W,H);
      const max=Math.max(1,...points), step=(W-2*P)/Math.max(1,points.length-1);
      const pts=points.map((v,i)=>(P+i*step).toFixed(1)+','+(H-P-(v/max)*(H-2*P)).toFixed(1)).join(' ');
      const area=P+','+(H-P)+' '+pts+' '+(W-P).toFixed(1)+','+(H-P);
      return '<svg viewBox="0 0 '+W+' '+H+'" class="chart" preserveAspectRatio="none"><polygon points="'+area+'" class="spark-area"/><polyline points="'+pts+'" class="spark-line"/></svg>';
    },
    bars(items) {
      const W=300,H=92,P=4,base=H-16; if(!items||!items.length) return this._empty(W,H);
      const max=Math.max(1,...items.map(d=>d.value)), bw=(W-2*P)/items.length; let s='';
      items.forEach((d,i)=>{ const h=(d.value/max)*(base-P), x=P+i*bw;
        s+='<rect x="'+(x+bw*0.15).toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+(bw*0.7).toFixed(1)+'" height="'+h.toFixed(1)+'" class="bar"/>'
         + '<text x="'+(x+bw/2).toFixed(1)+'" y="'+(H-4)+'" class="svg-axis" text-anchor="middle">'+esc(d.label)+'</text>'; });
      return '<svg viewBox="0 0 '+W+' '+H+'" class="chart">'+s+'</svg>';
    },
    topN(items) {
      const rowH=20,W=300,P=2; if(!items||!items.length) return this._empty(W,80);
      const H=items.length*rowH+P*2, max=Math.max(1,...items.map(d=>d.value)), barX=94, barMax=W-barX-36; let s='';
      items.forEach((d,i)=>{ const y=P+i*rowH, bw=(d.value/max)*barMax;
        s+='<text x="0" y="'+(y+14)+'" class="svg-label-l">'+esc(String(d.label).slice(0,13))+'</text>'
         + '<rect x="'+barX+'" y="'+(y+4)+'" width="'+bw.toFixed(1)+'" height="12" class="bar-h"/>'
         + '<text x="'+(barX+bw+4).toFixed(1)+'" y="'+(y+14)+'" class="svg-val">'+fmtNum(d.value)+'</text>'; });
      return '<svg viewBox="0 0 '+W+' '+H+'" class="chart">'+s+'</svg>';
    },
    histogram(buckets) {
      const W=300,H=90,P=4,base=H-4; if(!buckets||!buckets.length) return this._empty(W,H);
      const mc=Math.max(1,...buckets.map(b=>b.count)), bw=(W-2*P)/buckets.length; let s='';
      buckets.forEach((b,i)=>{ const h=(b.count/mc)*(base-P), x=P+i*bw;
        s+='<rect x="'+x.toFixed(1)+'" y="'+(base-h).toFixed(1)+'" width="'+Math.max(1,bw-1).toFixed(1)+'" height="'+h.toFixed(1)+'" class="bar"/>'; });
      return '<svg viewBox="0 0 '+W+' '+H+'" class="chart">'+s+'</svg>';
    },
    donut(slices) {
      const W=120,H=120,cx=60,cy=60,r=44,sw=18; const total=(slices||[]).reduce((a,d)=>a+d.value,0);
      if(!total) return this._empty(W,H); let a=-Math.PI/2,s='';
      slices.forEach(d=>{ const frac=d.value/total, a2=a+frac*2*Math.PI;
        const x1=cx+r*Math.cos(a),y1=cy+r*Math.sin(a),x2=cx+r*Math.cos(a2),y2=cy+r*Math.sin(a2),large=frac>0.5?1:0;
        s+='<path d="M '+x1.toFixed(1)+' '+y1.toFixed(1)+' A '+r+' '+r+' 0 '+large+' 1 '+x2.toFixed(1)+' '+y2.toFixed(1)+'" fill="none" stroke="'+d.color+'" stroke-width="'+sw+'"/>'; a=a2; });
      return '<svg viewBox="0 0 '+W+' '+H+'" class="chart-donut">'+s+'</svg>';
    }
  };

  // ---------- data load ----------
  async function load() {
    setStatus(true, 'Loading…');
    clearTimeout(refreshTimer);
    try {
      const res = await fetch('/dashboard.json?key=' + encodeURIComponent(KEY));
      if (!res.ok) { setStatus(false, 'HTTP ' + res.status); schedule(); return; }
      const data = await res.json();
      fetchGhDownloads(() => {
        renderOverview(data); renderGrowth(data);
      });
      renderOverview(data); renderGrowth(data); renderGameplay(data);
      renderRooms(data.live_rooms || []); renderFeedback(data.feedback || []);
      setStatus(true, 'Updated ' + new Date(data.generated_at).toLocaleTimeString() + ' · auto-refresh 30s');
    } catch (e) { setStatus(false, 'Error: ' + e.message); }
    schedule();
  }
  function schedule() { clearTimeout(refreshTimer); refreshTimer = setTimeout(load, REFRESH_MS); }

  function fetchGhDownloads(cb) {
    if (ghDownloads !== null) { if (cb) cb(); return; }
    fetch('https://api.github.com/repos/stoopkid713/TL-DPS-Meter/releases', {
      headers: { 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }
    }).then(r => r.ok ? r.json() : Promise.reject('HTTP ' + r.status))
      .then(rel => { let t = 0; rel.forEach(r => (r.assets||[]).forEach(a => t += (a.download_count||0))); ghDownloads = t; if (cb) cb(); })
      .catch(() => { ghDownloads = 'N/A'; if (cb) cb(); });
  }

  // ---------- Overview ----------
  function renderOverview(data) {
    const a = data.analytics, hist = data.history || [], live = data.live_rooms || [];
    const enc7 = a ? (a.encounters_per_day||[]).slice(-7).reduce((s,d)=>s+d.count,0) : 0;
    const peak = hist.reduce((m,s)=>Math.max(m, s.active_rooms||0), 0);
    const kpis = [
      ['Live Now', live.length, ''],
      ['Parties · 7d', a ? a.distinct_parties : '—', ''],
      ['Encounters · 7d', a ? fmtNum(enc7) : '—', ''],
      ['Downloads', ghDownloads==null?'…':(typeof ghDownloads==='number'?fmtNum(ghDownloads):ghDownloads), 'purple'],
      ['Peak Rooms', peak, ''],
    ];
    document.getElementById('kpis').innerHTML = kpis.map(k =>
      '<div class="kpi"><div class="label">'+k[0]+'</div><div class="value '+k[2]+'">'+k[1]+'</div></div>').join('');

    const epd = a ? (a.encounters_per_day||[]).map(d=>d.count) : [];
    const bosses = a ? (a.top_bosses||[]).slice(0,4).map(b=>({label:b.boss,value:b.count})) : [];
    const psize = a ? (a.party_size_dist||[]).map(d=>({label:String(d.size),value:d.count})) : [];
    const q = a ? a.hit_quality : null;
    const tiles = [];
    tiles.push(tile('span2', 'Encounters / day · 30d', 'growth', '↗ GROWTH', SVGChart.sparkline(epd), 'growth'));
    tiles.push(tile('', 'Top Bosses · 7d', 'game', '⚔ GAMEPLAY', SVGChart.topN(bosses), 'gameplay'));
    tiles.push(tile('', 'Party Size', 'game', '⚔', SVGChart.bars(psize), 'gameplay'));
    tiles.push(tile('', 'Hit Quality', 'game', '⚔',
      q ? ('<div class="qline">Crit <b style="color:var(--green)">'+pct(q.crit_rate)+'</b></div>'
         + '<div class="qline">Heavy <b style="color:var(--yellow)">'+pct(q.heavy_rate)+'</b></div>'
         + '<div class="qline">Crit+Heavy <b style="color:var(--purple)">'+pct(q.crit_heavy_rate)+'</b></div>')
        : '<div class="empty">no data</div>', 'gameplay'));
    tiles.push(tile('', 'Live Rooms', 'ops', 'OPS',
      live.length ? live.slice(0,3).map(r=>'<div class="mini"><code>'+esc(r.code||'?')+'</code> · '+(r.member_count||0)+'p · '+esc(r.active_boss||'—')+'</div>').join('')
        : '<div class="empty">none live</div>', 'rooms'));
    tiles.push(tile('', 'Feedback', 'fb', (data.feedback||[]).length+' total',
      (data.feedback||[]).length ? (data.feedback||[]).slice(0,2).map(f=>'<div class="mini">'+badgeEmoji(f.type)+' '+esc((f.message||'').slice(0,46))+'</div>').join('')
        : '<div class="empty">none</div>', 'feedback'));
    tiles.push('<div class="tile pending"><div class="t-head">⏱ Fight Duration</div><div style="color:var(--yellow);font-size:.74rem">pending #56 — needs real fight start/end</div></div>');
    document.getElementById('bento').innerHTML = tiles.join('');
  }
  function tile(extra, head, tagClass, tag, body, goTab) {
    return '<div class="tile '+extra+'" onclick="showTab(\\''+goTab+'\\')">'
      + '<div class="t-head"><span>'+head+'</span><span class="t-tag tag-'+tagClass+'">'+tag+'</span></div>'
      + body + '</div>';
  }

  // ---------- Growth ----------
  function renderGrowth(data) {
    const a = data.analytics, hist = data.history || [];
    const epd = a ? (a.encounters_per_day||[]).map(d=>d.count) : [];
    const rooms = hist.slice(-72).map(s=>({label:'', value:s.active_rooms||0}));
    const dl = ghDownloads==null?'…':(typeof ghDownloads==='number'?fmtNum(ghDownloads):ghDownloads);
    document.getElementById('growth').innerHTML =
      '<div class="card"><h2>Encounters / day · 30d</h2>'+SVGChart.sparkline(epd)+'</div>'
      + '<div class="grid2">'
      +   '<div class="card"><h2>Distinct Parties · 7d</h2><div class="kpi"><div class="value">'+(a?a.distinct_parties:'—')+'</div></div></div>'
      +   '<div class="card"><h2>GitHub Downloads</h2><div class="kpi"><div class="value purple">'+dl+'</div></div></div>'
      + '</div>'
      + '<div class="card"><h2>Active Rooms / hour · last 72h</h2>'+SVGChart.bars(rooms.length?rooms:[])+'</div>'
      + '<div class="note">Time-of-day &amp; new-vs-returning need per-fight timing — pending #56.</div>';
  }

  // ---------- Gameplay ----------
  function renderGameplay(data) {
    const a = data.analytics;
    if (!a) { document.getElementById('gameplay').innerHTML = '<div class="card"><div class="empty">No analytics data.</div></div>'; return; }
    const bosses = (a.top_bosses||[]).map(b=>({label:b.boss,value:b.count}));
    const psize = (a.party_size_dist||[]).map(d=>({label:String(d.size),value:d.count}));
    const q = a.hit_quality;
    const donut = q ? SVGChart.donut([
      {label:'Crit', value:q.crit_rate, color:'#3fb950'},
      {label:'Heavy', value:q.heavy_rate, color:'#d29922'},
      {label:'Other', value:Math.max(0,1-q.crit_rate-q.heavy_rate), color:'#30363d'},
    ]) : '<div class="empty">no data</div>';
    const mix = (a.content_mix||[]).slice(0,8).map(c=>'<tr><td>'+esc(c.content_type||'—')+'</td><td>'+esc(c.content_tier||'—')+'</td><td>'+fmtNum(c.count)+'</td></tr>').join('')
      || '<tr><td colspan="3" class="empty">no data</td></tr>';
    document.getElementById('gameplay').innerHTML =
      '<div class="grid2">'
      +   '<div class="card"><h2>Top Bosses · 7d</h2>'+SVGChart.topN(bosses)+'</div>'
      +   '<div class="card"><h2>Boss Damage Distribution</h2>'+SVGChart.histogram((a.damage_dist||{}).buckets)+'</div>'
      +   '<div class="card"><h2>Party Size</h2>'+SVGChart.bars(psize)+'</div>'
      +   '<div class="card"><h2>Hit Quality</h2>'+donut+'</div>'
      + '</div>'
      + '<div class="card"><h2>Content Mix · 7d</h2><table><thead><tr><th>Type</th><th>Tier</th><th>Count</th></tr></thead><tbody>'+mix+'</tbody></table></div>';
  }

  // ---------- Live Rooms ----------
  function renderRooms(rooms) {
    document.getElementById('rooms-count').textContent = rooms.length;
    const tbody = document.getElementById('rooms-tbody');
    if (!rooms.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty">No active parties right now.</td></tr>'; return; }
    const now = Date.now();
    tbody.innerHTML = rooms.map(r => {
      const ageSec = r.last_activity ? Math.floor((now - r.last_activity)/1000) : null;
      const ageStr = ageSec===null ? '—' : fmtAge(ageSec);
      const ageClass = ageSec===null ? '' : ageSec<120 ? 'age-ok' : ageSec<600 ? 'age-warn' : 'age-stale';
      return '<tr><td><code>'+esc(r.code||'?')+'</code></td><td>'+(r.member_count||0)+'</td><td>'+(r.online_count||0)+'</td><td>'+esc(r.leader||'—')+'</td><td>'+esc(r.active_boss||'—')+'</td><td class="'+ageClass+'">'+ageStr+'</td></tr>';
    }).join('');
  }

  // ---------- Feedback ----------
  function renderFeedback(items) {
    document.getElementById('fb-count').textContent = items.length;
    const list = document.getElementById('fb-list');
    if (!items.length) { list.innerHTML = '<div class="empty">No feedback reports yet.</div>'; return; }
    list.innerHTML = items.map(fb => {
      const type = fb.type || 'feedback';
      const badgeClass = type==='bug' ? 'badge-bug' : type==='idea' ? 'badge-idea' : 'badge-fb';
      const ctx = fb.context || {}, parts = [];
      if (ctx.app_version) parts.push('v'+esc(ctx.app_version));
      if (ctx.screen) parts.push('screen:'+esc(ctx.screen));
      return '<div class="feedback-card"><div class="meta"><span class="badge '+badgeClass+'">'+esc(type)+'</span><span>'+esc(fb.ts||'')+'</span>'
        + (parts.length?'<span>'+parts.join(' · ')+'</span>':'') + '</div><div class="msg">'+esc(fb.message||'')+'</div></div>';
    }).join('');
  }

  // ---------- helpers ----------
  function fmtAge(s) { if(s<60) return s+'s ago'; if(s<3600) return Math.floor(s/60)+'m ago'; return Math.floor(s/3600)+'h ago'; }
  function fmtNum(n) { n = Number(n)||0; if(n>=1e9) return (n/1e9).toFixed(1)+'B'; if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'k'; return String(n); }
  function pct(x) { return Math.round((Number(x)||0)*100)+'%'; }
  function badgeEmoji(t) { return t==='bug'?'🐛':t==='idea'?'💡':'💬'; }
  function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  window.esc = esc; window.fmtNum = fmtNum;

  window.load = load;
  load();
})();
</script>
</body>
</html>`;
}
