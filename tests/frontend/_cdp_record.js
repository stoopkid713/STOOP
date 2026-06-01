// Attach Playwright to the LIVE pywebview/WebView2 app over CDP and record the
// session for review-together. The app must be launched with a debug port:
//   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222
//
// CRASH-RESILIENT (fixed 2026-05-31): Playwright's tracing.stop() needs the browser
// ALIVE to fetch the trace — so if the app closes/crashes FIRST, a single stop-at-the-end
// loses everything ("Target page ... has been closed"). Instead we flush rolling CHUNKS
// every FLUSH_MS while connected; each chunk is a self-contained viewable trace. On
// app-close we keep everything up to the last flush (lose <= FLUSH_MS seconds).
//
// Usage:  node _cdp_record.js [seconds]   (seconds => stop after N s; no arg => until app-close/Ctrl+C)
// Output: test-results/human-run-<ts>/part###.zip  +  console.log
// Review: npx playwright show-trace test-results/human-run-<ts>/part*.zip   (opens all parts as one timeline)
const fs = require('fs');
const { chromium } = require('@playwright/test');
const PORT = process.env.CDP_PORT || '9222';
const secs = process.argv[2] ? Number(process.argv[2]) : null;
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const outDir = `test-results/human-run-${stamp}`;
const consolePath = `${outDir}/console.log`;
const FLUSH_MS = 10000; // how often to persist a trace chunk (crash window)

async function connectWithRetry(ms = 30000) {
  const deadline = Date.now() + ms;
  for (;;) {
    try { return await chromium.connectOverCDP(`http://localhost:${PORT}`); }
    catch (e) {
      if (Date.now() > deadline) throw e;
      await new Promise(r => setTimeout(r, 1000)); // waiting for the app window
    }
  }
}

(async () => {
  console.log(`waiting for the app on :${PORT} ...`);
  const browser = await connectWithRetry();
  const ctx = browser.contexts()[0];
  const page = ctx.pages()[0];
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(consolePath, `# human session ${stamp}\n`);
  page.on('console', m => fs.appendFileSync(consolePath, `[${m.type()}] ${m.text()}\n`));
  page.on('pageerror', e => fs.appendFileSync(consolePath, `[pageerror] ${e.message}\n`));

  await ctx.tracing.start({ screenshots: true, snapshots: true, sources: true });
  await ctx.tracing.startChunk();
  let part = 0, flushing = false, finished = false;
  const partPath = () => `${outDir}/part${String(part).padStart(3, '0')}.zip`;
  console.log(`RECORDING -> ${outDir}/  (crash-resilient: flushing a chunk every ${FLUSH_MS / 1000}s)`);

  // Persist the current chunk to disk and open a new one. Returns false if the
  // browser is gone (app closed) — earlier chunks are already safely on disk.
  const flush = async () => {
    if (flushing || finished) return false;
    flushing = true;
    try { await ctx.tracing.stopChunk({ path: partPath() }); part++; await ctx.tracing.startChunk(); return true; }
    catch (e) { return false; }
    finally { flushing = false; }
  };
  const timer = setInterval(flush, FLUSH_MS);

  const finish = async (reason) => {
    if (finished) return;
    finished = true;
    clearInterval(timer);
    await flush(); // best-effort final flush (succeeds only if still connected)
    const parts = fs.existsSync(outDir) ? fs.readdirSync(outDir).filter(f => f.endsWith('.zip')) : [];
    console.log(`\n[${reason}] ${parts.length} trace part(s) saved in ${outDir}/`);
    console.log(parts.length
      ? `Review (all parts as one timeline): npx playwright show-trace ${outDir}/part*.zip`
      : 'No parts captured (app died before the first 10s flush).');
    process.exit(0);
  };
  process.on('SIGINT',  () => finish('Ctrl+C'));
  process.on('SIGTERM', () => finish('SIGTERM'));
  // Save when the APP closes / CDP drops — earlier chunks survive even though this
  // final flush can't reach the dead browser.
  browser.on('disconnected', () => finish('app closed / CDP disconnected'));
  page.on('close',           () => finish('page closed'));
  if (secs) setTimeout(() => finish('timer elapsed'), secs * 1000);
  else console.log('Interact with the app; it flushes every 10s. Close the app or Ctrl+C to finalize.');
})().catch(e => { console.error('RECORD FAILED:', e.message); process.exit(1); });
