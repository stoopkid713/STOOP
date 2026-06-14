# STOOP Dashboard Upgrade — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the D1 `encounter_analytics` data and ship a bento Overview + Growth & Gameplay drill-downs on the DEBUG_KEY-gated party dashboard, in the Refined Dev-Dark style, with a zero-dependency SVG chart toolkit.

**Architecture:** A new **pure** server module (`dashboard_analytics.js`) builds the `analytics` block from D1 via `GROUP BY` queries — pure row→shape transforms are unit-tested with `node:test`; the async assembler runs the queries with per-query try/catch. `dashboard.js` gains the `analytics` block in `handleDashboardJson` (additive) and a rewritten `buildDashboardHtml` (bento + drill-down + inline SVG charts). Auth, KV blocks, and JSON keys are unchanged/additive.

**Tech Stack:** Cloudflare Worker (ES modules), D1 (`ANALYTICS_DB`), vanilla client JS + inline SVG (no libs/CDN), `node:test` for unit tests, `wrangler deploy --dry-run` + `node --check` for verification.

**Spec:** `docs/superpowers/specs/2026-06-14-dashboard-upgrade-design.md`

**Phase scope:** P1 only. Follow-on plans: **P2** (Live Ops drill-down + Feedback polish), **P3** (time-based tiles — depends on #56). Time-based tiles in P1 render a static "pending #56" placeholder.

**Note on UI tasks:** backend/data/test tasks below carry complete code (that's where bugs hide). The client render tasks (Tasks 7–10) specify the **data contract, function signatures, and acceptance checks**; the HTML/SVG bodies are built against that contract and iterated live against the running preview server (`http://localhost:61507`) rather than pre-written pixel-for-pixel — pre-writing ~800 lines of inline markup in a plan is wasteful and harder to verify than a live render. This is a deliberate scoping choice, not a placeholder.

---

## File Structure

- **Create** `workers/party/src/dashboard_analytics.js` — pure SQL builders + row→block transforms + async `buildAnalyticsBlock(env, nowMs)`. No template/DOM code. The only file with unit tests.
- **Create** `workers/party/test/dashboard_analytics.test.mjs` — `node:test` unit tests for the pure functions + the assembler (with a stub `env.ANALYTICS_DB`).
- **Modify** `workers/party/src/dashboard.js` — import + call `buildAnalyticsBlock` in `handleDashboardJson` (additive `analytics` key); rewrite `buildDashboardHtml` (bento Overview + Growth/Gameplay drill-downs + inline SVG toolkit + "pending #56" tiles).
- **No change** `workers/party/src/index.js` — already routes `/dashboard` + `/dashboard.json`; `env.ANALYTICS_DB` already in scope.

## Data contract — the `analytics` block

`handleDashboardJson` response gains one additive key:

```
analytics: {
  window_days: 7,
  top_bosses:        [{ boss: string, count: number, boss_damage: number }],   // desc, top 10
  encounters_per_day:[{ day: "YYYY-MM-DD", count: number }],                    // 30d, zero-filled
  distinct_parties:  number,                                                    // COUNT(DISTINCT party_code_hash), window
  party_size_dist:   [{ size: number, count: number }],                         // asc by size
  content_mix:       [{ content_type: string|null, content_tier: string|null, count: number }],
  damage_dist:       { buckets: [{ lo: number, hi: number, count: number }], max: number }, // boss_damage histogram
  hit_quality:       { crit_rate: number, heavy_rate: number, crit_heavy_rate: number } | null, // 0..1, hits-weighted
  time_based:        null   // P3 / #56
}
```
If `env.ANALYTICS_DB` is absent → `analytics: null`. Any single failing query → that sub-key is `[]`/`null`, rest still populated.

---

## Task 1: Scaffold pure module + `mapTopBosses` (TDD)

**Files:**
- Create: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
// workers/party/test/dashboard_analytics.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mapTopBosses } from "../src/dashboard_analytics.js";

test("mapTopBosses maps rows and drops null boss_name", () => {
  const rows = [
    { boss_name: "Daigon", n: 41, dmg: 999 },
    { boss_name: null, n: 5, dmg: 10 },
  ];
  assert.deepEqual(mapTopBosses(rows), [{ boss: "Daigon", count: 41, boss_damage: 999 }]);
});

test("mapTopBosses on empty input returns []", () => {
  assert.deepEqual(mapTopBosses([]), []);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — cannot find module `../src/dashboard_analytics.js` / `mapTopBosses is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
// workers/party/src/dashboard_analytics.js
// Pure, runtime-free helpers for the dashboard analytics block. No Cloudflare/DOM deps.

export function mapTopBosses(rows) {
  return (rows || [])
    .filter((r) => r && r.boss_name != null)
    .map((r) => ({ boss: r.boss_name, count: Number(r.n) || 0, boss_damage: Number(r.dmg) || 0 }));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): pure analytics module scaffold + mapTopBosses"
```

---

## Task 2: `fillDailySeries` — zero-filled encounters/day (TDD)

**Files:**
- Modify: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
import { fillDailySeries } from "../src/dashboard_analytics.js";

test("fillDailySeries zero-fills gaps and is ascending", () => {
  // now = 2026-06-03T00:00:00Z; 3-day window
  const now = Date.parse("2026-06-03T12:00:00Z");
  const rows = [
    { day: "2026-06-01", n: 4 },
    { day: "2026-06-03", n: 7 },
  ];
  assert.deepEqual(fillDailySeries(rows, now, 3), [
    { day: "2026-06-01", count: 4 },
    { day: "2026-06-02", count: 0 },
    { day: "2026-06-03", count: 7 },
  ]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — `fillDailySeries is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
// append to dashboard_analytics.js
function dayKey(ms) {
  return new Date(ms).toISOString().slice(0, 10); // YYYY-MM-DD (UTC)
}

export function fillDailySeries(rows, nowMs, days) {
  const byDay = new Map((rows || []).map((r) => [r.day, Number(r.n) || 0]));
  const out = [];
  const startMs = nowMs - (days - 1) * 86_400_000;
  for (let i = 0; i < days; i++) {
    const k = dayKey(startMs + i * 86_400_000);
    out.push({ day: k, count: byDay.get(k) || 0 });
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): zero-filled daily encounters series"
```

---

## Task 3: simple mappers — party_size, content_mix (TDD)

**Files:**
- Modify: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
import { mapPartySizeDist, mapContentMix } from "../src/dashboard_analytics.js";

test("mapPartySizeDist sorts ascending by size", () => {
  const rows = [{ party_size: 4, n: 9 }, { party_size: 2, n: 3 }];
  assert.deepEqual(mapPartySizeDist(rows), [{ size: 2, count: 3 }, { size: 4, count: 9 }]);
});

test("mapContentMix passes through type/tier with counts", () => {
  const rows = [{ content_type: "dungeon", content_tier: "hard", n: 5 }];
  assert.deepEqual(mapContentMix(rows), [{ content_type: "dungeon", content_tier: "hard", count: 5 }]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — functions undefined.

- [ ] **Step 3: Write minimal implementation**

```js
export function mapPartySizeDist(rows) {
  return (rows || [])
    .map((r) => ({ size: Number(r.party_size) || 0, count: Number(r.n) || 0 }))
    .sort((a, b) => a.size - b.size);
}

export function mapContentMix(rows) {
  return (rows || []).map((r) => ({
    content_type: r.content_type ?? null,
    content_tier: r.content_tier ?? null,
    count: Number(r.n) || 0,
  }));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): party-size + content-mix mappers"
```

---

## Task 4: `bucketDamage` histogram (TDD)

**Files:**
- Modify: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
import { bucketDamage } from "../src/dashboard_analytics.js";

test("bucketDamage builds N equal buckets over [0, max]", () => {
  const rows = [{ boss_damage: 0 }, { boss_damage: 50 }, { boss_damage: 100 }];
  const h = bucketDamage(rows, 2);
  assert.equal(h.max, 100);
  assert.equal(h.buckets.length, 2);
  // 0 and 50 land in [0,50); 100 lands in [50,100] (last bucket inclusive)
  assert.equal(h.buckets[0].count, 2);
  assert.equal(h.buckets[1].count, 1);
});

test("bucketDamage on empty input returns max 0, empty buckets", () => {
  assert.deepEqual(bucketDamage([], 2), { buckets: [], max: 0 });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — `bucketDamage is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
export function bucketDamage(rows, n = 12) {
  const vals = (rows || []).map((r) => Number(r.boss_damage) || 0);
  if (!vals.length) return { buckets: [], max: 0 };
  const max = Math.max(...vals);
  if (max <= 0) return { buckets: [{ lo: 0, hi: 0, count: vals.length }], max: 0 };
  const w = max / n;
  const buckets = Array.from({ length: n }, (_, i) => ({ lo: i * w, hi: (i + 1) * w, count: 0 }));
  for (const v of vals) {
    let idx = Math.floor(v / w);
    if (idx >= n) idx = n - 1; // max value lands in the last (inclusive) bucket
    buckets[idx].count++;
  }
  return { buckets, max };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): boss-damage histogram bucketing"
```

---

## Task 5: `computeHitQuality` — hits-weighted crit/heavy from `detail` JSON (TDD)

**Files:**
- Modify: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

Each row's `detail` is the JSON string written at log time; it carries `quality:{hits,crit_rate,heavy_rate,crit_heavy_rate}` (rates 0..1) when present. Aggregate hits-weighted; rows without quality are skipped.

- [ ] **Step 1: Write the failing test**

```js
import { computeHitQuality } from "../src/dashboard_analytics.js";

test("computeHitQuality is hits-weighted across rows", () => {
  const rows = [
    { detail: JSON.stringify({ quality: { hits: 100, crit_rate: 0.4, heavy_rate: 0.2, crit_heavy_rate: 0.1 } }) },
    { detail: JSON.stringify({ quality: { hits: 300, crit_rate: 0.2, heavy_rate: 0.1, crit_heavy_rate: 0.05 } }) },
  ];
  const q = computeHitQuality(rows);
  // weighted crit = (100*.4 + 300*.2)/400 = 0.25
  assert.ok(Math.abs(q.crit_rate - 0.25) < 1e-9);
});

test("computeHitQuality returns null when no quality present", () => {
  assert.equal(computeHitQuality([{ detail: "{}" }, { detail: null }]), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — `computeHitQuality is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
export function computeHitQuality(rows) {
  let hits = 0, crit = 0, heavy = 0, critHeavy = 0;
  for (const r of rows || []) {
    let q = null;
    try { q = JSON.parse(r.detail || "null")?.quality || null; } catch (_) { q = null; }
    if (!q) continue;
    const h = Number(q.hits) || 0;
    if (h <= 0) continue;
    hits += h;
    crit += (Number(q.crit_rate) || 0) * h;
    heavy += (Number(q.heavy_rate) || 0) * h;
    critHeavy += (Number(q.crit_heavy_rate) || 0) * h;
  }
  if (hits <= 0) return null;
  return { crit_rate: crit / hits, heavy_rate: heavy / hits, crit_heavy_rate: critHeavy / hits };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): hits-weighted crit/heavy quality aggregate"
```

---

## Task 6: `buildAnalyticsBlock(env, nowMs)` assembler + stub-DB test (TDD)

**Files:**
- Modify: `workers/party/src/dashboard_analytics.js`
- Test: `workers/party/test/dashboard_analytics.test.mjs`

Runs the D1 queries (each in its own try/catch), feeds rows to the pure mappers, returns the data-contract object. D1 read API: `env.ANALYTICS_DB.prepare(sql).bind(...).all()` → `{ results }`.

- [ ] **Step 1: Write the failing test (fake DB stub)**

```js
import { buildAnalyticsBlock } from "../src/dashboard_analytics.js";

function fakeDB(map) {
  // map: substring-of-SQL -> results array; .prepare().bind().all() resolves to {results}
  return {
    prepare(sql) {
      const key = Object.keys(map).find((k) => sql.includes(k));
      const results = key ? map[key] : [];
      return { bind: () => ({ all: async () => ({ results }) }) };
    },
  };
}

test("buildAnalyticsBlock assembles all sub-blocks", async () => {
  const now = Date.parse("2026-06-03T12:00:00Z");
  const env = { ANALYTICS_DB: fakeDB({
    "GROUP BY boss_name": [{ boss_name: "Daigon", n: 41, dmg: 9 }],
    "GROUP BY day":       [{ day: "2026-06-03", n: 7 }],
    "COUNT(DISTINCT":     [{ n: 12 }],
    "GROUP BY party_size":[{ party_size: 4, n: 9 }],
    "GROUP BY content_type":[{ content_type: "dungeon", content_tier: "hard", n: 5 }],
    "SELECT boss_damage": [{ boss_damage: 100 }],
    "SELECT detail":      [{ detail: JSON.stringify({ quality: { hits: 10, crit_rate: 0.5, heavy_rate: 0, crit_heavy_rate: 0 } }) }],
  }) };
  const a = await buildAnalyticsBlock(env, now);
  assert.equal(a.top_bosses[0].boss, "Daigon");
  assert.equal(a.distinct_parties, 12);
  assert.equal(a.time_based, null);
  assert.equal(a.encounters_per_day.at(-1).day, "2026-06-03");
});

test("buildAnalyticsBlock returns null when ANALYTICS_DB missing", async () => {
  assert.equal(await buildAnalyticsBlock({}, Date.now()), null);
});

test("buildAnalyticsBlock isolates a failing query", async () => {
  const env = { ANALYTICS_DB: { prepare(sql) {
    if (sql.includes("GROUP BY boss_name")) throw new Error("boom");
    return { bind: () => ({ all: async () => ({ results: [] }) }) };
  } } };
  const a = await buildAnalyticsBlock(env, Date.now());
  assert.deepEqual(a.top_bosses, []);          // failed query → empty, not thrown
  assert.equal(a.distinct_parties, 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: FAIL — `buildAnalyticsBlock is not a function`.

- [ ] **Step 3: Write minimal implementation**

```js
const WINDOW_DAYS = 7;
const SERIES_DAYS = 30;

async function q(env, sql, binds, mapper, fallback) {
  try {
    const { results } = await env.ANALYTICS_DB.prepare(sql).bind(...binds).all();
    return mapper(results || []);
  } catch (_) {
    return fallback;
  }
}

export async function buildAnalyticsBlock(env, nowMs) {
  if (!env || !env.ANALYTICS_DB) return null;
  const sinceWin = nowMs - WINDOW_DAYS * 86_400_000;
  const sinceSeries = nowMs - SERIES_DAYS * 86_400_000;

  const top_bosses = await q(env,
    "SELECT boss_name, COUNT(*) n, SUM(COALESCE(boss_damage,0)) dmg FROM encounter_analytics WHERE created_at >= ? AND boss_name IS NOT NULL GROUP BY boss_name ORDER BY n DESC LIMIT 10",
    [sinceWin], mapTopBosses, []);

  const epdRows = await q(env,
    "SELECT strftime('%Y-%m-%d', created_at/1000, 'unixepoch') day, COUNT(*) n FROM encounter_analytics WHERE created_at >= ? GROUP BY day",
    [sinceSeries], (r) => r, []);
  const encounters_per_day = fillDailySeries(epdRows, nowMs, SERIES_DAYS);

  const dpRows = await q(env,
    "SELECT COUNT(DISTINCT party_code_hash) n FROM encounter_analytics WHERE created_at >= ?",
    [sinceWin], (r) => r, []);
  const distinct_parties = Number(dpRows?.[0]?.n) || 0;

  const party_size_dist = await q(env,
    "SELECT party_size, COUNT(*) n FROM encounter_analytics WHERE created_at >= ? GROUP BY party_size",
    [sinceWin], mapPartySizeDist, []);

  const content_mix = await q(env,
    "SELECT content_type, content_tier, COUNT(*) n FROM encounter_analytics WHERE created_at >= ? GROUP BY content_type, content_tier ORDER BY n DESC",
    [sinceWin], mapContentMix, []);

  const damage_dist = await q(env,
    "SELECT boss_damage FROM encounter_analytics WHERE created_at >= ? AND boss_damage IS NOT NULL",
    [sinceWin], (r) => bucketDamage(r, 12), { buckets: [], max: 0 });

  const hit_quality = await q(env,
    "SELECT detail FROM encounter_analytics WHERE created_at >= ? AND detail IS NOT NULL",
    [sinceWin], computeHitQuality, null);

  return {
    window_days: WINDOW_DAYS,
    top_bosses, encounters_per_day, distinct_parties,
    party_size_dist, content_mix, damage_dist, hit_quality,
    time_based: null,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers/party && node --test test/dashboard_analytics.test.mjs`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard_analytics.js workers/party/test/dashboard_analytics.test.mjs
git commit -m "feat(dashboard): D1 analytics assembler with per-query isolation"
```

---

## Task 7: Wire `analytics` into `handleDashboardJson` (additive)

**Files:**
- Modify: `workers/party/src/dashboard.js` (top: add import; in `handleDashboardJson`: add the block before the response)

- [ ] **Step 1: Add the import** (top of `dashboard.js`, after the header comment)

```js
import { buildAnalyticsBlock } from "./dashboard_analytics.js";
```

- [ ] **Step 2: Build + include the block** — in `handleDashboardJson`, after `feedback` is assembled and before `const body = JSON.stringify(...)`:

```js
  // --- analytics: D1 cross-encounter aggregates (additive; null if binding/queries unavailable) ---
  let analytics = null;
  try { analytics = await buildAnalyticsBlock(env, generated_at); } catch (_) { analytics = null; }

  const body = JSON.stringify({ generated_at, live_rooms, history, feedback, analytics }, null, 2);
```

(Remove the old `const body = JSON.stringify({ generated_at, live_rooms, history, feedback }, null, 2);` line it replaces.)

- [ ] **Step 3: Syntax check**

Run: `cd workers/party && node --check src/dashboard.js && node --check src/dashboard_analytics.js`
Expected: no output (exit 0).

- [ ] **Step 4: Dry-run the worker build**

Run: `cd workers/party && wrangler deploy --dry-run`
Expected: bundles successfully, no errors.

- [ ] **Step 5: Manual JSON check (live)**

Run (PowerShell): `xh GET "https://tldps-party.kyle-526.workers.dev/dashboard.json?key=<DEBUG_KEY>" | jq '.analytics | keys'`
Expected: lists `top_bosses, encounters_per_day, distinct_parties, party_size_dist, content_mix, damage_dist, hit_quality, time_based, window_days`. Existing keys (`live_rooms`, `history`, `feedback`) still present.

- [ ] **Step 6: Commit**

```bash
git add workers/party/src/dashboard.js
git commit -m "feat(dashboard): include analytics block in /dashboard.json (additive)"
```

> ⚠️ Pushing `main` auto-deploys the worker. **Confirm no live parties first** (`node backend/tools/obs_rooms.mjs rooms`). Backward-compatible (additive only).

---

## Task 8: Inline SVG chart toolkit (client)

**Files:**
- Modify: `workers/party/src/dashboard.js` (inside the `<script>` block of `buildDashboardHtml`)

Add a small chart namespace used by all render functions. **Signatures (the contract):**

```
SVGChart.sparkline(points: number[]) -> svg string         // area line, auto-scaled
SVGChart.bars(points: {label,value}[]) -> svg string       // vertical bars + x labels
SVGChart.topN(items: {label,value}[]) -> svg string        // horizontal bars, value at end
SVGChart.histogram(buckets:{lo,hi,count}[], max) -> svg    // vertical bars, no gaps
SVGChart.donut(slices:{label,value,color}[]) -> svg        // single ring
```

Rules: pure string builders (take data, return `<svg viewBox=...>` markup using the CSS vars already in `:root`); responsive via `viewBox` + `width:100%`; numbers `esc()`-safe (numeric only); empty input → a muted "no data" `<text>`. No external libs.

- [ ] **Step 1:** Implement `SVGChart` against the signatures above, built and visually checked live (render each into a scratch tile on `http://localhost:61507` via the preview, or a temporary local `/dashboard` load). Keep each builder under ~30 lines.
- [ ] **Step 2: Syntax check** — `cd workers/party && node --check src/dashboard.js` → exit 0.
- [ ] **Step 3: Acceptance** — load `/dashboard?key=…` locally (`wrangler dev`) and confirm each chart type renders with sample data and degrades to "no data" on empty arrays.
- [ ] **Step 4: Commit**

```bash
git add workers/party/src/dashboard.js
git commit -m "feat(dashboard): zero-dep inline SVG chart toolkit"
```

---

## Task 9: Bento Overview view (Refined Dev-Dark)

**Files:**
- Modify: `workers/party/src/dashboard.js` (CSS in `<style>`; markup + a `renderOverview(data)` in `<script>`; default tab → Overview)

**Acceptance (contract):** Overview renders from one `/dashboard.json` payload:
- KPI strip: Live Now (`live_rooms.length`), Parties·7d (`analytics.distinct_parties`), Encounters·7d (sum of last 7 of `encounters_per_day`), Downloads (existing GH fetch), Peak Rooms (max `history[].active_rooms`).
- Tiles: Encounters/day (`SVGChart.sparkline`), Top Bosses (`SVGChart.topN`), Party Size (`SVGChart.bars`), Hit Quality (`analytics.hit_quality` as %), Live Rooms mini (first 3 rooms), Feedback mini (count + latest 2), and a greyed **"pending #56"** tile for Fight Duration.
- Theme accent per tile (growth=`--accent`, gameplay=`--orange`, ops=`--green`, feedback=`--accent`). Matches the approved `overview-preview.html`.
- Each tile is clickable → switches to its drill-down tab.
- Empty/missing `analytics` (null) → tiles show "no data", page does not error.

- [ ] **Step 1:** Build the Overview markup + `renderOverview(data)` + CSS; iterate live against the preview/`wrangler dev` until it matches `overview-preview.html`.
- [ ] **Step 2: Syntax check** — `node --check src/dashboard.js` → exit 0.
- [ ] **Step 3: Acceptance** — `wrangler dev`, load `/dashboard?key=…`; confirm all tiles populate from real JSON and the "pending #56" tile shows greyed.
- [ ] **Step 4: Commit**

```bash
git add workers/party/src/dashboard.js
git commit -m "feat(dashboard): bento Overview (Refined Dev-Dark)"
```

---

## Task 10: Growth + Gameplay drill-downs

**Files:**
- Modify: `workers/party/src/dashboard.js` (two panels + `renderGrowth(data)` / `renderGameplay(data)`; nav tabs)

**Acceptance (contract):**
- **Growth panel:** encounters/day full line (`sparkline` enlarged), distinct parties (window), GitHub downloads, history-based active-rooms/hour bar (reuse existing `history`), and a "pending #56" note where time-of-day would go.
- **Gameplay panel:** Top Bosses (`topN`), boss-damage histogram (`SVGChart.histogram` from `damage_dist`), party-size (`bars`), content-type/tier mix (table or `topN`), hit quality (`donut` or stat block).
- Both render purely from the existing `/dashboard.json`; no new endpoint. Switching tabs shows/hides panels (extend existing `showTab`).
- Each panel independently handles missing data (no throw).

- [ ] **Step 1:** Build both panels + render fns; wire nav tabs (Overview · Growth · Gameplay · Live Ops · Feedback — Live Ops/Feedback keep the *existing* content for now, polished in P2). Iterate live.
- [ ] **Step 2: Syntax check** — `node --check src/dashboard.js` → exit 0.
- [ ] **Step 3: Run the full unit suite** — `cd workers/party && node --test test/` → all green.
- [ ] **Step 4: Acceptance** — `wrangler dev`; click through all tabs; verify Growth + Gameplay charts populate, Live Ops + Feedback still work.
- [ ] **Step 5: Commit**

```bash
git add workers/party/src/dashboard.js
git commit -m "feat(dashboard): Growth + Gameplay drill-down panels"
```

---

## Task 11: Final verification + ship

- [ ] **Step 1: Unit tests** — `cd workers/party && node --test test/` → all PASS.
- [ ] **Step 2: Syntax** — `node --check src/dashboard.js src/dashboard_analytics.js` → exit 0.
- [ ] **Step 3: Build** — `wrangler deploy --dry-run` → bundles clean.
- [ ] **Step 4: Backward-compat check** — confirm `/dashboard.json` still returns `live_rooms`, `history`, `feedback` (additive only); `/rooms`, `/party/<code>/debug` unchanged.
- [ ] **Step 5: Live-deploy gate** — confirm no live parties (`node backend/tools/obs_rooms.mjs rooms`); then `git push origin main` (auto-deploys the worker). If parties are live, wait for a quiet window.
- [ ] **Step 6: Post-deploy smoke** — load `/dashboard?key=…` against the live worker; verify Overview + Growth + Gameplay render with real data; spot-check one D1 number against a manual query.
- [ ] **Step 7: Board** — move the P1 dashboard issue to Done with the commit hash; confirm #56 + the P2/P3 follow-on issues exist.

---

## Follow-on plans (out of scope for P1)

- **P2** — Live Ops drill-down (enhanced live-room x-ray, submission completeness = `submission_count` vs `party_size`) + Feedback inbox polish.
- **P3** — time-based tiles (fight duration, DPS/sec, phase splits, gap analysis). **Blocked on #56** (real fight start/end in submissions). When #56 lands, flip `time_based` from `null` to a populated block and un-grey the tiles.
