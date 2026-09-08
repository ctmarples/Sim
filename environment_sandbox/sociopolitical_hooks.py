"""Bootstrap the Sociopolitical Test Settlement and apply decision effects."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from entities import (
    Building,
    BuildingKind,
    RationMode,
    Villager,
    apply_building_storage,
    default_building_plot,
)
from society import (
    JOB_SKILL_REQUIREMENTS,
    SKILL_ORDER,
    SkillState,
    SkillType,
    apply_timed_happiness_impact,
    free_housing_beds,
    skills_from_dict,
)
from sociopolitical import (
    DECISION_EVENTS,
    EVENT_ORDER,
    ImmediateEffect,
    OpenApplicant,
    RecruitmentPolicy,
    SettlementPoliticalState,
    TEST_SEASON_LIMIT,
    average,
    ecology_recovery_multiplier,
    event_by_id,
    extractive_work_multiplier,
    generate_settlement_description,
    missing_ration_happiness_scale,
    next_manual_event_id,
    principle_by_id,
    resolve_option,
    work_efficiency_multiplier,
)
from status_effects_ui import StatusMod

if TYPE_CHECKING:
    from game import Game


FEATURE_FOR_KIND = {
    BuildingKind.HOME: "HOME",
    BuildingKind.WORKSTATION: "WORKSTATION",
    BuildingKind.FORESTER: "FORESTER",
    BuildingKind.HUNTER: "HUNTER",
    BuildingKind.FORAGER: "FORAGER",
    BuildingKind.FISHER: "FISHER",
    BuildingKind.FARM: "FARM",
    BuildingKind.FIELD: "FIELD",
    BuildingKind.KITCHEN: "KITCHEN",
    BuildingKind.MARKET: "MARKET",
    BuildingKind.HOUSE: "HOUSE",
    BuildingKind.HOUSE_SMALL: "HOUSE_SMALL",
    BuildingKind.TENT: "TENT",
    BuildingKind.CRAFT_BENCH: "CRAFT_BENCH",
}


VILLAGER_PRESETS: tuple[dict, ...] = (
    {"name": "Mara", "skills": {"farming": 5, "labour": 3}},
    {"name": "Oren", "skills": {"extraction": 5, "labour": 2}},
    {"name": "Sela", "skills": {"hunting": 4, "labour": 2}},
    {"name": "Bram", "skills": {"crafting": 4, "farming": 2}},
    {"name": "Nila", "skills": {"transport": 4, "labour": 3}},
    {"name": "Joss", "skills": {"extraction": 3, "farming": 3, "labour": 3}},
)

JOB_ASSIGNMENTS: tuple[BuildingKind, ...] = (
    BuildingKind.FARM,
    BuildingKind.FORESTER,
    BuildingKind.HUNTER,
    BuildingKind.FORAGER,
    BuildingKind.KITCHEN,
    BuildingKind.MARKET,
)


def _find_plot(
    game: Game,
    kind: BuildingKind,
    origin: tuple[int, int],
    *,
    plot_w: int | None = None,
    plot_h: int | None = None,
    radius: int = 18,
) -> tuple[int, int] | None:
    from world import FeatureType, TerrainType

    pw, ph = default_building_plot(kind)
    if plot_w is not None:
        pw = plot_w
    if plot_h is not None:
        ph = plot_h
    ox, oy = origin
    blocked = {
        FeatureType.HOME,
        FeatureType.WORKSTATION,
        FeatureType.FORESTER,
        FeatureType.MASON,
        FeatureType.HUNTER,
        FeatureType.FORAGER,
        FeatureType.FISHER,
        FeatureType.FARM,
        FeatureType.FIELD,
        FeatureType.MILL,
        FeatureType.KITCHEN,
        FeatureType.FIRE,
        FeatureType.CRAFT_BENCH,
        FeatureType.ALCHEMIST,
        FeatureType.TAILOR,
        FeatureType.MARKET,
        FeatureType.CONSTRUCTION_SITE,
        FeatureType.STRUCTURE_PAD,
        FeatureType.TREE,
        FeatureType.ROCK,
        FeatureType.TENT,
        FeatureType.HOUSE_SMALL,
        FeatureType.HOUSE,
    }
    land = {TerrainType.GRASS, TerrainType.MEADOW, TerrainType.SOIL, TerrainType.PATH}
    candidates: list[tuple[int, int, int]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = ox + dx, oy + dy
            if x < 1 or y < 1 or x + pw >= game.world.cols - 1 or y + ph >= game.world.rows - 1:
                continue
            ok = True
            for py in range(y, y + ph):
                for px in range(x, x + pw):
                    cell = game.world.get_cell(px, py)
                    if cell is None or cell.terrain not in land or cell.feature in blocked:
                        ok = False
                        break
                    if game._building_at(px, py) is not None:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                candidates.append((abs(dx) + abs(dy), x, y))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1], candidates[0][2]


def _place_building(
    game: Game,
    kind: BuildingKind,
    x: int,
    y: int,
    *,
    plot_w: int | None = None,
    plot_h: int | None = None,
) -> Building:
    from world import FeatureType

    pw, ph = default_building_plot(kind)
    if plot_w is not None:
        pw = plot_w
    if plot_h is not None:
        ph = plot_h
    building = Building(
        id=game.next_building_id,
        kind=kind,
        x=x,
        y=y,
        plot_w=pw,
        plot_h=ph,
    )
    apply_building_storage(building)
    game.buildings[building.id] = building
    game.next_building_id += 1
    feature_name = FEATURE_FOR_KIND.get(kind)
    if feature_name:
        feature = FeatureType[feature_name]
        game.world.claim_structure_footprint(x, y, pw, ph, feature)
    if kind == BuildingKind.WORKSTATION:
        game.world.workstation_pos = building.center_cell()
    if kind == BuildingKind.HOME:
        game.world.home_pos = building.center_cell()
    return building


def bootstrap_sociopolitical_test(game: Game) -> SettlementPoliticalState:
    """Build a stable mid-game settlement for political testing."""
    hx, hy = game.world.home_pos
    # Clear default starting villagers; we replace with a crafted roster.
    game.villagers.clear()
    game.next_villager_id = 1
    game.hire_candidates.clear()
    game.construction_sites.clear()

    # Ensure storehouse + hiring hall.
    if not any(b.kind == BuildingKind.HOME for b in game.buildings.values()):
        pos = _find_plot(game, BuildingKind.HOME, (hx, hy)) or (hx - 1, hy - 1)
        _place_building(game, BuildingKind.HOME, pos[0], pos[1])
    home = next(b for b in game.buildings.values() if b.kind == BuildingKind.HOME)
    hx, hy = home.center_cell()
    game.world.home_pos = (hx, hy)

    if not any(b.kind == BuildingKind.WORKSTATION for b in game.buildings.values()):
        pos = _find_plot(game, BuildingKind.WORKSTATION, (hx + 4, hy))
        if pos:
            _place_building(game, BuildingKind.WORKSTATION, pos[0], pos[1])

    # Housing with spare beds: one HOUSE (8 beds) for 6 villagers → 2 empty.
    if not any(b.kind == BuildingKind.HOUSE for b in game.buildings.values()):
        pos = _find_plot(game, BuildingKind.HOUSE, (hx - 5, hy))
        if pos is None:
            pos = _find_plot(game, BuildingKind.HOUSE, (hx, hy), radius=28)
        if pos:
            _place_building(game, BuildingKind.HOUSE, pos[0], pos[1])

    workplaces: dict[BuildingKind, Building] = {}
    offsets = [
        (BuildingKind.FARM, (hx + 6, hy + 2)),
        (BuildingKind.FORESTER, (hx - 6, hy + 3)),
        (BuildingKind.HUNTER, (hx + 3, hy - 6)),
        (BuildingKind.FORAGER, (hx - 3, hy - 6)),
        (BuildingKind.KITCHEN, (hx + 2, hy + 5)),
        (BuildingKind.MARKET, (hx - 2, hy + 5)),
        (BuildingKind.CRAFT_BENCH, (hx + 7, hy - 2)),
    ]
    for kind, near in offsets:
        if any(b.kind == kind for b in game.buildings.values()):
            workplaces[kind] = next(b for b in game.buildings.values() if b.kind == kind)
            continue
        pos = _find_plot(game, kind, near)
        if pos is None:
            pos = _find_plot(game, kind, (hx, hy), radius=30)
        if pos:
            workplaces[kind] = _place_building(game, kind, pos[0], pos[1])

    # Established field attached near the farm.
    if not any(b.kind == BuildingKind.FIELD for b in game.buildings.values()):
        farm = workplaces.get(BuildingKind.FARM)
        near = farm.center_cell() if farm else (hx + 8, hy + 2)
        pos = _find_plot(game, BuildingKind.FIELD, near, plot_w=4, plot_h=3)
        if pos:
            field = _place_building(
                game, BuildingKind.FIELD, pos[0], pos[1], plot_w=4, plot_h=3
            )
            # Mark soil as worked field tiles.
            from world import FeatureType, TerrainType

            for cell_x, cell_y in field.plot_cells():
                cell = game.world.get_cell(cell_x, cell_y)
                if cell is not None:
                    cell.terrain = TerrainType.SOIL
                    if hasattr(cell, "ploughed"):
                        cell.ploughed = True

    # Food / materials / gold sufficient to ignore survival balance.
    game.home_storage.reset()
    game.home_storage.deposit_dict(
        {
            "logs": 40,
            "wood": 30,
            "rock": 30,
            "twine": 20,
            "berries": 40,
            "meat": 30,
            "fish": 24,
            "bread": 36,
            "wheat": 20,
            "wheat_grain": 20,
            "stew": 12,
            "axe": 3,
            "hoe": 3,
            "spear": 2,
            "knife": 2,
            "fishing_rod": 1,
        }
    )
    game.regional_wealth = 60

    # Six villagers with distinct skills and housing.
    house = next((b for b in game.buildings.values() if b.kind == BuildingKind.HOUSE), None)
    for i, preset in enumerate(VILLAGER_PRESETS):
        sx, sy = home.center_cell()
        skills = skills_from_dict(
            {k: {"level": v, "potential": max(5, v), "peak": v} for k, v in preset["skills"].items()}
        )
        villager = Villager(
            id=game.next_villager_id,
            x=sx,
            y=sy,
            name=preset["name"],
            skills=skills,
            housing_need=1,
            required_foods=["bread", "meat"],
            favourite_foods=["stew"],
            happiness=0.72,
            energy=1.0,
            satiation=0.85,
            ration_mode=RationMode.NORMAL,
        )
        game.next_villager_id += 1
        game.villagers.append(villager)
        if house is not None:
            villager.housed = True
            villager.housing_id = house.id
        job_kind = JOB_ASSIGNMENTS[i % len(JOB_ASSIGNMENTS)]
        workplace = workplaces.get(job_kind)
        if workplace is not None:
            villager.building_id = workplace.id
            # building_id alone is not enough — default priorities are unassigned
            # (Build/Transport), which filter down to hauling once a workplace is set.
            villager.set_default_priorities()

    game._sync_building_collision()
    # Drop incidental tents so bed math matches the brief (HOUSE 8 − 6 = 2 free).
    for bid, building in list(game.buildings.items()):
        if building.kind != BuildingKind.TENT:
            continue
        for cell_x, cell_y in building.plot_cells():
            cell = game.world.get_cell(cell_x, cell_y)
            if cell is not None:
                from world import FeatureType

                if cell.feature == FeatureType.TENT:
                    cell.feature = FeatureType.NONE
        del game.buildings[bid]
    for villager in game.villagers:
        villager.housed = False
        villager.housing_id = None
    if house is not None:
        for villager in game.villagers:
            villager.housed = True
            villager.housing_id = house.id
    game._rehouse_villagers()
    game._seed_map_communities()
    # Keep a few hire candidates for contract recruitment testing.
    if len(game.hire_candidates) < 3:
        game._top_up_hire_candidates()

    state = SettlementPoliticalState(
        test_active=True,
        starting_population=len(game.villagers),
        recruitment_policy=RecruitmentPolicy.CONTRACT,
    )
    state.add_diary(
        int(game.calendar_day),
        "note",
        "Sociopolitical Test Settlement prepared.",
        "Survival is stable — focus on political decisions.",
    )
    game.political = state
    sample_metrics(game)
    game._set_status(
        "Sociopolitical Test Settlement ready. Open File → Sociopolitical… "
        "or press the panel controls to begin decisions."
    )
    return state


def _seasonal_work_cause_label(state: SettlementPoliticalState) -> str:
    """Principle / decision title for the seasonal work buff (never a bare 'Decision')."""
    cause = str(getattr(state, "seasonal_work_source", "") or "").strip()
    if cause and cause.lower() not in {"decision", "seasonal decision"}:
        return cause
    # Recover from enacted principles that granted a seasonal work bonus.
    for pid in reversed(list(state.enacted_principle_ids)):
        for event in DECISION_EVENTS.values():
            for opt in event.options:
                if opt.principle_id != pid:
                    continue
                if not any(e.kind == "work_efficiency_season" for e in opt.immediate_effects):
                    continue
                principle = principle_by_id(pid)
                return principle.name if principle is not None else opt.label
    return "Work organisation"


def political_status_mods(game: Game, villager: Villager) -> list[StatusMod]:
    """Buff/debuff tiles for the diary Buffs section from institutions + decisions.

    Only includes impacts that currently apply to this villager. Hover tips are
    short: effect on the slot, cause name on the badge.
    """
    state = getattr(game, "political", None)
    if state is None or not (state.test_active or state.institution_ids or state.seasonal_work_bonus):
        return []
    mods: list[StatusMod] = []
    matches = job_matches_strongest(villager, game.buildings)

    if state.has_institution("settlement_office"):
        mods.append(
            StatusMod(
                cause_key="settlement_office",
                cause_icon="construction_site",
                cause_group="political",
                effect="work",
                mult=1.10,
                cause_label="Settlement Office",
                display_kind="buff",
            )
        )
        if villager.building_id is not None and not matches:
            mods.append(
                StatusMod(
                    cause_key="settlement_office_mismatch",
                    cause_icon="construction_site",
                    cause_group="political",
                    effect="happiness",
                    mult=-5,
                    cause_label="Settlement Office",
                    tip_override="Happiness −5",
                    display_kind="debuff",
                )
            )

    if state.has_institution("labour_exchange") and matches:
        mods.append(
            StatusMod(
                cause_key="labour_exchange",
                cause_icon="coins",
                cause_group="political",
                effect="work",
                mult=1.10,
                cause_label="Labour Exchange",
                display_kind="buff",
            )
        )

    # Rations: show happiness impact only (never a "rations: half/full" chip).
    if villager.ration_mode.name == "HALF":
        from society import HAPPINESS_HALF_RATION_PENALTY

        scale = missing_ration_happiness_scale(state)
        penalty = HAPPINESS_HALF_RATION_PENALTY * scale
        pct = int(round(penalty * 100))
        if state.has_institution("common_provision"):
            cause = "Common Provision: half rations"
        else:
            cause = "Half rations"
        mods.append(
            StatusMod(
                cause_key="half_rations",
                cause_icon="bread",
                cause_group="political",
                effect="happiness",
                mult=-pct,
                cause_label=cause,
                tip_override=f"Happiness −{pct}%",
                display_kind="debuff",
            )
        )
    elif villager.ration_mode.name == "DOUBLE":
        from society import HAPPINESS_DOUBLE_RATION_BONUS

        pct = int(round(HAPPINESS_DOUBLE_RATION_BONUS * 100))
        if state.has_institution("common_provision"):
            cause = "Common Provision: double rations"
        else:
            cause = "Double rations"
        mods.append(
            StatusMod(
                cause_key="double_rations",
                cause_icon="bread",
                cause_group="political",
                effect="happiness",
                mult=pct,
                cause_label=cause,
                tip_override=f"Happiness +{pct}%",
                display_kind="buff",
            )
        )

    if state.has_institution("covenant_of_the_land"):
        slow = extractive_work_multiplier(state)
        building = game.buildings.get(villager.building_id or -1)
        if building is not None and building.kind in (
            BuildingKind.FORESTER,
            BuildingKind.FIELD,
            BuildingKind.ORCHARD,
        ):
            mods.append(
                StatusMod(
                    cause_key="covenant_extractive",
                    cause_icon="tree_round",
                    cause_group="political",
                    effect="work",
                    mult=1.0 / slow,
                    cause_label="Covenant of the Land",
                    display_kind="debuff",
                )
            )

    if state.seasonal_work_bonus > 0:
        bonus = 1.0 + float(state.seasonal_work_bonus)
        cause = _seasonal_work_cause_label(state)
        # Keep stored source in sync when recovered from principles / old saves.
        if state.seasonal_work_source != cause:
            state.seasonal_work_source = cause
        mods.append(
            StatusMod(
                cause_key="seasonal_decision",
                cause_icon="construction_site",
                cause_group="political",
                effect="work",
                mult=bonus,
                cause_label=cause,
                display_kind="buff",
            )
        )

    return mods


def villager_political_work_mult(game: Game, villager: Villager) -> float:
    state = getattr(game, "political", None)
    mult = work_efficiency_multiplier(
        state,
        job_matches_strongest=job_matches_strongest(villager, game.buildings),
    )
    building = game.buildings.get(villager.building_id or -1)
    if building is not None and building.kind in (
        BuildingKind.FORESTER,
        BuildingKind.FIELD,
        BuildingKind.ORCHARD,
    ):
        mult /= extractive_work_multiplier(state)
    return mult


def live_effect_snapshot(game: Game) -> dict[str, float]:
    """Current settlement averages including political work modifiers."""
    state = getattr(game, "political", None)
    happiness = 0.0
    efficiency = 0.0
    if game.villagers:
        happiness = sum(float(v.happiness) for v in game.villagers) / len(game.villagers)
        efficiency = sum(
            (0.65 + 0.35 * float(v.happiness))
            * max(0.2, float(v.satiation))
            * float(getattr(v, "food_work_mult", 1.0) or 1.0)
            * villager_political_work_mult(game, v)
            for v in game.villagers
        ) / len(game.villagers)
    hx, hy = game.world.home_pos
    total = 0.0
    count = 0
    for y in range(max(0, hy - 12), min(game.world.rows, hy + 11)):
        for x in range(max(0, hx - 12), min(game.world.cols, hx + 11)):
            total += float(game.world.cells[y][x].disturbance)
            count += 1
    ecology = max(0.0, 1.0 - total / count) if count else 0.0
    return {
        "happiness": happiness,
        "efficiency": efficiency,
        "ecology": ecology,
        "happiness_delta": float(getattr(state, "cumulative_happiness_delta", 0) or 0)
        if state
        else 0.0,
        "political_work": float(work_efficiency_multiplier(state)) if state else 1.0,
    }


def record_happiness_delta(game: Game, points: float) -> None:
    state = getattr(game, "political", None)
    if state is None:
        return
    state.cumulative_happiness_delta = float(state.cumulative_happiness_delta) + float(points)


def strongest_skill(villager: Villager) -> SkillType:
    best = SkillType.LABOUR
    best_level = -1
    for skill in SKILL_ORDER:
        skill_state = villager.skills.get(skill)
        level = int(skill_state.level) if skill_state is not None else 1
        if level > best_level:
            best_level = level
            best = skill
    return best


def job_matches_strongest(villager: Villager, buildings: dict) -> bool:
    if villager.building_id is None:
        return False
    building = buildings.get(villager.building_id)
    if building is None:
        return False
    job_skill, _ = JOB_SKILL_REQUIREMENTS.get(building.kind.name, (SkillType.LABOUR, 1))
    return job_skill == strongest_skill(villager)


def apply_immediate_effects(
    game: Game,
    effects: tuple[ImmediateEffect, ...],
    *,
    source_label: str = "",
) -> None:
    state: SettlementPoliticalState = game.political
    for effect in effects:
        kind = effect.kind
        amount = float(effect.amount)
        event_label = source_label.strip() or effect.label or "Decision"
        if kind == "happiness_all":
            for villager in game.villagers:
                apply_timed_happiness_impact(
                    villager,
                    amount,
                    icon="stew",
                    label=event_label,
                    day=int(game.calendar_day),
                    ticks_per_day=int(game.ticks_per_day),
                )
            record_happiness_delta(game, amount * max(1, len(game.villagers)))
        elif kind == "happiness_workers":
            n = 0
            for villager in game.villagers:
                if villager.building_id is not None:
                    apply_timed_happiness_impact(
                        villager,
                        amount,
                        icon="coins",
                        label=event_label,
                        day=int(game.calendar_day),
                        ticks_per_day=int(game.ticks_per_day),
                    )
                    n += 1
            record_happiness_delta(game, amount * n)
        elif kind == "happiness_skilled":
            n = 0
            for villager in game.villagers:
                if int(getattr(villager.skills.get(strongest_skill(villager)), "level", 1) or 1) >= 4:
                    apply_timed_happiness_impact(
                        villager,
                        amount,
                        icon="stew",
                        label=event_label,
                        day=int(game.calendar_day),
                        ticks_per_day=int(game.ticks_per_day),
                    )
                    n += 1
            record_happiness_delta(game, amount * n)
        elif kind == "gold":
            game.regional_wealth = max(0, int(game.regional_wealth) + int(amount))
        elif kind == "work_efficiency_season":
            if amount >= float(state.seasonal_work_bonus):
                state.seasonal_work_bonus = amount
                state.seasonal_work_source = (
                    source_label.strip()
                    or state.seasonal_work_source
                    or "Work organisation"
                )
        elif kind == "set_ration_all":
            mode = RationMode.NORMAL
            state.settlement_ration_mode = mode.name
            for villager in game.villagers:
                villager.ration_mode = mode
        elif kind == "set_ration_workers_double":
            for villager in game.villagers:
                if villager.building_id is not None:
                    villager.ration_mode = RationMode.DOUBLE
                else:
                    villager.ration_mode = RationMode.HALF
            state.settlement_ration_mode = "MIXED"
        elif kind == "set_policy_open":
            state.recruitment_policy = RecruitmentPolicy.OPEN_ADMISSION
        elif kind == "set_policy_contract":
            state.recruitment_policy = RecruitmentPolicy.CONTRACT
        elif kind == "ecology_boost":
            _nudge_disturbance(game, -abs(amount or 0.05))
        elif kind == "ecology_harm":
            _nudge_disturbance(game, abs(amount or 0.08))


def _nudge_disturbance(game: Game, delta: float) -> None:
    hx, hy = game.world.home_pos
    for y in range(max(0, hy - 8), min(game.world.rows, hy + 9)):
        for x in range(max(0, hx - 8), min(game.world.cols, hx + 9)):
            cell = game.world.cells[y][x]
            cell.disturbance = max(0.0, min(1.0, float(cell.disturbance) + delta))


def apply_covenant_ecology_recovery(game: Game) -> None:
    state = getattr(game, "political", None)
    mult = ecology_recovery_multiplier(state)
    if mult <= 1.0:
        return
    # Base seasonal recovery near the settlement, scaled by Covenant bonus.
    amount = 0.025 * mult
    hx, hy = game.world.home_pos
    for y in range(max(0, hy - 10), min(game.world.rows, hy + 11)):
        for x in range(max(0, hx - 10), min(game.world.cols, hx + 11)):
            cell = game.world.cells[y][x]
            if cell.disturbance > 0:
                cell.disturbance = max(0.0, float(cell.disturbance) - amount)


def apply_settlement_office_seasonal(game: Game) -> None:
    state = getattr(game, "political", None)
    if state is None or not state.has_institution("settlement_office"):
        return
    hit = 0
    for villager in game.villagers:
        if villager.building_id is None:
            continue
        if job_matches_strongest(villager, game.buildings):
            continue
        apply_timed_happiness_impact(
            villager,
            -5,
            icon="construction_site",
            label="Assigned outside strongest skill",
            day=int(game.calendar_day),
            duration_hours=12.0,
            ticks_per_day=int(game.ticks_per_day),
        )
        hit += 1
    if hit:
        record_happiness_delta(game, -5 * hit)


def sync_common_provision_rations(game: Game) -> None:
    state = getattr(game, "political", None)
    if state is None or not state.has_institution("common_provision"):
        return
    # MIXED is a directed-ration staging value, not a real RationMode.
    raw = str(state.settlement_ration_mode or "NORMAL")
    if raw == "MIXED":
        raw = "NORMAL"
        state.settlement_ration_mode = raw
    try:
        mode = RationMode[raw]
    except Exception:
        mode = RationMode.NORMAL
        state.settlement_ration_mode = mode.name
    for villager in game.villagers:
        villager.ration_mode = mode


def maybe_spawn_open_applicant(game: Game) -> None:
    state = getattr(game, "political", None)
    if state is None or not state.test_active:
        return
    if state.recruitment_policy != RecruitmentPolicy.OPEN_ADMISSION:
        return
    if state.open_applicant is not None:
        return
    if free_housing_beds(game.buildings, game.villagers) <= 0:
        return
    rng = random.Random(int(game.calendar_day) ^ game.world.seed ^ 0x0A11)
    # Prefer drawing from hire pool when present.
    if game.hire_candidates:
        cand = rng.choice(list(game.hire_candidates))
        skills = {
            skill.name.lower(): int(getattr(cand.skills.get(skill), "level", 1) or 1)
            for skill in SKILL_ORDER
            if cand.skills.get(skill) is not None
        }
        state.open_applicant = OpenApplicant(
            name=cand.name,
            skills=skills or {"labour": 2},
            housing_need=int(cand.housing_need),
            required_foods=list(cand.required_foods or ["bread"]),
            favourite_foods=list(cand.favourite_foods or []),
            template_id=str(getattr(cand, "template_id", "") or ""),
            portrait_seed=int(getattr(cand, "portrait_seed", 0) or 0),
            happiness=float(cand.happiness),
            energy=float(cand.energy),
            satiation=float(cand.satiation),
        )
        game._set_status(f"Open admission: {cand.name} seeks a place to settle.")
        return
    skills = {"labour": rng.randint(2, 4), "farming": rng.randint(1, 4)}
    state.open_applicant = OpenApplicant(
        name=rng.choice(("Tavi", "Rook", "Esha", "Cal", "Miri", "Wren")),
        skills=skills,
        housing_need=1,
        required_foods=["bread"],
        portrait_seed=rng.randint(1, 99999),
    )
    game._set_status(f"Open admission: {state.open_applicant.name} seeks a place to settle.")


def accept_open_applicant(game: Game) -> None:
    state: SettlementPoliticalState = game.political
    app = state.open_applicant
    if app is None:
        return
    from entities import DEFAULT_PRIORITIES_UNASSIGNED

    if free_housing_beds(game.buildings, game.villagers) <= 0:
        game._set_status("No free bed for the applicant.")
        return
    skills = skills_from_dict(
        {k: {"level": v, "potential": max(5, v), "peak": v} for k, v in app.skills.items()}
    )
    wx, wy = game.world.workstation_pos
    villager = Villager(
        id=game.next_villager_id,
        x=wx,
        y=wy,
        name=app.name,
        skills=skills,
        housing_need=app.housing_need,
        required_foods=list(app.required_foods),
        favourite_foods=list(app.favourite_foods),
        happiness=app.happiness,
        energy=app.energy,
        satiation=app.satiation,
        template_id=app.template_id,
        portrait_seed=app.portrait_seed,
        ration_mode=RationMode.NORMAL,
    )
    villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
    game.next_villager_id += 1
    game.villagers.append(villager)
    game._assign_housing(villager)
    # Remove matching hire candidate if present.
    game.hire_candidates = [c for c in game.hire_candidates if c.name != app.name]
    state.open_applicant = None
    state.villagers_accepted += 1
    state.add_diary(int(game.calendar_day), "note", f"Accepted open applicant {villager.name}.")
    game._set_status(f"Accepted {villager.name} under open admission.")


def refuse_open_applicant(game: Game) -> None:
    state: SettlementPoliticalState = game.political
    app = state.open_applicant
    if app is None:
        return
    name = app.name
    state.open_applicant = None
    state.villagers_refused += 1
    state.solidarity = max(0, state.solidarity - 5)
    for villager in game.villagers:
        apply_timed_happiness_impact(
            villager,
            -2,
            icon="stew",
            label="Refused open applicant",
            day=int(game.calendar_day),
            ticks_per_day=int(game.ticks_per_day),
        )
    state.add_diary(
        int(game.calendar_day),
        "note",
        f"Refused open applicant {name}.",
        "Solidarity −5; small happiness penalty.",
    )
    game._set_status(f"Refused {name}. Solidarity fell; villagers are uneasy.")


def resolve_decision_choice(game: Game, event_id: str, option_id: str) -> None:
    state: SettlementPoliticalState = game.political
    event = event_by_id(event_id)
    if event is None:
        return
    option = next((o for o in event.options if o.id == option_id), None)
    if option is None:
        return
    principle = principle_by_id(option.principle_id)
    source_label = principle.name if principle is not None else option.label
    apply_immediate_effects(
        game, option.immediate_effects, source_label=source_label
    )
    reveal = resolve_option(state, event, option, day=int(game.calendar_day))
    sample_metrics(game)
    if principle is not None:
        game._set_status(
            f"Chose “{option.label}”. Enacted {principle.name}."
        )
    if reveal is not None:
        game.institution_reveal.show(reveal.institution_id, reveal.summary_lines)
        # Common Provision: lock rations immediately.
        if reveal.institution_id == "common_provision":
            state.settlement_ration_mode = "NORMAL"
            sync_common_provision_rations(game)
    if state.decisions_resolved >= len(EVENT_ORDER) and not state.summary_shown:
        show_end_of_test_summary(game)


def show_end_of_test_summary(game: Game) -> None:
    state: SettlementPoliticalState = game.political
    sample_metrics(game)
    snap = live_effect_snapshot(game)
    if state.starting_population <= 0:
        state.starting_population = max(len(game.villagers), 0)
    description = generate_settlement_description(state)
    principles = [
        PRINCIPLE_NAME(pid) for pid in state.enacted_principle_ids
    ]
    institutions = [
        INSTITUTION_NAME(iid) for iid in state.institution_ids
    ]
    pop_now = len(game.villagers)
    happiness = snap["happiness"] if snap["happiness"] else average(state.happiness_samples)
    efficiency = snap["efficiency"] if snap["efficiency"] else average(state.efficiency_samples)
    ecology = snap["ecology"] if snap["ecology"] else average(state.ecology_samples)
    happy_delta = int(round(snap["happiness_delta"]))
    delta_note = f" (decisions/institutions Δ {happy_delta:+d} pts)" if happy_delta else ""
    work_note = ""
    if state.institution_ids or state.seasonal_work_bonus:
        work_note = f" (political work ×{snap['political_work']:.2f}"
        if state.seasonal_work_bonus:
            work_note += f", seasonal +{state.seasonal_work_bonus:.0%}"
        work_note += ")"
    lines = [
        f"Authority {state.authority} · Solidarity {state.solidarity} · Stewardship {state.stewardship}",
        f"Principles: {', '.join(principles) if principles else 'none'}",
        f"Institutions: {', '.join(institutions) if institutions else 'none'}",
        f"Population {state.starting_population} → {pop_now} "
        f"(accepted {state.villagers_accepted}, refused {state.villagers_refused})",
        f"Gold spent on recruitment: {state.gold_spent_recruitment}",
        f"Average happiness: {happiness:.0%}{delta_note}",
        f"Average work efficiency: {efficiency:.0%}{work_note}",
        f"Ecological condition: {ecology:.0%}",
        f"Recruitment policy: {state.recruitment_policy.value.replace('_', ' ')}",
        f"Seasons elapsed: {state.seasons_elapsed}",
        "Active effects shown on each villager's Buffs diary page.",
    ]
    game.end_of_test_summary.show(lines, description)
    state.summary_shown = True


def PRINCIPLE_NAME(pid: str) -> str:
    p = principle_by_id(pid)
    return p.name if p else pid


def INSTITUTION_NAME(iid: str) -> str:
    from sociopolitical import institution_by_id

    inst = institution_by_id(iid)
    return inst.name if inst else iid


def sample_metrics(game: Game) -> None:
    state = getattr(game, "political", None)
    if state is None:
        return
    snap = live_effect_snapshot(game)
    if game.villagers:
        state.happiness_samples.append(snap["happiness"])
        state.efficiency_samples.append(snap["efficiency"])
    state.ecology_samples.append(snap["ecology"])


def on_season_changed(game: Game) -> None:
    state = getattr(game, "political", None)
    if state is None or not state.test_active:
        return
    state.seasons_elapsed += 1
    state.seasonal_work_bonus = 0.0
    state.seasonal_work_source = ""
    sample_metrics(game)
    apply_settlement_office_seasonal(game)
    apply_covenant_ecology_recovery(game)
    sync_common_provision_rations(game)
    maybe_spawn_open_applicant(game)
    if (
        state.seasons_elapsed >= TEST_SEASON_LIMIT or state.decisions_resolved >= len(EVENT_ORDER)
    ) and not state.summary_shown:
        show_end_of_test_summary(game)


def trigger_next_decision(game: Game) -> None:
    state: SettlementPoliticalState = game.political
    if game.decision_modal.open or game.institution_reveal.open:
        return
    event_id = next_manual_event_id(state)
    if event_id is None:
        game._set_status("All test decisions have been resolved.")
        if not state.summary_shown:
            show_end_of_test_summary(game)
        return
    open_decision(game, event_id)


def open_decision(game: Game, event_id: str) -> None:
    if event_by_id(event_id) is None:
        return
    game.political.active_event_id = event_id
    game.decision_modal.show(event_id)
    game.sim_speed = 0


def create_empty_housing(game: Game) -> None:
    hx, hy = game.world.home_pos
    pos = _find_plot(game, BuildingKind.HOUSE_SMALL, (hx + 4, hy - 4))
    if pos is None:
        game._set_status("Could not find space for empty housing.")
        return
    building = _place_building(game, BuildingKind.HOUSE_SMALL, pos[0], pos[1])
    game._sync_building_collision()
    game._set_status(
        f"Created empty {building.kind.name.replace('_', ' ').title()} "
        f"with free beds."
    )


def add_test_food(game: Game) -> None:
    game.home_storage.deposit_dict({"bread": 20, "meat": 15, "berries": 20, "stew": 8})
    game._set_status("Added food reserves to the storehouse.")


def add_test_gold(game: Game, amount: int = 20) -> None:
    game.regional_wealth = int(game.regional_wealth) + amount
    game._set_status(f"Added {amount} gold (regional wealth now {game.regional_wealth}).")


def advance_one_season(game: Game) -> None:
    """Jump the calendar to the next season without simulating villager ticks.

    Developer control only: runs the normal season-boundary hooks (fees,
    wildlife, sociopolitical season logic) once, instead of
    ``simulate_fast_days(28)`` which can hang for minutes.
    """
    from seasons import DAYS_PER_SEASON, YEAR_DAYS

    current = float(game.calendar_day) % YEAR_DAYS
    season_i = int(current) // DAYS_PER_SEASON
    boundary = float((season_i + 1) * DAYS_PER_SEASON)
    step = max(1e-6, float(game._calendar_step_per_day()))
    # Sit just before the season boundary so one day advance crosses it.
    game.calendar_day = (boundary - step) % YEAR_DAYS
    game.day_tick = game.ticks_per_day
    game._advance_day()
    game._set_status(f"Skipped to {game._calendar_label()}.")
