// party_render.js — SINGLE SOURCE OF TRUTH for the party scoreboard's shared constants
// + formatters (F5 "light seam"). Edit HERE only.
//
// This file is INLINED into both surfaces at build time by build.py inline_party_render():
//   - index.html              (the main app — base party view)
//   - overlay/src/index.html  (the Tauri spectator overlay)
// ...inside a `@inject:party_render ... @end:party_render` region. The committed copies in
// those files are GENERATED from this one — never hand-edit the region; edit this file and the
// build (or `python build.py`'s inline step) refreshes both. A drift check asserts they match.
//
// Namespaced under `PartyRender` so it can be inlined into the base app WITHOUT colliding with
// the base's own app-wide `formatNumber`/`escapeHtml` globals (used by the solo meter too).
// The base view adopts the shared CATEGORY_LABELS; the overlay delegates its label map AND
// formatters here (it previously kept its own copies — that was the drift this kills).
//
// Phase 3 (per-skill drill-down, tabs) will grow this into the shared RENDER module — the seam
// is here now so that work lands in one place instead of being built twice.
const PartyRender = {
  // Pretty labels for the room's boss_category (server-side detected).
  CATEGORY_LABELS: {
    archboss: '👑 Archboss',
    field_boss: '🌍 Field Boss',
    world_boss: '🌍 World Boss',
    raid_boss: '⚔️ Raid Boss',
    dungeon_boss: '🏰 Dungeon Boss',
    boss: '💀 Boss',
    mini_boss: '☠️ Mini Boss',
    unknown: '🎯 Boss',
  },
  catLabel(cat) {
    return PartyRender.CATEGORY_LABELS[cat] || PartyRender.CATEGORY_LABELS.unknown;
  },
  // Plain grouped integer (e.g. 1,234,567). Used for DPS + the base view's damage column.
  fmtNum(n) {
    return Math.round(Number(n) || 0).toLocaleString();
  },
  // Compact damage (1.2M / 34.5K) — the overlay's tight layout.
  fmtDmg(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return Math.round(n).toLocaleString();
  },
  escapeHtml(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : t;
    return d.innerHTML;
  },

  // ===== Fix #4/#9/#10 — shared scoreboard row renderer =====
  // Renders a full stats row for one scoreboard entry (base + overlay).
  // ``entry`` shape: {rank, user_id, username, total_damage, dps, hits, duration,
  //   crit_rate, heavy_rate, crit_heavy_rate, crit_heavy_count, contribution}
  // ``opts``: {isYou, color:{bg,text}, drillAttrs, compact}
  scoreboardRowHtml(entry, totalDamage, opts) {
    opts = opts || {};
    const e = entry || {};
    const esc = PartyRender.escapeHtml;
    const pct = (typeof e.contribution === 'number') ? e.contribution
      : (totalDamage > 0 ? (e.total_damage / totalDamage * 100) : 0);
    const rank = e.rank || 1;
    const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-other';
    const safeName = esc(e.username || '?');
    const color = opts.color || { bg: 'rgba(34,211,238,0.25)', text: '#22d3ee' };
    const isYou = !!opts.isYou;
    // Drill-down: build onclick/class attrs if supplied. drillAttrs is a partial attr string.
    const drillAttrs = opts.drillAttrs || '';
    const dps   = PartyRender.fmtNum(Math.round(e.dps || 0));
    const dmg   = PartyRender.fmtNum(e.total_damage || 0);
    const hits  = e.hits || 0;
    const avgHit = hits > 0 ? PartyRender.fmtNum(Math.round((e.total_damage || 0) / hits)) : '—';
    const critR  = ((e.crit_rate  || 0)).toFixed(1);
    const heavyR = ((e.heavy_rate || 0)).toFixed(1);
    const chR    = ((e.crit_heavy_rate || 0)).toFixed(1);
    const chCount = e.crit_heavy_count || 0;

    if (opts.compact) {
      // Overlay: tighter row — rank · name · % · dmg · dps · crit% · heavy%
      return '<div class="party-result-row ' + rankClass + (drillAttrs ? ' party-result-clickable' : '') + '"' + drillAttrs + '>'
        + '<div class="party-result-rank ' + rankClass + '">' + rank + '</div>'
        + '<div class="party-result-bar-container">'
        + '<div class="party-result-bar" style="width:' + pct.toFixed(1) + '%;background:' + color.bg + ';border-left:3px solid ' + color.text + ';"></div>'
        + '<div class="party-result-info">'
        + '<span class="party-result-name"><span style="color:' + color.text + ';">' + safeName + '</span>'
        + (isYou ? '<span class="party-result-you">YOU</span>' : '') + '</span>'
        + '<span class="party-result-stats">'
        + '<span class="party-result-percent">' + pct.toFixed(1) + '%</span>'
        + '<span class="party-result-dps">' + dps + ' DPS</span>'
        + '<span class="party-result-damage">' + dmg + '</span>'
        + '<span class="party-result-crit">' + critR + '% C</span>'
        + '<span class="party-result-heavy">' + heavyR + '% H</span>'
        + '</span></div></div></div>';
    }

    // Base (full): rank · bar · name · % · DPS · total · hits · avg · crit% · heavy% · C+H%
    return '<div class="party-result-row ' + rankClass + (drillAttrs ? ' party-result-clickable' : '') + '"' + drillAttrs + '>'
      + '<div class="party-result-rank ' + rankClass + '">' + rank + '</div>'
      + '<div class="party-result-bar-container">'
      + '<div class="party-result-bar" style="width:' + pct.toFixed(1) + '%;background:' + color.bg + ';border-left:3px solid ' + color.text + ';"></div>'
      + '<div class="party-result-info">'
      + '<span class="party-result-name"><span style="color:' + color.text + ';">' + safeName + '</span>'
      + (isYou ? '<span class="party-result-you">YOU</span>' : '') + '</span>'
      + '<span class="party-result-stats">'
      + '<span class="party-result-percent">' + pct.toFixed(1) + '%</span>'
      + '<span class="party-result-rates">'
      + '<span class="party-result-crit" title="Crit rate">' + critR + '% C</span>'
      + '<span class="party-result-heavy" title="Heavy rate">' + heavyR + '% H</span>'
      + '<span class="party-result-critheavy" title="Crit+Heavy rate (' + chCount + ' hits)">' + chR + '% C+H</span>'
      + '</span>'
      + '<span class="party-result-dps">' + dps + ' DPS</span>'
      + '<span class="party-result-damage">' + dmg + '</span>'
      + '<span class="party-result-hits" title="Hits · Avg hit">' + hits + ' hits · ' + avgHit + ' avg</span>'
      + '</span></div></div></div>';
  },

  // ===== Phase 3 / C2 — shared member-drill-down render (skill table + rotation) =====
  // Both surfaces feed these the raw ``rotation`` hit list the room serves via
  // ``get_member_detail`` (solo-hit shape: {relative_time, skill, damage, is_crit,
  // is_heavy}). SELF-CONTAINED on purpose — no dependency on the base app's globals
  // (``groupBySkill`` / ``calculateRotationStats`` / ``formatNumber``), so the overlay
  // (which has only PartyRender) renders identically. Variant via ``opts.compact``.

  // Raw hits -> per-skill rows (mirrors the solo skill block + groupBySkill), damage desc.
  aggregateSkills(rotation) {
    const rows = {};
    let total = 0;
    (rotation || []).forEach((h) => {
      const name = (h && h.skill) || 'Unknown';
      const r = rows[name] || (rows[name] = { name: name, damage: 0, hits: 0, crits: 0, heavies: 0, crit_heavies: 0 });
      const dmg = Number(h && h.damage) || 0;
      r.damage += dmg; r.hits += 1;
      if (h && h.is_crit) r.crits += 1;
      if (h && h.is_heavy) r.heavies += 1;
      if (h && h.is_crit && h.is_heavy) r.crit_heavies += 1;
      total += dmg;
    });
    const list = Object.keys(rows).map((k) => rows[k]).sort((a, b) => b.damage - a.damage);
    list.forEach((r) => {
      r.percent = total > 0 ? +(r.damage / total * 100).toFixed(1) : 0;
      r.crit_rate = r.hits > 0 ? +(r.crits / r.hits * 100).toFixed(1) : 0;
      r.heavy_rate = r.hits > 0 ? +(r.heavies / r.hits * 100).toFixed(1) : 0;
      r.crit_heavy_count = r.crit_heavy_count != null ? r.crit_heavy_count : r.crit_heavies;
    });
    return list;
  },

  // Full-fight rotation stats (port of the solo ``calculateRotationStats``) — self-contained.
  // The window spans the WHOLE fight (floored at 60s so short fights are byte-identical); TL
  // bosses run 3-15 min and were silently truncated at 60s before. (#17)
  rotationStats(rotation) {
    if (!rotation || !rotation.length) return null;
    const first = Math.floor((rotation[0] && rotation[0].relative_time) || 0);
    let last = first;
    rotation.forEach((h) => {
      const s = Math.floor((h && h.relative_time) || 0);
      if (s > last) last = s;
    });
    const windowSec = Math.max(60, last);
    const dps = {};
    for (let i = 0; i <= windowSec; i++) dps[i] = 0;
    rotation.forEach((h) => {
      const s = Math.floor((h && h.relative_time) || 0);
      if (s >= 0 && s <= windowSec) dps[s] += Number(h && h.damage) || 0;
    });
    let peak = 0;
    for (let i = 0; i <= windowSec - 5; i++) {
      let sum = 0;
      for (let j = i; j < i + 5; j++) sum += dps[j] || 0;
      if (sum / 5 > peak) peak = sum / 5;
    }
    const active = Object.keys(dps).filter((i) => dps[i] > 0 && +i >= first && +i <= last).length;
    const totalSec = Math.max(1, last - first + 1);
    return { dpsPerSecond: dps, peakDps: peak, activityRate: active / totalSec * 100, firstHitTime: first, lastHitTime: last, windowSec: windowSec };
  },

  // Skill-table HTML for a member's rotation. ``opts.compact`` => overlay variant.
  skillTableHtml(rotation, opts) {
    opts = opts || {};
    const skills = PartyRender.aggregateSkills(rotation);
    if (!skills.length) return '<div class="pr-empty">No skill data</div>';
    let max = 1;
    skills.forEach((s) => { if (s.damage > max) max = s.damage; });
    const esc = PartyRender.escapeHtml;
    if (opts.compact) {
      // overlay: name · bar · compact dmg · %
      const rows = skills.map((s) => {
        const w = (s.damage / max * 100).toFixed(1);
        return '<div class="pr-skill-row">'
          + '<span class="pr-skill-name" title="' + esc(s.name) + '">' + esc(s.name) + '</span>'
          + '<span class="pr-skill-bar"><span style="width:' + w + '%"></span></span>'
          + '<span class="pr-skill-dmg">' + PartyRender.fmtDmg(s.damage) + '</span>'
          + '<span class="pr-skill-pct">' + s.percent + '%</span>'
          + '</div>';
      }).join('');
      return '<div class="pr-skill-list">' + rows + '</div>';
    }
    // base: full 10-col table mirroring the solo skill table (reuses the solo num/bar classes).
    const body = skills.map((s) => {
      const w = (s.damage / max * 100).toFixed(1);
      const chCount = s.crit_heavy_count != null ? s.crit_heavy_count : (s.crit_heavies || 0);
      return '<tr><td>' + esc(s.name) + '</td>'
        + '<td class="num cyan">' + PartyRender.fmtNum(s.damage) + '</td>'
        + '<td><div class="damage-bar-container"><div class="damage-bar" style="width:' + w + '%"></div></div></td>'
        + '<td class="num">' + s.hits + '</td>'
        + '<td class="num yellow">' + s.crits + '</td>'
        + '<td class="num yellow">' + s.crit_rate + '%</td>'
        + '<td class="num orange">' + s.heavies + '</td>'
        + '<td class="num orange">' + s.heavy_rate + '%</td>'
        + '<td class="num teal">' + chCount + '</td>'
        + '<td class="num purple">' + s.percent + '%</td></tr>';
    }).join('');
    return '<table class="pr-skill-table"><thead><tr>'
      + '<th>Skill</th><th>Damage</th><th></th><th>Hits</th><th>Crits</th><th>Crit%</th>'
      + '<th>Heavy</th><th>Heavy%</th><th>C+H</th><th>%</th></tr></thead><tbody>' + body + '</tbody></table>';
  },

  // ===== Phase 3 / C4 — shared A/B member compare (head-to-head) =====
  // Mirrors the SOLO Run-Lab compare (``computeSkillMatrix`` + ``renderRunLabMatrix``/
  // ``renderRunLabHeader`` in index.html), but lives HERE so base + overlay render two
  // PARTY members identically with no dependency on the solo Run-Lab DOM/globals
  // (which read from ``sessionQueue`` slots A/B — solo-only). Same inputs as the
  // drill-down: each side is a raw ``rotation`` hit list ({relative_time, skill, damage,
  // is_crit, is_heavy}) the room serves via ``get_member_detail``. Per-skill rows are the
  // SAME aggregation the Run-Lab matrix shows (damage, hits, crit%, heavy%), sorted by
  // combined damage — so the head-to-head reads the same way as the solo lab.

  // Per-skill A/B matrix from two rotations. Returns rows sorted by combined damage desc.
  compareSkillMatrix(rotA, rotB) {
    const a = {}; PartyRender.aggregateSkills(rotA).forEach((r) => { a[r.name] = r; });
    const b = {}; PartyRender.aggregateSkills(rotB).forEach((r) => { b[r.name] = r; });
    const names = {};
    Object.keys(a).forEach((k) => { names[k] = true; });
    Object.keys(b).forEach((k) => { names[k] = true; });
    const blank = { damage: 0, hits: 0, crits: 0, heavies: 0, percent: 0, crit_rate: 0, heavy_rate: 0 };
    return Object.keys(names).map((name) => {
      const ra = a[name] || blank, rb = b[name] || blank;
      return {
        name: name,
        dmgA: ra.damage, dmgB: rb.damage, dmgDelta: ra.damage - rb.damage,
        hitsA: ra.hits, hitsB: rb.hits,
        critA: ra.crit_rate, critB: rb.crit_rate,
        heavyA: ra.heavy_rate, heavyB: rb.heavy_rate,
        pctA: ra.percent, pctB: rb.percent,
      };
    }).sort((x, y) => (y.dmgA + y.dmgB) - (x.dmgA + x.dmgB));
  },

  // Totals for one rotation: total damage, peak-5s DPS, crit/heavy rates over all hits.
  compareTotals(rotation) {
    let dmg = 0, hits = 0, crits = 0, heavies = 0;
    (rotation || []).forEach((h) => {
      dmg += Number(h && h.damage) || 0; hits += 1;
      if (h && h.is_crit) crits += 1;
      if (h && h.is_heavy) heavies += 1;
    });
    const stats = PartyRender.rotationStats(rotation);
    return {
      damage: dmg, hits: hits,
      crit_rate: hits > 0 ? +(crits / hits * 100).toFixed(1) : 0,
      heavy_rate: hits > 0 ? +(heavies / hits * 100).toFixed(1) : 0,
      peakDps: stats ? Math.round(stats.peakDps) : 0,
    };
  },

  // Head-to-head HTML for two members. ``meta`` = {name} label per side (defaults A/B).
  // ``opts.compact`` => overlay variant (tighter, fewer columns).
  compareHtml(rotA, rotB, metaA, metaB, opts) {
    opts = opts || {};
    const esc = PartyRender.escapeHtml;
    const labA = esc((metaA && metaA.name) || 'A');
    const labB = esc((metaB && metaB.name) || 'B');
    const hasA = rotA && rotA.length, hasB = rotB && rotB.length;
    if (!hasA || !hasB) {
      return '<div class="pr-empty">Pick two members with detailed data to compare.</div>';
    }
    const tA = PartyRender.compareTotals(rotA), tB = PartyRender.compareTotals(rotB);
    const rows = PartyRender.compareSkillMatrix(rotA, rotB);
    const sign = (v) => (v > 0 ? '+' : '');
    const dcls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : 'zero');

    // Header: peak-5s DPS for each side + delta (peak is the stable cross-member yardstick).
    const dmgDelta = tA.damage - tB.damage;
    const dmgPct = tB.damage > 0 ? (dmgDelta / tB.damage * 100) : 0;
    const fnum = opts.compact ? PartyRender.fmtDmg : PartyRender.fmtNum;
    const header = '<div class="pr-cmp-head">'
      + '<div class="pr-cmp-side a"><div class="pr-cmp-name">' + labA + '</div>'
        + '<div class="pr-cmp-dmg">' + fnum(tA.damage) + '</div>'
        + '<div class="pr-cmp-sub">Peak5s ' + fnum(tA.peakDps) + ' · ' + tA.crit_rate + '% C · ' + tA.heavy_rate + '% H</div></div>'
      + '<div class="pr-cmp-delta"><div class="pr-cmp-delta-val ' + dcls(dmgDelta) + '">'
        + sign(dmgDelta) + fnum(Math.abs(dmgDelta)) + '</div>'
        + '<div class="pr-cmp-delta-sub ' + dcls(dmgDelta) + '">' + sign(dmgPct) + Math.abs(dmgPct).toFixed(0) + '%</div>'
        + '<div class="pr-cmp-delta-lbl">total dmg Δ</div></div>'
      + '<div class="pr-cmp-side b"><div class="pr-cmp-name">' + labB + '</div>'
        + '<div class="pr-cmp-dmg">' + fnum(tB.damage) + '</div>'
        + '<div class="pr-cmp-sub">Peak5s ' + fnum(tB.peakDps) + ' · ' + tB.crit_rate + '% C · ' + tB.heavy_rate + '% H</div></div>'
      + '</div>';

    if (!rows.length) return header + '<div class="pr-empty">No overlapping skill data.</div>';

    let body, table;
    if (opts.compact) {
      // overlay: skill · A dmg · B dmg · Δ
      body = rows.map((r) => '<tr><td class="pr-cmp-skill" title="' + esc(r.name) + '">' + esc(r.name) + '</td>'
        + '<td class="num cyan">' + PartyRender.fmtDmg(r.dmgA) + '</td>'
        + '<td class="num purple">' + PartyRender.fmtDmg(r.dmgB) + '</td>'
        + '<td class="num pr-cmp-d ' + dcls(r.dmgDelta) + '">' + sign(r.dmgDelta) + PartyRender.fmtDmg(Math.abs(r.dmgDelta)) + '</td></tr>').join('');
      table = '<table class="pr-cmp-table compact"><thead><tr><th>Skill</th><th>' + labA + '</th><th>' + labB + '</th><th>Δ</th></tr></thead><tbody>' + body + '</tbody></table>';
    } else {
      // base: skill · A dmg · B dmg · Δ dmg · A hits/B hits · A crit%/B · A heavy%/B
      body = rows.map((r) => '<tr><td class="pr-cmp-skill" title="' + esc(r.name) + '">' + esc(r.name) + '</td>'
        + '<td class="num cyan">' + PartyRender.fmtNum(r.dmgA) + '</td>'
        + '<td class="num purple">' + PartyRender.fmtNum(r.dmgB) + '</td>'
        + '<td class="num pr-cmp-d ' + dcls(r.dmgDelta) + '">' + sign(r.dmgDelta) + PartyRender.fmtNum(Math.abs(r.dmgDelta)) + '</td>'
        + '<td class="num">' + r.hitsA + '<span class="pr-cmp-vs">/</span>' + r.hitsB + '</td>'
        + '<td class="num yellow">' + r.critA + '%<span class="pr-cmp-vs">/</span>' + r.critB + '%</td>'
        + '<td class="num orange">' + r.heavyA + '%<span class="pr-cmp-vs">/</span>' + r.heavyB + '%</td></tr>').join('');
      table = '<table class="pr-cmp-table"><thead><tr><th>Skill</th><th>' + labA + '</th><th>' + labB + '</th><th>Δ</th>'
        + '<th>Hits A/B</th><th>Crit% A/B</th><th>Heavy% A/B</th></tr></thead><tbody>' + body + '</tbody></table>';
    }
    return header + table;
  },

  // Rotation chart HTML — up to 61 bars spanning the FULL fight (one-second bars for <=60s, then
  // bucketed so long TL fights stay readable instead of being cut off at 60s). The axis labels
  // scale to the real fight length. ``opts.compact`` => overlay variant. (#17)
  rotationChartHtml(rotation, opts) {
    opts = opts || {};
    const stats = PartyRender.rotationStats(rotation);
    if (!stats) return '<div class="pr-empty">No rotation data</div>';
    const windowSec = stats.windowSec || 60;
    const bucketSec = Math.max(1, Math.ceil((windowSec + 1) / 61));
    const nBars = Math.ceil((windowSec + 1) / bucketSec);
    const buckets = new Array(nBars).fill(0);
    for (let i = 0; i <= windowSec; i++) buckets[Math.floor(i / bucketSec)] += stats.dpsPerSecond[i] || 0;
    let max = 1;
    for (let b = 0; b < nBars; b++) { if (buckets[b] > max) max = buckets[b]; }
    const firstBucket = Math.floor(stats.firstHitTime / bucketSec);
    const lastBucket = Math.floor(stats.lastHitTime / bucketSec);
    let bars = '';
    for (let b = 0; b < nBars; b++) {
      const d = buckets[b];
      const h = max > 0 ? (d / max * 100) : 0;
      let cls = 'normal';
      if (d === 0 && b >= firstBucket && b <= lastBucket) cls = 'gap';
      bars += '<div class="pr-rot-bar ' + cls + '" style="height:' + Math.max(h, 1) + '%"></div>';
    }
    const axisAt = (frac) => {
      const s = Math.round(windowSec * frac);
      // Short fights (<=60s, the floor) stay in plain seconds — byte-identical to the old axis.
      if (windowSec <= 60) return s + 's';
      return s >= 60 ? (Math.floor(s / 60) + 'm' + (s % 60 ? ' ' + (s % 60) + 's' : '')) : (s + 's');
    };
    return '<div class="pr-rot">'
      + '<div class="pr-rot-meta">Activity ' + stats.activityRate.toFixed(0) + '% · Peak 5s '
        + PartyRender.fmtNum(Math.round(stats.peakDps)) + '</div>'
      + '<div class="pr-rot-chart' + (opts.compact ? ' compact' : '') + '">' + bars + '</div>'
      + '<div class="pr-rot-axis"><span>0s</span><span>' + axisAt(0.25) + '</span><span>' + axisAt(0.5) + '</span><span>' + axisAt(0.75) + '</span><span>' + axisAt(1) + '</span></div>'
      + '</div>';
  },

  // ===== Trophies tab — post-fight superlatives =====
  //
  // computeTrophies(entries, memberDetails, encounterId)
  //   entries       — array of scoreboard entry objects from the board
  //                   ({user_id, username, total_damage, dps, hits, crit_rate,
  //                     heavy_rate, crit_heavy_rate, crit_heavy_count, has_detail})
  //   memberDetails — the partyState.memberDetails map (keys: "encId:userId")
  //                   each value has a ``rotation`` array of per-hit objects:
  //                   {relative_time, skill, damage, is_crit, is_heavy}
  //   encounterId   — the encounter_id string used to build the lookup key
  //
  // Returns a trophies object with these awards (all nullable when data absent):
  //   {
  //     highestSustainedDps:  { username, dps (number), windowSec }  | null
  //     hardestHit:           { username, skill, damage }            | null
  //     mostDamage:           { username, damage }                   | null  (redundant with rank-1 but explicit)
  //     mostCritHeavy:        { username, count, rate }              | null
  //     biggestCritHit:       { username, skill, damage }            | null
  //     missingDetail:        boolean  — true if ≥1 member lacks fetched rotation
  //     totalMembers:         number
  //     membersWithDetail:    number
  //   }
  //
  // "Highest sustained DPS" uses a rolling WINDOW_SEC-second window over per-hit data.
  // Members without fetched detail are skipped for hit-level trophies; ``missingDetail``
  // flags the partial-data state so the renderer can show a loading nudge.
  computeTrophies(entries, memberDetails, encounterId) {
    const WINDOW_SEC = 10; // rolling window for sustained-DPS trophy
    entries = entries || [];
    memberDetails = memberDetails || {};

    let highestSustainedDps = null;
    let hardestHit = null;
    let mostDamage = null;
    let mostCritHeavy = null;
    let biggestCritHit = null;
    let missingDetail = false;
    let membersWithDetail = 0;

    // --- Most damage (from scoreboard totals — always available) ---
    entries.forEach((e) => {
      const dmg = Number(e && e.total_damage) || 0;
      if (!mostDamage || dmg > mostDamage.damage) {
        mostDamage = { username: (e && e.username) || '?', damage: dmg };
      }
    });

    // --- Most crit+heavy hits (from scoreboard stats — always available) ---
    entries.forEach((e) => {
      const count = Number(e && e.crit_heavy_count) || 0;
      const rate  = Number(e && e.crit_heavy_rate) || 0;
      if (!mostCritHeavy || count > mostCritHeavy.count) {
        mostCritHeavy = { username: (e && e.username) || '?', count: count, rate: rate };
      }
    });

    // --- Hit-level trophies (need rotation detail) ---
    entries.forEach((e) => {
      if (!e || !e.user_id) return;
      const key    = encounterId + ':' + e.user_id;
      const detail = memberDetails[key];
      const rot    = detail && Array.isArray(detail.rotation) ? detail.rotation : null;

      if (!rot) {
        // has_detail may be true (detail requested/in-flight) or false (still fighting) —
        // either way we lack hit data for this member; mark partial.
        missingDetail = true;
        return;
      }
      membersWithDetail += 1;
      if (!rot.length) return;

      const uname = (e && e.username) || '?';

      // Hardest single hit
      rot.forEach((h) => {
        const dmg = Number(h && h.damage) || 0;
        if (!hardestHit || dmg > hardestHit.damage) {
          hardestHit = { username: uname, skill: (h && h.skill) || 'Unknown', damage: dmg };
        }
      });

      // Biggest crit+heavy hit (both flags must be set — highest-roll, 2× multiplier)
      rot.forEach((h) => {
        if (!(h && h.is_crit && h.is_heavy)) return;
        const dmg = Number(h && h.damage) || 0;
        if (!biggestCritHit || dmg > biggestCritHit.damage) {
          biggestCritHit = { username: uname, skill: (h && h.skill) || 'Unknown', damage: dmg };
        }
      });

      // Highest sustained DPS — rolling WINDOW_SEC window
      // Sort hits by time, accumulate damage within each window.
      const sorted = rot.slice().sort((a, b) => ((a && a.relative_time) || 0) - ((b && b.relative_time) || 0));
      let winStart = 0;
      let winDmg   = 0;
      for (let head = 0; head < sorted.length; head++) {
        winDmg += Number(sorted[head] && sorted[head].damage) || 0;
        // Shrink the tail until the window fits within WINDOW_SEC
        while (winStart < head) {
          const span = ((sorted[head] && sorted[head].relative_time) || 0)
                     - ((sorted[winStart] && sorted[winStart].relative_time) || 0);
          if (span <= WINDOW_SEC) break;
          winDmg -= Number(sorted[winStart] && sorted[winStart].damage) || 0;
          winStart++;
        }
        const span = Math.max(
          WINDOW_SEC,
          ((sorted[head] && sorted[head].relative_time) || 0)
            - ((sorted[winStart] && sorted[winStart].relative_time) || 0)
        );
        const sustDps = winDmg / span;
        if (!highestSustainedDps || sustDps > highestSustainedDps.dps) {
          highestSustainedDps = { username: uname, dps: sustDps, windowSec: WINDOW_SEC };
        }
      }
    });

    return {
      highestSustainedDps,
      hardestHit,
      mostDamage,
      mostCritHeavy,
      biggestCritHit,
      missingDetail,
      totalMembers: entries.length,
      membersWithDetail,
    };
  },

  // trophiesHtml(trophies)
  //   trophies — result of computeTrophies (or null/undefined for a full empty state)
  // Renders the full Trophies tab panel HTML. Self-contained — no DOM globals needed.
  trophiesHtml(trophies) {
    const esc = PartyRender.escapeHtml;
    const fnum = PartyRender.fmtNum;

    if (!trophies || !trophies.totalMembers) {
      return '<div class="party-empty-state">'
        + '<div class="party-empty-icon">🏆</div>'
        + '<div class="party-empty-title">No Trophies Yet</div>'
        + '<div class="party-empty-text">Trophies appear after the encounter ends and member data is loaded.</div>'
        + '</div>';
    }

    const t = trophies;

    // Loading nudge — shown as a small banner if some members are still missing rotation data.
    const loadingBanner = t.missingDetail
      ? '<div class="pr-trophy-loading">'
        + '⏳ Loading breakdowns for '
        + (t.totalMembers - t.membersWithDetail)
        + ' member' + (t.totalMembers - t.membersWithDetail !== 1 ? 's' : '')
        + ' — hit-level trophies will update automatically.'
        + '</div>'
      : '';

    // Helper: render one trophy card.
    // icon, title, winner (string|null), detail (string|null)
    const card = (icon, title, winner, detail) => {
      if (!winner) {
        // Trophy not yet computable (detail missing for all members, or no data at all).
        return '<div class="pr-trophy-card pr-trophy-pending">'
          + '<div class="pr-trophy-icon">' + icon + '</div>'
          + '<div class="pr-trophy-body">'
          + '<div class="pr-trophy-title">' + title + '</div>'
          + '<div class="pr-trophy-winner pr-trophy-na">—</div>'
          + '</div></div>';
      }
      return '<div class="pr-trophy-card">'
        + '<div class="pr-trophy-icon">' + icon + '</div>'
        + '<div class="pr-trophy-body">'
        + '<div class="pr-trophy-title">' + title + '</div>'
        + '<div class="pr-trophy-winner">' + esc(winner) + '</div>'
        + (detail ? '<div class="pr-trophy-detail">' + detail + '</div>' : '')
        + '</div></div>';
    };

    // --- Build each card ---

    // 1. Most Damage (always available from scoreboard)
    const mostDmgCard = card(
      '💥',
      'Most Damage',
      t.mostDamage ? t.mostDamage.username : null,
      t.mostDamage ? fnum(t.mostDamage.damage) + ' total' : null
    );

    // 2. Highest Sustained DPS (rolling 10s window — needs rotation detail)
    const sustainCard = t.highestSustainedDps
      ? card(
          '⚡',
          'Highest Sustained DPS',
          t.highestSustainedDps.username,
          fnum(Math.round(t.highestSustainedDps.dps)) + ' DPS (best ' + t.highestSustainedDps.windowSec + 's window)'
        )
      : card('⚡', 'Highest Sustained DPS', null, null);

    // 3. Hardest Single Hit — needs rotation detail
    const hardHitCard = t.hardestHit
      ? card(
          '🎯',
          'Hardest Single Hit',
          t.hardestHit.username,
          esc(t.hardestHit.skill) + ' · ' + fnum(t.hardestHit.damage)
        )
      : card('🎯', 'Hardest Single Hit', null, null);

    // 4. Biggest Crit+Heavy Hit — needs rotation detail (both is_crit AND is_heavy)
    const bigCritCard = t.biggestCritHit
      ? card(
          '💢',
          'Biggest Crit+Heavy Hit',
          t.biggestCritHit.username,
          esc(t.biggestCritHit.skill) + ' · ' + fnum(t.biggestCritHit.damage)
        )
      : card('💢', 'Biggest Crit+Heavy Hit', null, null);

    // 5. Most Crit+Heavy Hits (count + rate — from scoreboard stats, always available)
    const critHeavyCard = t.mostCritHeavy && t.mostCritHeavy.count > 0
      ? card(
          '✨',
          'Most Crit+Heavy Hits',
          t.mostCritHeavy.username,
          t.mostCritHeavy.count + ' hits · ' + t.mostCritHeavy.rate.toFixed(1) + '% C+H rate'
        )
      : card('✨', 'Most Crit+Heavy Hits', null, null);

    return '<div class="pr-trophies">'
      + loadingBanner
      + '<div class="pr-trophy-grid">'
      + mostDmgCard
      + sustainCard
      + hardHitCard
      + bigCritCard
      + critHeavyCard
      + '</div>'
      + '</div>';
  },
};
