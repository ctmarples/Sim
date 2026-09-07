"""Chronological tutorial progress for checkpoint skip-ahead.

Loading any later quest reapplies every unlock, item, and map reveal that
should already have happened by that step — JSON flags are optional hints,
not the source of truth.
"""

from __future__ import annotations

# Story order. Unknown / dialogue-only steps alias onto the nearest prior beat.
STEP_ORDER: tuple[str, ...] = (
    "hunger_dialog",
    "find_food",
    "follow_deer",
    "find_tent",
    "fix_tent",
    "go_to_sleep",
    "talk_to_rhea",
    "morning_greeting",
    "walk_to_field",
    "equip_hoe",
    "clear_weeds",
    "weeds_complete_dialog",
    "ask_villagers",
    "gwen_intro",
    "joss_intro",
    "enter_farmhouse",
    "open_book",
    "field_handbook",
    "rhea_forage_approaches",
    "walk_to_forager",
    "gwen_forager_intro",
    "walk_to_meadow",
    "equip_satchel",
    "forage_meadow",
    "find_diversity_hotspot",
    "diversity_quiz",
    "inspect_hotspot_flora",
    "find_hotspot_wildlife",
    "return_to_rhea",
    "visit_berry_traveller",
    "collect_trade_food",
    "create_orchard_field",
    "plan_orchard_crops",
    "plant_orchard_bushes",
    "complete",
)

# Dialogue / transient steps → nearest ordered beat they belong to.
STEP_ALIASES: dict[str, str] = {
    "sleeping": "go_to_sleep",
    "join_rhea": "fix_tent",
    "rhea_congrats_approaches": "fix_tent",
    "tent_repaired_dialog": "fix_tent",
    "field_reaction": "walk_to_field",
    "hoe_gift": "equip_hoe",
    "give_hoe": "equip_hoe",
    "rhea_weeds_approaches": "clear_weeds",
    "farm_question": "weeds_complete_dialog",
    "rhea_abundance": "weeds_complete_dialog",
    "ask_villagers_intro": "ask_villagers",
    "gwen_player": "gwen_intro",
    "gwen_history": "gwen_intro",
    "joss_help": "joss_intro",
    "joss_doubt": "joss_intro",
    "joss_learn": "joss_intro",
    "joss_books": "joss_intro",
    "finish_interview": "joss_intro",
    "gwen_forager_haulers": "gwen_forager_intro",
    "gwen_meadow_intro": "walk_to_meadow",
    "give_satchel": "equip_satchel",
    "gwen_forage_ready": "equip_satchel",
    "abundance_dialog": "forage_meadow",
    "diversity_wrong": "diversity_quiz",
    "diversity_correct": "diversity_quiz",
    "wildlife_footprints": "find_hotspot_wildlife",
    "knowledge_thanks": "return_to_rhea",
    "knowledge_player_glad": "return_to_rhea",
    "knowledge_rhea_winter": "return_to_rhea",
    "knowledge_player_edge": "return_to_rhea",
    "knowledge_rhea_we": "return_to_rhea",
    "knowledge_player_hesitate": "return_to_rhea",
    "knowledge_rhea_stay": "return_to_rhea",
    "knowledge_player_berries": "return_to_rhea",
    "berry_trade_accuse": "visit_berry_traveller",
    "berry_trade_player_stay": "visit_berry_traveller",
    "berry_trade_mine": "visit_berry_traveller",
    "berry_trade_offer": "visit_berry_traveller",
    "berry_trade_listening": "visit_berry_traveller",
    "berry_trade_terms": "visit_berry_traveller",
    "berry_trade_delivery": "collect_trade_food",
}


def normalize_step(step: str) -> str:
    step = str(step or "")
    return STEP_ALIASES.get(step, step)


def step_rank(step: str) -> int:
    key = normalize_step(step)
    try:
        return STEP_ORDER.index(key)
    except ValueError:
        return -1


def reached(current: str, milestone: str) -> bool:
    """True when ``current`` is at or past ``milestone`` in story order."""
    cur = step_rank(current)
    need = step_rank(milestone)
    return cur >= 0 and need >= 0 and cur >= need


def apply_cumulative_progress(director, game, step: str, checkpoint: dict) -> None:
    """Grant every unlock / item / reveal that should already be true at ``step``."""
    state = director.state

    # --- Flags from chronology (reset first so skip-back does not leak) -----
    state.field_planner_unlocked = False
    state.forager_unlocked = False
    state.village_buildings_unlocked = False
    state.gwen_asked = False
    state.joss_asked = False

    if reached(step, "open_book") or reached(step, "field_handbook"):
        state.field_planner_unlocked = True
    # Forager hut unlocks when Gwen explains it (checkpoint 22+).
    if (
        reached(step, "gwen_forager_intro")
        or reached(step, "equip_satchel")
        or reached(step, "forage_meadow")
    ):
        state.forager_unlocked = True
    if reached(step, "forage_meadow"):
        state.village_buildings_unlocked = True
        state.forager_unlocked = True

    # JSON may only force unlocks True (never clear chronology-derived True).
    state.field_planner_unlocked = state.field_planner_unlocked or bool(
        checkpoint.get("field_planner_unlocked", False)
    )
    state.forager_unlocked = state.forager_unlocked or bool(
        checkpoint.get("forager_unlocked", False)
    )
    state.village_buildings_unlocked = state.village_buildings_unlocked or bool(
        checkpoint.get("village_buildings_unlocked", False)
    )

    if reached(step, "enter_farmhouse") or reached(step, "open_book") or reached(step, "field_handbook"):
        state.gwen_asked = True
        state.joss_asked = True
    else:
        state.gwen_asked = bool(checkpoint.get("gwen_asked", False))
        state.joss_asked = bool(checkpoint.get("joss_asked", False))

    # --- Inventory (always after any player.reset in the caller) ------------
    inv = game.player.inventory
    if reached(step, "equip_hoe") or reached(step, "clear_weeds"):
        if int(getattr(inv, "hoe", 0) or 0) <= 0 and not inv.has_equipped_tool("hoe"):
            inv.add_item("hoe", 1)
        if reached(step, "clear_weeds") or reached(step, "weeds_complete_dialog"):
            inv.equip_tool("hoe")

    if (
        reached(step, "equip_satchel")
        or reached(step, "forage_meadow")
        or bool(checkpoint.get("satchel_equipped", False))
        or bool(checkpoint.get("has_satchel", False))
    ):
        if int(getattr(inv, "leather_satchel", 0) or 0) <= 0 and inv.equipped_in_slot("bag") != "leather_satchel":
            inv.add_item("leather_satchel", 1)
        if reached(step, "forage_meadow") or bool(checkpoint.get("satchel_equipped", False)):
            inv.equip_clothing("leather_satchel")

    if bool(checkpoint.get("has_book", False)) or (
        reached(step, "open_book") and not reached(step, "field_handbook")
    ):
        if int(getattr(inv, "book", 0) or 0) <= 0:
            inv.add_item("book", 1)

    if reached(step, "create_orchard_field"):
        from berry_bushes import TRADE_SEED_REWARDS
        for key, n in TRADE_SEED_REWARDS:
            have = int(getattr(inv, key, 0) or 0)
            if have < n:
                inv.add_item(key, n - have)
        if not reached(step, "complete"):
            if int(getattr(inv, "hoe", 0) or 0) <= 0 and not inv.has_equipped_tool("hoe"):
                inv.add_item("hoe", 1)
            inv.equip_tool("hoe")
        if reached(step, "plan_orchard_crops") and int(getattr(game.home_storage, "hoe", 0) or 0) <= 0:
            game.home_storage.hoe = 1

    # --- Map reveals for previously unlocked places -------------------------
    _reveal_unlocked_places(director, game, step)


def _reveal_unlocked_places(director, game, step: str) -> None:
    """Unshroud buildings / areas the player has already unlocked."""
    reveal = director._reveal_clearing
    specs = director.layout.get("buildings", {})

    def reveal_role(role: str, radius: int = 6) -> None:
        for raw_id, spec in specs.items():
            if str(spec.get("role", "")) != role:
                continue
            building = game.buildings.get(int(raw_id))
            if building is None:
                continue
            reveal(game, building.center_cell(), radius)
            return

    if reached(step, "talk_to_rhea"):
        for role in (
            "village_storehouse",
            "village_farm",
            "village_field",
            "village_house",
        ):
            reveal_role(role, 8)
        tent_id = director.state.repaired_tent_id
        if tent_id is not None and tent_id in game.buildings:
            reveal(game, game.buildings[tent_id].center_cell(), 5)

    if director.state.forager_unlocked or reached(step, "gwen_forager_intro"):
        reveal_role("village_forager", 8)

    if director.state.village_buildings_unlocked or reached(step, "forage_meadow"):
        for bid, group in director.building_groups.items():
            if group != "village":
                continue
            building = game.buildings.get(bid)
            if building is not None:
                reveal(game, building.center_cell(), 6)

    if reached(step, "walk_to_meadow") or reached(step, "forage_meadow"):
        from quest_progress import MEADOW_CELL
        reveal(game, MEADOW_CELL, 10)

    if reached(step, "find_diversity_hotspot"):
        from quest_progress import MEADOW_CELL
        hx = director.state.hotspot_x if director.state.hotspot_x is not None else MEADOW_CELL[0]
        hy = director.state.hotspot_y if director.state.hotspot_y is not None else MEADOW_CELL[1]
        reveal(game, (hx, hy), 10)
        reveal(game, MEADOW_CELL, 10)
