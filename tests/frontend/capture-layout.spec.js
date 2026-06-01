// Capture pass for the party-first layout change (UI lane):
//   - new top tab row: Dashboard | Party DPS | Encounters | Solo Lab ▾
//   - Solo Lab dropdown open
//   - Party DPS view with the app sidebar auto-collapsed (reclaimed board width)
// Run: npx playwright test capture-layout.spec.js
const { test, expect } = require('@playwright/test');
const { openApp } = require('./harness');
const path = require('path');
const SHOTS = path.join(__dirname, 'shots');
const EID = '1780270000000';

function welcomeFrame() {
  const e = (uid, name, rank, contrib, dmg, dps, crit, heavy, ch) =>
    ({ user_id: uid, username: name, rank, contribution: contrib, total_damage: dmg, dps,
       crit_rate: crit, heavy_rate: heavy, crit_heavy_rate: ch, has_detail: true });
  return {
    type: 'welcome', you: { is_leader: true, user_id: 'user_test_1' }, active_encounter_id: EID,
    roster: [
      { user_id: 'user_test_1', username: 'TestUser', is_leader: true, online: true, has_posted: true, joined_age_s: 200 },
      { user_id: 'bot_2', username: 'Vareth', is_leader: false, online: true, has_posted: true, joined_age_s: 140 },
      { user_id: 'bot_3', username: 'Synapse', is_leader: false, online: true, has_posted: true, joined_age_s: 90 },
    ],
    scoreboard: { encounter_id: EID, boss: 'Tevent', boss_category: 'archboss', total_damage: 1000000,
      entries: [
        e('user_test_1','TestUser',1,45,450000,7500,42,38,19.5),
        e('bot_2','Vareth',2,33,330000,5500,35,30,14),
        e('bot_3','Synapse',3,22,220000,3666,28,22,9),
      ] },
    encounters: [{ encounter_id: EID, boss: 'Tevent', boss_category: 'archboss', total_damage: 1000000, entries_n: 3 }],
  };
}

test('layout: tab row, Solo Lab dropdown, party-view collapsed sidebar', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  await openApp(page);

  // (1) the new top tab row (lands on Dashboard by default)
  const tabs = page.locator('.tabs').first();
  await tabs.screenshot({ path: path.join(SHOTS, 'layout-tabs.png') });
  const order = await page.evaluate(() =>
    [...document.querySelectorAll('.tabs > .tab, .tabs button.tab')].slice(0, 4).map(b => b.textContent.trim()));
  console.log('[tab order, first 4]:', JSON.stringify(order));

  // (2) Solo Lab dropdown open
  await page.evaluate(() => { const t = document.getElementById('soloLabToggle'); if (t) t.click(); });
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(SHOTS, 'layout-solo-open.png'), clip: { x: 0, y: 0, width: 1280, height: 420 } });
  const dropdownOpen = await page.evaluate(() => {
    const d = document.getElementById('soloLabDropdown'); return !!(d && d.classList.contains('open'));
  });
  console.log('[solo lab dropdown open]:', dropdownOpen);

  // sidebar state BEFORE party (on Dashboard)
  const collapsedOnDash = await page.evaluate(() => document.querySelector('.sidebar')?.classList.contains('collapsed'));
  console.log('[sidebar collapsed on Dashboard]:', collapsedOnDash);

  // (3) go to Party DPS -> land in a joined party -> sidebar should auto-collapse
  await page.evaluate(() => {
    const b = document.querySelector('[data-tab="partyDps"]'); if (b) b.click();
  });
  await page.evaluate(() => {
    partyState.user_id = 'user_test_1'; partyState.username = 'TestUser';
    partyState.party_code = 'TEST'; partyState.connected = true; connectPartyWS('TEST', true);
  });
  await page.waitForFunction(() => window.__mock.counts().worker > 0, null, { timeout: 10_000 });
  await page.evaluate((f) => window.__mock.pushWorker(f), welcomeFrame());
  await page.waitForTimeout(400);
  const collapsedOnParty = await page.evaluate(() => document.querySelector('.sidebar')?.classList.contains('collapsed'));
  console.log('[sidebar collapsed on Party DPS]:', collapsedOnParty);
  await page.screenshot({ path: path.join(SHOTS, 'layout-party-collapsed.png'), fullPage: false });

  // (3b) party panel narrowed (was 260 -> 210)
  const partyPanelW = await page.evaluate(() => {
    const el = document.querySelector('.party-sidebar'); return el ? Math.round(el.getBoundingClientRect().width) : null;
  });
  console.log('[party-sidebar width]:', partyPanelW);

  // (3c) hover the collapsed app sidebar -> flies open (width back to ~280, content visible)
  await page.locator('.sidebar').hover();
  await page.waitForTimeout(450);
  const hoverW = await page.evaluate(() => Math.round(document.querySelector('.sidebar').getBoundingClientRect().width));
  const hoverContentVisible = await page.evaluate(() => {
    const c = document.querySelector('.sidebar .sidebar-content'); return c ? getComputedStyle(c).display !== 'none' : null;
  });
  console.log('[app sidebar width on hover]:', hoverW, '| content visible:', hoverContentVisible);
  await page.screenshot({ path: path.join(SHOTS, 'layout-party-hover.png'), fullPage: false });

  // (4) back to Dashboard -> sidebar restores
  await page.evaluate(() => { const b = document.querySelector('[data-tab="dashboard"]'); if (b) b.click(); });
  await page.waitForTimeout(250);
  const collapsedBack = await page.evaluate(() => document.querySelector('.sidebar')?.classList.contains('collapsed'));
  console.log('[sidebar collapsed after back-to-Dashboard]:', collapsedBack);

  expect(order[1]).toContain('Party DPS');
  expect(dropdownOpen).toBe(true);
  expect(collapsedOnParty).toBe(true);
  expect(collapsedBack).toBe(false);
  expect(partyPanelW).toBeLessThanOrEqual(215);          // narrowed 260 -> 210
  expect(hoverW).toBeGreaterThan(200);                   // collapsed sidebar flew open on hover
  expect(hoverContentVisible).toBe(true);                // ...and its content re-showed
});
