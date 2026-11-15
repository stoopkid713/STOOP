// Issue #18 — overlay member-detail re-request. Loads the REAL inline <script> of
// overlay/src/index.html into a vm sandbox with a stubbed DOM + WebSocket, and observes
// behaviour only at the socket seam (get_member_detail frames sent).
// Run: node --test tests/overlay/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML = fs.readFileSync(path.resolve(__dirname, '..', '..', 'overlay', 'src', 'index.html'), 'utf8');
const SCRIPT = HTML.slice(HTML.indexOf('<script>') + 8, HTML.lastIndexOf('</script>'));

function stubEl() {
  return {
    style: {}, dataset: {}, className: '', classList: { add() {}, remove() {}, toggle() {} },
    _t: '', get textContent() { return this._t; },
    set textContent(v) { this._t = String(v); this.innerHTML = this._t.replace(/&/g, '&amp;').replace(/</g, '&lt;'); },
    innerHTML: '', offsetWidth: 0, addEventListener() {}, closest() { return null; },
  };
}

function loadOverlay() {
  const sent = [];
  class FakeWS {
    constructor() { this.readyState = 1; FakeWS.last = this; }
    send(s) { sent.push(JSON.parse(s)); }
    close() {}
  }
  FakeWS.OPEN = 1;
  const els = {};
  const sandbox = {
    console: { log() {} },
    URLSearchParams, JSON, Math, Array, Object, String, Number, Date, encodeURIComponent, decodeURIComponent,
    setTimeout() { return 0; }, clearTimeout() {},
    WebSocket: FakeWS,
    window: { location: { search: '?code=ABCD&name=Tester' }, close() {} },
    document: {
      getElementById: (id) => (els[id] = els[id] || stubEl()),
      querySelectorAll: () => [],
      createElement: () => stubEl(),
      addEventListener() {},
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  const ws = FakeWS.last;
  const deliver = (m) => ws.onmessage({ data: JSON.stringify(m) });
  const requests = () => sent.filter((m) => m.type === 'get_member_detail');
  const ctx = (expr) => vm.runInContext(expr, sandbox);
  // A board for encounter E1 with one drillable member.
  deliver({ type: 'welcome', encounter_active: false, active_encounter_id: 'E1', encounters: [{ encounter_id: 'E1' }],
    scoreboard: { encounter_id: 'E1', boss: 'B', entries: [{ user_id: 'u1', username: 'Alice', rank: 1, has_detail: true }] } });
  return { deliver, requests, ctx, ws };
}

const detailReply = (rotation) => ({ type: 'member_detail', encounter_id: 'E1', user_id: 'u1', skills: null, rotation });

test('null-rotation reply -> next ovEnsureDetail re-requests', () => {
  const { deliver, requests, ctx } = loadOverlay();
  ctx("ovSwitchTab('skills')");
  assert.strictEqual(requests().length, 1, 'first open requests detail');
  deliver(detailReply(null));
  ctx("ovEnsureDetail('E1','u1')");
  assert.strictEqual(requests().length, 2, 'null rotation must be requested again');
});

test('non-empty rotation reply -> no re-request (negative control)', () => {
  const { deliver, requests, ctx } = loadOverlay();
  ctx("ovSwitchTab('skills')");
  deliver(detailReply([{ relative_time: 0, skill: 'Slash', damage: 10, is_crit: false }]));
  ctx("ovEnsureDetail('E1','u1')");
  ctx("ovEnsureDetail('E1','u1')");
  assert.strictEqual(requests().length, 1);
});

test('legitimately empty rotation: repeated calls stay bounded (one request per reply)', () => {
  const { deliver, requests, ctx } = loadOverlay();
  ctx("ovSwitchTab('skills')");
  for (let i = 0; i < 50; i++) ctx("ovEnsureDetail('E1','u1')");   // no reply yet
  assert.strictEqual(requests().length, 1, 'one request while one is in flight');
  deliver(detailReply([]));                                         // legit empty rotation
  for (let i = 0; i < 50; i++) ctx("ovEnsureDetail('E1','u1')");
  assert.strictEqual(requests().length, 2, 'at most one new request until its own reply arrives');
});

test('a reply never self-triggers a request (no loop without a new call)', () => {
  const { deliver, requests, ctx } = loadOverlay();
  ctx("ovSwitchTab('skills')");
  for (let i = 0; i < 10; i++) deliver(detailReply(null));
  assert.strictEqual(requests().length, 1);
});

const resultsHtml = (ctx) => ctx("document.getElementById('results').innerHTML");

test('Skills tab: answered-but-empty detail shows "no breakdown", never a permanent Loading…', () => {
  const { deliver, ctx } = loadOverlay();
  ctx("ovSwitchTab('skills')");
  assert.match(resultsHtml(ctx), /Loading/, 'before any reply the tab is loading (control)');
  deliver(detailReply(null));
  ctx('render()');
  assert.doesNotMatch(resultsHtml(ctx), /Loading/, 'a null reply is an answer, not a pending load');
  assert.match(resultsHtml(ctx), /No breakdown/);
});

test('Compare tab: Loading only while a member is unanswered; names the member with no breakdown', () => {
  const { deliver, ctx } = loadOverlay();
  deliver({ type: 'welcome', encounter_active: false, active_encounter_id: 'E1', encounters: [{ encounter_id: 'E1' }],
    scoreboard: { encounter_id: 'E1', boss: 'B', entries: [
      { user_id: 'u1', username: 'Alice', rank: 1, has_detail: true },
      { user_id: 'u2', username: 'Bob', rank: 2, has_detail: true }] } });
  ctx("ovSwitchTab('compare')");
  assert.match(resultsHtml(ctx), /Loading/, 'nothing answered yet (control)');
  deliver(detailReply(null));                                     // u1 answered: empty
  ctx('render()');
  assert.match(resultsHtml(ctx), /Loading/, 'u2 still unanswered');
  deliver({ type: 'member_detail', encounter_id: 'E1', user_id: 'u2', skills: null,
    rotation: [{ relative_time: 0, skill: 'Slash', damage: 10, is_crit: false }] });
  ctx('render()');
  assert.doesNotMatch(resultsHtml(ctx), /Loading/);
  assert.match(resultsHtml(ctx), /No breakdown for Alice/);
});
