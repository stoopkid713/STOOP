#!/usr/bin/env node
// analytics.mjs — query the cross-room encounter analytics D1 (stoop-analytics).
//
// Answers questions like "what's the real gap distribution between phase transitions?"
// and "how often is party data incomplete?" using fight data collected from real sessions.
// Intended to calibrate encounter-segmentation thresholds and validate combine logic.
//
// Uses `wrangler d1 execute --remote` — needs `wrangler login` once.
// Run from repo root or from backend/tools/.
//
// Usage:
//   node backend/tools/analytics.mjs gaps        # gap_before_s for phase transitions
//   node backend/tools/analytics.mjs bosses      # boss frequency + avg duration
//   node backend/tools/analytics.mjs capture     # submission_count vs party_size
//   node backend/tools/analytics.mjs recent [N]  # last N rows (default 20)
//   node backend/tools/analytics.mjs raw <sql>   # run a custom SQL query
//   node backend/tools/analytics.mjs count       # total rows in the table

import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DB   = "stoop-analytics";
const here = dirname(fileURLToPath(import.meta.url));
// wrangler must run where wrangler.toml lives (workers/party/) so it can resolve the project
// + the ANALYTICS_DB binding. (here = backend/tools -> ../../workers/party.)
const workerDir = join(here, "../../workers/party");

// ── helpers ──────────────────────────────────────────────────────────────────

function wranglerD1(sql) {
  try {
    // ROOT-CAUSE FIX: flatten to a SINGLE LINE. Multi-line SQL (template-literal newlines)
    // embedded in the Windows cmd.exe command string breaks the spawn and throws a
    // UV_HANDLE_CLOSING libuv crash (src\win\async.c). count/raw used single-line SQL so they
    // survived; every multi-line command crashed. SQL is whitespace-insensitive, so collapsing
    // whitespace runs to single spaces is semantically identical and fixes every command here.
    const flatSql = sql.replace(/\s+/g, " ").trim();
    const out = execSync(
      `npx wrangler d1 execute ${DB} --remote --json --command "${flatSql.replace(/"/g, '\\"')}"`,
      // windowsHide avoids a flashed console; 16MB buffer headroom for large --json result sets.
      { cwd: workerDir, stdio: ["ignore", "pipe", "pipe"], windowsHide: true, maxBuffer: 16 * 1024 * 1024 }
    ).toString();
    const parsed = JSON.parse(out);
    // wrangler d1 --json returns an array of result objects; first one has the rows
    if (Array.isArray(parsed) && parsed[0]?.results) return parsed[0].results;
    if (Array.isArray(parsed) && parsed[0]?.success === false) {
      throw new Error(parsed[0].error || "D1 query failed");
    }
    return [];
  } catch (err) {
    const msg = err.stderr?.toString() || err.message || String(err);
    console.error("Query error:", msg.trim());
    process.exit(1);
  }
}

function fmt(n, unit = "") {
  if (n == null) return "—";
  if (unit === "M" && n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (unit === "M" && n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  if (unit === "s") return `${n}s`;
  return String(n);
}

function table(rows, cols) {
  if (!rows.length) { console.log("  (no rows)"); return; }
  const widths = cols.map((c) => Math.max(c.label.length,
    ...rows.map((r) => String(r[c.key] ?? "—").length)));
  const header = cols.map((c, i) => c.label.padEnd(widths[i])).join("  ");
  const sep    = widths.map((w) => "─".repeat(w)).join("  ");
  console.log(header);
  console.log(sep);
  for (const row of rows) {
    console.log(cols.map((c, i) => String(row[c.key] ?? "—").padEnd(widths[i])).join("  "));
  }
  console.log(`\n  ${rows.length} row${rows.length !== 1 ? "s" : ""}`);
}

// ── commands ─────────────────────────────────────────────────────────────────

function cmdGaps() {
  console.log("\n── Phase-transition gap distribution ──");
  console.log("   (consecutive_same_boss=1, full capture only)\n");

  const rows = wranglerD1(`
    SELECT
      gap_before_s,
      COUNT(*) AS occurrences
    FROM encounter_analytics
    WHERE consecutive_same_boss = 1
      AND submission_count = party_size
      AND gap_before_s IS NOT NULL
    GROUP BY gap_before_s
    ORDER BY gap_before_s
  `);
  table(rows, [
    { key: "gap_before_s", label: "gap_s" },
    { key: "occurrences",  label: "count" },
  ]);

  if (rows.length) {
    const vals = rows.flatMap((r) => Array(r.occurrences).fill(r.gap_before_s));
    vals.sort((a, b) => a - b);
    const median = vals[Math.floor(vals.length / 2)];
    const p90    = vals[Math.floor(vals.length * 0.9)];
    const max    = vals[vals.length - 1];
    console.log(`\n  median=${median}s  p90=${p90}s  max=${max}s`);
    console.log(`  Current threshold: 30s (non-boss) / 45s (boss)`);
  }

  const kinds = wranglerD1(`
    SELECT segment_kind, COUNT(*) AS n
    FROM encounter_analytics
    WHERE segment_kind IS NOT NULL
    GROUP BY segment_kind ORDER BY n DESC
  `);
  console.log("\n  Segment kinds:");
  table(kinds, [
    { key: "segment_kind", label: "kind" },
    { key: "n",            label: "count" },
  ]);
}

function cmdBosses() {
  console.log("\n── Boss frequency (full capture, >0 duration) ──\n");
  const rows = wranglerD1(`
    SELECT
      boss_name,
      COUNT(*)            AS kills,
      ROUND(AVG(duration_s)) AS avg_dur_s,
      ROUND(AVG(boss_damage / 1000000.0), 2) AS avg_dmg_M,
      ROUND(AVG(submission_count * 1.0 / party_size), 2) AS avg_capture
    FROM encounter_analytics
    WHERE boss_name IS NOT NULL
      AND submission_count = party_size
    GROUP BY boss_name
    ORDER BY kills DESC
    LIMIT 30
  `);
  table(rows, [
    { key: "boss_name",    label: "Boss" },
    { key: "kills",        label: "Kills" },
    { key: "avg_dur_s",    label: "Avg dur(s)" },
    { key: "avg_dmg_M",    label: "Avg dmg(M)" },
    { key: "avg_capture",  label: "Capture rate" },
  ]);
}

function cmdAccuracy() {
  console.log("\n── Hit-quality (crit/heavy) across boss fights ──");
  console.log("   (from detail.quality; rows pre-migration show no quality)\n");
  const rows = wranglerD1(`
    SELECT
      boss_name,
      COUNT(*) AS fights,
      ROUND(AVG(json_extract(detail, '$.quality.crit_rate')) * 100, 1)       AS crit_pct,
      ROUND(AVG(json_extract(detail, '$.quality.heavy_rate')) * 100, 1)      AS heavy_pct,
      ROUND(AVG(json_extract(detail, '$.quality.crit_heavy_rate')) * 100, 1) AS crit_heavy_pct
    FROM encounter_analytics
    WHERE boss_name IS NOT NULL
      AND json_extract(detail, '$.quality.hits') IS NOT NULL
    GROUP BY boss_name
    ORDER BY fights DESC
    LIMIT 30
  `);
  table(rows, [
    { key: "boss_name",      label: "Boss" },
    { key: "fights",         label: "Fights" },
    { key: "crit_pct",       label: "Crit%" },
    { key: "heavy_pct",      label: "Heavy%" },
    { key: "crit_heavy_pct", label: "Crit+Heavy%" },
  ]);
}

function cmdPhase() {
  console.log("\n── Phase grouping (is_phase = continues prior boss) ──\n");
  const rows = wranglerD1(`
    SELECT
      boss_name,
      SUM(CASE WHEN is_phase = 1 THEN 1 ELSE 0 END) AS phase_rows,
      COUNT(*)                                      AS total_rows,
      ROUND(AVG(boss_damage / 1000000.0), 2)        AS avg_boss_M,
      ROUND(AVG(trash_damage / 1000000.0), 2)       AS avg_trash_M
    FROM encounter_analytics
    WHERE boss_name IS NOT NULL
    GROUP BY boss_name
    ORDER BY total_rows DESC
    LIMIT 30
  `);
  table(rows, [
    { key: "boss_name",   label: "Boss" },
    { key: "phase_rows",  label: "Phase rows" },
    { key: "total_rows",  label: "Total rows" },
    { key: "avg_boss_M",  label: "Avg boss(M)" },
    { key: "avg_trash_M", label: "Avg trash(M)" },
  ]);
}

function cmdCapture() {
  console.log("\n── Partial capture analysis ──");
  console.log("   (how often is party data incomplete?)\n");

  const rows = wranglerD1(`
    SELECT
      submission_count,
      party_size,
      COUNT(*) AS fights,
      ROUND(submission_count * 100.0 / party_size, 0) AS pct
    FROM encounter_analytics
    WHERE boss_name IS NOT NULL
    GROUP BY submission_count, party_size
    ORDER BY party_size, submission_count
  `);
  table(rows, [
    { key: "submission_count", label: "submitted" },
    { key: "party_size",       label: "party_size" },
    { key: "pct",              label: "%" },
    { key: "fights",           label: "fights" },
  ]);

  const total = wranglerD1(
    "SELECT COUNT(*) AS n FROM encounter_analytics WHERE boss_name IS NOT NULL"
  );
  const full = wranglerD1(
    "SELECT COUNT(*) AS n FROM encounter_analytics WHERE boss_name IS NOT NULL AND submission_count = party_size"
  );
  if (total[0] && full[0]) {
    const pct = total[0].n ? ((full[0].n / total[0].n) * 100).toFixed(1) : "0";
    console.log(`\n  Full capture: ${full[0].n} / ${total[0].n} boss fights (${pct}%)`);
  }
}

function cmdRecent(n = 20) {
  console.log(`\n── Last ${n} encounters ──\n`);
  const rows = wranglerD1(`
    SELECT
      encounter_id,
      boss_name,
      duration_s,
      gap_before_s,
      total_damage,
      submission_count,
      party_size,
      consecutive_same_boss AS phase,
      datetime(created_at / 1000, 'unixepoch') AS ts
    FROM encounter_analytics
    ORDER BY created_at DESC
    LIMIT ${Number(n)}
  `);
  table(rows, [
    { key: "ts",                   label: "Time(UTC)" },
    { key: "boss_name",            label: "Boss" },
    { key: "duration_s",           label: "dur_s" },
    { key: "gap_before_s",         label: "gap_s" },
    { key: "total_damage",         label: "damage" },
    { key: "submission_count",     label: "subs" },
    { key: "party_size",           label: "sz" },
    { key: "phase",                label: "phase?" },
  ]);
}

function cmdCount() {
  const rows = wranglerD1("SELECT COUNT(*) AS total FROM encounter_analytics");
  const withBoss = wranglerD1("SELECT COUNT(*) AS n FROM encounter_analytics WHERE boss_name IS NOT NULL");
  console.log(`\n  Total rows: ${rows[0]?.total ?? 0}`);
  console.log(`  With boss:  ${withBoss[0]?.n ?? 0}`);
}

function cmdRaw(sql) {
  if (!sql) { console.error("Usage: analytics.mjs raw <sql>"); process.exit(1); }
  const rows = wranglerD1(sql);
  console.log(JSON.stringify(rows, null, 2));
}

// ── dispatch ─────────────────────────────────────────────────────────────────

const [,, cmd, ...rest] = process.argv;

switch (cmd) {
  case "gaps":     cmdGaps();              break;
  case "bosses":   cmdBosses();            break;
  case "accuracy": cmdAccuracy();          break;
  case "phase":    cmdPhase();             break;
  case "capture":  cmdCapture();           break;
  case "recent":   cmdRecent(rest[0]);     break;
  case "count":    cmdCount();             break;
  case "raw":      cmdRaw(rest.join(" ")); break;
  default:
    console.log(`
analytics.mjs — encounter analytics for stoop-analytics D1

Commands:
  gaps            gap_before_s distribution + segment_kind counts
  bosses          boss frequency, avg duration, avg boss damage
  accuracy        crit/heavy quality distribution per boss (from detail.quality)
  phase           is_phase grouping + boss/trash damage averages
  capture         partial-capture rate (submission_count vs party_size)
  recent [N]      last N rows (default 20)
  count           total row count
  raw <sql>       run a custom SQL query (JSON output)

Requires: wrangler login  (resolves CF auth automatically)
`);
}
