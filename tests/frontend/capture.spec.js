// Capture pass: render the fake party run in the REAL screens and save PNGs (board + drill-down).
// Run:  npx playwright test capture.spec.js
const { test } = require('@playwright/test');
const { openApp } = require('./harness');
const path = require('path');

const SHOTS = path.join(__dirname, 'shots');
const EID = '1780270000000';

function welcomeFrame() {
  const e = (uid, name, rank, contrib, dmg, dps, crit, heavy) =>
    ({ user_id: uid, username: name, rank, contribution: contrib, total_damage: dmg, dps,
       crit_rate: crit, heavy_rate: heavy, has_detail: true });
  return {
    type: 'welcome', you: { is_leader: true, user_id: 'user_test_1' },
    roster: [
      { user_id: 'user_test_1', username: 'TestUser', is_leader: true, online: true },
      { user_id: 'bot_2', username: 'Vareth', is_leader: false, online: true },
      { user_id: 'bot_3', username: 'Synapse', is_leader: false, online: true },
    ],
    active_encounter_id: EID,
    scoreboard: {
      encounter_id: EID, boss: 'Tevent', boss_category: 'archboss', total_damage: 1000000,
      entries: [
        e('user_test_1', 'TestUser', 1, 45.0, 450000, 7500, 42, 38),
        e('bot_2', 'Vareth', 2, 33.0, 330000, 5500, 35, 30),
        e('bot_3', 'Synapse', 3, 22.0, 220000, 3666, 28, 22),
      ],
    },
    encounters: [{ encounter_id: EID, boss: 'Tevent', boss_category: 'archboss', total_damage: 1000000, entries_n: 3 }],
  };
}

// A small rotation so the drill-down skill table has content.
function memberDetailFrame() {
  const rot = [];
  const skills = ['Brutal Incision', 'Slaughtering Slash', 'Camouflage Cleave'];
  for (let i = 0; i < 60; i++) {
    rot.push({ relative_time: +(i * 0.9).toFixed(2), skill: skills[i % 3],
               damage: 3000 + (i % 7) * 900, is_crit: i % 3 === 0, is_heavy: i % 4 === 0 });
  }
  return { type: 'member_detail', encounter_id: EID, user_id: 'user_test_1', skills: null, rotation: rot };
}

test('capture board + drill-down screenshots', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openApp(page);

  await page.evaluate(() => {
    partyState.user_id = 'user_test_1'; partyState.username = 'TestUser';
    partyState.party_code = 'TEST'; partyState.connected = true;
    connectPartyWS('TEST', true);
  });
  await page.waitForFunction(() => window.__mock.counts().worker > 0, null, { timeout: 10_000 });
  await page.evaluate((f) => window.__mock.pushWorker(f), welcomeFrame());

  // activate the Party tab so the board is visible
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.tab')].find(x => /party/i.test(x.textContent));
    if (b) b.click();
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(SHOTS, 'board.png') });

  // open a drill-down: click the first drillable row, then feed its detail
  const row = page.locator('#partyResultsContainer .party-result-clickable').first();
  if (await row.count()) {
    await row.click();
    await page.evaluate((f) => window.__mock.pushWorker(f), memberDetailFrame());
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SHOTS, 'drilldown.png') });
  }
});
