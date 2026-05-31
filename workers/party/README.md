# tldps-party

Cloudflare **Durable Object** party relay for TL-DPS-Meter — the owned replacement for the
dead CK-Supabase party feature. One `PartyRoom` instance per party code is the **authoritative
room**: members POST completed **boss-fight results** and the room broadcasts a merged, ranked
**boss scoreboard**. Post-combat model (T&L logs flush on combat-exit) — no per-hit streaming.

Full design: `TL-DPS-Meter-oracle/docs/WORKSTREAM-B-PARTY-REBOOT.md`.

## Wire protocol

**Connect (WebSocket):**
```
wss://<host>/party/<CODE>?user_id=<id>&username=<name>&leader=<0|1>
```
- `<CODE>` — 4–8 char uppercase alphanumeric party code.
- Cap: **12 distinct members** per room (reconnects don't count against it).

**Client → room** (JSON text frames):
| type | payload | meaning |
|---|---|---|
| `post_result` | `{ result: {...} }` | post a completed boss-fight result (see below) |
| `clear` | — | leader-only: wipe the board for a fresh pull |
| `leave` | — | leave the party (removes member + their result) |
| `ping` | — | keepalive → room replies `pong` |

`result` shape:
```jsonc
{
  "boss": "Tevent",            // target name
  "boss_category": "archboss", // archboss|field_boss|raid_boss|dungeon_boss|...
  "total_damage": 256000,
  "dps": 4100.0,
  "duration": 62.9,
  "hits": 412,
  "crit_rate": 42.7,
  "heavy_rate": 18.3,
  "fight_ts": 1735600000000   // encounter timestamp (epoch ms) — groups same-kill stragglers
}
```

**Room → client** (JSON text frames):
| type | payload |
|---|---|
| `welcome` | `{ you, roster:[...], scoreboard:{...} }` — sent to the joiner |
| `roster` | `{ members:[{user_id, username, is_leader, online}] }` |
| `scoreboard` | `{ boss, total_damage, updated_at, entries:[{rank, user_id, username, total_damage, dps, duration, hits, crit_rate, heavy_rate, contribution}] }` |
| `member_joined` / `member_left` / `member_offline` | `{ user_id, username? }` |
| `pong` | — |

The **active board** is the boss with the most recent `fight_ts`; same-kill stragglers share
`fight_ts` and merge onto one board. (Phase-1 simplification — per-boss history is Phase 2.)

## Local dev (no Cloudflare account needed)
```
cd workers/party
wrangler dev          # runs the DO locally in miniflare
```
Then open a WS to `ws://localhost:8787/party/TEST?user_id=u1&username=Alice`.

## Validate config/build (no auth)
```
wrangler deploy --dry-run
```

## Bootstrap (one-time, to deploy live)
1. **Cloudflare account** (the business account, now under the personal email).
2. **Durable Objects:** SQLite-backed DOs are intended to be **free-tier eligible** — verify;
   only enable Workers Paid ($5/mo) if the dashboard says it's required for this worker.
3. **CF API token** with "Edit Workers" scope → store as the GitHub Actions secret
   `CLOUDFLARE_API_TOKEN` (the CI workflow uses it for `wrangler deploy`).

## Deploy
`wrangler deploy` (manual) or push to `main` (CI auto-deploys — see `.github/workflows/`).
