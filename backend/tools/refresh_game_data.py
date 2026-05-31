"""Game-data refresh — keep skill->weapon / boss->category / weapon-spec current per T&L patch.

Driven off questlog.gg's own tRPC API (no scraping), consolidated to ONE canonical source per
domain, with the meter's derived files (weapon_config.json skillAssignments, the party worker's
KNOWN_BOSSES, dungeons.json) GENERATED so the layers can never drift.

Full design + the reverse-engineered API map: TL-DPS-Meter-oracle/docs/WORKSTREAM-GAME-DATA-REFRESH.md

The full workflow is pull -> extract -> reconcile -> diff -> review-gate -> regenerate -> verify,
built in gated segments. THIS FILE currently implements **G1 (pull + extract, read-only)**:
  * the questlog tRPC pull layer (GET, no auth, raw `input`),
  * the questlog-mainCategory -> meter-weapon-slug map (the 11 existing UI cards),
  * combat-log token normalization + the multi-feed skill->weapon extractor (recipe doc S7).
Later segments add reconcile/diff (G2), regenerate skills (G3), and derive bosses/dungeons (G4).

CLI (read-only; never touches canonical or derived files):
  py backend/tools/refresh_game_data.py --counts
      live-probe every feed and print record counts (the cheapest gate check).
  py backend/tools/refresh_game_data.py --dump [DIR] [--passives]
      pull every feed live and write the raw JSON + the extracted skill->weapon map to DIR
      (default backend/tools/_refresh_cache/, gitignored). --passives also pulls each weapon's
      item detail for feed #5 (slow: ~hundreds of getItem calls).

Run with the venv python (stdlib-only; no third-party deps):
  backend/.venv/Scripts/python.exe backend/tools/refresh_game_data.py --counts
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------------------------
# questlog tRPC pull layer
# --------------------------------------------------------------------------------------------
# Nuxt/Nitro SPA backed by tRPC over Meilisearch. All calls are GET, no auth, game-prefixed
# path, with a RAW `input` query param (NO superjson {"json":...} wrapper):
#   https://questlog.gg/throne-and-liberty/api/trpc/<router>.<proc>?input=<url-encoded JSON>
#   -> {"result":{"data": ... }}
BASE = "https://questlog.gg/throne-and-liberty/api/trpc"
UA = "Mozilla/5.0"
LANG = "en"
_TIMEOUT = 30
_RETRIES = 3
_RETRY_WAIT = 2.0  # seconds, linear backoff


def _trpc(proc: str, inp: dict):
    """GET one tRPC procedure and return ``result.data`` (raw shape varies per procedure)."""
    query = urllib.parse.urlencode({"input": json.dumps(inp, separators=(",", ":"))})
    url = f"{BASE}/{proc}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last_err = None
    for attempt in range(_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                payload = json.load(resp)
            return payload["result"]["data"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as err:  # noqa: PERF203
            last_err = err
            if attempt < _RETRIES - 1:
                time.sleep(_RETRY_WAIT * (attempt + 1))
    raise RuntimeError(f"tRPC {proc} failed after {_RETRIES} tries: {last_err}")


def _paginate(proc: str, base_input: dict) -> list:
    """Pull a paginated database.* procedure ({pageData, pageCount}) across all pages."""
    rows: list = []
    first = _trpc(proc, {**base_input, "page": 1})
    page_count = int(first.get("pageCount", 1) or 1)
    rows.extend(first.get("pageData", []) or [])
    for page in range(2, page_count + 1):
        data = _trpc(proc, {**base_input, "page": page})
        rows.extend(data.get("pageData", []) or [])
    return rows


# --- the six feeds (S2 of the workstream doc) ----------------------------------------------
def pull_skill_sets() -> list:
    """Feed #1+2: 180 base skill-sets (each carries `mainCategory`=weapon + `specializations`)."""
    return _trpc("skillBuilder.getSkillSets", {"language": LANG})


def pull_skill_traits() -> list:
    """Feed #3: 356 skill EFFECTS (`mainCategory`=weapon); names are "<Base> - <Trait>"."""
    return _trpc("skillBuilder.getSkillTraits", {"language": LANG})


def pull_weapon_specializations() -> list:
    """Feed #4: 490 MASTERIES (`mainCategory`=weapon) -> the meter's `mastery` card."""
    return _trpc("weaponSpecialization.getWeaponSpecializations", {"language": LANG})


def pull_npcs(main_category: str) -> list:
    """Bosses by category. `page` + `type` are REQUIRED (the `type` value itself is ignored);
    `mainCategory` (string) is THE real filter. Unfiltered is Meili-capped, so always filter."""
    return _paginate(
        "database.getNpcs",
        {"language": LANG, "type": "boss", "mainCategory": main_category},
    )


def pull_dungeons() -> list:
    return _paginate("database.getDungeons", {"language": LANG})


def pull_weapon_items() -> list:
    """List rows for weapons (metadata only; skill/damage live in the item DETAIL)."""
    return _paginate("database.getItems", {"language": LANG, "type": "item", "mainCategory": "weapons"})


def pull_item(item_id: str) -> dict:
    """Item detail: `.passives.name` = the combat-log weapon-skill token (feed #5)."""
    return _trpc("database.getItem", {"language": LANG, "id": item_id})


# --------------------------------------------------------------------------------------------
# weapon-label map: questlog `mainCategory` -> meter weapon slug (the 11 existing UI cards)
# --------------------------------------------------------------------------------------------
# Resolved 2026-05-31: index.html already defines all 11 `data-weapon` card slugs; greatsword/
# longbow/staff simply have 0 skills today. So questlog maps onto EXISTING slugs (no UI change):
WEAPON_MAP = {
    "sword2h": "greatsword",
    "sword": "sns",
    "dagger": "dagger",
    "spear": "spear",
    "crossbow": "crossbow",
    "bow": "longbow",
    "staff": "staff",
    "wand": "wand",
    "orb": "orb",
}
# The 11 meter slots (10 weapons + Mastery + Other). Used to validate derived output.
METER_SLUGS = set(WEAPON_MAP.values()) | {"mastery", "other"}

# Slug priority when feeds disagree on the same skill name: a real weapon beats `mastery`
# beats `other` (a concrete weapon attribution is always preferred over a fallback bucket).
_SLUG_PRIORITY = {slug: 2 for slug in WEAPON_MAP.values()}
_SLUG_PRIORITY["mastery"] = 1
_SLUG_PRIORITY["other"] = 0


def weapon_slug(main_category) -> str:
    """Map a questlog `mainCategory` to a meter weapon slug; unknown -> 'other'."""
    return WEAPON_MAP.get(str(main_category or "").strip().lower(), "other")


# --------------------------------------------------------------------------------------------
# token normalization + the multi-feed skill->weapon extractor (recipe doc S7)
# --------------------------------------------------------------------------------------------
_ICON_MARKUP = re.compile(r"\^<[^>]*>")  # combat-log icon markup, e.g. "^<imgf=...>"
_WS = re.compile(r"\s+")


def normalize_token(name) -> str:
    """Normalize a skill/effect name to its combat-log token form.

    Strips icon markup (``^<imgf=...> Sword of Judgment`` -> ``Sword of Judgment``) and
    collapses whitespace. Casing/spelling are preserved (combat-log tokens are case-stable).
    """
    if not name:
        return ""
    stripped = _ICON_MARKUP.sub(" ", str(name))
    return _WS.sub(" ", stripped).strip()


def _offer(out: dict, name, slug: str) -> None:
    """Record name->slug into `out`, keeping the higher-priority slug on conflict."""
    token = normalize_token(name)
    if not token:
        return
    current = out.get(token)
    if current is None or _SLUG_PRIORITY.get(slug, 0) > _SLUG_PRIORITY.get(current, 0):
        out[token] = slug


def extract_skill_weapons(
    skill_sets: list,
    skill_traits: list | None = None,
    weapon_specs: list | None = None,
    weapon_passives: list | None = None,
) -> dict:
    """Build the {combat-log token -> weapon slug} map from the feeds (recipe doc S7).

    Sources, in order:
      1. ``getSkillSets[].name``                 (base skill-sets)            -> mainCategory weapon
      2. ``getSkillSets[].specializations[].name`` (the combat log usually emits the SPEC name)
      3. ``getSkillTraits[].name``               (skill effects)             -> mainCategory weapon
      4. ``getWeaponSpecializations[].name``     (masteries)                 -> 'mastery'
      5. weapon-item passives ``{name, weapon}`` (non-null only; see pull_item) -> item weapon

    Each name is normalized; on conflict the higher-priority slug wins (weapon > mastery > other).
    """
    out: dict = {}
    for rec in skill_sets or []:
        slug = weapon_slug(rec.get("mainCategory"))
        _offer(out, rec.get("name"), slug)
        for spec in rec.get("specializations") or []:
            _offer(out, spec.get("name"), slug)
    for rec in skill_traits or []:
        _offer(out, rec.get("name"), weapon_slug(rec.get("mainCategory")))
    for rec in weapon_specs or []:
        _offer(out, rec.get("name"), "mastery")
    for rec in weapon_passives or []:
        # rec = {"name": <passive.name>, "weapon": <slug already mapped>}
        _offer(out, rec.get("name"), rec.get("weapon") or "other")
    return out


def extract_weapon_passives(items: list, details: dict) -> list:
    """Feed #5: from weapon item rows + their fetched details, yield non-null passive tokens.

    `items` = pull_weapon_items() rows (carry subCategory/mainCategory = weapon type);
    `details` = {item_id: pull_item(item_id)}. Only weapons with a passive contribute, which
    auto-filters to the ~dozens of unique/archboss weapons (common weapons have no passive).
    Returns [{"name": <passive name>, "weapon": <meter slug>}].
    """
    out: list = []
    by_id = {str(it.get("id")): it for it in (items or [])}
    for item_id, detail in (details or {}).items():
        passive = (detail or {}).get("passives") or {}
        pname = passive.get("name") if isinstance(passive, dict) else None
        if not pname:
            continue
        meta = by_id.get(str(item_id), {}) or detail or {}
        slug = weapon_slug(meta.get("subCategory") or meta.get("mainCategory"))
        out.append({"name": pname, "weapon": slug})
    return out


# --------------------------------------------------------------------------------------------
# CLI (read-only)
# --------------------------------------------------------------------------------------------
NPC_BOSS_CATEGORIES = ("boss-world", "boss", "solo-elite")
DEFAULT_CACHE = Path(__file__).resolve().parent / "_refresh_cache"


def _counts() -> int:
    print("Pulling questlog feeds (live)...")
    sets = pull_skill_sets()
    traits = pull_skill_traits()
    specs = pull_weapon_specializations()
    print(f"  getSkillSets ............. {len(sets):>5}  (expect ~180)")
    print(f"  getSkillTraits .......... {len(traits):>5}  (expect ~356)")
    print(f"  getWeaponSpecializations  {len(specs):>5}  (expect ~490)")
    for cat in NPC_BOSS_CATEGORIES:
        npcs = pull_npcs(cat)
        names = len({n.get("name") for n in npcs})
        print(f"  getNpcs[{cat:<11}] ... {len(npcs):>5} rows / {names} distinct names")
    dungeons = pull_dungeons()
    print(f"  getDungeons ............. {len(dungeons):>5}")
    items = pull_weapon_items()
    print(f"  getItems[weapons] ....... {len(items):>5}")
    skill_map = extract_skill_weapons(sets, traits, specs)
    by_slug: dict = {}
    for slug in skill_map.values():
        by_slug[slug] = by_slug.get(slug, 0) + 1
    print(f"  extracted skill->weapon . {len(skill_map):>5} tokens")
    print("    by slug: " + ", ".join(f"{k}={v}" for k, v in sorted(by_slug.items())))
    return 0


def _dump(out_dir: Path, with_passives: bool) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Dumping raw feeds -> {out_dir}")

    def _save(name: str, data) -> None:
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        n = len(data) if isinstance(data, (list, dict)) else "?"
        print(f"  {name:<26} {n}")

    sets = pull_skill_sets()
    traits = pull_skill_traits()
    specs = pull_weapon_specializations()
    _save("skill_sets", sets)
    _save("skill_traits", traits)
    _save("weapon_specializations", specs)
    npcs_by_cat = {cat: pull_npcs(cat) for cat in NPC_BOSS_CATEGORIES}
    _save("npcs_by_category", npcs_by_cat)
    _save("dungeons", pull_dungeons())
    items = pull_weapon_items()
    _save("weapon_items", items)

    passives: list = []
    if with_passives:
        print(f"  pulling {len(items)} weapon item details (feed #5)...")
        details = {}
        for i, it in enumerate(items, 1):
            iid = str(it.get("id"))
            if not iid:
                continue
            try:
                details[iid] = pull_item(iid)
            except RuntimeError as err:
                print(f"    [warn] getItem {iid}: {err}")
            if i % 50 == 0:
                print(f"    {i}/{len(items)}")
        passives = extract_weapon_passives(items, details)
        _save("weapon_passives", passives)

    skill_map = extract_skill_weapons(sets, traits, specs, passives or None)
    _save("skill_weapon_map", skill_map)
    print("Done. (read-only: no canonical or derived files were touched.)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Game-data refresh (G1: pull + extract, read-only)")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--counts", action="store_true", help="live-probe every feed and print counts")
    grp.add_argument("--dump", nargs="?", const=str(DEFAULT_CACHE), metavar="DIR",
                     help="pull every feed live and write raw JSON + the extracted map to DIR")
    parser.add_argument("--passives", action="store_true",
                        help="with --dump: also pull each weapon's item detail (feed #5; slow)")
    args = parser.parse_args(argv)
    try:
        if args.counts:
            return _counts()
        return _dump(Path(args.dump), args.passives)
    except RuntimeError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
