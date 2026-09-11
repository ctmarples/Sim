"""Serialize and restore game state as JSON save files."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crops import LEGACY_HERB_PRODUCE, LEGACY_HERB_SEED, PRODUCE_KEYS, SEED_KEYS
from trees import SAPLING_ITEM_KEYS
from height_sample import generate_height_sample
from entities import (
    Building,
    BuildingKind, is_field_plot_kind,
    ConstructionSite,
    CropPlan,
    FarmField,
    Inventory,
    RationMode,
    TaskArea,
    TaskType,
    TOOL_KEYS,
    Villager,
    VillagerState,
    WorkMode,
    WorkPriority,
)
from society import (
    Community,
    HireCandidate,
    skills_from_dict,
    skills_to_dict,
)
from world import Cell, FeatureType, NaturalObject, TerrainType, World

if TYPE_CHECKING:
    from game import Game

SAVE_VERSION = 1

_BASE_STORAGE_KEYS = (
    "logs",
    "hardwood_logs",
    "wood",
    "rock",
    "meat",
    "fish",
    *SAPLING_ITEM_KEYS,
    "mushrooms",
    "honey",
    "book",
    "berries",
    "blackberries",
    "sloe_berries",
    "elderberries",
    "hazelnuts",
    "berry_seeds",
    "blackberry_seeds",
    "sloe_berry_seeds",
    "elder_berry_seeds",
    "hazel_seeds",
    "reeds",
    "straw",
    "fur",
    "feathers",
    "hide",
    "leather",
    "twine",
    "coins",
    "axe",
    "spear",
    "fishing_rod",
    "hoe",
    "knife",
    "bow",
)
_CROP_STORAGE_KEYS = PRODUCE_KEYS + SEED_KEYS
def _storage_keys() -> tuple[str, ...]:
    """Resolve reloadable recipe outputs when serializing future state."""
    from recipes import PROCESSED_KEYS
    from resources import RESOURCE_KEYS

    return tuple(dict.fromkeys((*_BASE_STORAGE_KEYS, *_CROP_STORAGE_KEYS, *PROCESSED_KEYS, *RESOURCE_KEYS)))

# Pre-rename gather recipe keys → current recipe names.
_LEGACY_RECIPE_KEYS: dict[str, str] = {
    "wood": "logs",
    "hardwood": "hardwood_logs",
}


def _normalize_legacy_storage(data: dict[str, Any]) -> dict[str, Any]:
    """Map old save storage keys (wood/hardwood = tree products) to logs/hardwood_logs."""
    if not data:
        return data
    out = dict(data)
    if "logs" not in out and "wood" in out:
        out["logs"] = int(out.get("wood", 0))
        out["wood"] = 0
    if "hardwood_logs" not in out and "hardwood" in out:
        out["hardwood_logs"] = int(out.get("hardwood", 0))
    ws = int(out.get("wheat_seeds", 0))
    if ws:
        out["wheat_grain"] = int(out.get("wheat_grain", 0)) + ws
        out["wheat_seeds"] = 0
    rs = int(out.get("rye_seeds", 0))
    if rs:
        out["rye_grain"] = int(out.get("rye_grain", 0)) + rs
        out["rye_seeds"] = 0
    legacy = int(out.get("grain", 0))
    if legacy:
        out["wheat_grain"] = int(out.get("wheat_grain", 0)) + legacy
        out["grain"] = 0
    # Generic berries → blackberries (species-specific foods replaced the old key).
    legacy_berries = int(out.get("berries", 0) or 0)
    if legacy_berries:
        out["blackberries"] = int(out.get("blackberries", 0) or 0) + legacy_berries
        out["berries"] = 0
    return out


def _migrate_recipe_state(
    raw_enabled: dict[str, Any] | None,
    raw_progress: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    enabled = dict(raw_enabled or {})
    progress = dict(raw_progress or {})
    for old, new in _LEGACY_RECIPE_KEYS.items():
        if old in enabled and new not in enabled:
            enabled[new] = enabled.pop(old)
        if old in progress and new not in progress:
            progress[new] = progress.pop(old)
    return enabled, progress


def saves_dir() -> Path:
    path = Path(__file__).resolve().parent.parent / "saves"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Sidecar JSON in saves/ that must never be treated as world saves.
_NON_SAVE_JSON_NAMES = frozenset(
    {
        "balance_prefs.json",
    }
)


def is_world_save_path(path: Path | str) -> bool:
    """True for ``*.json`` world saves (excludes prefs / other sidecars)."""
    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".json":
        return False
    if p.name in _NON_SAVE_JSON_NAMES:
        return False
    return True


def iter_save_paths() -> list[Path]:
    return sorted(p for p in saves_dir().glob("*.json") if is_world_save_path(p))


def list_save_files() -> list[str]:
    return [p.name for p in iter_save_paths()]


def _inv_to_dict(inv: Inventory) -> dict[str, Any]:
    from food_spoilage import serialize_food_quality

    data: dict[str, Any] = {key: int(getattr(inv, key, 0)) for key in _storage_keys()}
    data["capacity"] = inv.capacity
    if inv.equipped_tools:
        data["equipped_tools"] = list(inv.equipped_tools)
    if inv.equipped_clothing:
        data["equipped_clothing"] = {
            str(slot): str(item) for slot, item in inv.equipped_clothing.items()
        }
    fq = serialize_food_quality(inv)
    if fq:
        data["food_quality"] = fq
    return data


def _inv_from_dict(data: dict[str, Any]) -> Inventory:
    data = _normalize_legacy_storage(data)
    from settings import INVENTORY_CAPACITY
    from entities import CLOTHING_ITEM_SLOT, CLOTHING_SLOTS

    # Prefer current settings capacity so old saves (e.g. cap 8) aren't stuck
    # unable to carry FARM_PRODUCE_YIELD / other multi-unit harvests.
    saved_cap = int(data.get("capacity", INVENTORY_CAPACITY))
    inv = Inventory(capacity=max(saved_cap, INVENTORY_CAPACITY))
    for key in _storage_keys():
        setattr(inv, key, int(data.get(key, 0)))
    # Legacy: generic herbs → sage; generic saplings → oak.
    inv.sage += int(data.get("herbs", 0))
    inv.sage_seeds += int(data.get("herb_seeds", 0))
    inv.oak_saplings += int(data.get("saplings", 0))
    raw_tools = data.get("equipped_tools")
    if isinstance(raw_tools, list):
        inv.equipped_tools = [str(t) for t in raw_tools if t in TOOL_KEYS][:3]
    else:
        tool = data.get("equipped_tool")
        if tool in TOOL_KEYS:
            inv.equipped_tools = [str(tool)]
    raw_clothes = data.get("equipped_clothing")
    if isinstance(raw_clothes, dict):
        worn: dict[str, str] = {}
        for slot, item in raw_clothes.items():
            slot_s = str(slot)
            item_s = str(item)
            if slot_s in CLOTHING_SLOTS and CLOTHING_ITEM_SLOT.get(item_s) == slot_s:
                worn[slot_s] = item_s
        inv.equipped_clothing = worn
    from food_spoilage import apply_food_quality

    fq = data.get("food_quality")
    if isinstance(fq, dict):
        apply_food_quality(inv, fq)
    return inv


def _storage_to_dict(obj: Any) -> dict[str, Any]:
    from food_spoilage import serialize_food_quality

    data: dict[str, Any] = {key: int(getattr(obj, key, 0)) for key in _storage_keys()}
    fq = serialize_food_quality(obj)
    if fq:
        data["food_quality"] = fq
    return data


def _apply_storage(obj: Any, data: dict[str, Any]) -> None:
    data = _normalize_legacy_storage(data)
    for key in _storage_keys():
        setattr(obj, key, int(data.get(key, 0)))
    # Legacy migration.
    setattr(obj, LEGACY_HERB_PRODUCE, getattr(obj, LEGACY_HERB_PRODUCE) + int(data.get("herbs", 0)))
    setattr(
        obj,
        LEGACY_HERB_SEED,
        getattr(obj, LEGACY_HERB_SEED) + int(data.get("herb_seeds", 0)),
    )
    if hasattr(obj, "oak_saplings"):
        setattr(obj, "oak_saplings", getattr(obj, "oak_saplings") + int(data.get("saplings", 0)))
    from food_spoilage import apply_food_quality

    fq = data.get("food_quality")
    if isinstance(fq, dict):
        apply_food_quality(obj, fq)


def _feature_from_save(name: str, crop_kind: str | None = None) -> FeatureType:
    if name == "HERB" and "WILD_CROP" in FeatureType.__members__:
        # Scenic flower herbs stay HERB. Legacy anonymous HERB (or a known
        # farm/wild-crop kind) becomes WILD_CROP so it is not mis-read as sage
        # via the old HERB→always-sage harvest path.
        kind = str(crop_kind) if crop_kind else ""
        if kind:
            from crops import CROP_BY_KEY
            from wild_species import WILD_BY_KEY

            wild = WILD_BY_KEY.get(kind)
            if wild is not None and wild.feature == "HERB":
                return FeatureType.HERB
            if kind in CROP_BY_KEY or (
                wild is not None and wild.feature == "WILD_CROP"
            ):
                return FeatureType.WILD_CROP
            return FeatureType.HERB
        return FeatureType.WILD_CROP
    if name == "FIELD" and "FIELD" in FeatureType.__members__:
        return FeatureType.FIELD
    try:
        return FeatureType[name]
    except KeyError:
        return FeatureType.NONE


def _cell_to_dict(cell: Cell) -> dict[str, Any]:
    data: dict[str, Any] = {
        "terrain": cell.terrain.name,
        "feature": cell.feature.name,
        "disturbance": cell.disturbance,
        "growth_ticks": cell.growth_ticks,
        "deposit": cell.deposit,
        "meat_deposit": cell.meat_deposit,
        "hide_deposit": cell.hide_deposit,
        "fur_deposit": cell.fur_deposit,
        "feather_deposit": cell.feather_deposit,
        "fish_deposit": cell.fish_deposit,
    }
    crop_kind = getattr(cell, "crop_kind", None)
    if crop_kind is not None:
        data["crop_kind"] = crop_kind
    tree_species = getattr(cell, "tree_species", None)
    if tree_species is not None:
        data["tree_species"] = tree_species
    if getattr(cell, "tree_age_years", 0):
        data["tree_age_years"] = int(cell.tree_age_years)
    icon_variant = getattr(cell, "icon_variant", None)
    if icon_variant is not None:
        data["icon_variant"] = int(icon_variant)
    if getattr(cell, "terrain_cluster", 0):
        data["terrain_cluster"] = int(cell.terrain_cluster)
    shade = getattr(cell, "terrain_shade", 0.55)
    if abs(shade - 0.55) > 0.001:
        data["terrain_shade"] = float(shade)
    data["fertility"] = float(getattr(cell, "fertility", 0.8))
    texture = float(getattr(cell, "soil_texture", -1.0))
    if texture >= 0.0:
        data["soil_texture"] = max(0.0, min(1.0, texture))
    weeds = float(getattr(cell, "weeds", 0.0))
    if weeds > 0.001:
        data["weeds"] = weeds
    appearances = int(getattr(cell, "weed_appearances", 0) or 0)
    if appearances > 0:
        data["weed_appearances"] = appearances
    if getattr(cell, "compost_cycle_applied", False):
        data["compost_cycle_applied"] = True
    if getattr(cell, "mineral_cycle_applied", False):
        data["mineral_cycle_applied"] = True
    suppression = float(getattr(cell, "weed_suppression", 0.0) or 0.0)
    if suppression > 0.0:
        data["weed_suppression"] = suppression
    if getattr(cell, "repellant_season", None) is not None:
        data["repellant_season"] = str(cell.repellant_season)
    if getattr(cell, "path_worn", False):
        data["path_worn"] = True
    if getattr(cell, "ploughed", False):
        data["ploughed"] = True
    if cell.object_anchor_slot is not None:
        data["object_anchor_slot"] = int(cell.object_anchor_slot)
    if cell.meat_anchor_slot is not None:
        data["meat_anchor_slot"] = int(cell.meat_anchor_slot)
    if cell.fish_anchor_slot is not None:
        data["fish_anchor_slot"] = int(cell.fish_anchor_slot)
    if cell.hide_anchor_slot is not None:
        data["hide_anchor_slot"] = int(cell.hide_anchor_slot)
    if cell.fur_anchor_slot is not None:
        data["fur_anchor_slot"] = int(cell.fur_anchor_slot)
    if cell.feather_anchor_slot is not None:
        data["feather_anchor_slot"] = int(cell.feather_anchor_slot)
    if cell.extra_objects:
        data["extra_objects"] = [
            {
                "feature": obj.feature.name,
                "anchor_slot": int(obj.anchor_slot),
                "deposit": int(obj.deposit),
                "growth_ticks": int(obj.growth_ticks),
                "crop_kind": obj.crop_kind,
                "tree_species": obj.tree_species,
                "tree_age_years": int(obj.tree_age_years),
                "icon_variant": obj.icon_variant,
            }
            for obj in cell.extra_objects
        ]
    return data


def _cell_from_save(c: dict[str, Any], *, migrate_legacy_fertility: bool = False) -> Cell:
    terrain = TerrainType[c["terrain"]]
    path_worn = bool(c.get("path_worn", False))
    # Legacy saves stored worn trails as PATH terrain — restore a soft base.
    if terrain == TerrainType.PATH:
        terrain = TerrainType.GRASS
        path_worn = True
    crop_kind = c.get("crop_kind")
    cell = Cell(
        terrain=terrain,
        feature=_feature_from_save(c["feature"], crop_kind),
        disturbance=float(c.get("disturbance", 0.0)),
        growth_ticks=int(c.get("growth_ticks", 0)),
        deposit=int(c.get("deposit", 0)),
        meat_deposit=int(c.get("meat_deposit", 0)),
        hide_deposit=int(c.get("hide_deposit", 0)),
        fur_deposit=int(c.get("fur_deposit", 0)),
        feather_deposit=int(c.get("feather_deposit", 0)),
        fish_deposit=int(c.get("fish_deposit", 0)),
        path_worn=path_worn,
        ploughed=bool(c.get("ploughed", False)),
        tree_age_years=int(c.get("tree_age_years", 0)),
    )
    if crop_kind is not None:
        setattr(cell, "crop_kind", crop_kind)
    elif cell.feature in (FeatureType.CROP_HERB, FeatureType.WILD_CROP):
        setattr(cell, "crop_kind", "sage")
    # Repair scenic herbs that were previously forced to WILD_CROP on load.
    if cell.feature == FeatureType.WILD_CROP and getattr(cell, "crop_kind", None):
        from wild_species import WILD_BY_KEY

        wild = WILD_BY_KEY.get(str(cell.crop_kind))
        if wild is not None and wild.feature == "HERB":
            cell.feature = FeatureType.HERB
    tree_species = c.get("tree_species")
    if tree_species is not None:
        setattr(cell, "tree_species", str(tree_species))
    elif cell.feature in (FeatureType.TREE, FeatureType.SAPLING):
        setattr(cell, "tree_species", "oak")
    if c.get("icon_variant") is not None:
        cell.icon_variant = int(c["icon_variant"])
    if c.get("terrain_cluster") is not None:
        cell.terrain_cluster = int(c["terrain_cluster"])
    if c.get("terrain_shade") is not None:
        cell.terrain_shade = float(c["terrain_shade"])
    from soil import clamp01, fertility_base_for
    from settings import FERTILITY_SOIL_LEGACY
    from world import TerrainType as _TT

    if c.get("fertility") is not None:
        cell.fertility = clamp01(float(c["fertility"]))
        # Model A: healthy cultivated soil is 1.0. Shift legacy absolute values
        # that were authored against the old 0.8 soil baseline.
        if migrate_legacy_fertility and cell.terrain == _TT.SOIL:
            new_base = fertility_base_for(_TT.SOIL)
            legacy = float(FERTILITY_SOIL_LEGACY)
            if new_base > legacy + 1e-6:
                cell.fertility = clamp01(cell.fertility + (new_base - legacy))
    else:
        cell.fertility = fertility_base_for(cell.terrain)
    if c.get("soil_texture") is not None:
        cell.soil_texture = clamp01(float(c["soil_texture"]))
    else:
        cell.soil_texture = -1.0
    cell.weeds = clamp01(float(c.get("weeds", 0.0)))
    cell.weed_appearances = max(0, int(c.get("weed_appearances", 0) or 0))
    cell.compost_cycle_applied = bool(c.get("compost_cycle_applied", False))
    cell.mineral_cycle_applied = bool(c.get("mineral_cycle_applied", False))
    cell.weed_suppression = clamp01(float(c.get("weed_suppression", 0.0) or 0.0))
    raw_repellant_season = c.get("repellant_season")
    cell.repellant_season = str(raw_repellant_season) if raw_repellant_season else None
    raw_anchor = c.get("object_anchor_slot")
    if raw_anchor is not None:
        cell.object_anchor_slot = max(0, min(8, int(raw_anchor)))
    raw_meat_anchor = c.get("meat_anchor_slot")
    if raw_meat_anchor is not None:
        cell.meat_anchor_slot = max(0, min(8, int(raw_meat_anchor)))
    raw_fish_anchor = c.get("fish_anchor_slot")
    if raw_fish_anchor is not None:
        cell.fish_anchor_slot = max(0, min(8, int(raw_fish_anchor)))
    raw_hide_anchor = c.get("hide_anchor_slot")
    if raw_hide_anchor is not None:
        cell.hide_anchor_slot = max(0, min(8, int(raw_hide_anchor)))
    raw_fur_anchor = c.get("fur_anchor_slot")
    if raw_fur_anchor is not None:
        cell.fur_anchor_slot = max(0, min(8, int(raw_fur_anchor)))
    raw_feather_anchor = c.get("feather_anchor_slot")
    if raw_feather_anchor is not None:
        cell.feather_anchor_slot = max(0, min(8, int(raw_feather_anchor)))
    for raw_obj in c.get("extra_objects", []):
        if not isinstance(raw_obj, dict):
            continue
        obj_kind = raw_obj.get("crop_kind")
        feature = _feature_from_save(str(raw_obj.get("feature", "NONE")), obj_kind)
        if feature == FeatureType.NONE:
            continue
        cell.extra_objects.append(
            NaturalObject(
                feature=feature,
                anchor_slot=max(0, min(8, int(raw_obj.get("anchor_slot", 4)))),
                deposit=int(raw_obj.get("deposit", 0)),
                growth_ticks=int(raw_obj.get("growth_ticks", 0)),
                crop_kind=obj_kind,
                tree_species=raw_obj.get("tree_species"),
                tree_age_years=int(raw_obj.get("tree_age_years", 0)),
                icon_variant=(
                    int(raw_obj["icon_variant"])
                    if raw_obj.get("icon_variant") is not None
                    else None
                ),
            )
        )
    # Existing weed cover counts as this season's appearance so clearing
    # does not immediately restart another wave under the default cap of 1.
    if cell.weeds > 0.0 and cell.weed_appearances <= 0:
        cell.weed_appearances = 1
    return cell


def _serialize_height_corners(world: World) -> list[list[float]] | None:
    """Snapshot the heightfield if present and sized for this map."""
    world.ensure_height_corners()
    need_h = world.rows + 1
    need_w = world.cols + 1
    corners = world.height_corners
    if len(corners) != need_h or not corners or len(corners[0]) != need_w:
        return None
    return [[float(v) for v in row] for row in corners]


def _apply_height_corners(world: World, raw: Any) -> bool:
    """Restore saved height corners. Returns True if applied."""
    if not isinstance(raw, list) or not raw:
        return False
    need_h = world.rows + 1
    need_w = world.cols + 1
    if len(raw) != need_h:
        return False
    corners: list[list[float]] = []
    for row in raw:
        if not isinstance(row, list) or len(row) != need_w:
            return False
        corners.append([float(v) for v in row])
    world.height_corners = corners
    return True


def serialize_game(game: Game) -> dict[str, Any]:
    import settings as cfg

    world = game.world
    cells = [[_cell_to_dict(cell) for cell in row] for row in world.cells]
    buildings = []
    for b in game.buildings.values():
        bdata: dict[str, Any] = {
            "id": b.id,
            "kind": b.kind.name,
            "x": b.x,
            "y": b.y,
            "storage": _storage_to_dict(b),
            "capacity": b.capacity,
            "input_capacity": b.input_capacity,
            "output_capacity": b.output_capacity,
            "fuel_capacity": b.fuel_capacity,
            "seed_capacity": getattr(b, "seed_capacity", 0),
            "fuel_wood": b.fuel_wood,
            "item_caps": {k: int(v) for k, v in b.item_caps.items()},
            "item_mins": {k: int(v) for k, v in b.item_mins.items()},
            "market_demand": {k: int(v) for k, v in b.market_demand.items()},
            "market_supply_mins": {k: int(v) for k, v in b.market_supply_mins.items()},
            "market_supply_stocks": {
                k: int(v) for k, v in b.market_supply_stocks.items()
            },
            "market_demand_season": b.market_demand_season,
            "recipe_enabled": dict(b.recipe_enabled),
            "recipe_progress": dict(b.recipe_progress),
            "recipe_priority": {k: int(v) for k, v in b.recipe_priority.items()},
            "draw_task_type": b.draw_task_type.name,
            "work_mode": b.work_mode.name,
            "areas": [
                {
                    "x0": a.x0,
                    "y0": a.y0,
                    "x1": a.x1,
                    "y1": a.y1,
                    "task_type": a.task_type.name,
                    "building_id": a.building_id,
                }
                for a in b.areas
            ],
            "fields": [
                {
                    "id": f.id,
                    "x0": f.x0,
                    "y0": f.y0,
                    "x1": f.x1,
                    "y1": f.y1,
                    "name": f.name,
                    "plans": [
                        {
                            "id": p.id,
                            "x0": p.x0,
                            "y0": p.y0,
                            "x1": p.x1,
                            "y1": p.y1,
                            "crop_kind": p.crop_kind,
                            "field_id": p.field_id,
                        }
                        for p in f.plans
                    ],
                }
                for f in getattr(b, "fields", [])
            ],
            "plans": [
                {
                    "id": p.id,
                    "x0": p.x0,
                    "y0": p.y0,
                    "x1": p.x1,
                    "y1": p.y1,
                    "crop_kind": p.crop_kind,
                    "field_id": p.field_id,
                }
                for p in getattr(b, "plans", [])
            ],
            "plot_w": getattr(b, "plot_w", 1),
            "plot_h": getattr(b, "plot_h", 1),
            "next_field_id": getattr(b, "next_field_id", 1),
            "next_plan_id": getattr(b, "next_plan_id", 1),
            "parent_building_id": getattr(b, "parent_building_id", None),
        }
        if hasattr(b, "crop_kind"):
            bdata["crop_kind"] = b.crop_kind
        if b.kind.name in ("FIELD", "ORCHARD"):
            bdata["crop_health"] = float(getattr(b, "crop_health", 1.0))
            bdata["pest_boost"] = float(getattr(b, "pest_boost", 0.0))
            bdata["fence_edges"] = [list(edge) for edge in sorted(b.fence_edges)]
            bdata["fence_gates"] = [list(cell) for cell in sorted(b.fence_gates)]
        buildings.append(bdata)
    villagers = []
    for v in game.villagers:
        villagers.append(
            {
                "id": v.id,
                "x": v.x,
                "y": v.y,
                "inventory": _inv_to_dict(v.inventory),
                "state": v.state.name,
                "building_id": v.building_id,
                "assigned_to_home": v.assigned_to_home,
                "move_cooldown": v.move_cooldown,
                "work_cooldown": v.work_cooldown,
                "work_in_progress": bool(getattr(v, "work_in_progress", False)),
                "work_anchor": list(v.work_anchor) if getattr(v, "work_anchor", None) else None,
                # Preserve a partial craft's sticky worker assignment.  Building
                # recipe_progress is saved separately; this prevents a reload
                # from immediately choosing a different ready recipe.
                "craft_recipe_name": v.craft_recipe_name,
                "target": list(v.target) if v.target else None,
                "haul_building_id": v.haul_building_id,
                "hunt_animal_id": v.hunt_animal_id,
                "hunt_colony_id": v.hunt_colony_id,
                "hunt_meat_pos": list(v.hunt_meat_pos) if v.hunt_meat_pos else None,
                "fish_target_id": v.fish_target_id,
                "fish_catch_pos": list(v.fish_catch_pos) if v.fish_catch_pos else None,
                "fish_post_pos": list(v.fish_post_pos) if v.fish_post_pos else None,
                "fish_bait_ticks": int(getattr(v, "fish_bait_ticks", 0)),
                "forage_colony_id": v.forage_colony_id,
                "construction_id": v.construction_id,
                "priorities": [p.name for p in v.priorities],
                "seasonal_priorities": bool(getattr(v, "seasonal_priorities", False)),
                "season_priorities": {
                    k: [p.name for p in row]
                    for k, row in getattr(v, "season_priorities", {}).items()
                },
                "workplace_slots": list(getattr(v, "workplace_slots", []) or []),
                "season_workplace_slots": {
                    k: list(row)
                    for k, row in getattr(v, "season_workplace_slots", {}).items()
                },
                "workplace_plan": [
                    s.to_save() for s in getattr(v, "workplace_plan", []) or []
                ],
                "season_workplace_plan": {
                    k: [s.to_save() for s in row]
                    for k, row in getattr(v, "season_workplace_plan", {}).items()
                },
                "satiation": round(v.satiation, 4),
                "ration_mode": v.ration_mode.name,
                "seeking_food": v.seeking_food,
                "last_meal": list(v.last_meal),
                "food_walk_mult": round(v.food_walk_mult, 4),
                "food_work_mult": round(v.food_work_mult, 4),
                "food_hunger_mult": round(v.food_hunger_mult, 4),
                "name": v.name,
                "energy": round(v.energy, 4),
                "happiness": round(v.happiness, 4),
                "underlying_happiness": round(
                    float(
                        getattr(v, "underlying_happiness", None)
                        if getattr(v, "underlying_happiness", None) is not None
                        else v.happiness
                    ),
                    4,
                ),
                "break_ticks_left": int(getattr(v, "break_ticks_left", 0) or 0),
                "break_cooldown_ticks": int(getattr(v, "break_cooldown_ticks", 0) or 0),
                "break_kind": str(getattr(v, "break_kind", "") or ""),
                "break_reason": str(getattr(v, "break_reason", "") or ""),
                "break_thought": str(getattr(v, "break_thought", "") or ""),
                "break_return_pos": (
                    list(getattr(v, "break_return_pos"))
                    if getattr(v, "break_return_pos", None)
                    else None
                ),
                "base_break_day": int(getattr(v, "base_break_day", -1)),
                "housed": v.housed,
                "housing_id": v.housing_id,
                "housing_need": v.housing_need,
                "required_foods": list(v.required_foods),
                "favourite_foods": list(v.favourite_foods),
                "favourite_is_junk": v.favourite_is_junk,
                "required_workplace": str(getattr(v, "required_workplace", "") or ""),
                "signing_fee": int(getattr(v, "signing_fee", 0) or 0),
                "join_fee_paid": v.join_fee_paid,
                "seasons_without_reqs": v.seasons_without_reqs,
                "coins_paid_total": int(getattr(v, "coins_paid_total", 0) or 0),
                "season_pay_due": int(getattr(v, "season_pay_due", 0) or 0),
                "happiness_events": [
                    {
                        "icon": str(imp.get("icon", "")),
                        "label": str(imp.get("label", "")),
                        "delta": int(round(float(imp.get("delta", 0)))),
                        "day": int(imp.get("day", 0)),
                    }
                    for imp in (
                        getattr(v, "happiness_events", None)
                        or getattr(v, "happiness_impacts", None)
                        or []
                    )
                    if isinstance(imp, dict)
                ],
                "happiness_temporary": [
                    {
                        "channel": str(m.get("channel", "")),
                        "peak": float(m.get("peak", 0)),
                        "ticks_left": int(m.get("ticks_left", 0)),
                        "ticks_total": int(m.get("ticks_total", 0)),
                        "icon": str(m.get("icon", "")),
                        "label": str(m.get("label", "")),
                        "source": str(m.get("source", "")),
                        "day": int(m.get("day", 0) or 0),
                    }
                    for m in (getattr(v, "happiness_temporary", None) or [])
                    if isinstance(m, dict)
                ],
                "happiness_modifiers": [
                    {
                        "icon": str(m.get("icon", "")),
                        "label": str(m.get("label", "")),
                        "peak": float(m.get("peak", 0)),
                        "remaining": float(m.get("remaining", 0)),
                        "ticks_left": int(m.get("ticks_left", 0)),
                        "ticks_total": int(m.get("ticks_total", 0)),
                        "until_meal": bool(m.get("until_meal", False)),
                        "points": int(m.get("points", 0)),
                        "channel": str(m.get("channel", "")),
                    }
                    for m in (getattr(v, "happiness_modifiers", None) or [])
                    if isinstance(m, dict)
                ],
                "low_happiness_days": round(v.low_happiness_days, 4),
                "low_happiness_seasons": int(
                    getattr(v, "low_happiness_seasons", 0) or 0
                ),
                "skills": skills_to_dict(v.skills) if v.skills else {},
                "community_id": v.community_id,
                "virtues": list(getattr(v, "virtues", []) or []),
                "vices": list(getattr(v, "vices", []) or []),
                "portrait_seed": int(getattr(v, "portrait_seed", 0) or 0),
                "template_id": str(getattr(v, "template_id", "") or ""),
                "tier": int(getattr(v, "tier", 1) or 1),
            }
        )
    sites = [
        {
            "id": s.id,
            "x": s.x,
            "y": s.y,
            "kind": s.kind.name,
            "need_wood": s.need_wood,
            "need_rock": s.need_rock,
            "need_logs": s.need_logs,
            "need_hardwood": s.need_hardwood,
            "have_wood": s.have_wood,
            "have_rock": s.have_rock,
            "have_logs": s.have_logs,
            "have_hardwood": s.have_hardwood,
            "build_progress": s.build_progress,
            "plot_w": getattr(s, "plot_w", 1),
            "plot_h": getattr(s, "plot_h", 1),
            "phase": getattr(s, "phase", "build"),
            "relocate_pair_id": getattr(s, "relocate_pair_id", None),
            "relocate_from_building_id": getattr(s, "relocate_from_building_id", None),
            "source_building_id": getattr(s, "source_building_id", None),
            "parent_building_id": getattr(s, "parent_building_id", None),
            "fence_field_id": getattr(s, "fence_field_id", None),
            "fence_edges": list(getattr(s, "fence_edges", ())),
        }
        for s in game.construction_sites.values()
    ]
    from wildlife import AnimalKind

    from seasons import TICKS_PER_DAY

    animals = [
        {
            "id": a.id,
            "x": a.x,
            "y": a.y,
            "world_x": round(float(a.world_x if a.world_x is not None else a.x), 4),
            "world_y": round(float(a.world_y if a.world_y is not None else a.y), 4),
            "kind": a.kind.name,
            "sex": a.sex.name,
            "patch_id": a.patch_id,
            "mate_id": a.mate_id,
            "move_cooldown": a.move_cooldown,
            "migrate_home_id": a.migrate_home_id,
            "migrate_target": list(a.migrate_target) if a.migrate_target else None,
            "migrated_this_year": a.migrated_this_year,
            "scare_from": list(a.scare_from) if a.scare_from else None,
            "scare_steps": a.scare_steps,
            "facing_right": bool(getattr(a, "facing_right", True)),
            "crop_target": list(a.crop_target) if a.crop_target else None,
            "crop_arrived_day": a.crop_arrived_day,
            "age_days": round(float(getattr(a, "age_days", 0.0)), 2),
        }
        for a in game.wildlife.animals
        if a.kind in (AnimalKind.DEER, AnimalKind.BOAR, AnimalKind.OWL, AnimalKind.HAWK)
    ]
    colonies = [
        {
            "id": c.id,
            "kind": c.kind.name,
            "x": c.x,
            "y": c.y,
            "level": c.level,
            "habitat_id": c.habitat_id,
            "harvest_cooldown": c.harvest_cooldown,
        }
        for c in game.wildlife.colonies
    ]
    fish = [
        {
            "id": f.id,
            "x": f.x,
            "y": f.y,
            "world_x": round(float(f.world_x if f.world_x is not None else f.x), 4),
            "world_y": round(float(f.world_y if f.world_y is not None else f.y), 4),
            "kind": f.kind.name,
            "move_cooldown": f.move_cooldown,
        }
        for f in game.fish.fish
    ]
    wolf_packs = [
        {
            "id": p.id,
            "kind": p.kind.name,
            "x": p.x,
            "y": p.y,
            "world_x": round(float(p.world_x if p.world_x is not None else p.x), 4),
            "world_y": round(float(p.world_y if p.world_y is not None else p.y), 4),
            "fed_days_remaining": p.fed_days_remaining,
            "move_cooldown": p.move_cooldown,
            "last_prey": p.last_prey,
            "last_meal_day": p.last_meal_day,
            "activity": p.activity,
            "members": [
                {
                    "sex": m.sex.name,
                    "x": m.x,
                    "y": m.y,
                    "world_x": round(float(m.world_x if m.world_x is not None else m.x), 4),
                    "world_y": round(float(m.world_y if m.world_y is not None else m.y), 4),
                    "move_cooldown": m.move_cooldown,
                }
                for m in p.members
            ],
        }
        for p in game.wildlife.wolf_packs
    ]
    payload: dict[str, Any] = {
        "version": SAVE_VERSION,
        "soil_fertility_model": 2,
        "grid": {"cols": world.cols, "rows": world.rows, "seed": world.seed},
        "display": {
            "grid_cols": cfg.GRID_COLS,
            "grid_rows": cfg.GRID_ROWS,
        },
        "sim_speed": game.sim_speed,
        "control_mode": str(getattr(game, "control_mode", "dog")),
        "ticks_per_day": getattr(game, "ticks_per_day", TICKS_PER_DAY),
        "season": game.season.name,
        "calendar_day": game.calendar_day,
        "day_tick": game.day_tick,
        "calendar_policy": getattr(game, "calendar_policy", None).to_dict()
        if getattr(game, "calendar_policy", None) is not None
        else None,
        "world": {
            "cells": cells,
            "home_pos": list(world.home_pos),
            "workstation_pos": list(world.workstation_pos),
            "start_pos": list(world.start_pos),
            "sprout_timer": world._sprout_timer,
            "mushroom_timer": world._mushroom_timer,
            "berry_spread_timer": world._berry_spread_timer,
            "herb_timer": world._herb_timer,
            "height_corners": _serialize_height_corners(world),
        },
        "player": {
            "x": game.player.x,
            "y": game.player.y,
            "world_x": round(float(game.player.world_x), 4),
            "world_y": round(float(game.player.world_y), 4),
            "discovered_cells": [
                [x, y]
                for x, y in sorted(
                    game.discovered_cells, key=lambda p: (p[1], p[0])
                )
            ],
            "inventory": _inv_to_dict(game.player.inventory),
            "satiation": float(getattr(game.player, "satiation", 0.75)),
            "energy": float(getattr(game.player, "energy", 1.0)),
            "happiness": float(getattr(game.player, "happiness", 0.7)),
            "last_meal": list(getattr(game.player, "last_meal", []) or []),
            "food_walk_mult": float(getattr(game.player, "food_walk_mult", 1.0)),
            "food_work_mult": float(getattr(game.player, "food_work_mult", 1.0)),
            "food_hunger_mult": float(getattr(game.player, "food_hunger_mult", 1.0)),
            "ration_mode": getattr(
                getattr(game.player, "ration_mode", None), "name", "NORMAL"
            ),
            "auto_eat": bool(getattr(game.player, "auto_eat", False)),
            "skills": skills_to_dict(game.player.skills) if game.player.skills else {},
        },
        "home_storage": _storage_to_dict(game.home_storage),
        "regional_wealth": int(getattr(game, "regional_wealth", 0)),
        "buildings": buildings,
        "construction_sites": sites,
        "villagers": villagers,
        "wildlife": {
            "animals": animals,
            "colonies": colonies,
            "wolf_packs": wolf_packs,
            "next_id": game.wildlife.next_id,
            "next_colony_id": game.wildlife.next_colony_id,
            "next_wolf_pack_id": game.wildlife.next_wolf_pack_id,
            "growth_timer": game.wildlife.growth_timer,
            "last_breed_year": int(getattr(game.wildlife, "_last_breed_year", -1)),
        },
        "fish": {
            "fish": fish,
            "next_id": game.fish.next_id,
            "growth_timer": game.fish.growth_timer,
        },
        "next_villager_id": game.next_villager_id,
        "next_building_id": game.next_building_id,
        "next_construction_id": game.next_construction_id,
        "scenario": game.scenario.to_dict() if hasattr(game,"scenario") else None,
        "place_kind": game.place_kind.name if game.place_kind else None,
        "overlay_mode": game.overlay_mode.name,
        "communities": [c.to_dict() for c in getattr(game, "communities", [])],
        "hire_candidates": [c.to_dict() for c in getattr(game, "hire_candidates", [])],
        "next_community_id": int(getattr(game, "next_community_id", 1)),
        "next_hire_id": int(getattr(game, "next_hire_id", 1)),
        "sociopolitical": (
            game.political.to_dict() if getattr(game, "political", None) is not None else None
        ),
    }
    if hasattr(game, "env_maps"):
        payload["env_maps"] = game.env_maps.to_save_dict()
    if hasattr(game, "weather"):
        payload["weather"] = game.weather.to_dict()
    if hasattr(game, "field_crop_kind"):
        payload["field_crop_kind"] = game.field_crop_kind
    if hasattr(game, "resource_history"):
        payload["resource_history"] = game.resource_history.to_dict()
    if hasattr(game, "_path_traffic") and game._path_traffic:
        payload["path_traffic"] = [
            [int(x), int(y), float(w)] for (x, y), w in game._path_traffic.items()
        ]
    return payload


def _migrate_legacy_fields(game: Game) -> None:
    """Promote nested Farm.fields / old Field areas into standalone Field buildings."""
    from world import FeatureType

    # Farm.areas → Field buildings (sage plan covering whole rectangle).
    for farm in list(game.buildings.values()):
        if farm.kind != BuildingKind.FARM or not farm.areas:
            continue
        for area in farm.areas:
            left, top, right, bottom = area.normalised()
            _spawn_field_building(
                game,
                left,
                top,
                right - left + 1,
                bottom - top + 1,
                plans=[("sage", left, top, right, bottom)],
            )
        farm.areas.clear()

    # Nested Farm.fields → Field buildings.
    for farm in list(game.buildings.values()):
        if farm.kind != BuildingKind.FARM or not farm.fields:
            continue
        for field_obj in farm.fields:
            left, top, right, bottom = field_obj.normalised()
            plan_specs = [
                (p.crop_kind, *p.normalised())
                for p in field_obj.plans
            ]
            _spawn_field_building(
                game,
                left,
                top,
                right - left + 1,
                bottom - top + 1,
                plans=plan_specs,
            )
        farm.fields.clear()

    # Old Field buildings with areas but no plot_w: expand plot from areas.
    for building in list(game.buildings.values()):
        if not building.is_field_plot:
            continue
        if building.plans:
            continue
        if building.areas:
            # Use first area as plot, rest as additional plan rects.
            first = building.areas[0]
            left, top, right, bottom = first.normalised()
            building.x, building.y = left, top
            building.plot_w = right - left + 1
            building.plot_h = bottom - top + 1
            crop = building.crop_kind or "sage"
            for area in building.areas:
                al, at, ar, ab = area.normalised()
                building.add_field_plan(al, at, ar, ab, crop)
            building.areas.clear()
            cell = game.world.get_cell(building.x, building.y)
            if cell is not None and cell.feature == FeatureType.FIELD:
                cell.feature = FeatureType.NONE
        elif getattr(building, "plot_w", 1) <= 1 and getattr(building, "plot_h", 1) <= 1:
            # 1×1 footprint Field with crop_kind → single-cell plan.
            if not building.plans and building.crop_kind:
                building.plot_w = 1
                building.plot_h = 1
                building.add_field_plan(
                    building.x, building.y, building.x, building.y, building.crop_kind
                )


def _migrate_building_footprints(game: Game) -> None:
    """Expand legacy 1×1 non-field buildings to the current square footprint."""
    from entities import default_building_plot
    from world import FeatureType

    FEATURE_FOR_BUILDING = {
        BuildingKind.HOME: FeatureType.HOME,
        BuildingKind.WORKSTATION: FeatureType.WORKSTATION,
        BuildingKind.FORESTER: FeatureType.FORESTER,
        BuildingKind.MASON: FeatureType.MASON,
        BuildingKind.HUNTER: FeatureType.HUNTER,
        BuildingKind.FORAGER: FeatureType.FORAGER,
        BuildingKind.FISHER: FeatureType.FISHER,
        BuildingKind.FARM: FeatureType.FARM,
        BuildingKind.MILL: FeatureType.MILL,
        BuildingKind.KITCHEN: FeatureType.KITCHEN,
        BuildingKind.FIRE: FeatureType.FIRE,
        BuildingKind.CRAFT_BENCH: FeatureType.CRAFT_BENCH,
        BuildingKind.ALCHEMIST: FeatureType.ALCHEMIST,
        BuildingKind.TAILOR: FeatureType.TAILOR,
        BuildingKind.COBBLER: FeatureType.COBBLER,
        BuildingKind.MARKET: FeatureType.MARKET,
        BuildingKind.TENT: FeatureType.TENT,
        BuildingKind.HOUSE_SMALL: FeatureType.HOUSE_SMALL,
        BuildingKind.HOUSE: FeatureType.HOUSE,
        BuildingKind.BARN: FeatureType.BARN,
        BuildingKind.COMPOST_HEAP: FeatureType.COMPOST_HEAP,
        BuildingKind.PANTRY: FeatureType.PANTRY,
        BuildingKind.CELLAR: FeatureType.CELLAR,
        BuildingKind.DRYING_RACK: FeatureType.DRYING_RACK,
    }

    for building in list(game.buildings.values()):
        if building.is_field_plot:
            continue
        pw, ph = default_building_plot(building.kind)
        if building.plot_w == pw and building.plot_h == ph:
            # Still refresh pads in case a prior save lost them.
            feature = FEATURE_FOR_BUILDING.get(building.kind)
            if feature is not None:
                game.world.claim_structure_footprint(
                    building.x, building.y, pw, ph, feature
                )
            continue
        # Legacy saves stored the glyph cell as x/y (1×1). Treat as centre.
        if building.plot_w <= 1 and building.plot_h <= 1:
            cx, cy = building.x, building.y
        else:
            cx, cy = building.center_cell()
        building.plot_w, building.plot_h = pw, ph
        building.x = cx - pw // 2
        building.y = cy - ph // 2
        feature = FEATURE_FOR_BUILDING.get(building.kind)
        if feature is not None:
            game.world.claim_structure_footprint(
                building.x, building.y, pw, ph, feature
            )
        if building.kind == BuildingKind.HOME:
            game.world.home_pos = (cx, cy)
        elif building.kind == BuildingKind.WORKSTATION:
            game.world.workstation_pos = (cx, cy)

    for site in list(game.construction_sites.values()):
        if is_field_plot_kind(site.kind):
            continue
        pw, ph = default_building_plot(site.kind)
        if site.plot_w == pw and site.plot_h == ph:
            game.world.claim_structure_footprint(
                site.x, site.y, pw, ph, FeatureType.CONSTRUCTION_SITE
            )
            continue
        if site.plot_w <= 1 and site.plot_h <= 1:
            cx, cy = site.x, site.y
        else:
            cx, cy = site.center_cell()
        site.plot_w, site.plot_h = pw, ph
        site.x = cx - pw // 2
        site.y = cy - ph // 2
        game.world.claim_structure_footprint(
            site.x, site.y, pw, ph, FeatureType.CONSTRUCTION_SITE
        )


def _spawn_field_building(
    game: Game,
    x: int,
    y: int,
    plot_w: int,
    plot_h: int,
    *,
    plans: list[tuple[str, int, int, int, int]] | None = None,
) -> Building:
    from world import FeatureType

    building = Building(
        id=game.next_building_id,
        kind=BuildingKind.FIELD,
        x=x,
        y=y,
        plot_w=max(1, plot_w),
        plot_h=max(1, plot_h),
        draw_task_type=TaskType.FARM_FIELD,
        work_mode=WorkMode.COLLECT,
    )
    building.sync_draw_task_from_mode()
    game.next_building_id += 1
    game.buildings[building.id] = building
    for spec in plans or []:
        crop_kind, x0, y0, x1, y1 = spec
        building.add_field_plan(x0, y0, x1, y1, crop_kind)
    # Place no map glyph — Field is an outline-only plot.
    cell = game.world.get_cell(x, y)
    if cell is not None and cell.feature == FeatureType.FIELD:
        cell.feature = FeatureType.NONE
    return building


def apply_save(game: Game, data: dict[str, Any]) -> None:
    from indicators import OverlayMode, build_overlay_grid
    from settings import BUILDING_STORAGE_CAPACITY, RANDOM_SEED

    if hasattr(game, "_player_inside_building_id"):
        game._player_inside_building_id = None

    if int(data.get("version", 0)) != SAVE_VERSION:
        raise ValueError(f"Unsupported save version: {data.get('version')}")

    grid = data["grid"]
    cols, rows = int(grid["cols"]), int(grid["rows"])
    # World size comes from the save; keep the current window / viewport
    # (configure_for_display). Camera pans/zooms over maps of any size.
    if len(data["world"]["cells"]) != rows or len(data["world"]["cells"][0]) != cols:
        raise ValueError(
            f"Save cell grid {len(data['world']['cells'][0])}x{len(data['world']['cells'])} "
            f"does not match {cols}x{rows}."
        )

    world_data = data["world"]
    world = World(
        cols=cols,
        rows=rows,
        seed=int(grid.get("seed", RANDOM_SEED)),
    )
    # World.__init__ calls generate(); replace with saved cells.
    cells: list[list[Cell]] = []
    migrate_legacy_fertility = int(data.get("soil_fertility_model", 1)) < 2
    for row in world_data["cells"]:
        cells.append([
            _cell_from_save(c, migrate_legacy_fertility=migrate_legacy_fertility)
            for c in row
        ])
    world.cells = cells
    world.reconcile_flora_with_catalogue()
    world.ensure_tree_ages()
    world.update_forest_floor()
    # Legacy saves lack subclusters — carve them so seasonal masks look right.
    if not any(
        cell.terrain_cluster
        for row in world.cells
        for cell in row
    ):
        world._paint_terrain_subclusters(random.Random(world.seed + 77))
    # Legacy saves lack soil_texture — generate once from the world seed.
    from soil_texture import ensure_soil_texture

    ensure_soil_texture(world)
    world.valley_path = world._valley_river_path()
    world.lake_cx, world.lake_cy, world.lake_rx, world.lake_ry = world._valley_lake_params()
    # Prefer painted/saved heights; older saves rebuild from the valley map.
    if not _apply_height_corners(world, world_data.get("height_corners")):
        world._build_valley_heightfield()
    world.bump_terrain()
    world.home_pos = tuple(world_data["home_pos"])  # type: ignore[assignment]
    world.workstation_pos = tuple(world_data["workstation_pos"])  # type: ignore[assignment]
    world.start_pos = tuple(world_data["start_pos"])  # type: ignore[assignment]
    world._sprout_timer = int(world_data.get("sprout_timer", world._sprout_timer))
    world._mushroom_timer = int(world_data.get("mushroom_timer", world._mushroom_timer))
    world._berry_spread_timer = int(
        world_data.get("berry_spread_timer", world._berry_spread_timer)
    )
    world._herb_timer = int(world_data.get("herb_timer", world._herb_timer))

    game.world = world
    if hasattr(game, "_invalidate_fishing_shore_cache"):
        game._invalidate_fishing_shore_cache()
    game.height_sample = generate_height_sample(
        world.cols,
        world.rows,
        seed=world.seed,
        corners=world.height_corners,
    )
    if hasattr(game, "_invalidate_height_sample_cache"):
        game._invalidate_height_sample_cache()
    player_data = data["player"]
    game.player.x = int(player_data["x"])
    game.player.y = int(player_data["y"])
    game.player.world_x = float(player_data.get("world_x", game.player.x))
    game.player.world_y = float(player_data.get("world_y", game.player.y))
    saved_discovery = player_data.get("discovered_cells")
    game.discovered_cells = {
        (int(pos[0]), int(pos[1]))
        for pos in (saved_discovery or [])
        if isinstance(pos, (list, tuple)) and len(pos) == 2
    }
    # Older saves begin with a normal reveal around their loaded player position.
    game._reveal_around_player()
    game.player.inventory = _inv_from_dict(player_data["inventory"])
    game.player.satiation = float(player_data.get("satiation", 0.75))
    game.player.energy = float(player_data.get("energy", 1.0))
    game.player.happiness = float(player_data.get("happiness", 0.7))
    game.player.last_meal = [
        str(k) for k in (player_data.get("last_meal") or []) if k
    ][:3]
    game.player.food_walk_mult = float(player_data.get("food_walk_mult", 1.0))
    game.player.food_work_mult = float(player_data.get("food_work_mult", 1.0))
    game.player.food_hunger_mult = float(player_data.get("food_hunger_mult", 1.0))
    try:
        from entities import RationMode

        game.player.ration_mode = RationMode[str(player_data.get("ration_mode", "NORMAL"))]
    except KeyError:
        from entities import RationMode

        game.player.ration_mode = RationMode.NORMAL
    game.player.auto_eat = bool(player_data.get("auto_eat", False))
    from society import ensure_skills, player_skills

    if player_data.get("skills"):
        game.player.skills = ensure_skills(
            skills_from_dict(player_data.get("skills")), player=True
        )
    else:
        # Pre-skill saves: start the player at the default baseline.
        game.player.skills = player_skills()
    game.player.move_cooldown = 0
    game.player.work_cooldown = 0
    from entities import snap_entity_visual

    snap_entity_visual(game.player)
    _apply_storage(game.home_storage, data["home_storage"])
    game.regional_wealth = max(0, int(data.get("regional_wealth", 0) or 0))

    game.buildings.clear()
    for bdata in data.get("buildings", []):
        kind = BuildingKind[bdata["kind"]]
        default_task = {
            BuildingKind.FORESTER: TaskType.FULL_MANAGE,
            BuildingKind.MASON: TaskType.COLLECT_ROCKS,
            BuildingKind.HUNTER: TaskType.HUNT,
            BuildingKind.FISHER: TaskType.FISH,
            BuildingKind.FORAGER: TaskType.FULL_FORAGE,
            BuildingKind.FARM: TaskType.FARM_FIELD,
            BuildingKind.FIELD: TaskType.FARM_FIELD,
            BuildingKind.ORCHARD: TaskType.FARM_FIELD,
            BuildingKind.MILL: TaskType.FULL_FORAGE,
            BuildingKind.KITCHEN: TaskType.FULL_FORAGE,
            BuildingKind.FIRE: TaskType.FULL_FORAGE,
            BuildingKind.CRAFT_BENCH: TaskType.FULL_FORAGE,
            BuildingKind.ALCHEMIST: TaskType.FULL_FORAGE,
            BuildingKind.TAILOR: TaskType.FULL_FORAGE,
            BuildingKind.COBBLER: TaskType.FULL_FORAGE,
            BuildingKind.MARKET: TaskType.FULL_FORAGE,
        }.get(kind, TaskType.FULL_MANAGE)
        raw_task = bdata.get("draw_task_type")
        if raw_task is None:
            draw_task = default_task
        else:
            draw_task = TaskType[raw_task]
            # Older saves used chop-only as the forester default.
            if (
                kind == BuildingKind.FORESTER
                and draw_task == TaskType.CHOP_TREES
                and not bdata.get("areas")
            ):
                draw_task = TaskType.FULL_MANAGE
        raw_mode = bdata.get("work_mode")
        if raw_mode == "BOTH":
            work_mode = WorkMode.ALL
        elif raw_mode is not None:
            try:
                work_mode = WorkMode[str(raw_mode)]
            except KeyError:
                work_mode = Building.work_mode_from_task(kind, draw_task)
        else:
            work_mode = Building.work_mode_from_task(kind, draw_task)
        if kind == BuildingKind.FARM:
            if raw_mode is None:
                work_mode = WorkMode.ALL
            # else keep loaded Collect / Plant / Both
        elif kind not in (BuildingKind.FORESTER, BuildingKind.FORAGER, BuildingKind.FIELD, BuildingKind.ORCHARD):
            work_mode = WorkMode.COLLECT
        building = Building(
            id=int(bdata["id"]),
            kind=kind,
            x=int(bdata["x"]),
            y=int(bdata["y"]),
            capacity=int(bdata.get("capacity", BUILDING_STORAGE_CAPACITY)),
            input_capacity=int(bdata.get("input_capacity", 0)),
            output_capacity=int(bdata.get("output_capacity", 0)),
            fuel_capacity=int(bdata.get("fuel_capacity", 0)),
            seed_capacity=int(bdata.get("seed_capacity", 0)),
            fuel_wood=int(bdata.get("fuel_wood", 0)),
            draw_task_type=draw_task,
            work_mode=work_mode,
            plot_w=max(1, int(bdata.get("plot_w", 1))),
            plot_h=max(1, int(bdata.get("plot_h", 1))),
            parent_building_id=(
                int(bdata["parent_building_id"])
                if bdata.get("parent_building_id") is not None
                else None
            ),
        )
        # Settings are the source of truth for pool sizes (avoids stale save caps).
        from entities import apply_building_storage

        apply_building_storage(building)
        raw_caps = bdata.get("item_caps") or {}
        if isinstance(raw_caps, dict):
            building.item_caps = {
                str(k): max(1, int(v))
                for k, v in raw_caps.items()
                if v is not None and int(v) > 0
            }
        raw_mins = bdata.get("item_mins") or {}
        if isinstance(raw_mins, dict):
            building.item_mins = {
                str(k): max(1, int(v))
                for k, v in raw_mins.items()
                if v is not None and int(v) > 0
            }
        if kind == BuildingKind.FORESTER and not building.item_mins:
            from entities import default_item_mins

            building.item_mins = dict(default_item_mins(kind))
        raw_demand = bdata.get("market_demand") or {}
        raw_supply = bdata.get("market_supply_mins") or {}
        raw_provide = bdata.get("market_provide") or {}
        if isinstance(raw_demand, dict):
            building.market_demand = {
                str(k): max(0, int(v)) for k, v in raw_demand.items() if int(v) > 0
            }
        if isinstance(raw_supply, dict) and raw_supply:
            building.market_supply_mins = {
                str(k): max(0, int(v)) for k, v in raw_supply.items()
            }
        elif isinstance(raw_provide, dict) and raw_provide:
            # Migrate old "provide quota" into enabled supply with min 0.
            building.market_supply_mins = {
                str(k): 0 for k, v in raw_provide.items() if int(v) > 0
            }
        raw_stocks = bdata.get("market_supply_stocks") or {}
        if isinstance(raw_stocks, dict) and raw_stocks:
            building.market_supply_stocks = {
                str(k): max(0, int(v)) for k, v in raw_stocks.items()
            }
        # Keep stock targets aligned with enabled supply keys.
        for key in list(building.market_supply_mins):
            building.market_supply_stocks.setdefault(key, 0)
        for key in list(building.market_supply_stocks):
            if key not in building.market_supply_mins:
                building.market_supply_stocks.pop(key, None)
        season_name = bdata.get("market_demand_season")
        building.market_demand_season = (
            str(season_name) if season_name else None
        )
        raw_enabled = bdata.get("recipe_enabled") or {}
        raw_progress = bdata.get("recipe_progress") or {}
        raw_priority = bdata.get("recipe_priority") or {}
        raw_enabled, raw_progress = _migrate_recipe_state(raw_enabled, raw_progress)
        if building.has_recipes() or building.split_recipes():
            building.ensure_recipe_state()
            from entities import RECIPE_PRIORITY_DEFAULT, RECIPE_PRIORITY_MAX, RECIPE_PRIORITY_MIN

            for name in list(building.recipe_enabled):
                if name in raw_enabled:
                    building.recipe_enabled[name] = bool(raw_enabled[name])
                if name in raw_progress:
                    building.recipe_progress[name] = max(0, int(raw_progress[name]))
                if name in raw_priority:
                    building.recipe_priority[name] = max(
                        RECIPE_PRIORITY_MIN,
                        min(RECIPE_PRIORITY_MAX, int(raw_priority[name])),
                    )
            for recipe in building.split_recipes():
                if recipe.name in raw_enabled:
                    building.recipe_enabled[recipe.name] = bool(raw_enabled[recipe.name])
                if recipe.name in raw_progress:
                    building.recipe_progress[recipe.name] = max(0, int(raw_progress[recipe.name]))
                if recipe.name in raw_priority:
                    building.recipe_priority[recipe.name] = max(
                        RECIPE_PRIORITY_MIN,
                        min(RECIPE_PRIORITY_MAX, int(raw_priority[recipe.name])),
                    )
        if is_field_plot_kind(kind):
            building.crop_kind = str(bdata.get("crop_kind", "sage"))
            from environment import CROP_HEALTH_MIN

            building.crop_health = max(
                CROP_HEALTH_MIN,
                min(1.0, float(bdata.get("crop_health", 1.0))),
            )
            from resource_balance import FIELD_PEST_BOOST_MAX

            building.pest_boost = max(
                0.0,
                min(FIELD_PEST_BOOST_MAX, float(bdata.get("pest_boost", 0.0))),
            )
            building.fence_edges = {
                (int(edge[0]), int(edge[1]), str(edge[2]))
                for edge in bdata.get("fence_edges", [])
                if isinstance(edge, (list, tuple)) and len(edge) == 3
            }
            building.fence_gates = {
                (int(cell[0]), int(cell[1]))
                for cell in bdata.get("fence_gates", [])
                if isinstance(cell, (list, tuple)) and len(cell) >= 2
            }
            # Migrate the first fence format, where a gate was one edge.
            old_gate = bdata.get("fence_gate")
            if isinstance(old_gate, (list, tuple)) and len(old_gate) >= 2:
                building.fence_gates.add((int(old_gate[0]), int(old_gate[1])))
            if is_field_plot_kind(kind) and work_mode not in building.supported_work_modes():
                building.work_mode = WorkMode.COLLECT
        building.sync_draw_task_from_mode()
        _apply_storage(building, bdata.get("storage", {}))
        building.areas = [
            TaskArea(
                x0=int(a["x0"]),
                y0=int(a["y0"]),
                x1=int(a["x1"]),
                y1=int(a["y1"]),
                task_type=TaskType[a["task_type"]],
                building_id=int(a["building_id"]),
            )
            for a in bdata.get("areas", [])
        ]
        building.fields = []
        for fdata in bdata.get("fields", []):
            field_obj = FarmField(
                id=int(fdata["id"]),
                x0=int(fdata["x0"]),
                y0=int(fdata["y0"]),
                x1=int(fdata["x1"]),
                y1=int(fdata["y1"]),
                name=str(fdata.get("name", "")),
            )
            for pdata in fdata.get("plans", []):
                field_obj.plans.append(
                    CropPlan(
                        id=int(pdata["id"]),
                        x0=int(pdata["x0"]),
                        y0=int(pdata["y0"]),
                        x1=int(pdata["x1"]),
                        y1=int(pdata["y1"]),
                        crop_kind=str(pdata.get("crop_kind", "sage")),
                        field_id=field_obj.id,
                    )
                )
            building.fields.append(field_obj)
        building.plans = []
        for pdata in bdata.get("plans", []):
            building.plans.append(
                CropPlan(
                    id=int(pdata["id"]),
                    x0=int(pdata["x0"]),
                    y0=int(pdata["y0"]),
                    x1=int(pdata["x1"]),
                    y1=int(pdata["y1"]),
                    crop_kind=str(pdata.get("crop_kind", "sage")),
                    field_id=int(pdata.get("field_id", building.id)),
                )
            )
        building.next_field_id = int(
            bdata.get(
                "next_field_id",
                max((f.id for f in building.fields), default=0) + 1,
            )
        )
        max_plan = max(
            [p.id for p in building.plans]
            + [p.id for f in building.fields for p in f.plans],
            default=0,
        )
        building.next_plan_id = int(bdata.get("next_plan_id", max_plan + 1))
        game.buildings[building.id] = building

    from extensions import apply_extension_storage_boosts

    apply_extension_storage_boosts(game.buildings)

    # Cold storage is food-only. Recover disallowed legacy stock to the
    # storehouse when loading older saves.
    for building in game.buildings.values():
        if building.kind not in (BuildingKind.KITCHEN, BuildingKind.PANTRY, BuildingKind.CELLAR):
            continue
        for key in ("hemp", "flax", "wheat", "rye"):
            amount = int(getattr(building, key, 0) or 0)
            if amount > 0:
                setattr(building, key, 0)
                setattr(game.home_storage, key, int(getattr(game.home_storage, key, 0) or 0) + amount)

    # Ensure new Field buildings from migration get unique ids.
    if game.buildings:
        game.next_building_id = max(
            game.next_building_id,
            max(b.id for b in game.buildings.values()) + 1,
        )

    # Promote nested Farm.fields / legacy Field areas into Field buildings.
    _migrate_legacy_fields(game)
    _migrate_building_footprints(game)

    # Markets: refresh demand if missing or from another season.
    for building in game.buildings.values():
        if building.is_market():
            game._ensure_market_demand(building)
    # Coins are regional wealth — fold any leftover stock into it.
    if hasattr(game, "_absorb_coins_to_wealth"):
        game._absorb_coins_to_wealth()

    # Re-sync after migration may have spawned buildings.
    if game.buildings:
        game.next_building_id = max(b.id for b in game.buildings.values()) + 1

    game.villagers.clear()
    for vdata in data.get("villagers", []):
        target = vdata.get("target")
        meat_pos = vdata.get("hunt_meat_pos")
        catch_pos = vdata.get("fish_catch_pos")
        post_pos = vdata.get("fish_post_pos")
        raw_state = str(vdata.get("state", "IDLE") or "IDLE")
        try:
            loaded_state = VillagerState[raw_state]
        except KeyError:
            loaded_state = VillagerState.IDLE
        villager = Villager(
            id=int(vdata["id"]),
            x=int(vdata["x"]),
            y=int(vdata["y"]),
            inventory=_inv_from_dict(vdata.get("inventory", {})),
            state=loaded_state,
            building_id=vdata.get("building_id"),
            assigned_to_home=bool(vdata.get("assigned_to_home", False)),
            move_cooldown=int(vdata.get("move_cooldown", 0)),
            work_cooldown=int(vdata.get("work_cooldown", 0)),
            work_in_progress=bool(vdata.get("work_in_progress", False)),
            target=tuple(target) if target else None,  # type: ignore[arg-type]
            haul_building_id=vdata.get("haul_building_id"),
            hunt_animal_id=vdata.get("hunt_animal_id"),
            hunt_colony_id=vdata.get("hunt_colony_id"),
            hunt_meat_pos=tuple(meat_pos) if meat_pos else None,  # type: ignore[arg-type]
            fish_target_id=vdata.get("fish_target_id"),
            fish_catch_pos=tuple(catch_pos) if catch_pos else None,  # type: ignore[arg-type]
            fish_post_pos=tuple(post_pos) if post_pos else None,  # type: ignore[arg-type]
            fish_bait_ticks=max(0, int(vdata.get("fish_bait_ticks", 0))),
            forage_colony_id=vdata.get("forage_colony_id"),
            construction_id=vdata.get("construction_id"),
        )
        raw_anchor = vdata.get("work_anchor")
        if isinstance(raw_anchor, (list, tuple)) and len(raw_anchor) >= 2:
            villager.work_anchor = (int(raw_anchor[0]), int(raw_anchor[1]))
        raw_craft_recipe = vdata.get("craft_recipe_name")
        villager.craft_recipe_name = (
            str(raw_craft_recipe) if raw_craft_recipe else None
        )
        raw_prio = vdata.get("priorities")
        if raw_prio:
            villager.priorities = [
                WorkPriority[name] if name in WorkPriority.__members__ else WorkPriority.NONE
                for name in raw_prio
            ]
        else:
            villager.set_default_priorities()
        villager.seasonal_priorities = bool(vdata.get("seasonal_priorities", False))
        raw_season_prio = vdata.get("season_priorities") or {}
        if isinstance(raw_season_prio, dict):
            for skey, names in raw_season_prio.items():
                if not isinstance(names, list):
                    continue
                villager.season_priorities[str(skey)] = [
                    WorkPriority[name]
                    if name in WorkPriority.__members__
                    else WorkPriority.NONE
                    for name in names
                ]
        raw_wp = vdata.get("workplace_slots")
        if isinstance(raw_wp, list):
            villager.workplace_slots = [
                int(b) if b is not None else None for b in raw_wp[:3]
            ]
            while len(villager.workplace_slots) < 3:
                villager.workplace_slots.append(None)
        villager.sync_workplace_slot_zero()
        raw_season_wp = vdata.get("season_workplace_slots") or {}
        if isinstance(raw_season_wp, dict):
            for skey, ids in raw_season_wp.items():
                if not isinstance(ids, list):
                    continue
                villager.season_workplace_slots[str(skey)] = [
                    int(b) if b is not None else None for b in ids[:3]
                ]
        raw_plan = vdata.get("workplace_plan")
        if isinstance(raw_plan, list) and raw_plan:
            from entities import WorkplaceSlot

            villager.workplace_plan = [
                WorkplaceSlot.from_save(item) for item in raw_plan[:3]
            ]
            while len(villager.workplace_plan) < 3:
                villager.workplace_plan.append(WorkplaceSlot())
            villager._sync_legacy_from_plan()
        else:
            # Migrate legacy priorities + workplace_slots into the unified plan.
            villager.ensure_workplace_plan()
        raw_season_plan = vdata.get("season_workplace_plan") or {}
        if isinstance(raw_season_plan, dict) and raw_season_plan:
            from entities import WorkplaceSlot

            for skey, items in raw_season_plan.items():
                if not isinstance(items, list):
                    continue
                row = [WorkplaceSlot.from_save(item) for item in items[:3]]
                while len(row) < 3:
                    row.append(WorkplaceSlot())
                villager.season_workplace_plan[str(skey)] = row
            villager._sync_legacy_from_plan()
        elif villager.seasonal_priorities:
            villager.ensure_season_workplace_plan(copy_from=villager.workplace_plan)
        villager.satiation = float(vdata.get("satiation", 0.75))
        villager.satiation = max(0.0, min(1.0, villager.satiation))
        raw_ration = vdata.get("ration_mode", "NORMAL")
        try:
            villager.ration_mode = RationMode[str(raw_ration)]
        except KeyError:
            villager.ration_mode = RationMode.NORMAL
        villager.seeking_food = bool(vdata.get("seeking_food", False))
        raw_meal = vdata.get("last_meal")
        if isinstance(raw_meal, list):
            villager.last_meal = [str(k) for k in raw_meal if k]
        else:
            # Migrate older saves that stored a single last_food key.
            raw_last = vdata.get("last_food")
            villager.last_meal = [str(raw_last)] if raw_last else []
        villager.food_walk_mult = max(0.1, float(vdata.get("food_walk_mult", 1.0)))
        villager.food_work_mult = max(0.1, float(vdata.get("food_work_mult", 1.0)))
        villager.food_hunger_mult = max(0.05, float(vdata.get("food_hunger_mult", 1.0)))
        villager.name = str(vdata.get("name") or villager.name)
        villager.energy = max(0.0, min(1.0, float(vdata.get("energy", 1.0))))
        villager.happiness = max(0.0, min(1.0, float(vdata.get("happiness", 0.7))))
        if "underlying_happiness" in vdata:
            villager.underlying_happiness = max(
                0.0, min(1.0, float(vdata.get("underlying_happiness", villager.happiness)))
            )
        else:
            villager.underlying_happiness = float(villager.happiness)
        villager.break_ticks_left = max(0, int(vdata.get("break_ticks_left", 0) or 0))
        villager.break_cooldown_ticks = max(
            0, int(vdata.get("break_cooldown_ticks", 0) or 0)
        )
        villager.break_kind = str(vdata.get("break_kind", "") or "")
        villager.break_reason = str(vdata.get("break_reason", "") or "")
        villager.break_thought = str(vdata.get("break_thought", "") or "")
        raw_return = vdata.get("break_return_pos")
        if isinstance(raw_return, (list, tuple)) and len(raw_return) >= 2:
            villager.break_return_pos = (int(raw_return[0]), int(raw_return[1]))
        else:
            villager.break_return_pos = None
        villager.base_break_day = int(vdata.get("base_break_day", -1))
        # Break states without timers fall back to idle so old/partial saves recover.
        from society import is_happiness_break_state

        if is_happiness_break_state(villager.state) and villager.break_ticks_left <= 0:
            if villager.state == VillagerState.RETURNING_TO_WORK:
                pass
            else:
                villager.state = VillagerState.IDLE
                villager.break_kind = ""
                villager.break_reason = ""
                villager.break_thought = ""
                villager.break_return_pos = None
        villager.housed = bool(vdata.get("housed", False))
        hid = vdata.get("housing_id")
        villager.housing_id = int(hid) if hid is not None else None
        villager.housing_need = int(vdata.get("housing_need", 1))
        villager.required_foods = list(vdata.get("required_foods") or ["meat"])
        villager.favourite_foods = list(vdata.get("favourite_foods") or [])
        villager.favourite_is_junk = bool(vdata.get("favourite_is_junk", False))
        villager.required_workplace = str(vdata.get("required_workplace", "") or "")
        villager.signing_fee = max(0, int(vdata.get("signing_fee", 0) or 0))
        villager.join_fee_paid = bool(vdata.get("join_fee_paid", False))
        villager.seasons_without_reqs = int(vdata.get("seasons_without_reqs", 0))
        villager.coins_paid_total = int(vdata.get("coins_paid_total", 0) or 0)
        villager.season_pay_due = int(vdata.get("season_pay_due", 0) or 0)
        raw_events = vdata.get("happiness_events")
        if not isinstance(raw_events, list):
            raw_events = vdata.get("happiness_impacts")
        events: list[dict] = []
        if isinstance(raw_events, list):
            for imp in raw_events:
                if not isinstance(imp, dict):
                    continue
                events.append(
                    {
                        "icon": str(imp.get("icon", "") or "coins"),
                        "label": str(imp.get("label", "") or "Event"),
                        "delta": int(round(float(imp.get("delta", 0) or 0))),
                        "day": int(imp.get("day", 0) or 0),
                    }
                )
        villager.happiness_events = events
        raw_temps = vdata.get("happiness_temporary")
        temps: list[dict] = []
        if isinstance(raw_temps, list):
            for m in raw_temps:
                if not isinstance(m, dict):
                    continue
                temps.append(
                    {
                        "channel": str(m.get("channel", "") or "event"),
                        "peak": float(m.get("peak", 0) or 0),
                        "ticks_left": max(0, int(m.get("ticks_left", 0) or 0)),
                        "ticks_total": max(1, int(m.get("ticks_total", 1) or 1)),
                        "icon": str(m.get("icon", "") or "stew"),
                        "label": str(m.get("label", "") or "Mood"),
                        "source": str(m.get("source", "") or "event"),
                        "day": int(m.get("day", 0) or 0),
                    }
                )
        raw_mods = vdata.get("happiness_modifiers")
        loaded_mods: list[dict] = []
        if isinstance(raw_mods, list):
            for m in raw_mods:
                if not isinstance(m, dict):
                    continue
                loaded_mods.append(
                    {
                        "icon": str(m.get("icon", "") or "stew"),
                        "label": str(m.get("label", "") or "Happiness"),
                        "peak": float(m.get("peak", 0) or 0),
                        "remaining": float(m.get("remaining", 0) or 0),
                        "ticks_left": max(0, int(m.get("ticks_left", 0) or 0)),
                        "ticks_total": max(1, int(m.get("ticks_total", 1) or 1)),
                        "until_meal": bool(m.get("until_meal", False)),
                        "points": int(m.get("points", 0) or 0),
                        "channel": str(m.get("channel", "") or ""),
                    }
                )
                # Migrate legacy unwind mods into temporary capped moods.
                if not temps:
                    ch = str(m.get("channel") or "")
                    if not ch:
                        ch = "meal" if m.get("until_meal") else f"legacy:{m.get('label', 'event')}"
                    peak = float(m.get("remaining", m.get("peak", 0)) or 0)
                    if abs(peak) > 1e-6 and int(m.get("ticks_left", 0) or 0) > 0:
                        temps.append(
                            {
                                "channel": ch,
                                "peak": peak,
                                "ticks_left": max(0, int(m.get("ticks_left", 0) or 0)),
                                "ticks_total": max(1, int(m.get("ticks_total", 1) or 1)),
                                "icon": str(m.get("icon", "") or "stew"),
                                "label": str(m.get("label", "") or "Mood"),
                                "source": "legacy",
                                "day": 0,
                            }
                        )
        villager.happiness_temporary = temps
        villager.happiness_modifiers = loaded_mods
        from happiness import sync_displayed_happiness

        sync_displayed_happiness(villager)
        villager.low_happiness_days = float(vdata.get("low_happiness_days", 0.0))
        villager.low_happiness_seasons = int(vdata.get("low_happiness_seasons", 0) or 0)
        villager.skills = skills_from_dict(vdata.get("skills"))
        cid = vdata.get("community_id")
        villager.community_id = int(cid) if cid is not None else None
        villager.virtues = list(vdata.get("virtues") or [])
        villager.vices = list(vdata.get("vices") or [])
        villager.portrait_seed = int(vdata.get("portrait_seed", 0) or 0)
        villager.template_id = str(vdata.get("template_id", "") or "")
        villager.tier = int(vdata.get("tier", 1) or 1)
        if not villager.virtues and not villager.vices:
            villager.__post_init__()
        game.villagers.append(villager)

    game.construction_sites.clear()
    for sdata in data.get("construction_sites", []):
        pair = sdata.get("relocate_pair_id")
        from_b = sdata.get("relocate_from_building_id")
        src_b = sdata.get("source_building_id")
        site = ConstructionSite(
            id=int(sdata["id"]),
            x=int(sdata["x"]),
            y=int(sdata["y"]),
            kind=BuildingKind[sdata["kind"]],
            need_wood=int(sdata.get("need_wood", 0)),
            need_rock=int(sdata.get("need_rock", 0)),
            need_logs=int(sdata.get("need_logs", 0)),
            need_hardwood=int(sdata.get("need_hardwood", 0)),
            have_wood=int(sdata.get("have_wood", 0)),
            have_rock=int(sdata.get("have_rock", 0)),
            have_logs=int(sdata.get("have_logs", 0)),
            have_hardwood=int(sdata.get("have_hardwood", 0)),
            build_progress=int(sdata.get("build_progress", 0)),
            plot_w=max(1, int(sdata.get("plot_w", 1))),
            plot_h=max(1, int(sdata.get("plot_h", 1))),
            phase=str(sdata.get("phase") or "build"),
            relocate_pair_id=int(pair) if pair is not None else None,
            relocate_from_building_id=int(from_b) if from_b is not None else None,
            source_building_id=int(src_b) if src_b is not None else None,
            parent_building_id=(
                int(sdata["parent_building_id"])
                if sdata.get("parent_building_id") is not None
                else None
            ),
            fence_field_id=(
                int(sdata["fence_field_id"])
                if sdata.get("fence_field_id") is not None else None
            ),
            fence_edges=tuple(str(edge) for edge in sdata.get("fence_edges", [])),
        )
        game.construction_sites[site.id] = site

    from wildlife import (
        Animal,
        AnimalKind,
        AnimalSex,
        Colony,
        Fish,
        FishKind,
        WolfMember,
        WolfPack,
    )

    wild = data.get("wildlife", {})
    game.wildlife.animals = []
    for a in wild.get("animals", []):
        kind_name = a.get("kind", "DEER")
        try:
            kind = AnimalKind[kind_name]
        except KeyError:
            kind = AnimalKind.DEER
        # Legacy bee/rabbit individuals → drop (colonies handle those now).
        if kind in (AnimalKind.BEE, AnimalKind.RABBIT, AnimalKind.FOX):
            continue
        if kind not in (
            AnimalKind.DEER,
            AnimalKind.BOAR,
            AnimalKind.OWL,
            AnimalKind.HAWK,
        ):
            kind = AnimalKind.DEER
        sex_name = a.get("sex", "MALE")
        try:
            sex = AnimalSex[sex_name]
        except KeyError:
            sex = AnimalSex.MALE
        mt = a.get("migrate_target")
        migrate_target = (int(mt[0]), int(mt[1])) if mt else None
        sf = a.get("scare_from")
        scare_from = (int(sf[0]), int(sf[1])) if sf else None
        ct = a.get("crop_target")
        crop_target = (int(ct[0]), int(ct[1])) if ct else None
        # New field migrate_home_id; older saves used migrate_patch_id as dest — drop.
        home_raw = a.get("migrate_home_id")
        if home_raw is None and a.get("patch_id") is None and a.get("migrate_patch_id") is not None:
            # Legacy mid-migration: treat as dispersing without a tracked home.
            home_raw = None
        game.wildlife.animals.append(
            Animal(
                id=int(a["id"]),
                x=int(a["x"]),
                y=int(a["y"]),
                kind=kind,
                sex=sex,
                patch_id=int(a["patch_id"]) if a.get("patch_id") is not None else None,
                mate_id=int(a["mate_id"]) if a.get("mate_id") is not None else None,
                move_cooldown=int(a.get("move_cooldown", 0)),
                migrate_home_id=int(home_raw) if home_raw is not None else None,
                migrate_target=migrate_target,
                migrated_this_year=bool(a.get("migrated_this_year", False)),
                scare_from=scare_from,
                scare_steps=int(a.get("scare_steps", 0)),
                facing_right=bool(a.get("facing_right", True)),
                crop_target=crop_target,
                crop_arrived_day=(
                    float(a["crop_arrived_day"])
                    if a.get("crop_arrived_day") is not None else None
                ),
                age_days=float(a.get("age_days", 224.0)),
                world_x=float(a.get("world_x", a["x"])),
                world_y=float(a.get("world_y", a["y"])),
            )
        )
    game.wildlife.next_id = int(wild.get("next_id", 1))
    game.wildlife.growth_timer = int(wild.get("growth_timer", game.wildlife.growth_timer))
    game.wildlife._last_breed_year = int(wild.get("last_breed_year", -1))
    game.wildlife._seeded = True
    game.wildlife._index_animals()
    game.wildlife._form_mating_pairs()

    game.wildlife.colonies = []
    for c in wild.get("colonies", []):
        kind_name = c.get("kind", "BEE")
        try:
            kind = AnimalKind[kind_name]
        except KeyError:
            continue
        if kind not in (
            AnimalKind.BEE,
            AnimalKind.RABBIT,
            AnimalKind.FROG,
            AnimalKind.VOLE,
        ):
            continue
        colony = Colony(
            id=int(c["id"]),
            kind=kind,
            x=int(c["x"]),
            y=int(c["y"]),
            level=int(c.get("level", 1)),
            habitat_id=int(c["habitat_id"]) if c.get("habitat_id") is not None else None,
            harvest_cooldown=int(c.get("harvest_cooldown", 0)),
        )
        colony.clamp_level()
        game.wildlife.colonies.append(colony)
    game.wildlife.next_colony_id = int(
        wild.get(
            "next_colony_id",
            max((c.id for c in game.wildlife.colonies), default=0) + 1,
        )
    )
    # Colony backfill happens in ensure_missing_wildlife after packs load.
    game.wildlife._colonies_need_seed = False

    game.wildlife.wolf_packs = []
    for p in wild.get("wolf_packs", []):
        members: list[WolfMember] = []
        for m in p.get("members", []):
            try:
                sex = AnimalSex[str(m.get("sex", "MALE"))]
            except KeyError:
                sex = AnimalSex.MALE
            members.append(
                WolfMember(
                    sex=sex,
                    x=int(m["x"]),
                    y=int(m["y"]),
                    move_cooldown=int(m.get("move_cooldown", 0)),
                    world_x=float(m.get("world_x", m["x"])),
                    world_y=float(m.get("world_y", m["y"])),
                )
            )
        if not members:
            continue
        kind_name = str(p.get("kind", "WOLF")).upper()
        try:
            pack_kind = AnimalKind[kind_name]
        except KeyError:
            pack_kind = AnimalKind.WOLF
        if pack_kind not in (AnimalKind.WOLF, AnimalKind.FOX):
            pack_kind = AnimalKind.WOLF
        # Prefer countdown; migrate legacy absolute fed_until_day (year-wrap bug).
        if "fed_days_remaining" in p:
            remaining = float(p.get("fed_days_remaining", 0) or 0)
        else:
            from seasons import YEAR_DAYS
            from settings import WOLF_FEED_BOAR_DAYS

            fed_until = float(p.get("fed_until_day", 0) or 0)
            day_now = float(game.calendar_day)
            left = fed_until - day_now
            if left < -0.5 * YEAR_DAYS:
                left += float(YEAR_DAYS)
            max_feed = float(WOLF_FEED_BOAR_DAYS)
            # Impossible leftovers are year-wrap artifacts → hungry.
            remaining = left if 0.0 < left <= max_feed + 0.05 else 0.0
        remaining = min(
            float(game.wildlife._wolf_feed_cap()),
            max(0.0, remaining),
        )
        game.wildlife.wolf_packs.append(
            WolfPack(
                id=int(p["id"]),
                x=int(p["x"]),
                y=int(p["y"]),
                members=members,
                kind=pack_kind,
                fed_days_remaining=remaining,
                move_cooldown=int(p.get("move_cooldown", 0)),
                last_prey=str(p.get("last_prey", "") or ""),
                last_meal_day=float(p.get("last_meal_day", -1)),
                activity=str(p.get("activity", "Roaming") or "Roaming"),
                world_x=float(p.get("world_x", p["x"])),
                world_y=float(p.get("world_y", p["y"])),
            )
        )
    game.wildlife.next_wolf_pack_id = int(
        wild.get(
            "next_wolf_pack_id",
            max((p.id for p in game.wildlife.wolf_packs), default=0) + 1,
        )
    )
    # Rebuild habitats then backfill any species older saves lack
    # (frogs/voles/birds need sites that do not exist until refresh).
    game.wildlife.ensure_missing_wildlife(game.world)
    game.wildlife._colonies_need_seed = False

    fish_data = data.get("fish", {})

    def _load_fish_kind(raw: object) -> FishKind:
        if isinstance(raw, str):
            try:
                return FishKind[raw]
            except KeyError:
                pass
        # Legacy saves had no species — roll the live spawn mix.
        return game.fish.pick_kind()

    game.fish.fish = [
        Fish(
            id=int(f["id"]),
            x=int(f["x"]),
            y=int(f["y"]),
            kind=_load_fish_kind(f.get("kind")),
            move_cooldown=int(f.get("move_cooldown", 0)),
            world_x=float(f.get("world_x", f["x"])),
            world_y=float(f.get("world_y", f["y"])),
        )
        for f in fish_data.get("fish", [])
    ]
    game.fish.next_id = int(fish_data.get("next_id", 1))
    game.fish.growth_timer = int(fish_data.get("growth_timer", game.fish.growth_timer))

    game.next_villager_id = int(data.get("next_villager_id", 1))
    game.next_building_id = int(data.get("next_building_id", 1))
    if game.buildings:
        game.next_building_id = max(
            game.next_building_id,
            max(b.id for b in game.buildings.values()) + 1,
        )
    game.next_construction_id = int(data.get("next_construction_id", 1))
    game.communities = [
        Community.from_dict(c) for c in data.get("communities", []) if isinstance(c, dict)
    ]
    game.hire_candidates = [
        HireCandidate.from_dict(c)
        for c in data.get("hire_candidates", [])
        if isinstance(c, dict)
    ]
    game.next_community_id = int(
        data.get(
            "next_community_id",
            max((c.id for c in game.communities), default=0) + 1,
        )
    )
    game.next_hire_id = int(
        data.get(
            "next_hire_id",
            max((c.id for c in game.hire_candidates), default=0) + 1,
        )
    )
    from sociopolitical import SettlementPoliticalState

    game.political = SettlementPoliticalState.from_dict(data.get("sociopolitical"))
    place = data.get("place_kind")
    game.place_kind = BuildingKind[place] if place else None
    game.sim_speed = int(data.get("sim_speed", 1))
    if game.sim_speed not in (0, 1, 2, 4, 8, 16, 32, 64, 128):
        game.sim_speed = 1

    from seasons import (
        DAYS_PER_SEASON,
        SEASON_LENGTH_TICKS,
        TICKS_PER_DAY,
        YEAR_DAYS,
        Season,
        season_for_day,
        set_ticks_per_day,
    )

    saved_tpd = max(1, int(data.get("ticks_per_day", TICKS_PER_DAY)))
    game.ticks_per_day = set_ticks_per_day(saved_tpd)

    if "calendar_day" in data:
        game.calendar_day = float(data["calendar_day"]) % YEAR_DAYS
        game.day_tick = int(data.get("day_tick", game.ticks_per_day))
    elif "season" in data:
        # Older saves: map season (+ optional timer) onto calendar day.
        try:
            season = Season[str(data.get("season", "SPRING"))]
        except KeyError:
            season = Season.SPRING
        base = {
            Season.SPRING: 0,
            Season.SUMMER: DAYS_PER_SEASON,
            Season.AUTUMN: DAYS_PER_SEASON * 2,
            Season.WINTER: DAYS_PER_SEASON * 3,
        }[season]
        timer = int(data.get("season_timer", SEASON_LENGTH_TICKS))
        elapsed = max(0, SEASON_LENGTH_TICKS - timer)
        day_offset = min(DAYS_PER_SEASON - 1, elapsed // max(1, game.ticks_per_day))
        game.calendar_day = (base + day_offset) % YEAR_DAYS
        game.day_tick = game.ticks_per_day
    else:
        game.calendar_day = 0
        game.day_tick = game.ticks_per_day

    # Sanity: season property should match day.
    _ = season_for_day(game.calendar_day)
    from calendar_system import CalendarPolicy

    game.calendar_policy = CalendarPolicy.from_dict(
        data.get("calendar_policy"), season_for_day(game.calendar_day)
    )


    overlay_name = data.get("overlay_mode", "NONE")
    if overlay_name == "PATH_TRAFFIC":
        overlay_name = "DISTURBANCE"
    try:
        game.overlay_mode = OverlayMode[overlay_name]
    except KeyError:
        game.overlay_mode = OverlayMode.NONE
    game._clear_selection()
    game.drawing = False
    game.draw_start = None
    game.draw_current = None
    game._mouse_down_cell = None

    if hasattr(game, "field_crop_kind") and "field_crop_kind" in data:
        game.field_crop_kind = str(data["field_crop_kind"])

    if hasattr(game, "resource_history"):
        game.resource_history.load_dict(data.get("resource_history"))
    if hasattr(game, "resource_tracker"):
        game.resource_tracker.close()
    
    # Ensure core buildings exist (HOME, WORKSTATION)
    if hasattr(game, "_ensure_core_buildings"):
        game._ensure_core_buildings()

    # Restore cyclic env layers (biodiversity / floral / pollination / pest-control).
    if hasattr(game, "env_maps"):
        game.env_maps.resize(game.world.rows, game.world.cols)
        saved_env = data.get("env_maps")
        if saved_env:
            game.env_maps.load_save_dict(saved_env)
            from developer_tools.terrain_editor import ecology_signature
            if saved_env.get("terrain_ecology_signature") != ecology_signature():
                from environment import rainfall_modifier_grid, soil_moisture_grid, temperature_grid
                game.env_maps.soil_moisture = soil_moisture_grid(game.world, game.calendar_day)
                game.env_maps.temperature = temperature_grid(game.world, game.calendar_day)
                game.env_maps.rainfall_modifiers = rainfall_modifier_grid(game.world)
            game._biodiversity_samples = game.env_maps.biodiversity_samples
            game._biodiversity_average = game.env_maps.biodiversity
            # Older saves may lack floral/pollination — backfill without ratcheting health.
            if hasattr(game, "_backfill_env_overlays"):
                game._backfill_env_overlays()
        elif hasattr(game, "_sample_environment"):
            game._sample_environment()
        elif hasattr(game, "_sample_biodiversity"):
            game._sample_biodiversity()
    elif hasattr(game, "_biodiversity_samples"):
        game._biodiversity_samples.clear()
        if hasattr(game, "_sample_biodiversity"):
            game._sample_biodiversity()

    if hasattr(game, "_bake_erosion"):
        erosion = (
            (data.get("env_maps") or {}).get("erosion")
            if isinstance(data.get("env_maps"), dict)
            else None
        )
        rows, cols = game.world.rows, game.world.cols
        needs_bake = (
            not isinstance(erosion, list)
            or len(erosion) != rows
            or not erosion
            or len(erosion[0]) != cols
        )
        if needs_bake:
            game._bake_erosion()

    if hasattr(game, "weather"):
        game.weather.load_dict(data.get("weather"))
        if hasattr(game, "rain_effect"):
            game.rain_effect.reset_seed(game.world.seed)

    # Villager wear map for PATH painting (optional; older saves omit it).
    if hasattr(game, "_path_traffic"):
        game._path_traffic = {}
        for entry in data.get("path_traffic") or []:
            if len(entry) < 3:
                continue
            x, y, wear = int(entry[0]), int(entry[1]), float(entry[2])
            if game.world.in_bounds(x, y) and wear > 0:
                game._path_traffic[(x, y)] = wear

    if hasattr(game, "_refresh_hardscape_terrain"):
        game._refresh_hardscape_terrain()
    if hasattr(game, "_sync_field_fences"):
        game._sync_field_fences()
    if hasattr(game, "_sync_building_collision"):
        game._sync_building_collision()

    if hasattr(game, "_refresh_indicators"):
        game._refresh_indicators()
    else:
        from indicators import build_overlay_grid

        game.overlay_values = build_overlay_grid(game.world, game.overlay_mode)

    if hasattr(game, "_invalidate_terrain_layer"):
        game._invalidate_terrain_layer()
    if hasattr(game, "control_mode"):
        saved_mode = str(data.get("control_mode", "dog")).lower()
        dog = next(
            (v for v in game.villagers if getattr(v, "template_id", "") == "player_dog"),
            None,
        )
        game._god_dog_villager = dog
        if saved_mode == "god" and dog is not None:
            game.control_mode = "god"
            game.player.inventory = dog.inventory
            if hasattr(game, "_sync_player_from_god_dog"):
                game._sync_player_from_god_dog()
        else:
            game.control_mode = "dog"
            if dog is not None and dog in game.villagers:
                game.villagers.remove(dog)
    if hasattr(game, "camera"):
        game.camera.center_on(
            game.player.x, game.player.y, game.world.cols, game.world.rows
        )
    # Mid-season loads: snap harvest-season crops so workers aren't idle on
    # visually mature but still-growing tiles (e.g. after TICKS_PER_DAY changes).
    if hasattr(game, "_ripen_crops_for_harvest_season"):
        game._ripen_crops_for_harvest_season()


def save_to_path(game: Game, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(serialize_game(game), fh, indent=2)


def load_from_path(game: Game, path: Path | str) -> None:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    checkpoint = data.get("tutorial_checkpoint") if isinstance(data, dict) else None
    if isinstance(checkpoint, dict):
        base = Path(__file__).resolve().parents[1] / "saves" / "tutorial_slice.json"
        load_from_path(game, base)
        game.scenario.start_tutorial(game)
        game.scenario.apply_checkpoint(game, checkpoint)
        return
    apply_save(game, data)
    # Large forest animals are introduced by runtime/scenario progression, not
    # inherited from authored map-save populations.
    if hasattr(game, "wildlife"):
        from wildlife import AnimalKind
        game.wildlife.animals = [
            animal for animal in game.wildlife.animals
            if animal.kind not in (AnimalKind.DEER, AnimalKind.BOAR)
        ]
        game.wildlife._index_animals()
    if hasattr(game,"scenario"):
        if hasattr(game,"scenario_dialog"):game.scenario_dialog.close()
        restored=isinstance(data.get("scenario"),dict)
        if restored:game.scenario.load_dict(data.get("scenario"))
        game.scenario.configure_after_load(game,path.stem,restored=restored)
