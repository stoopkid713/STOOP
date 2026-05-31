// tldps-party — Cloudflare Durable Object party relay for TL-DPS-Meter.
//
// Model (see ../../../TL-DPS-Meter-oracle/docs/WORKSTREAM-B-PARTY-REBOOT.md):
//   - One PartyRoom Durable Object instance per party code = the authoritative room.
//   - POST-COMBAT: members POST a completed boss-fight result; the room merges results
//     into a ranked boss scoreboard and broadcasts it. NO per-hit streaming.
//   - Presence = the set of connected WebSockets. Reconnect-safe via WS Hibernation.
//   - Bounded to small parties (<=12). The room is the single source of truth.
//
// Wire protocol — see README.md.

const CODE_RE = /^[A-Z0-9]{4,8}$/;
const MAX_MEMBERS = 12;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("tldps-party ok", { status: 200 });
    }

    // WS join:  /party/<CODE>?user_id=..&username=..&leader=0|1
    const m = url.pathname.match(/^\/party\/([A-Za-z0-9]+)$/);
    if (m) {
      const code = m[1].toUpperCase();
      if (!CODE_RE.test(code)) return new Response("bad party code", { status: 400 });
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("expected websocket", { status: 426 });
      }
      const id = env.PARTY_ROOM.idFromName(code);
      return env.PARTY_ROOM.get(id).fetch(request);
    }

    return new Response("not found", { status: 404 });
  },
};

export class PartyRoom {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  // --- connection (WS upgrade) ---
  async fetch(request) {
    const url = new URL(request.url);
    const code = (url.pathname.split("/").pop() || "").toUpperCase();
    const user_id = url.searchParams.get("user_id") || "";
    const username = (url.searchParams.get("username") || "Anon").slice(0, 32);
    const is_leader = url.searchParams.get("leader") === "1";

    if (!user_id) return new Response("missing user_id", { status: 400 });

    // Enforce the <=12 cap by distinct member ids (a reconnect of an existing
    // member doesn't count against the cap).
    const members = (await this.ctx.storage.get("members")) || {};
    if (!members[user_id] && Object.keys(members).length >= MAX_MEMBERS) {
      return new Response("party full", { status: 403 });
    }

    // Drop any prior socket for this user (reconnect / duplicate tab).
    for (const old of this.ctx.getWebSockets(user_id)) {
      try { old.close(1000, "replaced"); } catch (_) {}
    }

    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server, [user_id]); // tag = user_id (survives hibernation)
    server.serializeAttachment({ user_id, username, is_leader, code });

    members[user_id] = { username, is_leader, joined_at: Date.now() };
    await this.ctx.storage.put("members", members);

    // Snapshot to the joiner, then notify the room.
    server.send(JSON.stringify({
      type: "welcome",
      you: { user_id, username, is_leader },
      ...(await this.snapshot()),
    }));
    this.broadcastExcept(user_id, { type: "member_joined", user_id, username });
    this.broadcast(await this.buildRoster());

    return new Response(null, { status: 101, webSocket: client });
  }

  // --- hibernation handlers ---
  async webSocketMessage(ws, message) {
    const att = ws.deserializeAttachment() || {};
    let msg;
    try { msg = JSON.parse(typeof message === "string" ? message : "{}"); }
    catch (_) { return; }

    switch (msg.type) {
      case "ping":
        ws.send(JSON.stringify({ type: "pong" }));
        return;

      case "post_result":
        if (msg.result) {
          await this.postResult(att.user_id, att.username, msg.result);
          this.broadcast(await this.buildScoreboard());
        }
        return;

      case "clear": // leader starts a fresh board (new pull)
        if (att.is_leader) {
          await this.ctx.storage.put("results", {});
          this.broadcast(await this.buildScoreboard());
        }
        return;

      case "leave":
        await this.removeMember(att.user_id);
        try { ws.close(1000, "left"); } catch (_) {}
        this.broadcast(await this.buildRoster());
        this.broadcastExcept(att.user_id, { type: "member_left", user_id: att.user_id });
        return;
    }
  }

  async webSocketClose(ws) {
    const att = ws.deserializeAttachment() || {};
    // Offline, but keep their last result on the board until they explicitly leave
    // or the room is cleared. Just refresh presence.
    this.broadcast(await this.buildRoster());
    this.broadcastExcept(att.user_id, { type: "member_offline", user_id: att.user_id });
  }

  async webSocketError(ws) {
    try { await this.webSocketClose(ws); } catch (_) {}
  }

  // --- state mutations ---
  async postResult(user_id, username, r) {
    const results = (await this.ctx.storage.get("results")) || {};
    results[user_id] = {
      user_id,
      username,
      boss: String(r.boss || "Unknown").slice(0, 80),
      boss_category: String(r.boss_category || "other").slice(0, 32),
      total_damage: Number(r.total_damage) || 0,
      dps: Number(r.dps) || 0,
      duration: Number(r.duration) || 0,
      hits: Number(r.hits) || 0,
      crit_rate: Number(r.crit_rate) || 0,
      heavy_rate: Number(r.heavy_rate) || 0,
      // fight_ts: the encounter's timestamp (epoch ms) — groups stragglers from the
      // SAME boss kill onto one board and prevents an old straggler from flipping the
      // active board. Falls back to now() if the client omits it.
      fight_ts: Number(r.fight_ts) || Date.now(),
      posted_at: Date.now(),
    };
    await this.ctx.storage.put("results", results);
  }

  async removeMember(user_id) {
    const members = (await this.ctx.storage.get("members")) || {};
    const results = (await this.ctx.storage.get("results")) || {};
    delete members[user_id];
    delete results[user_id];
    await this.ctx.storage.put("members", members);
    await this.ctx.storage.put("results", results);
  }

  // --- views ---
  // Active board = the boss with the most recent fight_ts. Stragglers from the same
  // kill share fight_ts -> one board. PHASE-1 SIMPLIFICATION: cross-member clock skew
  // can misgroup edge cases; per-boss history/session view is Phase 2.
  async buildScoreboard() {
    const results = (await this.ctx.storage.get("results")) || {};
    const entries = Object.values(results);
    if (!entries.length) {
      return { type: "scoreboard", boss: null, entries: [], total_damage: 0, updated_at: Date.now() };
    }
    const activeTs = Math.max(...entries.map((e) => e.fight_ts));
    const activeBoss = entries.find((e) => e.fight_ts === activeTs).boss;
    const board = entries.filter((e) => e.boss === activeBoss);
    const total = board.reduce((s, e) => s + e.total_damage, 0);
    board.sort((a, b) => b.total_damage - a.total_damage);
    return {
      type: "scoreboard",
      boss: activeBoss,
      total_damage: total,
      updated_at: Date.now(),
      entries: board.map((e, i) => ({
        rank: i + 1,
        user_id: e.user_id,
        username: e.username,
        total_damage: e.total_damage,
        dps: e.dps,
        duration: e.duration,
        hits: e.hits,
        crit_rate: e.crit_rate,
        heavy_rate: e.heavy_rate,
        contribution: total > 0 ? Math.round((e.total_damage / total) * 1000) / 10 : 0,
      })),
    };
  }

  async buildRoster() {
    const members = (await this.ctx.storage.get("members")) || {};
    const online = new Set(
      this.ctx.getWebSockets().map((ws) => (ws.deserializeAttachment() || {}).user_id)
    );
    return {
      type: "roster",
      members: Object.entries(members).map(([uid, m]) => ({
        user_id: uid,
        username: m.username,
        is_leader: !!m.is_leader,
        online: online.has(uid),
      })),
    };
  }

  async snapshot() {
    const roster = await this.buildRoster();
    const scoreboard = await this.buildScoreboard();
    return { roster: roster.members, scoreboard };
  }

  // --- broadcast helpers ---
  broadcast(obj) {
    const s = JSON.stringify(obj);
    for (const ws of this.ctx.getWebSockets()) {
      try { ws.send(s); } catch (_) {}
    }
  }

  broadcastExcept(user_id, obj) {
    const s = JSON.stringify(obj);
    for (const ws of this.ctx.getWebSockets()) {
      const att = ws.deserializeAttachment() || {};
      if (att.user_id !== user_id) {
        try { ws.send(s); } catch (_) {}
      }
    }
  }
}
