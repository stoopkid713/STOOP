"""Unit tests for the game-data refresh tool (G1: pure functions; no live network).

Covers token normalization, the questlog->meter weapon-slug map, and the multi-feed
skill->weapon extractor (recipe doc S7). The tRPC pull layer is intentionally NOT exercised
here (it hits questlog live) -- it's verified at the gate with `--counts`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import refresh_game_data as rgd  # noqa: E402


# --- normalize_token -----------------------------------------------------------------------
def test_normalize_strips_icon_markup():
    assert rgd.normalize_token("^<imgf=foo.png> Sword of Judgment") == "Sword of Judgment"


def test_normalize_collapses_whitespace_and_trims():
    assert rgd.normalize_token("  Phoenix   Barrage  ") == "Phoenix Barrage"


def test_normalize_handles_empty_and_none():
    assert rgd.normalize_token("") == ""
    assert rgd.normalize_token(None) == ""


def test_normalize_strips_multiple_markup_runs():
    assert rgd.normalize_token("^<imgf=a> Milky ^<imgf=b> Way") == "Milky Way"


# --- weapon_slug ---------------------------------------------------------------------------
def test_weapon_slug_known_mappings():
    assert rgd.weapon_slug("sword2h") == "greatsword"
    assert rgd.weapon_slug("sword") == "sns"
    assert rgd.weapon_slug("bow") == "longbow"
    assert rgd.weapon_slug("staff") == "staff"
    assert rgd.weapon_slug("wand") == "wand"
    assert rgd.weapon_slug("orb") == "orb"


def test_weapon_slug_case_insensitive():
    assert rgd.weapon_slug("SWORD2H") == "greatsword"
    assert rgd.weapon_slug(" Bow ") == "longbow"


def test_weapon_slug_unknown_is_other():
    assert rgd.weapon_slug("trumpet") == "other"
    assert rgd.weapon_slug(None) == "other"


def test_every_mapped_slug_is_a_real_meter_slot():
    assert set(rgd.WEAPON_MAP.values()) <= rgd.METER_SLUGS


# --- extract_skill_weapons -----------------------------------------------------------------
def test_extract_base_and_specialization_names():
    sets = [
        {"name": "Brutal Fury", "mainCategory": "spear", "specializations": [
            {"name": "Slaughtering Slash"}, {"name": "Phoenix Barrage"}]},
        {"name": "Copy Satellite", "mainCategory": "orb", "specializations": []},
    ]
    out = rgd.extract_skill_weapons(sets)
    assert out["Brutal Fury"] == "spear"
    assert out["Slaughtering Slash"] == "spear"   # spec inherits parent weapon
    assert out["Phoenix Barrage"] == "spear"
    assert out["Copy Satellite"] == "orb"


def test_extract_normalizes_names_from_feeds():
    sets = [{"name": "^<imgf=x> Gale Rush", "mainCategory": "spear", "specializations": []}]
    out = rgd.extract_skill_weapons(sets)
    assert out["Gale Rush"] == "spear"


def test_extract_masteries_become_mastery():
    specs = [{"name": "Dragon Ascent", "mainCategory": "spear"}]
    out = rgd.extract_skill_weapons([], weapon_specs=specs)
    assert out["Dragon Ascent"] == "mastery"


def test_extract_priority_weapon_beats_mastery_beats_other():
    # 'other' offered first, then mastery, then a real weapon -> weapon must win.
    sets = [{"name": "Ambiguous", "mainCategory": "nonsense", "specializations": []}]   # -> other
    specs = [{"name": "Ambiguous", "mainCategory": "spear"}]                            # -> mastery
    traits = [{"name": "Ambiguous", "mainCategory": "dagger"}]                          # -> dagger
    out = rgd.extract_skill_weapons(sets, skill_traits=traits, weapon_specs=specs)
    assert out["Ambiguous"] == "dagger"


def test_extract_lower_priority_does_not_clobber_weapon():
    sets = [{"name": "Shadow Strike", "mainCategory": "dagger", "specializations": []}]
    specs = [{"name": "Shadow Strike", "mainCategory": "dagger"}]  # mastery offer must not win
    out = rgd.extract_skill_weapons(sets, weapon_specs=specs)
    assert out["Shadow Strike"] == "dagger"


def test_extract_weapon_passives_feed():
    sets = [{"name": "Corrupting Hit", "mainCategory": "wand", "specializations": []}]
    passives = [{"name": "Enraged Tevent's Hunger", "weapon": "wand"}]
    out = rgd.extract_skill_weapons(sets, weapon_passives=passives)
    assert out["Enraged Tevent's Hunger"] == "wand"   # moves off the 'other' bucket


# --- extract_weapon_passives ---------------------------------------------------------------
def test_extract_weapon_passives_keeps_non_null_only():
    items = [
        {"id": "wand_aa_t2_polymorph_003", "subCategory": "wand"},
        {"id": "plain_sword_001", "subCategory": "sword"},
    ]
    details = {
        "wand_aa_t2_polymorph_003": {"passives": {"name": "Enraged Tevent's Hunger", "text": "..."}},
        "plain_sword_001": {"passives": None},  # common weapon: no passive -> dropped
    }
    out = rgd.extract_weapon_passives(items, details)
    assert out == [{"name": "Enraged Tevent's Hunger", "weapon": "wand"}]


def test_extract_weapon_passives_maps_item_weapon_type():
    items = [{"id": "bow_x", "subCategory": "bow"}]
    details = {"bow_x": {"passives": {"name": "Skywatch Salvo"}}}
    out = rgd.extract_weapon_passives(items, details)
    assert out == [{"name": "Skywatch Salvo", "weapon": "longbow"}]
