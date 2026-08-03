"""Serialize and restore game state as JSON save files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crops import LEGACY_HERB_PRODUCE, LEGACY_HERB_SEED, PRODUCE_KEYS, SEED_KEYS
from trees import SAPLING_ITEM_KEYS
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
    Villager,
    VillagerState,
    WorkMode,
    WorkPriority,
)
from world import Cell, FeatureType, TerrainType, World

if TYPE_CHECKING:
    from game import Game

SAVE_VERSION = 1

_BASE_STORAGE_KEYS = (
    "wood",
    "hardwood",
    "rock",
    "meat",
    "fish",
    *SAPLING_ITEM_KEYS,
    "mushrooms",
    "berries",
    "berry_seeds",
    "reeds",
)
_CROP_STORAGE_KEYS = PRODUCE_KEYS + SEED_KEYS
_STORAGE_KEYS = _BASE_STORAGE_KEYS + _CROP_STORAGE_KEYS


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
    return data


def _inv_from_dict(data: dict[str, Any]) -> Inventory:
    inv = Inventory(capacity=int(data.get("capacity", Inventory().capacity)))
    for key in _STORAGE_KEYS:
        setattr(inv, key, int(data.get(key, 0)))
    # Legacy: generic herbs → sage; generic saplings → oak.
    inv.sage += int(data.get("herbs", 0))
    inv.sage_seeds += int(data.get("herb_seeds", 0))
    inv.oak_saplings += int(data.get("saplings", 0))
    return inv


def _storage_to_dict(obj: Any) -> dict[str, int]:
    return {key: int(getattr(obj, key, 0)) for key in _STORAGE_KEYS}


def _apply_storage(obj: Any, data: dict[str, Any]) -> None:
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
    return cell


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
                "hunt_meat_pos": list(v.hunt_meat_pos) if v.hunt_meat_pos else None,
                "fish_target_id": v.fish_target_id,
                "fish_catch_pos": list(v.fish_catch_pos) if v.fish_catch_pos else None,
                "construction_id": v.construction_id,
                "priorities": [p.name for p in v.priorities],
                "satiation": round(v.satiation, 4),
                "ration_mode": v.ration_mode.name,
                "seeking_food": v.seeking_food,
                "last_food": v.last_food,
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
            "have_wood": s.have_wood,
            "have_rock": s.have_rock,
            "build_progress": s.build_progress,
            "plot_w": getattr(s, "plot_w", 1),
            "plot_h": getattr(s, "plot_h", 1),
        }
        for s in game.construction_sites.values()
    ]
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
            "migrate_target": list(a.migrate_target) if a.migrate_target else None,
            "migrate_patch_id": a.migrate_patch_id,
        }
        for a in game.wildlife.animals
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
            "next_id": game.wildlife.next_id,
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
    }
    if hasattr(game, "field_crop_kind"):
        payload["field_crop_kind"] = game.field_crop_kind
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
        if raw_mode is not None:
            try:
                work_mode = WorkMode[str(raw_mode)]
            except KeyError:
                work_mode = Building.work_mode_from_task(kind, draw_task)
        else:
            work_mode = Building.work_mode_from_task(kind, draw_task)
        if kind == BuildingKind.FARM:
            if raw_mode is None:
                work_mode = WorkMode.BOTH
            # else keep loaded Collect / Plant / Both
        elif kind not in (BuildingKind.FORESTER, BuildingKind.FORAGER, BuildingKind.FIELD):
            work_mode = WorkMode.COLLECT
        building = Building(
            id=int(bdata["id"]),
            kind=kind,
            x=int(bdata["x"]),
            y=int(bdata["y"]),
            capacity=int(bdata.get("capacity", BUILDING_STORAGE_CAPACITY)),
            draw_task_type=draw_task,
            work_mode=work_mode,
            plot_w=max(1, int(bdata.get("plot_w", 1))),
            plot_h=max(1, int(bdata.get("plot_h", 1))),
        )
        if kind == BuildingKind.FIELD:
            building.crop_kind = str(bdata.get("crop_kind", "sage"))
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

    # Re-sync after migration may have spawned buildings.
    if game.buildings:
        game.next_building_id = max(b.id for b in game.buildings.values()) + 1

    game.villagers.clear()
    for vdata in data.get("villagers", []):
        target = vdata.get("target")
        meat_pos = vdata.get("hunt_meat_pos")
        catch_pos = vdata.get("fish_catch_pos")
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
            hunt_meat_pos=tuple(meat_pos) if meat_pos else None,  # type: ignore[arg-type]
            fish_target_id=vdata.get("fish_target_id"),
            fish_catch_pos=tuple(catch_pos) if catch_pos else None,  # type: ignore[arg-type]
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
        raw_last = vdata.get("last_food")
        villager.last_food = str(raw_last) if raw_last else None
        game.villagers.append(villager)

    game.construction_sites.clear()
    for sdata in data.get("construction_sites", []):
        site = ConstructionSite(
            id=int(sdata["id"]),
            x=int(sdata["x"]),
            y=int(sdata["y"]),
            kind=BuildingKind[sdata["kind"]],
            need_wood=int(sdata["need_wood"]),
            need_rock=int(sdata["need_rock"]),
            have_wood=int(sdata.get("have_wood", 0)),
            have_rock=int(sdata.get("have_rock", 0)),
            build_progress=int(sdata.get("build_progress", 0)),
            plot_w=max(1, int(sdata.get("plot_w", 1))),
            plot_h=max(1, int(sdata.get("plot_h", 1))),
        )
        game.construction_sites[site.id] = site

    from wildlife import Animal, AnimalKind, AnimalSex, Fish

    wild = data.get("wildlife", {})
    game.wildlife.animals = []
    for a in wild.get("animals", []):
        kind_name = a.get("kind", "DEER")
        try:
            kind = AnimalKind[kind_name]
        except KeyError:
            kind = AnimalKind.DEER
        sex_name = a.get("sex", "MALE")
        try:
            sex = AnimalSex[sex_name]
        except KeyError:
            sex = AnimalSex.MALE
        mt = a.get("migrate_target")
        migrate_target = (int(mt[0]), int(mt[1])) if mt else None
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
                migrate_target=migrate_target,
                migrate_patch_id=(
                    int(a["migrate_patch_id"])
                    if a.get("migrate_patch_id") is not None
                    else None
                ),
            )
        )
    game.wildlife.next_id = int(wild.get("next_id", 1))
    game.wildlife.growth_timer = int(wild.get("growth_timer", game.wildlife.growth_timer))
    game.wildlife._seeded = True
    game.wildlife._index_animals()
    game.wildlife._form_mating_pairs()

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
    place = data.get("place_kind")
    game.place_kind = BuildingKind[place] if place else None
    game.sim_speed = int(data.get("sim_speed", 1))
    if game.sim_speed not in (0, 1, 2, 4, 8, 16):
        game.sim_speed = 1

    from seasons import (
        DAYS_PER_SEASON,
        SEASON_LENGTH_TICKS,
        TICKS_PER_DAY,
        YEAR_DAYS,
        Season,
        season_for_day,
    )

    if "calendar_day" in data:
        game.calendar_day = int(data["calendar_day"]) % YEAR_DAYS
        game.day_tick = int(data.get("day_tick", TICKS_PER_DAY))
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
        day_offset = min(DAYS_PER_SEASON - 1, elapsed // max(1, TICKS_PER_DAY))
        game.calendar_day = (base + day_offset) % YEAR_DAYS
        game.day_tick = TICKS_PER_DAY
    else:
        game.calendar_day = 0
        game.day_tick = TICKS_PER_DAY

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
    
    # Ensure core buildings exist (HOME, WORKSTATION)
    if hasattr(game, "_ensure_core_buildings"):
        game._ensure_core_buildings()

    # Biodiversity average is not saved; start a fresh rolling year window.
    if hasattr(game, "_biodiversity_samples"):
        game._biodiversity_samples.clear()
    if hasattr(game, "_sample_biodiversity"):
        game._sample_biodiversity()
    elif hasattr(game, "_refresh_indicators"):
        game._refresh_indicators()
    else:
        game.overlay_values = build_overlay_grid(game.world, game.overlay_mode)

    if hasattr(game, "_invalidate_terrain_layer"):
        game._invalidate_terrain_layer()
    if hasattr(game, "camera"):
        game.camera.center_on(
            game.player.x, game.player.y, game.world.cols, game.world.rows
        )


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
