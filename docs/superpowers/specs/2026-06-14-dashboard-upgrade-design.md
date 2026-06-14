# STOOP Party Dashboard Upgrade — Design Spec

**Date:** 2026-06-14
**Status:** Approved (brainstorm) → ready for implementation plan
**Scope:** `workers/party/src/dashboard.js` (+ a read-only aggregation addition in `workers/party/src/index.js`)
**Audience:** admin-only (DEBUG_KEY-gated). Not public-facing.

## Problem

The party worker's `/dashboard?key=…` page (DEBUG_KEY-gated) shows only three tabs —
Adoption, Live Rooms, Feedback — fed by `ROOMS_KV` (live rooms + hourly history snapshots),
`FEEDBACK_KV`, and a client-side GitHub releases fetch. Meanwhile a whole **D1
`encounter_analytics`** dataset (one row per completed fight, across every party) is being
collected and **never surfaced**. The dashboard also looks like a bare dev page. We want both:
**richer analytics and a redesigned UI**, in one cohesive upgrade.

## Goals

- Surface the untapped `encounter_analytics` (D1) data.
- Cover four insight themes: **Product Growth · Gameplay Meta · Live Ops & Health · Feedback.**
- Redesign the UI: **bento Overview + drill-down**, **Refined Dev-Dark** style.
- Stay **self-contained** (no CDN / no chart libraries) and **admin-only** (DEBUG_KEY unchanged).
- Remain **backward-compatible** (additive JSON; old behavior intact; no deploy while parties live).

## Non-goals

- Public / community-facing stats or leaderboards (separate future effort).
- Changing the auth model (DEBUG_KEY gate stays exactly as-is: 404 unset / 403 wrong / 200 ok).
- Fixing the time-based data quality bug — that is **issue #56**, a *separate prerequisite track*
  (see Dependencies). The dashboard is built to degrade gracefully without it.

## Decisions (from brainstorm)

| Decision | Choice |
|---|---|
| Upgrade goal | Both data + looks |
| Themes | All four (Growth · Gameplay · Live Ops · Feedback) |
| Layout / IA | **C — Bento overview + drill-down** |
| Visual style | **A — Refined Dev-Dark** (evolve the GitHub-dark + monospace look) |
| #56 (time-based data fix) | **Separate prerequisite track**, not folded into this spec |
| Chart rendering | **Zero-dep inline SVG helpers** (no external lib) |
| Aggregation | On-the-fly D1 `GROUP BY` per request, optional ~60s cache |

## Dependencies

- **Issue #56** (worker: submissions lack real fight start/end → `duration_s`, `gap_*`,
  `is_phase`/phase detection unreliable). Time-based dashboard tiles (fight duration, DPS/sec,
  phase splits, gap analysis) render a **"pending #56"** placeholder until #56 lands. Track 1
  (this dashboard) is buildable today on the reliable fields; it does **not** block on #56.

## Architecture

### Backend — `handleDashboardJson` (extend)

Add an `analytics` block sourced from `env.ANALYTICS_DB` (D1) alongside the existing
`live_rooms` / `history` / `feedback`. Response shape becomes:

```
{ generated_at, live_rooms[], history[], feedback[], analytics{…} }
```

- Each aggregate query is **independently try/caught** — a failing query yields an empty
  sub-block, never a broken response (mirrors the existing KV-block pattern).
- If `env.ANALYTICS_DB` is absent, `analytics` is `null` and the page hides analytics tiles.
- **Optional cache:** memoize the `analytics` block for ~60s (in-DO memory or a short KV key) so
  the page's 30s poll does not re-run the D1 aggregation every time. Acceptable staleness for an
  admin view; start without it and add only if D1 cost/latency warrants.
- Indexes already exist: `idx_analytics_boss`, `idx_analytics_party`, `idx_analytics_created`.

### `analytics` sub-blocks (D1 `GROUP BY` over `encounter_analytics`)

Reliable now:
- `top_bosses` — `boss_name`, count, sum(boss_damage); `GROUP BY boss_name ORDER BY count DESC LIMIT N`, windowed by `created_at`.
- `encounters_per_day` — bucket `created_at` by day (last 30d).
- `distinct_parties` — `COUNT(DISTINCT party_code_hash)` over a window (e.g. 7d).
- `party_size_dist` — `GROUP BY party_size`.
- `content_mix` — `GROUP BY content_type, content_tier`.
- `damage_dist` — total/boss/trash damage buckets (histogram).
- `hit_quality` — crit/heavy/crit+heavy rates (hits-weighted; from the `detail` JSON / quality fields).

Gated on #56 (return `null` / flagged until reliable):
- `duration_dist`, `dps_per_sec`, `phase_splits`, `gap_analysis`.

### Frontend — `buildDashboardHtml` (rewrite)

- **Information architecture (Layout C):**
  - **Overview** landing — KPI strip (Live Now · Parties 7d · Encounters 7d · Downloads · Peak
    Rooms) + a bento grid of tiles spanning all four themes; each tile links to its drill-down.
  - **Drill-downs** (in-page views/tabs): **Growth · Gameplay · Live Ops · Feedback.**
- **Style: Refined Dev-Dark** — keep the GitHub-dark palette + monospace, polished: rounded
  cards, consistent spacing, clear hierarchy, theme accent colors (growth=blue, gameplay=orange,
  ops=green, feedback=accent). The reference CSS variables already in `dashboard.js` are the base.
- **Charts: zero-dep inline SVG toolkit** — small helper set: `lineChart`/`sparkline`,
  `barChart`, `topNBars` (horizontal), `histogram`, `donut`. Responsive (viewBox), hoverable
  tooltips. Replaces the single hand-rolled Canvas chart. **No external libraries, no CDN.**
- **Time-based tiles** show a greyed **"pending #56"** state until that data is trustworthy.
- The key is still read from the page URL at runtime and reused for `/dashboard.json` (unchanged).

## Security

Unchanged. `checkKey` gate (404 unset / 403 wrong / 200 ok). Admin-only. GitHub download count
stays a client-side fetch of the public releases API. No new data exposure; party codes remain
hashed in D1; no user IDs stored.

## Error handling / graceful degradation

- Per-block isolation server-side; per-tile isolation client-side (a tile with no data shows an
  empty/placeholder state, never throws).
- `Cache-Control: no-store` retained on both routes.
- Additive JSON — older clients (none, since the page is server-paired) and the `/rooms`,
  `/dashboard.json` consumers keep working; nothing removed or renamed.

## Testing

- **Worker unit tests:** seed fixture rows into a test D1 (or stub) and assert the shape/values
  of each `analytics` sub-block. **Host-independent** (ADR-009) — never depend on the game.
- **JS:** `node --check workers/party/src/dashboard.js` (and `index.js`).
- **Manual:** load `/dashboard?key=…` against the live worker; verify each Overview tile and each
  drill-down renders; confirm `/dashboard.json` is additive (existing keys intact).
- **Live-service discipline:** worker auto-deploys on push to `workers/party/*`; **do not deploy
  while parties are live** (ADR-004/007). Confirm quiet first.

## Phasing

- **P1:** backend `analytics` block (reliable queries) + Overview bento + Growth & Gameplay
  drill-downs + SVG chart toolkit.
- **P2:** Live Ops drill-down (enhanced live-room x-ray, submission completeness) + Feedback
  polish.
- **P3 (after #56):** time-based tiles — fight duration, DPS/sec, phase splits, gap analysis.

## Open questions

- Cache the `analytics` block from day one, or ship uncached and add only if D1 latency/cost
  shows up? (Default: ship uncached, measure.)
- Exact window defaults (7d vs 30d) per tile — finalize during implementation against real row
  volume.
