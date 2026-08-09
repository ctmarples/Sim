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
    BuildingKind,
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
from recipes import PROCESSED_KEYS
from society import (
    Community,
    HireCandidate,
    skills_from_dict,
    skills_to_dict,
)
from world import Cell, FeatureType, TerrainType, World

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
    "berries",
    "berry_seeds",
    "reeds",
    "straw",
    "fur",
    "twine",
    "axe",
    "spear",
    "fishing_rod",
    "hoe",
    "knife",
)
_CROP_STORAGE_KEYS = PRODUCE_KEYS + SEED_KEYS
_STORAGE_KEYS = _BASE_STORAGE_KEYS + _CROP_STORAGE_KEYS + PROCESSED_KEYS

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


def list_save_files() -> list[str]:
    files = sorted(p.name for p in saves_dir().glob("*.json") if p.is_file())
    return files


def _inv_to_dict(inv: Inventory) -> dict[str, int]:
    data = {key: int(getattr(inv, key, 0)) for key in _STORAGE_KEYS}
    data["capacity"] = inv.capacity
    if inv.equipped_tool:
        data["equipped_tool"] = inv.equipped_tool
    return data


def _inv_from_dict(data: dict[str, Any]) -> Inventory:
    data = _normalize_legacy_storage(data)
    from settings import INVENTORY_CAPACITY

    # Prefer current settings capacity so old saves (e.g. cap 8) aren't stuck
    # unable to carry FARM_PRODUCE_YIELD / other multi-unit harvests.
    saved_cap = int(data.get("capacity", INVENTORY_CAPACITY))
    inv = Inventory(capacity=max(saved_cap, INVENTORY_CAPACITY))
    for key in _STORAGE_KEYS:
        setattr(inv, key, int(data.get(key, 0)))
    # Legacy: generic herbs → sage; generic saplings → oak.
    inv.sage += int(data.get("herbs", 0))
    inv.sage_seeds += int(data.get("herb_seeds", 0))
    inv.oak_saplings += int(data.get("saplings", 0))
    tool = data.get("equipped_tool")
    if tool in TOOL_KEYS:
        inv.equipped_tool = str(tool)
    return inv


def _storage_to_dict(obj: Any) -> dict[str, int]:
    return {key: int(getattr(obj, key, 0)) for key in _STORAGE_KEYS}


def _apply_storage(obj: Any, data: dict[str, Any]) -> None:
    data = _normalize_legacy_storage(data)
    for key in _STORAGE_KEYS:
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


def _feature_from_save(name: str) -> FeatureType:
    if name == "HERB" and "WILD_CROP" in FeatureType.__members__:
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
        "fish_deposit": cell.fish_deposit,
    }
    crop_kind = getattr(cell, "crop_kind", None)
    if crop_kind is not None:
        data["crop_kind"] = crop_kind
    tree_species = getattr(cell, "tree_species", None)
    if tree_species is not None:
        data["tree_species"] = tree_species
    icon_variant = getattr(cell, "icon_variant", None)
    if icon_variant is not None:
        data["icon_variant"] = int(icon_variant)
    if getattr(cell, "terrain_cluster", 0):
        data["terrain_cluster"] = int(cell.terrain_cluster)
    shade = getattr(cell, "terrain_shade", 0.55)
    if abs(shade - 0.55) > 0.001:
        data["terrain_shade"] = float(shade)
    return data


def _cell_from_save(c: dict[str, Any]) -> Cell:
    cell = Cell(
        terrain=TerrainType[c["terrain"]],
        feature=_feature_from_save(c["feature"]),
        disturbance=float(c.get("disturbance", 0.0)),
        growth_ticks=int(c.get("growth_ticks", 0)),
        deposit=int(c.get("deposit", 0)),
        meat_deposit=int(c.get("meat_deposit", 0)),
        fish_deposit=int(c.get("fish_deposit", 0)),
    )
    crop_kind = c.get("crop_kind")
    if crop_kind is not None:
        setattr(cell, "crop_kind", crop_kind)
    elif cell.feature in (FeatureType.CROP_HERB, FeatureType.WILD_CROP):
        setattr(cell, "crop_kind", "sage")
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
        }
        if hasattr(b, "crop_kind"):
            bdata["crop_kind"] = b.crop_kind
        if b.kind.name == "FIELD":
            bdata["crop_health"] = float(getattr(b, "crop_health", 1.0))
            bdata["pest_boost"] = float(getattr(b, "pest_boost", 0.0))
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
                "target": list(v.target) if v.target else None,
                "haul_building_id": v.haul_building_id,
                "hunt_animal_id": v.hunt_animal_id,
                "hunt_colony_id": v.hunt_colony_id,
                "hunt_meat_pos": list(v.hunt_meat_pos) if v.hunt_meat_pos else None,
                "fish_target_id": v.fish_target_id,
                "fish_catch_pos": list(v.fish_catch_pos) if v.fish_catch_pos else None,
                "fish_post_pos": list(v.fish_post_pos) if v.fish_post_pos else None,
                "forage_colony_id": v.forage_colony_id,
                "construction_id": v.construction_id,
                "priorities": [p.name for p in v.priorities],
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
                "housed": v.housed,
                "housing_id": v.housing_id,
                "housing_need": v.housing_need,
                "required_foods": list(v.required_foods),
                "favourite_foods": list(v.favourite_foods),
                "favourite_is_junk": v.favourite_is_junk,
                "join_fee_paid": v.join_fee_paid,
                "seasons_without_reqs": v.seasons_without_reqs,
                "low_happiness_days": round(v.low_happiness_days, 4),
                "skills": skills_to_dict(v.skills) if v.skills else {},
                "community_id": v.community_id,
                "virtues": list(getattr(v, "virtues", []) or []),
                "vices": list(getattr(v, "vices", []) or []),
                "portrait_seed": int(getattr(v, "portrait_seed", 0) or 0),
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
            "kind": a.kind.name,
            "sex": a.sex.name,
            "patch_id": a.patch_id,
            "mate_id": a.mate_id,
            "move_cooldown": a.move_cooldown,
            "migrate_home_id": a.migrate_home_id,
            "migrate_target": list(a.migrate_target) if a.migrate_target else None,
            "migrated_this_year": a.migrated_this_year,
        }
        for a in game.wildlife.animals
        if a.kind in (AnimalKind.DEER, AnimalKind.BOAR)
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
            "move_cooldown": f.move_cooldown,
        }
        for f in game.fish.fish
    ]
    payload: dict[str, Any] = {
        "version": SAVE_VERSION,
        "grid": {"cols": world.cols, "rows": world.rows, "seed": world.seed},
        "display": {
            "grid_cols": cfg.GRID_COLS,
            "grid_rows": cfg.GRID_ROWS,
        },
        "sim_speed": game.sim_speed,
        "ticks_per_day": getattr(game, "ticks_per_day", TICKS_PER_DAY),
        "season": game.season.name,
        "calendar_day": game.calendar_day,
        "day_tick": game.day_tick,
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
            "inventory": _inv_to_dict(game.player.inventory),
        },
        "home_storage": _storage_to_dict(game.home_storage),
        "buildings": buildings,
        "construction_sites": sites,
        "villagers": villagers,
        "wildlife": {
            "animals": animals,
            "colonies": colonies,
            "next_id": game.wildlife.next_id,
            "next_colony_id": game.wildlife.next_colony_id,
            "growth_timer": game.wildlife.growth_timer,
        },
        "fish": {
            "fish": fish,
            "next_id": game.fish.next_id,
            "growth_timer": game.fish.growth_timer,
        },
        "next_villager_id": game.next_villager_id,
        "next_building_id": game.next_building_id,
        "next_construction_id": game.next_construction_id,
        "place_kind": game.place_kind.name if game.place_kind else None,
        "overlay_mode": game.overlay_mode.name,
        "communities": [c.to_dict() for c in getattr(game, "communities", [])],
        "hire_candidates": [c.to_dict() for c in getattr(game, "hire_candidates", [])],
        "next_community_id": int(getattr(game, "next_community_id", 1)),
        "next_hire_id": int(getattr(game, "next_hire_id", 1)),
    }
    if hasattr(game, "env_maps"):
        payload["env_maps"] = game.env_maps.to_save_dict()
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
        if building.kind != BuildingKind.FIELD:
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
        BuildingKind.CRAFT_BENCH: FeatureType.CRAFT_BENCH,
        BuildingKind.ALCHEMIST: FeatureType.ALCHEMIST,
        BuildingKind.TAILOR: FeatureType.TAILOR,
        BuildingKind.TENT: FeatureType.TENT,
        BuildingKind.HOUSE_SMALL: FeatureType.HOUSE_SMALL,
        BuildingKind.HOUSE: FeatureType.HOUSE,
    }

    for building in list(game.buildings.values()):
        if building.kind == BuildingKind.FIELD:
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
        if site.kind == BuildingKind.FIELD:
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
    for row in world_data["cells"]:
        cells.append([_cell_from_save(c) for c in row])
    world.cells = cells
    world.update_forest_floor()
    # Legacy saves lack subclusters — carve them so seasonal masks look right.
    if not any(
        cell.terrain_cluster
        for row in world.cells
        for cell in row
    ):
        world._paint_terrain_subclusters(random.Random(world.seed + 77))
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
    game.player.inventory = _inv_from_dict(player_data["inventory"])
    _apply_storage(game.home_storage, data["home_storage"])

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
            BuildingKind.MILL: TaskType.FULL_FORAGE,
            BuildingKind.KITCHEN: TaskType.FULL_FORAGE,
            BuildingKind.CRAFT_BENCH: TaskType.FULL_FORAGE,
            BuildingKind.ALCHEMIST: TaskType.FULL_FORAGE,
            BuildingKind.TAILOR: TaskType.FULL_FORAGE,
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
        elif kind not in (BuildingKind.FORESTER, BuildingKind.FORAGER, BuildingKind.FIELD):
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
        if kind == BuildingKind.FIELD:
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
            if kind == BuildingKind.FIELD and work_mode not in building.supported_work_modes():
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

    # Ensure new Field buildings from migration get unique ids.
    if game.buildings:
        game.next_building_id = max(
            game.next_building_id,
            max(b.id for b in game.buildings.values()) + 1,
        )

    # Promote nested Farm.fields / legacy Field areas into Field buildings.
    _migrate_legacy_fields(game)
    _migrate_building_footprints(game)

    # Re-sync after migration may have spawned buildings.
    if game.buildings:
        game.next_building_id = max(b.id for b in game.buildings.values()) + 1

    game.villagers.clear()
    for vdata in data.get("villagers", []):
        target = vdata.get("target")
        meat_pos = vdata.get("hunt_meat_pos")
        catch_pos = vdata.get("fish_catch_pos")
        post_pos = vdata.get("fish_post_pos")
        villager = Villager(
            id=int(vdata["id"]),
            x=int(vdata["x"]),
            y=int(vdata["y"]),
            inventory=_inv_from_dict(vdata.get("inventory", {})),
            state=VillagerState[vdata.get("state", "IDLE")],
            building_id=vdata.get("building_id"),
            assigned_to_home=bool(vdata.get("assigned_to_home", False)),
            move_cooldown=int(vdata.get("move_cooldown", 0)),
            work_cooldown=int(vdata.get("work_cooldown", 0)),
            target=tuple(target) if target else None,  # type: ignore[arg-type]
            haul_building_id=vdata.get("haul_building_id"),
            hunt_animal_id=vdata.get("hunt_animal_id"),
            hunt_colony_id=vdata.get("hunt_colony_id"),
            hunt_meat_pos=tuple(meat_pos) if meat_pos else None,  # type: ignore[arg-type]
            fish_target_id=vdata.get("fish_target_id"),
            fish_catch_pos=tuple(catch_pos) if catch_pos else None,  # type: ignore[arg-type]
            fish_post_pos=tuple(post_pos) if post_pos else None,  # type: ignore[arg-type]
            forage_colony_id=vdata.get("forage_colony_id"),
            construction_id=vdata.get("construction_id"),
        )
        raw_prio = vdata.get("priorities")
        if raw_prio:
            villager.priorities = [
                WorkPriority[name] if name in WorkPriority.__members__ else WorkPriority.NONE
                for name in raw_prio
            ]
        else:
            villager.set_default_priorities()
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
        villager.housed = bool(vdata.get("housed", False))
        hid = vdata.get("housing_id")
        villager.housing_id = int(hid) if hid is not None else None
        villager.housing_need = int(vdata.get("housing_need", 1))
        villager.required_foods = list(vdata.get("required_foods") or ["meat"])
        villager.favourite_foods = list(vdata.get("favourite_foods") or [])
        villager.favourite_is_junk = bool(vdata.get("favourite_is_junk", False))
        villager.join_fee_paid = bool(vdata.get("join_fee_paid", False))
        villager.seasons_without_reqs = int(vdata.get("seasons_without_reqs", 0))
        villager.low_happiness_days = float(vdata.get("low_happiness_days", 0.0))
        villager.skills = skills_from_dict(vdata.get("skills"))
        cid = vdata.get("community_id")
        villager.community_id = int(cid) if cid is not None else None
        villager.virtues = list(vdata.get("virtues") or [])
        villager.vices = list(vdata.get("vices") or [])
        villager.portrait_seed = int(vdata.get("portrait_seed", 0) or 0)
        if not villager.virtues and not villager.vices:
            villager.__post_init__()
        game.villagers.append(villager)

    game.construction_sites.clear()
    for sdata in data.get("construction_sites", []):
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
        )
        game.construction_sites[site.id] = site

    from wildlife import Animal, AnimalKind, AnimalSex, Colony, Fish

    wild = data.get("wildlife", {})
    game.wildlife.animals = []
    for a in wild.get("animals", []):
        kind_name = a.get("kind", "DEER")
        try:
            kind = AnimalKind[kind_name]
        except KeyError:
            kind = AnimalKind.DEER
        # Legacy bee/rabbit individuals → drop (colonies handle those now).
        if kind in (AnimalKind.BEE, AnimalKind.RABBIT):
            continue
        sex_name = a.get("sex", "MALE")
        try:
            sex = AnimalSex[sex_name]
        except KeyError:
            sex = AnimalSex.MALE
        mt = a.get("migrate_target")
        migrate_target = (int(mt[0]), int(mt[1])) if mt else None
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
            )
        )
    game.wildlife.next_id = int(wild.get("next_id", 1))
    game.wildlife.growth_timer = int(wild.get("growth_timer", game.wildlife.growth_timer))
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
        if kind not in (AnimalKind.BEE, AnimalKind.RABBIT):
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
    # Colony seeding deferred until habitats refresh (_sample_environment).
    game.wildlife._colonies_need_seed = not bool(game.wildlife.colonies)

    fish_data = data.get("fish", {})
    game.fish.fish = [
        Fish(
            id=int(f["id"]),
            x=int(f["x"]),
            y=int(f["y"]),
            move_cooldown=int(f.get("move_cooldown", 0)),
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
    from settings import TICKS_PER_DAY_OPTIONS

    saved_tpd = int(data.get("ticks_per_day", TICKS_PER_DAY))
    if saved_tpd not in TICKS_PER_DAY_OPTIONS:
        saved_tpd = min(TICKS_PER_DAY_OPTIONS, key=lambda x: abs(x - saved_tpd))
    game.ticks_per_day = set_ticks_per_day(saved_tpd)

    if "calendar_day" in data:
        game.calendar_day = int(data["calendar_day"]) % YEAR_DAYS
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

    overlay_name = data.get("overlay_mode", "NONE")
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

    if hasattr(game, "_refresh_indicators"):
        game._refresh_indicators()
    else:
        from indicators import build_overlay_grid

        game.overlay_values = build_overlay_grid(game.world, game.overlay_mode)

    if hasattr(game, "_invalidate_terrain_layer"):
        game._invalidate_terrain_layer()
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
    apply_save(game, data)
