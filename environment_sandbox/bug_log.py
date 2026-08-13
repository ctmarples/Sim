"""Automatic playtime bug log — detect stuck AI / supply issues, append JSONL.

Output: ``saves/bug_log.jsonl`` (one JSON object per line).
Offline review: ``python bug_log_report.py``.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from entities import (
    BUILDING_LABELS,
    BuildingKind,
    VillagerState,
)
from save_load import saves_dir

if TYPE_CHECKING:
    from entities import Building, Villager
    from game import Game

# Persist this many consecutive scans before logging (filters 1-tick flicker).
PERSIST_SCANS: int = 3
# Do not re-log the same dedupe key until this many calendar days pass.
COOLDOWN_DAYS: float = 1.0
# How often to scan, as a fraction of one in-game day.
SCAN_DAY_FRACTION: float = 0.25
# Never scan more often than this in real time (avoids hitching at high sim speed).
MIN_WALL_SECONDS: float = 2.0

PROCESSOR_KINDS = frozenset(
    {
        BuildingKind.MILL,
        BuildingKind.KITCHEN,
        BuildingKind.CRAFT_BENCH,
        BuildingKind.ALCHEMIST,
        BuildingKind.TAILOR,
        BuildingKind.COBBLER,
    }
)


@dataclass
class BugEvent:
    id: str
    kind: str
    summary: str
    wall_time: str
    calendar_day: int
    season: str
    day_tick: int
    save_name: str | None
    subjects: dict[str, list[int]]
    snapshot: dict[str, Any]
    hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bug_log_path() -> Path:
    return saves_dir() / "bug_log.jsonl"


# Optional override used by offline assessment runs.
_BUG_LOG_PATH_OVERRIDE: Path | None = None


def set_bug_log_path(path: Path | None) -> None:
    global _BUG_LOG_PATH_OVERRIDE
    _BUG_LOG_PATH_OVERRIDE = path


def _active_bug_log_path() -> Path:
    return _BUG_LOG_PATH_OVERRIDE if _BUG_LOG_PATH_OVERRIDE is not None else bug_log_path()


def _inv_nonzero(inv: object) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in vars(inv).items():
        if key.startswith("_") or key in ("equipped_tools", "equipped_clothing", "capacity", "seed_capacity"):
            continue
        if isinstance(value, int) and value > 0:
            out[key] = value
    return out


def _job_label(game: Game, villager: Villager) -> str:
    if villager.building_id is not None:
        building = game.buildings.get(villager.building_id)
        if building is None:
            return "INVALID_BUILDING"
        label = BUILDING_LABELS.get(building.kind, building.kind.name)
        return f"{label}#{building.id}"
    if villager.assigned_to_home:
        return "HAULER"
    return "UNASSIGNED"


def _villager_snapshot(game: Game, villager: Villager) -> dict[str, Any]:
    building = (
        game.buildings.get(villager.building_id)
        if villager.building_id is not None
        else None
    )
    data: dict[str, Any] = {
        "id": villager.id,
        "x": villager.x,
        "y": villager.y,
        "state": villager.state.name,
        "job": _job_label(game, villager),
        "building_id": villager.building_id,
        "target": list(villager.target) if villager.target else None,
        "haul_building_id": villager.haul_building_id,
        "craft_recipe_name": villager.craft_recipe_name,
        "equipped_tools": list(villager.inventory.equipped_tools),
        "inventory": _inv_nonzero(villager.inventory),
        "cargo_total": villager.inventory.cargo_total,
        "capacity": villager.inventory.effective_capacity,
        "satiation": round(float(villager.satiation), 3),
        "seeking_food": bool(villager.seeking_food),
        "priorities": [p.name for p in villager.active_priorities(game.season)],
    }
    if building is not None:
        try:
            data["primary_available"] = game._workplace_primary_available(
                villager, building
            )
            data["has_work_at"] = game._workplace_has_work_at(villager, building.id)
            data["needs_home_supply"] = game._workplace_needs_home_supply(building)
            data["assigned_transport"] = game._assigned_transport_has_work(
                villager, building
            )
        except Exception as exc:  # noqa: BLE001 — diagnostics must not crash sim
            data["probe_error"] = str(exc)
    return data


def _building_snapshot(game: Game, building: Building) -> dict[str, Any]:
    demand = {}
    try:
        demand = dict(game._building_supply_demand(building))
    except Exception:  # noqa: BLE001
        demand = dict(building.supply_demand())
    stock: dict[str, int] = {}
    for key, amount in _inv_nonzero(building).items():
        stock[key] = amount
    return {
        "id": building.id,
        "kind": building.kind.name,
        "label": BUILDING_LABELS.get(building.kind, building.kind.name),
        "pos": list(building.center_cell()),
        "cargo_stored": building.cargo_stored_total,
        "capacity": building.capacity,
        "space_left": building.space_left,
        "seed_stored": building.seed_stored_total,
        "seed_capacity": building.seed_capacity,
        "haulable_total": building.haulable_total(),
        "stock": stock,
        "supply_demand": demand,
        "item_caps": dict(building.item_caps),
        "recipe_enabled": dict(building.recipe_enabled),
        "recipe_progress": dict(building.recipe_progress),
    }


def _village_stock_for(game: Game, keys: list[str]) -> dict[str, dict[str, int]]:
    home: dict[str, int] = {}
    farms: dict[str, int] = {}
    for key in keys:
        home[key] = int(getattr(game.home_storage, key, 0))
        total = 0
        for building in game.buildings.values():
            if building.kind == BuildingKind.FARM:
                total += int(building.haulable_amount(key))
        farms[key] = total
    return {"home": home, "farm_haulable": farms}


class BugLog:
    """Periodic detectors → JSONL append with persistence + dedupe."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self._scan_counter = 0
        self._last_scan_day_frac: float | None = None
        self._last_scan_wall: float = 0.0
        # key → consecutive positive scans
        self._streak: dict[str, int] = {}
        # key → calendar_day float when last logged
        self._last_logged: dict[str, float] = {}

    def scan(self, game: Game, *, force: bool = False) -> list[BugEvent]:
        """Run detectors if enabled and enough time has passed. Returns newly logged events."""
        if not self.enabled and not force:
            return []
        now = time.monotonic()
        if not force and now - self._last_scan_wall < MIN_WALL_SECONDS:
            return []
        day_frac = float(game.calendar_day) + (
            1.0 - game.day_tick / max(1, game.ticks_per_day)
        )
        if not force and self._last_scan_day_frac is not None:
            if day_frac - self._last_scan_day_frac < SCAN_DAY_FRACTION:
                return []
        self._last_scan_day_frac = day_frac
        self._last_scan_wall = now
        self._scan_counter += 1

        # Lightweight candidates first; build rich BugEvent only when logging.
        found: list[tuple[str, Callable[[], BugEvent]]] = []
        found.extend(self._detect_idle_assigned(game, day_frac))
        found.extend(self._detect_supply_blocked(game, day_frac))
        found.extend(self._detect_farm_harvest_divert(game, day_frac))

        seen_now = {key for key, _ in found}
        for key in list(self._streak):
            if key not in seen_now:
                self._streak.pop(key, None)

        # Offline/forced scans: log on first detection (no multi-scan persist gate).
        persist_need = 1 if force else PERSIST_SCANS
        logged: list[BugEvent] = []
        for key, builder in found:
            streak = self._streak.get(key, 0) + 1
            self._streak[key] = streak
            if streak < persist_need:
                continue
            last = self._last_logged.get(key)
            if last is not None and day_frac - last < COOLDOWN_DAYS:
                continue
            event = builder()
            self._append(event)
            self._last_logged[key] = day_frac
            logged.append(event)
        return logged

    def _save_name(self, game: Game) -> str | None:
        path = getattr(game, "_last_save_path", None) or getattr(
            game, "_loaded_save_name", None
        )
        if path is None:
            return None
        return Path(path).name

    def _base_event(
        self,
        game: Game,
        *,
        kind: str,
        dedupe_key: str,
        summary: str,
        subjects: dict[str, list[int]],
        snapshot: dict[str, Any],
        hints: list[str],
        day_frac: float,
    ) -> BugEvent:
        bucket = int(day_frac)
        event_id = f"{dedupe_key}:{bucket}"
        return BugEvent(
            id=event_id,
            kind=kind,
            summary=summary,
            wall_time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            calendar_day=int(game.calendar_day),
            season=game.season.name,
            day_tick=int(game.day_tick),
            save_name=self._save_name(game),
            subjects=subjects,
            snapshot=snapshot,
            hints=hints,
        )

    def _append(self, event: BugEvent) -> None:
        path = _active_bug_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------
    def _detect_idle_assigned(
        self, game: Game, day_frac: float
    ) -> list[tuple[str, Callable[[], BugEvent]]]:
        out: list[tuple[str, Callable[[], BugEvent]]] = []
        # Cache building-level probes once per scan (many workers share a workplace).
        supply_cache: dict[int, bool] = {}
        demand_cache: dict[int, dict[str, int]] = {}

        for villager in game.villagers:
            if villager.building_id is None:
                continue
            if villager.state != VillagerState.IDLE:
                continue
            if villager.seeking_food or villager.needs_food():
                continue
            building = game.buildings.get(villager.building_id)
            if building is None:
                continue

            bid = building.id
            try:
                if bid not in supply_cache:
                    supply_cache[bid] = game._workplace_needs_home_supply(building)
                needs_supply = supply_cache[bid]
                primary = game._workplace_primary_available(villager, building)
                has_at = game._workplace_has_work_at(villager, building.id)
                barn = (
                    game._farm_barn_has_work(villager, building)
                    if building.kind == BuildingKind.FARM
                    else False
                )
                has_work = primary or has_at or needs_supply or barn
            except Exception:  # noqa: BLE001
                continue

            if not has_work:
                continue

            if bid not in demand_cache:
                try:
                    demand_cache[bid] = dict(game._building_supply_demand(building))
                except Exception:  # noqa: BLE001
                    demand_cache[bid] = {}
            demand = demand_cache[bid]
            label = BUILDING_LABELS.get(building.kind, building.kind.name)
            dedupe = f"idle_assigned:{villager.id}:{building.id}"
            v_ref, b_ref = villager, building
            p_ref, ha_ref, ns_ref, barn_ref = primary, has_at, needs_supply, barn

            def _build(
                villager=v_ref,
                building=b_ref,
                demand=demand,
                label=label,
                primary=p_ref,
                has_at=ha_ref,
                needs_supply=ns_ref,
                barn=barn_ref,
                dedupe=dedupe,
            ) -> BugEvent:
                hints = [
                    f"primary_available={primary}",
                    f"has_work_at={has_at}",
                    f"needs_home_supply={needs_supply}",
                ]
                if building.kind == BuildingKind.FARM:
                    hints.append(f"barn_has_work={barn}")
                stock: dict[str, Any] = {}
                if demand:
                    hints.append(f"supply_demand={demand}")
                    stock = _village_stock_for(game, list(demand))
                    hints.append(f"village_stock={stock}")
                return self._base_event(
                    game,
                    kind="idle_assigned",
                    dedupe_key=dedupe,
                    summary=(
                        f"{label} worker #{villager.id} IDLE while workplace "
                        f"#{building.id} has available work"
                    ),
                    subjects={
                        "villager_ids": [villager.id],
                        "building_ids": [building.id],
                    },
                    snapshot={
                        "villager": _villager_snapshot(game, villager),
                        "building": _building_snapshot(game, building),
                        "village_stock": stock,
                    },
                    hints=hints,
                    day_frac=day_frac,
                )

            out.append((dedupe, _build))
        return out

    def _detect_supply_blocked(
        self, game: Game, day_frac: float
    ) -> list[tuple[str, Callable[[], BugEvent]]]:
        out: list[tuple[str, Callable[[], BugEvent]]] = []
        for building in game.buildings.values():
            if building.kind not in PROCESSOR_KINDS:
                continue
            try:
                demand = dict(game._building_supply_demand(building))
            except Exception:  # noqa: BLE001
                continue
            if not demand:
                continue
            try:
                can_supply = game._processor_can_be_supplied(building)
            except Exception:  # noqa: BLE001
                can_supply = False
            if not can_supply:
                continue

            serving = False
            for other in game.villagers:
                if other.haul_building_id == building.id and other.state in (
                    VillagerState.HAULING,
                    VillagerState.DELIVERING,
                ):
                    serving = True
                    break
                if (
                    other.building_id == building.id
                    and other.state
                    in (VillagerState.HAULING, VillagerState.DELIVERING, VillagerState.WORKING)
                    and other.craft_recipe_name
                ):
                    serving = True
                    break
            if serving:
                continue

            workers = [v for v in game.villagers if v.building_id == building.id]
            idle_workers = [
                v for v in workers if v.state == VillagerState.IDLE and not v.seeking_food
            ]
            if workers and not idle_workers:
                try:
                    craftable = game._craftable_recipe(building) is not None
                except Exception:  # noqa: BLE001
                    craftable = False
                if craftable:
                    continue

            label = BUILDING_LABELS.get(building.kind, building.kind.name)
            dedupe = f"supply_blocked:{building.id}"
            b_ref = building

            def _build(
                building=b_ref,
                demand=demand,
                can_supply=can_supply,
                workers=workers,
                idle_workers=idle_workers,
                label=label,
                dedupe=dedupe,
            ) -> BugEvent:
                stock = _village_stock_for(game, list(demand))
                hints = [
                    f"supply_demand={demand}",
                    f"can_be_supplied={can_supply}",
                    f"village_stock={stock}",
                    f"workers={len(workers)} idle={len(idle_workers)}",
                ]
                return self._base_event(
                    game,
                    kind="supply_blocked",
                    dedupe_key=dedupe,
                    summary=(
                        f"{label} #{building.id} needs {demand} with village stock "
                        f"available, but nobody is supplying it"
                    ),
                    subjects={
                        "villager_ids": [v.id for v in workers],
                        "building_ids": [building.id],
                    },
                    snapshot={
                        "building": _building_snapshot(game, building),
                        "workers": [_villager_snapshot(game, v) for v in workers],
                        "village_stock": stock,
                    },
                    hints=hints,
                    day_frac=day_frac,
                )

            out.append((dedupe, _build))
        return out

    def _detect_farm_harvest_divert(
        self, game: Game, day_frac: float
    ) -> list[tuple[str, Callable[[], BugEvent]]]:
        out: list[tuple[str, Callable[[], BugEvent]]] = []
        home = game.world.home_pos
        candidates: list[tuple[Any, Any]] = []
        for villager in game.villagers:
            if villager.building_id is None:
                continue
            if villager.state != VillagerState.DELIVERING:
                continue
            if villager.target != home:
                continue
            farm = game.buildings.get(villager.building_id)
            if farm is None or farm.kind != BuildingKind.FARM:
                continue
            inv = villager.inventory
            if not farm.has_gather_cargo(inv):
                continue
            if inv.is_full or not inv.can_add(1):
                continue
            if inv.effective_capacity > 0 and inv.cargo_total * 10 >= inv.effective_capacity * 7:
                continue
            candidates.append((villager, farm))
        if not candidates:
            return out

        ripe_cache: dict[int, int] = {}
        for villager, farm in candidates:
            if farm.id not in ripe_cache:
                ripe = 0
                try:
                    for field_b in game._fields_near_farm(farm):
                        for x, y in field_b.plot_cells():
                            if game.world.crop_herb_ready(x, y):
                                ripe += 1
                except Exception:  # noqa: BLE001
                    ripe = 0
                ripe_cache[farm.id] = ripe
            ripe = ripe_cache[farm.id]
            if ripe <= 0:
                continue

            dedupe = f"farm_harvest_divert:{villager.id}:{farm.id}"
            v_ref, f_ref = villager, farm

            def _build(villager=v_ref, farm=f_ref, ripe=ripe, dedupe=dedupe) -> BugEvent:
                inv = villager.inventory
                hints = [
                    f"ripe_tiles={ripe}",
                    f"cargo={inv.cargo_total}/{inv.effective_capacity}",
                    f"farm_space_left={farm.space_left}",
                    f"can_accept={farm.can_accept_from(inv)}",
                    f"item_caps={dict(farm.item_caps)}",
                    f"needs_clear={game._farm_or_processor_needs_clear(farm)}",
                ]
                return self._base_event(
                    game,
                    kind="farm_harvest_divert",
                    dedupe_key=dedupe,
                    summary=(
                        f"Farmer #{villager.id} delivering partial harvest "
                        f"({inv.cargo_total}/{inv.effective_capacity}) to storehouse "
                        f"while {ripe} ripe tiles remain"
                    ),
                    subjects={
                        "villager_ids": [villager.id],
                        "building_ids": [farm.id],
                    },
                    snapshot={
                        "villager": _villager_snapshot(game, villager),
                        "farm": _building_snapshot(game, farm),
                        "ripe_tiles": ripe,
                    },
                    hints=hints,
                    day_frac=day_frac,
                )

            out.append((dedupe, _build))
        return out
