// #69: Encounters tab "Show all logs" toggle -> get_encounter_history {whole_folder:true},
// 200-row cap with "Show more", and whole-folder replies kept out of Run Builder / target list.
const { test, expect } = require('@playwright/test');
const { openApp } = require('./harness');

// Answer every get_encounter_history the app has sent but we have not yet replied to, the way
// the real backend does (one reply per request, echoing whole_folder).
async function serveHistory(page, { active, folder }) {
  await page.evaluate(([a, f]) => {
    const m = window.__mock;
    m.__served = m.__served || 0;
    const reqs = m.sentBackend().filter(c => c.command === 'get_encounter_history');
    for (; m.__served < reqs.length; m.__served++) {
      const req = reqs[m.__served];
      m.pushBackend({ type: 'encounter_history', whole_folder: !!req.whole_folder, encounters: req.whole_folder ? f : a });
    }
  }, [active, folder]);
}
const historyRequests = page => page.evaluate(
  () => window.__mock.sentBackend().filter(c => c.command === 'get_encounter_history'));
const enc = (name, i) => ({
  target_name: name, category: 'archboss', start_time: new Date(2026, 0, 1, 0, 0, i).toISOString(),
  duration: 60, total_damage: 1000000 + i, gap_before: 0,
});
const openEncountersTab = async page => {
  await page.locator('[data-tab="encounters"]').first().click();
  await expect(page.locator('#showAllLogsToggle')).toBeVisible();
};
const many = (prefix, n) => Array.from({ length: n }, (_, i) => enc(`${prefix}${i}`, i));

test('toggle is off by default and sends / drops the whole_folder flag', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  const toggle = page.locator('#showAllLogsToggle');
  await expect(toggle).toHaveCount(1);
  await expect(toggle).not.toBeChecked();

  await page.evaluate(() => window.__mock.clearSent());
  await toggle.check();
  await expect.poll(async () => (await historyRequests(page)).length).toBe(1);
  expect((await historyRequests(page))[0]).toEqual({ command: 'get_encounter_history', whole_folder: true });

  await page.evaluate(() => window.__mock.clearSent());
  await toggle.uncheck();
  await expect.poll(async () => (await historyRequests(page)).length).toBe(1);
  const off = (await historyRequests(page))[0];
  expect(off).toEqual({ command: 'get_encounter_history' });
  expect('whole_folder' in off).toBe(false);
});

test('a reply over 200 renders 200 rows plus Show more, which reveals the next 200', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  await page.locator('#showAllLogsToggle').check();
  await serveHistory(page, { active: [], folder: many('Hist', 450) });

  const rows = page.locator('#encountersSessionList .encounters-session-item');
  await expect(rows).toHaveCount(200);
  const more = page.locator('#encountersSessionList .encounters-show-more');
  await expect(more).toHaveCount(1);
  await expect(more).toContainText('Show more');

  await more.click();
  await expect(rows).toHaveCount(400);
  await more.click();
  await expect(rows).toHaveCount(450);
  await expect(more).toHaveCount(0);
});

test('a reply of 200 or fewer has no Show more control', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  await page.locator('#showAllLogsToggle').check();
  await serveHistory(page, { active: [], folder: many('Hist', 200) });
  await expect(page.locator('#encountersSessionList .encounters-session-item')).toHaveCount(200);
  await expect(page.locator('#encountersSessionList .encounters-show-more')).toHaveCount(0);
});

test('whole-folder reply does not populate Run Builder timeline or target list; normal reply does', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  // Negative control: an ordinary (unflagged) reply populates both consumers.
  await serveHistory(page, { active: [enc('ActiveBoss', 1)], folder: [] });
  await expect.poll(() => page.evaluate(() => timelineEncounters.length)).toBe(1);
  expect(await page.evaluate(() => allKnownTargets.has('ActiveBoss'))).toBe(true);

  await page.locator('#showAllLogsToggle').check();
  await serveHistory(page, { active: [], folder: many('Hist', 5) });
  await expect(page.locator('#encountersSessionList .encounters-session-item')).toHaveCount(5);

  expect(await page.evaluate(() => timelineEncounters.map(e => e.target_name))).toEqual(['ActiveBoss']);
  expect(await page.evaluate(() => allKnownTargets.has('Hist0'))).toBe(false);
  expect(await page.evaluate(() => encounterHistory.length)).toBe(1);
});

test('a failed whole-folder request does not misroute the next normal reply', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  await serveHistory(page, { active: [], folder: [] });            // drain the opening requests
  await page.locator('#showAllLogsToggle').check();
  // The backend answers a failed handler with an error frame instead of encounter_history.
  await page.evaluate(() => { window.__mock.__served++; window.__mock.pushBackend({ type: 'error', message: 'parse failed' }); });
  await page.getByRole('button', { name: 'OK', exact: true }).click();                    // the app surfaces the error as an alert
  await page.locator('#showAllLogsToggle').uncheck();
  await serveHistory(page, { active: [enc('ActiveBoss', 1)], folder: many('Hist', 3) });
  await expect.poll(() => page.evaluate(() => timelineEncounters.map(e => e.target_name))).toEqual(['ActiveBoss']);
  await expect(page.locator('#encountersSessionList .encounters-session-item')).toHaveCount(1);
});

test('Encounters Refresh still clears the Run Builder selection', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  await page.evaluate(() => selectedTimelineIndices.add(0));
  await page.locator('.encounters-list-header button', { hasText: 'Refresh' }).click();
  expect(await page.evaluate(() => selectedTimelineIndices.size)).toBe(0);
});

test('re-opening the Encounters tab with the toggle on does not re-parse the whole folder', async ({ page }) => {
  await openApp(page);
  await openEncountersTab(page);
  await page.locator('#showAllLogsToggle').check();
  await serveHistory(page, { active: [], folder: many('Hist', 5) });
  await expect(page.locator('#encountersSessionList .encounters-session-item')).toHaveCount(5);

  await page.evaluate(() => { window.__mock.clearSent(); window.__mock.__served = 0; });
  await page.locator('[data-tab="dashboard"]').first().click();
  await page.locator('[data-tab="encounters"]').first().click();
  await expect.poll(async () => (await historyRequests(page)).length).toBeGreaterThan(0);
  expect((await historyRequests(page)).every(r => !('whole_folder' in r))).toBe(true);
  await serveHistory(page, { active: [enc('ActiveBoss', 1)], folder: many('Hist', 5) });
  await expect(page.locator('#encountersSessionList .encounters-session-item')).toHaveCount(5);  // list keeps the folder view
});
