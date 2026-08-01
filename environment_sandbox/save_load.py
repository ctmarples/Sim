"""Serialize and restore game state as JSON save files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from entities import (
    Building,
    BuildingKind,
    ConstructionSite,
    Inventory,
    TaskArea,
    TaskType,
    Villager,
    VillagerState,
    WorkMode,
    WorkPriority,
)
from wildlife import Animal
from world import Cell, FeatureType, TerrainType, World

if TYPE_CHECKING:
    from game import Game

SAVE_VERSION = 1


def saves_dir() -> Path:
    path = Path(__file__).resolve().parent.parent / "saves"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_save_files() -> list[str]:
    files = sorted(p.name for p in saves_dir().glob("*.json") if p.is_file())
    return files


def _inv_to_dict(inv: Inventory) -> dict[str, int]:
    return {
        "wood": inv.wood,
        "rock": inv.rock,
        "meat": inv.meat,
        "fish": inv.fish,
        "saplings": inv.saplings,
        "mushrooms": inv.mushrooms,
        "berries": inv.berries,
        "berry_seeds": inv.berry_seeds,
        "herbs": inv.herbs,
        "herb_seeds": inv.herb_seeds,
        "capacity": inv.capacity,
    }


def _inv_from_dict(data: dict[str, Any]) -> Inventory:
    inv = Inventory(capacity=int(data.get("capacity", Inventory().capacity)))
    for key in (
        "wood",
        "rock",
        "meat",
        "fish",
        "saplings",
        "mushrooms",
        "berries",
        "berry_seeds",
        "herbs",
        "herb_seeds",
    ):
        setattr(inv, key, int(data.get(key, 0)))
    return inv


def _storage_to_dict(obj: Any) -> dict[str, int]:
    return {
        "wood": obj.wood,
        "rock": obj.rock,
        "meat": obj.meat,
        "fish": getattr(obj, "fish", 0),
        "saplings": obj.saplings,
        "mushrooms": obj.mushrooms,
        "berries": obj.berries,
        "berry_seeds": obj.berry_seeds,
        "herbs": obj.herbs,
        "herb_seeds": obj.herb_seeds,
    }


def _apply_storage(obj: Any, data: dict[str, Any]) -> None:
    for key, value in _storage_to_dict(obj).items():
        setattr(obj, key, int(data.get(key, 0)))


def serialize_game(game: Game) -> dict[str, Any]:
    import settings as cfg

    world = game.world
    cells = [
        [
            {
                "terrain": cell.terrain.name,
                "feature": cell.feature.name,
                "disturbance": cell.disturbance,
                "growth_ticks": cell.growth_ticks,
                "deposit": cell.deposit,
                "meat_deposit": cell.meat_deposit,
                "fish_deposit": cell.fish_deposit,
            }
            for cell in row
        ]
        for row in world.cells
    ]
    buildings = []
    for b in game.buildings.values():
        buildings.append(
            {
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
            }
        )
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
        }
        for s in game.construction_sites.values()
    ]
    animals = [
        {
            "id": a.id,
            "x": a.x,
            "y": a.y,
            "move_cooldown": a.move_cooldown,
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
    return {
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


def apply_save(game: Game, data: dict[str, Any]) -> None:
    import settings as cfg

    from indicators import OverlayMode, build_overlay_grid
    from settings import BUILDING_STORAGE_CAPACITY, RANDOM_SEED

    if int(data.get("version", 0)) != SAVE_VERSION:
        raise ValueError(f"Unsupported save version: {data.get('version')}")

    grid = data["grid"]
    cols, rows = int(grid["cols"]), int(grid["rows"])
    display = data.get("display") or {}
    # Prefer the display size the save was created with when present.
    want_cols = int(display.get("grid_cols", cols))
    want_rows = int(display.get("grid_rows", rows))
    if want_cols != cols or want_rows != rows:
        # Fall back to raw cell grid size.
        want_cols, want_rows = cols, rows

    if want_cols != cfg.GRID_COLS or want_rows != cfg.GRID_ROWS:
        # Rebuild window metrics so coordinates in the save stay valid.
        cell = cfg.CELL_SIZE
        cfg.GRID_COLS = want_cols
        cfg.GRID_ROWS = want_rows
        cfg.WINDOW_WIDTH = want_cols * cell + cfg.PANEL_WIDTH
        cfg.WINDOW_HEIGHT = cfg.MAP_OFFSET_Y + want_rows * cell
        game.screen = __import__("pygame").display.set_mode(
            (cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT)
        )
        # Toolbar button layout depends on window width.
        game.toolbar._rebuild_static()

    cols, rows = want_cols, want_rows
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
        cells.append(
            [
                Cell(
                    terrain=TerrainType[c["terrain"]],
                    feature=FeatureType[c["feature"]],
                    disturbance=float(c.get("disturbance", 0.0)),
                    growth_ticks=int(c.get("growth_ticks", 0)),
                    deposit=int(c.get("deposit", 0)),
                    meat_deposit=int(c.get("meat_deposit", 0)),
                    fish_deposit=int(c.get("fish_deposit", 0)),
                )
                for c in row
            ]
        )
    world.cells = cells
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
        if kind not in (BuildingKind.FORESTER, BuildingKind.FORAGER):
            work_mode = WorkMode.COLLECT
        building = Building(
            id=int(bdata["id"]),
            kind=kind,
            x=int(bdata["x"]),
            y=int(bdata["y"]),
            capacity=int(bdata.get("capacity", BUILDING_STORAGE_CAPACITY)),
            draw_task_type=draw_task,
            work_mode=work_mode,
        )
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
        game.buildings[building.id] = building

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
        )
        game.construction_sites[site.id] = site

    from wildlife import Fish

    wild = data.get("wildlife", {})
    game.wildlife.animals = [
        Animal(
            id=int(a["id"]),
            x=int(a["x"]),
            y=int(a["y"]),
            move_cooldown=int(a.get("move_cooldown", 0)),
        )
        for a in wild.get("animals", [])
    ]
    game.wildlife.next_id = int(wild.get("next_id", 1))
    game.wildlife.growth_timer = int(wild.get("growth_timer", game.wildlife.growth_timer))

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
    game.overlay_values = build_overlay_grid(game.world, game.overlay_mode)
    game._clear_selection()
    game.drawing = False
    game.draw_start = None
    game.draw_current = None
    game._mouse_down_cell = None


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
