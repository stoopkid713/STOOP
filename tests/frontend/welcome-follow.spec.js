// welcome-follow.spec.js — issue #19: the `welcome` frame must advance viewing_encounter_id
// when the user was following the active encounter (null, or on the previous active), and
// must NOT move a user who pinned an older encounter. Same rule the `encounters` handler uses.
//
// HARNESS NOTE: the harness loads the INLINED index.html, which only picks up src/js edits after
// a re-inline (ADR-003; never hand-edit index.html). To exercise the SOURCE handler, this spec
// extracts `handlePartyRoomMessage` from src/js/party.js and installs it over the inlined one
// in the page, then drives it with real `welcome` frames through the mocked worker socket.
const { test, expect } = require('@playwright/test');
const { openApp } = require('./harness');
const path = require('path');
const fs = require('fs');

const SRC = fs.readFileSync(path.resolve(__dirname, '..', '..', 'src', 'js', 'party.js'), 'utf8');

function extractFn(src, header) {
  const start = src.indexOf(header);
  if (start < 0) throw new Error('not found in src/js/party.js: ' + header);
  let i = src.indexOf('{', start), depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}' && --depth === 0) return src.slice(start, i + 1);
  }
  throw new Error('unbalanced braces for ' + header);
}
const HANDLER_SRC = extractFn(SRC, 'async function handlePartyRoomMessage(m)');

const MY_UID = 'user_test_1';
const OLD = '1780270000000', NEW = '1780270999999';

function welcome(activeId, encIds) {
  return {
    type: 'welcome',
    you: { is_leader: false, user_id: MY_UID, username: 'TestUser' },
    active_encounter_id: activeId,
    roster: [{ user_id: MY_UID, username: 'TestUser', is_leader: false, online: true, has_posted: true, joined_age_s: 5 }],
    scoreboard: { encounter_id: activeId, boss: 'Tevent', boss_category: 'archboss', total_damage: 1, entries: [] },
    encounters: encIds.map(id => ({ encounter_id: id, boss: 'Tevent', boss_category: 'archboss', total_damage: 1, entries_n: 1 })),
  };
}

async function inParty(page) {
  await openApp(page);
  await page.evaluate((src) => {
    window.handlePartyRoomMessage = (0, eval)('(' + src + ')'); // install SOURCE handler
    partyState.user_id = 'user_test_1'; partyState.username = 'TestUser';
    partyState.party_code = 'TEST'; partyState.connected = true;
    connectPartyWS('TEST', true);
  }, HANDLER_SRC);
  await page.waitForFunction(() => window.__mock.counts().worker > 0, null, { timeout: 10_000 });
}
const push = (page, f) => page.evaluate(x => window.__mock.pushWorker(x), f);
const viewing = page => page.evaluate(() => partyState.viewing_encounter_id);

test('first welcome (nothing viewed yet) follows the active encounter', async ({ page }) => {
  await inParty(page);
  await push(page, welcome(OLD, [OLD]));
  await page.waitForTimeout(100);
  expect(await viewing(page)).toBe(OLD);
});

test('following active, then welcome with a newer active: view advances (#19)', async ({ page }) => {
  await inParty(page);
  await push(page, welcome(OLD, [OLD]));
  await page.waitForTimeout(100);
  expect(await viewing(page)).toBe(OLD);
  await push(page, welcome(NEW, [OLD, NEW])); // reconnect while a newer encounter is live
  await page.waitForTimeout(100);
  expect(await viewing(page)).toBe(NEW);
});

test('pinned to an older encounter stays pinned across welcome (negative control)', async ({ page }) => {
  await inParty(page);
  await push(page, welcome(NEW, [OLD, NEW]));
  await page.waitForTimeout(100);
  await page.evaluate(id => { partyState.viewing_encounter_id = id; }, OLD); // user pins the old one
  await push(page, welcome(NEW, [OLD, NEW]));
  await page.waitForTimeout(100);
  expect(await viewing(page)).toBe(OLD);
});
