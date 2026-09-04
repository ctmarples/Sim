"""Persistent, data-friendly scenario runtime and the first player tutorial."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import random
import tempfile

TUTORIAL_KEY = "tutorial_slice"


@dataclass
class ScenarioState:
    key: str | None = None
    step: str = "inactive"
    completed: bool = False
    starting_berries: int = 0
    bush_x: int | None = None
    bush_y: int | None = None
    bush_berries_collected: int = 0
    traveller_id: int | None = None
    rhea_id: int | None = None
    deer_id: int | None = None
    wildlife_seeded: bool = False
    deer_move_wait: int = 0
    deer_move_serial: int = 0
    deer_migrate_x: int | None = None
    deer_migrate_y: int | None = None
    deer_migrate_patch: int | None = None
    broken_tent_site_id: int | None = None
    broken_tent_x: int | None = None
    broken_tent_y: int | None = None
    repaired_tent_id: int | None = None
    loose_wood_seeded: bool = False
    rhea_villager_id: int | None = None
    berry_villager_id: int | None = None
    intro_clock_released: bool = False
    gwen_asked: bool = False
    joss_asked: bool = False
    announced_unlocks: list[str] = field(default_factory=list)
    field_planner_unlocked: bool = False


class ScenarioDirector:
    """Advance narrative steps from observable game state."""

    def __init__(self) -> None:
        self.state = ScenarioState()
        self.prompt: str | None = None
        self._dialog_request: tuple[str, tuple[str, ...]] | None = None
        self.layout: dict = {}
        self.building_groups: dict[int, str] = {}
        self.person_groups: dict[str, str] = {}

    @property
    def active(self) -> bool:
        return bool(self.state.key and not self.state.completed)

    def configure_after_load(self, game, save_stem: str, *, restored: bool) -> None:
        self._load_layout()
        if restored:
            self._restore_presentation()
        elif save_stem == TUTORIAL_KEY:
            self.start_tutorial(game)
        else:
            self.state = ScenarioState()
            self.prompt = None
            self._dialog_request = None
        if self.state.key == TUTORIAL_KEY:
            self._prune_tutorial_travellers(game)
            if self.state.step in {
                "find_village", "deer_dialog", "follow_deer", "deer_flee", "find_tent",
                "rhea_approaches", "shelter_greeting", "shelter_request", "shelter_offer",
                "join_rhea", "fix_tent", "rhea_congrats_approaches", "tent_repaired_dialog",
                "go_to_sleep", "sleeping", "complete",
            }:
                self._join_berry_traveller(game)
        if save_stem == TUTORIAL_KEY:
            if self.state.wildlife_seeded or self.state.completed:
                self._seed_forest_animals(game)
            else:
                self._ensure_scenario_deer(game)

    def start_tutorial(self, game) -> None:
        from indicators import OverlayMode
        from settings import MAP_DISCOVERY_RADIUS
        from world import FeatureType

        self.state = ScenarioState(key=TUTORIAL_KEY, step="hunger_dialog", starting_berries=1)
        self.prompt = None
        self._dialog_request = None
        scenario_dialog = getattr(game, "scenario_dialog", None)
        if scenario_dialog is not None:
            scenario_dialog.close()
            scenario_dialog.dismissed = False
            scenario_dialog.choice = None
        # tutorial_slice.json is an authored world template.  Never inherit the
        # player's location, inventory, needs, overlays, or paused clock from a
        # playtest/editor save of that file.
        self._load_layout()
        self._apply_layout_buildings(game)
        start = self.layout.get("player_start", [game.world.cols-6, game.world.rows-3])
        px = max(0, min(game.world.cols-1, int(start[0])))
        py = max(0, min(game.world.rows-1, int(start[1])))
        game.world.start_pos = (px, py)
        game.player.reset(px, py)
        game.player.inventory.berries = 1
        game.player.energy = .5
        game.player.satiation = .5
        game.control_mode = "dog"
        game.sim_speed = 1
        game.calendar_day = 0
        game.day_tick = game.ticks_per_day // 2
        game.fast_forward = False
        game.overlay_mode = OverlayMode.NONE
        game.habitat_view_mode = False
        game.height_edit_mode = False
        if hasattr(game, "_clear_selection"):
            game._clear_selection()
        self._prepare_tutorial_people(game)
        self._prepare_broken_tent(game)
        self._seed_tutorial_wood(game)
        for name in (
            "management", "field_plan_dialog", "building_inspect",
            "villager_inspect", "resource_inspect", "resource_tracker",
            "balance_dialog", "habitat_inspect", "player_inventory",
            "assign_picker", "sound_settings", "villager_roster",
        ):
            window = getattr(game, name, None)
            if window is not None and hasattr(window, "close"):
                window.close()
        radius = max(0, int(MAP_DISCOVERY_RADIUS))
        for y in range(max(0, py-radius), min(game.world.rows, py+radius+1)):
            for x in range(max(0, px-radius), min(game.world.cols, px+radius+1)):
                if (x-px)**2 + (y-py)**2 > radius*radius:
                    continue
                cell = game.world.get_cell(x, y)
                if cell is not None and cell.feature == FeatureType.BERRY_BUSH:
                    cell.feature = FeatureType.NONE
                    cell.crop_kind = None
                    cell.deposit = cell.growth_ticks = 0
        game.discovered_cells = set()
        game._reveal_around_player()
        player_camera_x, player_camera_y = game._player_camera_point()
        game.camera.center_on(
            player_camera_x, player_camera_y, game.world.cols, game.world.rows
        )
        if hasattr(game, "_refresh_indicators"):
            game._refresh_indicators()
        if hasattr(game, "_invalidate_forage_index"):
            game._invalidate_forage_index()
        self.prompt = None
        self._request_dialog("(Stomach rumble) ... uhhh I'm getting hungry, I need to eat. I'll check what is in my bag")

    def _request_dialog(self, text: str, choices: tuple[str, ...] = ()) -> None:
        self._dialog_request = (text, choices)

    def take_dialog_request(self) -> tuple[str, tuple[str, ...]] | None:
        request, self._dialog_request = self._dialog_request, None
        return request

    def dismiss_dialog(self, choice: int | None = None) -> None:
        step = self.state.step
        if step == "hunger_dialog":
            self.state.step, self.prompt = "open_inventory", "Press I to open inventory"
        elif step == "last_berry_dialog":
            self.state.step, self.prompt = "find_food", "Look around for some more food"
        elif step == "found_berries_dialog":
            self.state.step = "pick_berries"
            self.prompt = "Press Enter by any berry bush to pick a berry"
        elif step == "traveller_accuses":
            self.state.step = "traveller_reply"
            self._request_dialog("Well you can't stay here. Try up at the village to the north west if you need a place to stay.")
        elif step == "traveller_reply":
            self.state.step, self.prompt = "join_berry_traveller", None
        elif step == "deer_dialog":
            self.state.step, self.prompt = "follow_deer", "Follow the deer to the village"
        elif step == "shelter_greeting":
            self.state.step = "shelter_request"
            self._request_dialog("I'm looking for a place to stay for the night")
        elif step == "shelter_request":
            self.state.step = "shelter_offer"
            self._request_dialog(
                "This tent is already occupied, but there's an old collapsed tent back there. "
                "It needs a new support. If you can fix it, it's yours. You should be able to "
                "find some wood in the forest to the North."
            )
        elif step == "shelter_offer":
            self.state.step, self.prompt = "join_rhea", None
        elif step == "tent_repaired_dialog":
            self.state.step, self.prompt = "go_to_sleep", "Get some sleep — press Enter on the tent"
        elif step == "morning_greeting":
            self.state.step = "morning_thanks"
            self._request_dialog("Thanks for the place to stay.")
        elif step == "morning_thanks":
            self.state.step = "morning_invitation"
            self._request_dialog("No problem! We are a small community here, maybe you can help us out with some tasks and you can stay a while longer?")
        elif step == "morning_invitation":
            self.state.step = "morning_accept"
            self._request_dialog("Sure! How can I help?")
        elif step == "morning_accept":
            self.state.step = "farm_history"
            self._request_dialog("Well... we need help with our farm. This used to be a prosperous village with abundant food. But for the past years our harvest is poor and the landscape is barren of wildlife.")
        elif step == "farm_history":
            self.state.step = "weed_request"
            self._request_dialog("But I don't want to bore you with our tale of woe. Weeds! That's how you can help! Our fields are overrun with weeds and we need help clear them. Dogs know, the harvest is poor enough without the weeds taking over our soils. I'll show you.")
        elif step == "weed_request":
            self.state.step, self.prompt = "walk_to_field", "Follow Rhea to the field"
        elif step == "field_reaction":
            self.state.step = "hoe_gift"
            self._request_dialog("Here, take this.")
        elif step == "hoe_gift":
            self.state.step, self.prompt = "give_hoe", None
        elif step == "weeds_complete_dialog":
            self.state.step = "farm_question"
            self._request_dialog("You said this field used to be more abundant... what happened?")
        elif step == "farm_question":
            self.state.step = "rhea_abundance"
            self._request_dialog("Yes, we used to have enough to feed four of us here and surplus to sell to travellers who pass through. But now... well, I don't know exactly. The land just looks lifeless. No insects. No birds. Just these damn dandelions and daisies!")
        elif step == "rhea_abundance":
            self.state.step = "ask_villagers_intro"
            self._request_dialog("Try asking the other villagers if they remember anything about the old farm.")
        elif step == "ask_villagers_intro":
            self.state.step, self.prompt = "ask_villagers", "Ask villagers about the farm"
        elif step == "gwen_intro":
            self.state.step = "gwen_player"
            self._request_dialog("Thanks! I wanted to ask you about the farm.")
        elif step == "gwen_player":
            self.state.step = "gwen_history"
            self._request_dialog("Haha, that old field is hardly a farm these days... lifeless! Even the shrubs and trees were cleared by the old forester to gather wood to build the village.")
        elif step == "gwen_history":
            self.state.gwen_asked = True
            self.state.step, self.prompt = "finish_interview", None
        elif step == "joss_intro":
            self.state.step = "joss_help"
            self._request_dialog("Uh, can I help?")
        elif step == "joss_help":
            self.state.step = "joss_doubt"
            self._request_dialog("You? You look about as useless as me. What do you know?")
        elif step == "joss_doubt":
            self.state.step = "joss_learn"
            self._request_dialog("Well... I learn fast!")
        elif step == "joss_learn":
            self.state.step = "joss_books"
            self._request_dialog("Fine. Go over to the Farmhouse. There are some old books in there... maybe you can make more sense of them than I can.")
        elif step == "joss_books":
            self.state.joss_asked = True
            self.state.step, self.prompt = "finish_interview", None

    def note_berry_collected(self, game, x: int, y: int, amount: int) -> None:
        if not self.active or self.state.step != "pick_berries" or int(amount) <= 0:
            return
        # Any bush counts. Discovery order can select a different bush in the
        # same clearing from the one the player actually harvests.
        self.state.bush_x, self.state.bush_y = int(x), int(y)
        self.state.bush_berries_collected += max(0, int(amount))
        self.state.step, self.prompt = "traveller_approaches", "Someone is coming..."
        traveller = self._tutorial_traveller(game)
        if traveller is not None:
            traveller.world_x = float(getattr(traveller, "world_x", traveller.x))
            traveller.world_y = float(getattr(traveller, "world_y", traveller.y))

    def update(self, game) -> None:
        if not self.active:
            return
        self._sync_management_unlocks(game)
        step = self.state.step
        if step == "found_berries_dialog" and self.state.bush_x is not None:
            self._pan_camera_toward(game, self.state.bush_x+.5, self.state.bush_y+.5)
        if step == "open_inventory" and game.player_inventory.open:
            self.state.step, self.prompt = "eat_berries", "Right click on the berries to eat."
        elif step == "eat_berries" and int(game.player.inventory.berries) <= 0:
            self.state.step, self.prompt = "last_berry_dialog", None
            self._request_dialog("Well that was the last of the berries. I should look for some more")
        elif step == "find_food":
            bush = self._discovered_fruiting_bush(game)
            if bush is not None:
                self.state.bush_x, self.state.bush_y = bush
                self._reveal_clearing(game, bush, 2)
                self.state.step, self.prompt = "found_berries_dialog", None
                self._request_dialog("There's some more! So that's where they come from!")
        elif step == "traveller_approaches":
            traveller = self._tutorial_traveller(game)
            if traveller is None or self._walk_toward_player(traveller, game.player):
                self.state.step, self.prompt = "traveller_accuses", None
                self._request_dialog("Hey! You're eating all my berries!", (
                    "I'm sorry, I didn't know they belonged to anyone",
                    "Get lost! I'm hungry",
                ))
        elif step == "find_village":
            deer = self._tutorial_deer(game)
            if deer is not None and (deer.x, deer.y) in game.discovered_cells:
                game.camera.center_on(deer.x+.5, deer.y+.5, game.world.cols, game.world.rows)
                self.state.step, self.prompt = "deer_dialog", None
                self._request_dialog("Oh it's an animal! Maybe he lives near the village. I'll follow him")
        elif step == "join_berry_traveller":
            self._join_berry_traveller(game)
            self.state.step, self.prompt = "find_village", "Find the village to the north west"
        elif step == "follow_deer":
            if self._farmhouse_revealed(game):
                self.state.step, self.prompt = "deer_flee", "Find a tent"
                self.state.deer_move_wait = 0
                self._request_dialog(
                    "Hey! Where are you going. Oh look it's a farm. Maybe I can find some shelter"
                )
            else:
                self._guide_deer(game)
        elif step == "deer_flee":
            if self._flee_deer_to_habitat(game):
                self._seed_forest_animals(game)
                self.state.wildlife_seeded = True
                self.state.step, self.prompt = "find_tent", "Find a tent"
        elif step == "find_tent" and self._village_tent_revealed(game):
            self.state.step, self.prompt = "rhea_approaches", "Rhea is coming to speak with you..."
        elif step == "rhea_approaches":
            traveller = self._tutorial_rhea(game)
            if traveller is None or self._walk_toward_player(traveller, game.player):
                self.state.step, self.prompt = "shelter_greeting", None
                self._request_dialog("Hi there, can I help you?")
        elif step == "fix_tent":
            repaired = self._repaired_tent(game)
            if repaired is not None:
                self.state.repaired_tent_id = repaired.id
                self._take_control_of_villager(game, self._rhea_villager(game))
                self.state.step, self.prompt = "rhea_congrats_approaches", "Rhea is coming to speak with you..."
        elif step == "rhea_congrats_approaches":
            rhea = next((v for v in game.villagers if v.id == self.state.rhea_villager_id), None)
            if rhea is None or self._walk_toward_player(rhea, game.player):
                self.state.step, self.prompt = "tent_repaired_dialog", None
                self._request_dialog("Great! You fixed it. Get some rest and we can talk in the morning.")
        elif step == "join_rhea":
            self._join_rhea_to_village(game)
            self.state.step, self.prompt = "fix_tent", "Fix the tent"
        elif step == "go_to_sleep":
            self._release_villager_control(self._rhea_villager(game))
            if getattr(game, "_player_inside_building_id", None) == self.state.repaired_tent_id:
                game.begin_tutorial_sleep()
                self.state.step, self.prompt = "sleeping", None
        elif step == "sleeping" and game.tutorial_sleep_complete():
            game.player.energy = 1.0
            game.calendar_day = 0
            game.day_tick = round(game.ticks_per_day * (1.0 - 8.0 / 24.0))
            self.state.intro_clock_released = True
            game.finish_tutorial_village_sleep()
            self.state.step, self.prompt = "talk_to_rhea", "Talk to Rhea — approach her and press Enter"
        elif step == "walk_to_field":
            rhea = self._rhea_villager(game)
            field = self._village_field(game)
            if rhea is not None and field is not None:
                target = (field.x, field.y)
                rhea_done = self._walk_toward_point(rhea, *target)
                player_done = self._walk_toward_point(game.player, field.x + 1, field.y)
                if rhea_done and player_done:
                    self.state.step, self.prompt = "field_reaction", None
                    self._seed_field_weeds(game, field)
                    self._request_dialog("Oh wow. Yes, this needs some work. I'll be glad to help.")
        elif step == "give_hoe":
            game.player.inventory.add_item("hoe", 1)
            self._release_villager_control(self._rhea_villager(game))
            self.state.step, self.prompt = "equip_hoe", "Equip the Hoe in Inventory"
        elif step == "equip_hoe" and game.player.inventory.has_equipped_tool("hoe"):
            self.state.step, self.prompt = "clear_weeds", "Clear the field of weeds"
        elif step == "clear_weeds" and self._field_weeds_cleared(game):
            self._take_control_of_villager(game, self._rhea_villager(game))
            self.state.step, self.prompt = "rhea_weeds_approaches", "Rhea is coming to speak with you..."
        elif step == "rhea_weeds_approaches":
            rhea = self._rhea_villager(game)
            if rhea is None or self._walk_toward_player(rhea, game.player):
                self.state.step, self.prompt = "weeds_complete_dialog", None
                self._request_dialog("Wow, you made light work of that. We'll have to find something else for you to do to keep you around!")

        elif step == "release_rhea":
            self._release_villager_control(self._rhea_villager(game))
            self.state.step, self.state.completed, self.prompt = "complete", True, None
        elif step == "finish_interview":
            for villager in game.villagers:
                self._release_villager_control(villager)
            if self.state.gwen_asked and self.state.joss_asked:
                self.state.step, self.prompt = "enter_farmhouse", "Enter the Farmhouse and find the old book"
            else:
                self.state.step, self.prompt = "ask_villagers", "Ask villagers about the farm"
        elif step == "enter_farmhouse":
            farm = next((b for b in game.buildings.values() if b.kind.name == "FARM"), None)
            if farm is not None and getattr(game, "_player_inside_building_id", None) == farm.id:
                game.player.inventory.add_item("book", 1)
                self.state.step, self.prompt = "open_book", "Open the old book — right-click it in your inventory"

    def _tutorial_traveller(self, game):
        candidates = list(getattr(game, "hire_candidates", ()))
        if not candidates:
            return None
        found = next((c for c in candidates if c.id == self.state.traveller_id), None)
        if found is None:
            bx = self.state.bush_x if self.state.bush_x is not None else game.player.x
            by = self.state.bush_y if self.state.bush_y is not None else game.player.y
            found = min(candidates, key=lambda c: (c.x-bx)**2 + (c.y-by)**2)
            self.state.traveller_id = found.id
        return found

    def _prepare_tutorial_people(self, game) -> None:
        """Reduce a progressed template save to its three tutorial actors."""
        from entities import BuildingKind, VillagerState, snap_entity_visual

        forager = next(
            (b for b in game.buildings.values() if b.kind == BuildingKind.FORAGER),
            None,
        )
        farm = next(
            (b for b in game.buildings.values() if b.kind == BuildingKind.FARM),
            None,
        )
        workplaces = [b for b in (forager, farm) if b is not None]
        villagers = sorted(game.villagers, key=lambda villager: villager.id)[:len(workplaces)]
        game.villagers = villagers
        for villager, building in zip(villagers, workplaces):
            villager.name = "Gwen Hill" if building.kind == BuildingKind.FORAGER else "Joss Fern"
            villager.clear_assignment()
            villager.inventory.reset()
            villager.state = VillagerState.IDLE
            villager.move_cooldown = villager.work_cooldown = 0
            bx, by = building.center_cell()
            villager.x, villager.y = bx, by
            villager.world_x, villager.world_y = float(bx), float(by)
            snap_entity_visual(villager)
            game._set_primary_workplace(villager, building.id, slot=0)
            key = f"villager:{villager.id}"
            group = self.person_groups.setdefault(key, "village")
            villager.community_id = self._community_id_for_group(group)
            if 9 in game.buildings:
                villager.housed, villager.housing_id = True, 9
        game.next_villager_id = max([v.id for v in villagers] + [0]) + 1

        candidates = list(getattr(game, "hire_candidates", ()))
        rhea = next((candidate for candidate in candidates if candidate.name.startswith("Rhea")), None)
        traveller = next((candidate for candidate in candidates if candidate is not rhea), None)
        game.hire_candidates = [candidate for candidate in (traveller, rhea) if candidate is not None]
        if traveller is not None:
            position = self.layout.get("people", {}).get("berry_traveller", {})
            traveller.x, traveller.y = int(position.get("x", 62)), int(position.get("y", 63))
            traveller.world_x, traveller.world_y = 62.0, 63.0
            self.state.traveller_id = traveller.id
            key = f"traveller:{traveller.id}"
            traveller.community_id = self._community_id_for_group(
                self.person_groups.setdefault(key, "berry_camp")
            )
        if rhea is not None:
            field = next(
                (b for b in game.buildings.values() if b.kind == BuildingKind.FIELD),
                None,
            )
            # Rhea is authored at the field's top-left and stays there because
            # only the rhea_approaches step gives her a movement target.
            rx, ry = (field.x, field.y) if field is not None else (9, 23)
            rhea.name = "Rhea"
            rhea.x, rhea.y = rx, ry
            rhea.world_x, rhea.world_y = float(rx), float(ry)
            self.state.rhea_id = rhea.id
            key = f"traveller:{rhea.id}"
            rhea.community_id = self._community_id_for_group(
                self.person_groups.setdefault(key, "village")
            )
        positions = self.layout.get("people_positions", {})
        for kind, collection in (("villager", game.villagers), ("traveller", game.hire_candidates)):
            for person in collection:
                saved = positions.get(f"{kind}:{person.id}")
                if isinstance(saved, list) and len(saved) == 2:
                    person.x, person.y = int(saved[0]), int(saved[1])
                    person.world_x, person.world_y = float(person.x), float(person.y)

    def _load_layout(self) -> None:
        path = Path(__file__).resolve().with_name("tutorial_layout.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            data = {}
        self.layout = data if isinstance(data, dict) else {}
        buildings = self.layout.get("buildings", {})
        legacy_repaired = buildings.get("16") if isinstance(buildings, dict) else None
        if isinstance(legacy_repaired, dict) and legacy_repaired.get("group") == "personal":
            broken = buildings.get("15")
            if isinstance(broken, dict):
                broken["x"], broken["y"] = legacy_repaired.get("x", broken.get("x")), legacy_repaired.get("y", broken.get("y"))
            buildings.pop("16", None)
        self.building_groups = {
            int(building_id): str(spec.get("group", "other"))
            for building_id, spec in self.layout.get("buildings", {}).items()
            if isinstance(spec, dict)
        }
        self.person_groups = {
            str(key): str(value)
            for key, value in self.layout.get("people_assignments", {}).items()
        }

    def _apply_layout_buildings(self, game) -> None:
        """Apply editable authored positions before tutorial runtime setup."""
        from game import FEATURE_FOR_BUILDING
        from entities import BuildingKind, default_building_plot

        specs = self.layout.get("buildings", {})
        moved = []
        for raw_id, spec in specs.items():
            if not isinstance(spec, dict):
                continue
            building = game.buildings.get(int(raw_id))
            if building is None or "x" not in spec or "y" not in spec:
                continue
            target = (int(spec["x"]), int(spec["y"]))
            target_kind = BuildingKind[str(spec["kind"])] if spec.get("kind") else building.kind
            if (building.x, building.y) == target and building.kind == target_kind:
                continue
            old = (building.x, building.y, max(1, building.plot_w), max(1, building.plot_h))
            game.world.clear_structure_footprint(*old)
            building.x, building.y = target
            if building.kind != target_kind:
                building.kind = target_kind
                building.plot_w, building.plot_h = default_building_plot(target_kind)
            moved.append(building)
        for building in moved:
            game.world.claim_structure_footprint(
                building.x, building.y, max(1, building.plot_w), max(1, building.plot_h),
                FEATURE_FOR_BUILDING[building.kind],
            )
        if moved and hasattr(game, "_sync_building_collision"):
            game._sync_building_collision()

    def _join_rhea_to_village(self, game) -> None:
        """Convert scripted Rhea into an unassigned village worker."""
        if self.state.rhea_villager_id is not None:
            return
        candidate = self._tutorial_rhea(game)
        if candidate is None:
            return
        from entities import DEFAULT_PRIORITIES_UNASSIGNED, Villager

        villager = Villager(
            id=game.next_villager_id, x=candidate.x, y=candidate.y, name="Rhea",
            skills=dict(candidate.skills), housing_need=candidate.housing_need,
            required_foods=list(candidate.required_foods),
            favourite_foods=list(candidate.favourite_foods),
            favourite_is_junk=candidate.favourite_is_junk,
            required_workplace=str(candidate.required_workplace or ""),
            signing_fee=0, community_id=0, virtues=list(candidate.virtues),
            vices=list(candidate.vices), portrait_seed=candidate.portrait_seed,
            energy=candidate.energy, satiation=candidate.satiation,
            happiness=candidate.happiness, template_id=candidate.template_id,
            tier=candidate.tier,
        )
        villager.world_x = float(getattr(candidate, "world_x", candidate.x))
        villager.world_y = float(getattr(candidate, "world_y", candidate.y))
        villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
        game.next_villager_id += 1
        game.villagers.append(villager)
        game.hire_candidates = [item for item in game.hire_candidates if item.id != candidate.id]
        self.state.rhea_villager_id = villager.id
        self.person_groups.pop(f"traveller:{candidate.id}", None)
        self.person_groups[f"villager:{villager.id}"] = "village"
        if 9 in game.buildings:
            villager.housed, villager.housing_id = True, 9
        if hasattr(game, "_bump_work_gen"):
            game._bump_work_gen()

    def _join_berry_traveller(self, game) -> None:
        """Make the berry traveller a resident of only the lower-right camp."""
        if self.state.berry_villager_id is not None:
            return
        candidate = self._tutorial_traveller(game)
        if candidate is None or candidate.name.startswith("Rhea"):
            return
        from entities import DEFAULT_PRIORITIES_UNASSIGNED, Villager

        villager = Villager(
            id=game.next_villager_id, x=candidate.x, y=candidate.y,
            name=candidate.name, skills=dict(candidate.skills),
            housing_need=candidate.housing_need,
            required_foods=list(candidate.required_foods),
            favourite_foods=list(candidate.favourite_foods),
            favourite_is_junk=candidate.favourite_is_junk,
            required_workplace=str(candidate.required_workplace or ""),
            community_id=1001, virtues=list(candidate.virtues), vices=list(candidate.vices),
            portrait_seed=candidate.portrait_seed, energy=candidate.energy,
            satiation=candidate.satiation, happiness=candidate.happiness,
            template_id=candidate.template_id, tier=candidate.tier,
        )
        villager.world_x = float(getattr(candidate, "world_x", candidate.x))
        villager.world_y = float(getattr(candidate, "world_y", candidate.y))
        villager.priorities = list(DEFAULT_PRIORITIES_UNASSIGNED)
        villager.housed = 12 in game.buildings
        villager.housing_id = 12 if villager.housed else None
        game.next_villager_id += 1
        game.villagers.append(villager)
        game.hire_candidates = [item for item in game.hire_candidates if item.id != candidate.id]
        self.state.berry_villager_id = villager.id
        self.person_groups.pop(f"traveller:{candidate.id}", None)
        self.person_groups[f"villager:{villager.id}"] = "berry_camp"
        if hasattr(game, "_bump_work_gen"):
            game._bump_work_gen()

    def tutorial_management_villagers(self, game) -> list:
        if self.state.key != TUTORIAL_KEY:
            return list(game.villagers)
        visible = {self.state.rhea_villager_id}
        if self.state.gwen_asked:
            visible.update(v.id for v in game.villagers if v.name == "Gwen Hill")
        if self.state.joss_asked:
            visible.update(v.id for v in game.villagers if v.name == "Joss Fern")
        return [v for v in game.villagers if v.id in visible]

    def tutorial_management_buildings(self, game) -> dict:
        if self.state.key != TUTORIAL_KEY:
            return dict(game.buildings)
        allowed = {self.state.repaired_tent_id}
        if self.state.joss_asked:
            allowed.update(b.id for b in game.buildings.values() if b.kind.name == "FARM")
        if self.state.field_planner_unlocked:
            for building in game.buildings.values():
                if building.kind.name == "FIELD":
                    building._tutorial_planner_entry = True
                    allowed.add(building.id)
        return {bid: b for bid, b in game.buildings.items() if bid in allowed}

    def tutorial_management_flora(self) -> set[str]:
        """Return only plant catalogue entries introduced by the narrative."""
        if self.state.key != TUTORIAL_KEY:
            return set()
        wheat_steps = {
            "clear_weeds", "rhea_weeds_approaches", "weeds_complete_dialog",
            "farm_question", "rhea_abundance", "ask_villagers_intro", "ask_villagers",
            "gwen_intro", "gwen_player", "gwen_history", "joss_intro", "joss_help",
            "joss_doubt", "joss_learn", "joss_books", "finish_interview",
            "enter_farmhouse", "open_book", "complete",
        }
        keys = {"wild:wheat"} if self.state.step in wheat_steps else set()
        if self.state.step in wheat_steps - {
            "clear_weeds", "rhea_weeds_approaches", "weeds_complete_dialog", "farm_question"
        }:
            keys.update(("wild:dandelion", "wild:daisy"))
        return keys

    def _sync_management_unlocks(self, game) -> None:
        """Show one replaceable discovery card when tutorial catalogue entries unlock."""
        candidates: list[tuple[str, str, str, str]] = []
        if self.state.rhea_villager_id is not None:
            candidates.append(("rhea", "Rhea added to People", "villager", "people"))
        if self.state.repaired_tent_id is not None:
            candidates.append(("tent", "Personal tent added to Buildings", "tent", "buildings"))
        flora = self.tutorial_management_flora()
        if "wild:wheat" in flora:
            candidates.append(("wheat", "Wheat added to Flora", "crop_plant", "flora:wild:wheat"))
        if "wild:dandelion" in flora:
            candidates.append(("flowers", "Dandelion and Daisy added to Flora", "flower_plant", "flora:wild:dandelion"))
        if self.state.gwen_asked:
            candidates.append(("gwen", "Gwen Hill added to People", "villager", "people"))
        if self.state.joss_asked:
            candidates.extend((("joss", "Joss Fern added to People", "villager", "people"),
                               ("farm", "Farmhouse added to Buildings", "farm", "buildings")))
        announced = self.state.announced_unlocks
        for key, label, icon, target in candidates:
            if key not in announced:
                announced.append(key)
                game._tutorial_unlock_popup = (label, icon, target)

    def can_player_interact_building(self, building) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        if building.id == self.state.repaired_tent_id:
            return True
        if self.state.joss_asked and building.kind.name == "FARM":
            return True
        return self.state.field_planner_unlocked and building.kind.name == "FIELD"

    def can_player_interact_site(self, site) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        return site.id == self.state.broken_tent_site_id

    def site_available_to_villagers(self, site) -> bool:
        return not (
            self.state.key == TUTORIAL_KEY
            and site.id == self.state.broken_tent_site_id
        )

    def can_villager_use_building(self, villager, building) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        group = "berry_camp" if villager.community_id == 1001 else "village"
        return self.building_groups.get(building.id) == group

    def can_villager_use_village_storehouse(self, villager) -> bool:
        return self.state.key != TUTORIAL_KEY or villager.community_id in (None, 0)

    def villager_foraging_near_home(self, villager, position: tuple[int, int]) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        house = 12 if villager.community_id == 1001 else 9
        spec = self.layout.get("buildings", {}).get(str(house), {})
        centre = (int(spec.get("x", villager.x)), int(spec.get("y", villager.y)))
        return abs(position[0] - centre[0]) + abs(position[1] - centre[1]) <= 18

    def assign_settlement(self, game, kind: str, entity_id: int, group: str) -> bool:
        if group not in {"personal", "village", "fisher", "berry_camp"}:
            return False
        if kind == "building" and entity_id in game.buildings:
            self.building_groups[entity_id] = group
            return True
        collection = game.villagers if kind == "villager" else game.hire_candidates
        person = next((item for item in collection if item.id == entity_id), None)
        if person is None:
            return False
        self.person_groups[f"{kind}:{entity_id}"] = group
        person.community_id = self._community_id_for_group(group)
        return True

    @staticmethod
    def _community_id_for_group(group: str) -> int | None:
        return {"personal": None, "village": 0, "fisher": 1002, "berry_camp": 1001}.get(group)

    def save_layout(self, game) -> Path:
        """Atomically save live editor positions and settlement assignments."""
        path = Path(__file__).resolve().with_name("tutorial_layout.json")
        data = dict(self.layout)
        specs = {str(key): dict(value) for key, value in data.get("buildings", {}).items()}
        for building_id, building in game.buildings.items():
            if building_id == self.state.repaired_tent_id:
                spec = specs.setdefault("15", {"role": "broken_tent"})
                spec.update(x=building.x, y=building.y, group="personal")
                continue
            spec = specs.setdefault(str(building_id), {"role": f"building_{building_id}"})
            spec.update(kind=building.kind.name, x=building.x, y=building.y,
                        group=self.building_groups.get(building_id, "personal"))
        site = game.construction_sites.get(self.state.broken_tent_site_id or -1)
        if site is not None and site.source_building_id == 15:
            spec = specs.setdefault("15", {"role": "broken_tent"})
            spec.update(x=site.x, y=site.y, group=self.building_groups.get(15, "personal"))
        data["buildings"] = specs
        data["people_assignments"] = dict(sorted(self.person_groups.items()))
        data["people_positions"] = {
            **{f"villager:{person.id}": [person.x, person.y] for person in game.villagers},
            **{f"traveller:{person.id}": [person.x, person.y] for person in game.hire_candidates},
        }
        self.layout = data
        payload = json.dumps(data, indent=2) + "\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        return path

    def freezes_calendar(self) -> bool:
        return self.state.key == TUTORIAL_KEY and not self.state.intro_clock_released

    def forces_night(self) -> bool:
        return self.state.step in {
            "rhea_congrats_approaches", "tent_repaired_dialog", "go_to_sleep", "sleeping"
        }

    def _prune_tutorial_travellers(self, game) -> None:
        """Remove seasonal/camp arrivals that do not belong in the tutorial."""
        candidates = list(getattr(game, "hire_candidates", ()))
        rhea = next(
            (candidate for candidate in candidates if candidate.id == self.state.rhea_id),
            None,
        )
        if rhea is None:
            rhea = next((candidate for candidate in candidates if candidate.name.startswith("Rhea")), None)
        berry_traveller = next(
            (candidate for candidate in candidates if candidate.id == self.state.traveller_id and candidate is not rhea),
            None,
        )
        game.hire_candidates = [
            candidate for candidate in (berry_traveller, rhea) if candidate is not None
        ]
        if rhea is not None:
            self.state.rhea_id = rhea.id

    def _tutorial_rhea(self, game):
        candidates = list(getattr(game, "hire_candidates", ()))
        found = next((candidate for candidate in candidates if candidate.id == self.state.rhea_id), None)
        if found is None:
            found = next((candidate for candidate in candidates if candidate.name.startswith("Rhea")), None)
            if found is not None:
                self.state.rhea_id = found.id
        return found

    def _prepare_broken_tent(self, game) -> None:
        """Turn authored tent #15 into the tutorial's one-wood repair site."""
        from entities import BuildingKind, ConstructionSite
        from world import FeatureType

        building = game.buildings.get(15)
        if building is None:
            return
        self.state.broken_tent_x, self.state.broken_tent_y = building.x, building.y
        del game.buildings[building.id]
        site = ConstructionSite(
            id=game.next_construction_id,
            x=building.x,
            y=building.y,
            kind=BuildingKind.TENT,
            need_wood=1,
            plot_w=max(1, building.plot_w),
            plot_h=max(1, building.plot_h),
            source_building_id=15,
        )
        game.next_construction_id += 1
        game.construction_sites[site.id] = site
        self.state.broken_tent_site_id = site.id
        game.world.claim_structure_footprint(
            site.x, site.y, site.plot_w, site.plot_h, FeatureType.CONSTRUCTION_SITE
        )
        if hasattr(game, "_sync_building_collision"):
            game._sync_building_collision()

    def _seed_tutorial_wood(self, game) -> None:
        """Place deterministic loose wood beside trees north of the village."""
        if self.state.loose_wood_seeded:
            return
        from world import FeatureType

        placed = 0
        authored = self.layout.get("scenario_objects", {}).get("loose_wood", [])
        positions = authored if isinstance(authored, list) else []
        if not positions:
            limit_y = self.state.broken_tent_y if self.state.broken_tent_y is not None else 22
            positions = [(x, y) for y in range(max(0, limit_y - 14), max(0, limit_y)) for x in range(game.world.cols)]
        for position in positions:
            if not isinstance(position, (list, tuple)) or len(position) != 2:
                continue
            x, y = int(position[0]), int(position[1])
            cell = game.world.get_cell(x, y)
            if cell is None or cell.feature != FeatureType.NONE:
                continue
            if not authored and not any(
                (near := game.world.get_cell(x + dx, y + dy)) is not None
                and near.feature == FeatureType.TREE
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                continue
            cell.feature = FeatureType.WOOD_BUSH
            cell.deposit = 1
            cell.crop_kind = "wood_bush"
            cell.icon_variant = placed % 4
            placed += 1
            if placed >= 3:
                self.state.loose_wood_seeded = True
                if hasattr(game, "_invalidate_forage_index"):
                    game._invalidate_forage_index()
                return
        self.state.loose_wood_seeded = placed > 0

    def _repaired_tent(self, game):
        from entities import BuildingKind

        x, y = self.state.broken_tent_x, self.state.broken_tent_y
        if x is None or y is None:
            return None
        return next(
            (b for b in game.buildings.values() if b.kind == BuildingKind.TENT and b.x == x and b.y == y),
            None,
        )

    def _tutorial_deer(self, game):
        from wildlife import AnimalKind
        deer = [a for a in game.wildlife.animals if a.kind == AnimalKind.DEER]
        if not deer:
            return self._ensure_scenario_deer(game)
        found = next((a for a in deer if a.id == self.state.deer_id), None)
        if found is None:
            found = min(deer, key=lambda a: (a.x-36)**2 + (a.y-60)**2)
            self.state.deer_id = found.id
        return found

    def _ensure_scenario_deer(self, game):
        from wildlife import Animal, AnimalKind, AnimalSex
        position = self.layout.get("scenario_objects", {}).get("guide_deer", [36, 60])
        deer_x, deer_y = int(position[0]), int(position[1])
        found = next((a for a in game.wildlife.animals if a.id == self.state.deer_id), None)
        if found is None:
            found = next(
                (a for a in game.wildlife.animals
                 if a.kind == AnimalKind.DEER and (a.x, a.y) == (deer_x, deer_y)),
                None,
            )
        if found is not None:
            self.state.deer_id = found.id
            found._scenario_controlled = True
            return found
        next_id = max([a.id for a in game.wildlife.animals] + [0]) + 1
        found = Animal(next_id, deer_x, deer_y, kind=AnimalKind.DEER, sex=AnimalSex.MALE,
                       move_cooldown=10**9, world_x=float(deer_x), world_y=float(deer_y))
        game.wildlife.animals.append(found)
        game.wildlife.next_id = max(game.wildlife.next_id, next_id+1)
        game.wildlife._index_animals()
        self.state.deer_id = found.id
        found._scenario_controlled = True
        return found

    def _guide_deer(self, game) -> None:
        from world import FeatureType, TerrainType
        deer = self._tutorial_deer(game)
        if deer is None:
            return
        elapsed = self._movement_ticks_this_frame(game)
        if elapsed <= 0:
            deer.move_cooldown = self.state.deer_move_wait
            return
        if self.state.deer_move_wait > 0:
            self.state.deer_move_wait = max(0, self.state.deer_move_wait-elapsed)
            deer.move_cooldown = self.state.deer_move_wait
            if self.state.deer_move_wait > 0:
                return
        target = self._village_target(game)
        rng = random.Random(
            (deer.id << 16)
            ^ int(deer.x*31 + deer.y*17)
            ^ self.state.deer_move_serial*7919
        )
        choices = []
        for dx, dy in ((-1,-1),(-1,0),(0,-1),(1,-1),(-1,1),(1,0),(0,1),(1,1)):
            nx, ny = deer.x+dx, deer.y+dy
            cell = game.world.get_cell(nx, ny)
            if cell is None or not game.world.can_step(deer.x, deer.y, nx, ny):
                continue
            if cell.feature != FeatureType.NONE:
                continue
            distance = math.hypot(nx-game.player.x, ny-game.player.y)
            # The 2–4 cell leash dominates. Within that band, progress toward
            # the farm is the strongest preference, with enough noise to keep
            # the animal's route from looking mechanical.
            band_penalty = (
                (2.0-distance)*40.0 if distance < 2.0
                else (distance-4.0)*40.0 if distance > 4.0
                else abs(distance-3.0)*1.5
            )
            terrain_penalty = 0.0 if cell.terrain == TerrainType.GRASS else 3.0
            score = (
                band_penalty
                + math.hypot(nx-target[0], ny-target[1])*4.0
                + terrain_penalty
                + rng.random()*3.5
            )
            nearby_trees = sum(
                game.world.get_cell(nx+ox, ny+oy) is not None
                and game.world.get_cell(nx+ox, ny+oy).feature == FeatureType.TREE
                for ox, oy in ((-1,0),(1,0),(0,-1),(0,1))
            )
            score -= nearby_trees*.18
            choices.append((score, nx, ny))
        if choices:
            from entities import arm_cell_step_visual, note_cell_step
            from wildlife import animal_roam_interval

            _, nx, ny = min(choices)
            note_cell_step(deer, nx, ny, world_target=(float(nx), float(ny)))
            distance = self._distance(deer, game.player)
            normal_wait = animal_roam_interval()
            target = self._village_target(game)
            player_ahead = math.hypot(
                game.player.x-target[0], game.player.y-target[1]
            ) < math.hypot(nx-target[0], ny-target[1])
            escort_wait = max(4, normal_wait//2)
            if player_ahead or distance < 2.0:
                self.state.deer_move_wait = max(4, normal_wait//3)
            elif distance > 4.0:
                self.state.deer_move_wait = normal_wait
            else:
                self.state.deer_move_wait = escort_wait
            deer.move_cooldown = self.state.deer_move_wait
            arm_cell_step_visual(deer, self.state.deer_move_wait)
            self.state.deer_move_serial += 1

    def _farmhouse_revealed(self, game) -> bool:
        from entities import BuildingKind
        farm = next((b for b in game.buildings.values() if b.kind == BuildingKind.FARM), None)
        if farm is None:
            return False
        return any(
            (x, y) in game.discovered_cells
            for y in range(farm.y, farm.y+max(1, farm.plot_h))
            for x in range(farm.x, farm.x+max(1, farm.plot_w))
        )

    def _village_tent_revealed(self, game) -> bool:
        from entities import BuildingKind
        village_x, village_y = self._village_target(game)
        return any(
            building.kind in (BuildingKind.TENT, BuildingKind.HOUSE)
            and math.hypot(building.x-village_x, building.y-village_y) <= 15.0
            and any(
                (x, y) in game.discovered_cells
                for y in range(building.y, building.y+max(1, building.plot_h))
                for x in range(building.x, building.x+max(1, building.plot_w))
            )
            for building in game.buildings.values()
        )

    def _flee_deer_to_habitat(self, game) -> bool:
        """Drive the guide east to the nearest viable deer habitat."""
        from wildlife import AnimalKind, animal_flee_interval
        deer = self._tutorial_deer(game)
        if deer is None:
            return True
        if not game.wildlife.habitats:
            game.wildlife.refresh_habitats(game.world)
        if self.state.deer_migrate_x is None:
            targets = [
                (x, y, habitat.id)
                for habitat in game.wildlife.breeding_grounds(AnimalKind.DEER)
                for x, y in habitat.deer_breeding
                if x > deer.x
            ]
            if not targets:
                targets = [
                    (x, y, habitat.id)
                    for habitat in game.wildlife.breeding_grounds(AnimalKind.DEER)
                    for x, y in habitat.deer_breeding
                ]
            if not targets:
                return True
            tx, ty, patch_id = min(
                targets, key=lambda p: math.hypot(p[0]-deer.x, p[1]-deer.y)
            )
            self.state.deer_migrate_x = tx
            self.state.deer_migrate_y = ty
            self.state.deer_migrate_patch = patch_id
            deer.migrate_target = (tx, ty)
        tx, ty = self.state.deer_migrate_x, self.state.deer_migrate_y
        patch_id = self.state.deer_migrate_patch
        if (deer.x, deer.y) == (tx, ty):
            deer.patch_id = patch_id
            deer.migrate_home_id = None
            deer.migrate_target = None
            deer.move_cooldown = 0
            deer._scenario_controlled = False
            return True
        elapsed = self._movement_ticks_this_frame(game)
        if elapsed <= 0:
            deer.move_cooldown = self.state.deer_move_wait
            return False
        if self.state.deer_move_wait > 0:
            self.state.deer_move_wait = max(0, self.state.deer_move_wait-elapsed)
            deer.move_cooldown = self.state.deer_move_wait
            if self.state.deer_move_wait > 0:
                return False
        next_cell = game.world.next_step_toward((deer.x, deer.y), (tx, ty))
        if next_cell is None:
            return True
        from entities import arm_cell_step_visual, note_cell_step
        note_cell_step(deer, *next_cell, world_target=(float(next_cell[0]), float(next_cell[1])))
        self.state.deer_move_wait = animal_flee_interval()
        deer.move_cooldown = self.state.deer_move_wait
        arm_cell_step_visual(deer, self.state.deer_move_wait)
        return False

    @staticmethod
    def _movement_ticks_this_frame(game) -> int:
        """Use the same clock as ordinary wildlife, including a true pause."""
        speed = max(0, int(getattr(game, "sim_speed", 0)))
        if speed <= 0:
            return 0
        try:
            playback_ticks = game._playback_ticks()
        except (AttributeError, TypeError):
            from settings import PLAYBACK_TICKS_AT_X1
            playback_ticks = PLAYBACK_TICKS_AT_X1
        return speed*max(1, int(playback_ticks))

    @staticmethod
    def _seed_forest_animals(game) -> None:
        """Seed boar and give the lone tutorial buck a habitat mate."""
        game.wildlife.refresh_habitats(game.world)
        game.wildlife._reseed_extinct_forest_species(game.world)
        game.wildlife.ensure_lone_animals_have_mates(game.world)

    @staticmethod
    def _walk_toward_player(traveller, player) -> bool:
        tx, ty = float(getattr(traveller, "world_x", traveller.x)), float(getattr(traveller, "world_y", traveller.y))
        dx, dy = float(player.x)-tx, float(player.y)-ty
        distance = math.hypot(dx, dy)
        if distance <= 2.2:
            return True
        step = min(.075, distance-2.0)
        tx, ty = tx+dx/distance*step, ty+dy/distance*step
        traveller.world_x, traveller.world_y = tx, ty
        traveller.x, traveller.y = round(tx), round(ty)
        return False

    @staticmethod
    def _walk_toward_point(actor, x: float, y: float) -> bool:
        class Target:
            pass
        target = Target()
        target.x, target.y = x, y
        return ScenarioDirector._walk_toward_player(actor, target)

    def _rhea_villager(self, game):
        return next((v for v in game.villagers if v.id == self.state.rhea_villager_id), None)

    @staticmethod
    def _take_control_of_villager(game, villager) -> None:
        """Stop ordinary AI and collapse all visual/logical motion to one point."""
        if villager is None:
            return
        from entities import VillagerState, snap_entity_visual

        wx = float(getattr(villager, "world_x", villager.x))
        wy = float(getattr(villager, "world_y", villager.y))
        villager.x, villager.y = round(wx), round(wy)
        villager.world_x, villager.world_y = float(villager.x), float(villager.y)
        villager.target = None
        villager.haul_building_id = None
        villager.construction_id = None
        villager.move_cooldown = 0
        villager.work_cooldown = 0
        villager.decision_cooldown = 0
        villager.state = VillagerState.IDLE
        villager._scenario_controlled = True
        villager._pending_building_entry_id = None
        villager._inside_building_id = None
        villager._building_entry_ticks = 0
        villager._building_inside_ticks = 0
        villager._building_exit_ticks = 0
        game._clear_villager_path(villager)
        snap_entity_visual(villager)

    @staticmethod
    def _release_villager_control(villager) -> None:
        if villager is not None and getattr(villager, "_scenario_controlled", False):
            villager._scenario_controlled = False
            villager.decision_cooldown = 0

    @staticmethod
    def _village_field(game):
        from entities import BuildingKind
        return next((b for b in game.buildings.values() if b.kind == BuildingKind.FIELD), None)

    @staticmethod
    def _seed_field_weeds(game, field) -> None:
        for x, y in field.plot_cells():
            cell = game.world.get_cell(x, y)
            if cell is not None:
                cell.weeds = max(float(getattr(cell, "weeds", 0.0)), 0.85)

    def _field_weeds_cleared(self, game) -> bool:
        field = self._village_field(game)
        return field is not None and all(
            float(getattr(game.world.get_cell(x, y), "weeds", 0.0)) <= 0.05
            for x, y in field.plot_cells()
        )

    def interact_villager(self, game, villager) -> bool:
        """Consume scenario dialogue interactions before opening management."""
        if self.state.key != TUTORIAL_KEY:
            return False
        if villager.id == self.state.rhea_villager_id and self.state.step == "talk_to_rhea":
            self._take_control_of_villager(game, villager)
            self.state.step, self.prompt = "morning_greeting", None
            self._request_dialog("Hey there, can I help you?")
            return True
        if self.state.step != "ask_villagers":
            return False
        self._take_control_of_villager(game, villager)
        if villager.name == "Gwen Hill" and not self.state.gwen_asked:
            game.player.inventory.add_item("honey", 1)
            self.state.step, self.prompt = "gwen_intro", None
            self._request_dialog("Hi, I'm Gwen, the forager here. Although it's slim pickings right now. But here, try some honey.")
            return True
        if villager.name == "Joss Fern" and not self.state.joss_asked:
            self.state.step, self.prompt = "joss_intro", None
            self._request_dialog("Hey there, I'm Joss. I'm the farmer... well, to be honest, I have no idea what I am doing.")
            return True
        self._release_villager_control(villager)
        return False

    def use_inventory_item(self, game, key: str) -> bool:
        if self.state.key != TUTORIAL_KEY or key != "book" or self.state.step != "open_book":
            return False
        field = self._village_field(game)
        if field is None:
            return False
        if not game.player.inventory.consume_item("book", 1):
            return False
        game.player_inventory.close()
        self.state.field_planner_unlocked = True
        field._tutorial_planner_entry = True
        game._select_building(field, show_player=True, detail_only=True)
        game._tutorial_unlock_popup = (
            "Field Planner added under the Farmhouse", "field", f"building:{field.id}"
        )
        self.state.step, self.state.completed, self.prompt = "complete", True, None
        return True

    @staticmethod
    def _distance(a, b) -> float:
        return math.hypot(float(a.x)-float(b.x), float(a.y)-float(b.y))

    @staticmethod
    def _pan_camera_toward(game, wx: float, wy: float) -> None:
        """Ease the view across the map while the discovery dialogue is open."""
        visible_w, visible_h = game.camera.visible_cells()
        target_x, target_y = wx-visible_w/2, wy-visible_h/2
        game.camera.x += (target_x-game.camera.x)*.075
        game.camera.y += (target_y-game.camera.y)*.075
        game.camera.clamp(game.world.cols, game.world.rows)

    @staticmethod
    def _reveal_clearing(game, centre: tuple[int, int], radius: int) -> None:
        cx, cy = centre
        for y in range(max(0, cy-radius), min(game.world.rows, cy+radius+1)):
            for x in range(max(0, cx-radius), min(game.world.cols, cx+radius+1)):
                if (x-cx)**2 + (y-cy)**2 <= radius*radius+1:
                    game.discovered_cells.add((x, y))

    @staticmethod
    def _discovered_fruiting_bush(game) -> tuple[int, int] | None:
        from world import FeatureType
        for x, y in sorted(game.discovered_cells):
            cell = game.world.get_cell(x, y)
            if cell is not None and cell.feature == FeatureType.BERRY_BUSH and cell.deposit > 0:
                return x, y
        return None

    @staticmethod
    def _village_target(game) -> tuple[int, int]:
        from entities import BuildingKind
        farm = next(
            (building for building in game.buildings.values()
             if building.kind == BuildingKind.FARM),
            None,
        )
        if farm is not None:
            return farm.center_cell()
        return 15, 27

    def _player_reached_village(self, game) -> bool:
        vx, vy = self._village_target(game)
        return math.hypot(game.player.x-vx, game.player.y-vy) <= 7

    def to_dict(self) -> dict:
        return asdict(self.state)

    def load_dict(self, data: object) -> None:
        if not isinstance(data, dict):
            self.state, self.prompt, self._dialog_request = ScenarioState(), None, None
            return
        fields = ScenarioState.__dataclass_fields__
        self.state = ScenarioState(**{k: data[k] for k in fields if k in data})
        self._restore_presentation()

    def _restore_presentation(self) -> None:
        self._dialog_request = None
        prompts = {
            "open_inventory":"Press I to open inventory", "eat_berries":"Right click on the berries to eat.",
            "find_food":"Look around for some more food", "pick_berries":"Press Enter by any berry bush to pick a berry",
            "traveller_approaches":"Someone is coming...",
            "find_village":"Find the village to the north west", "follow_deer":"Follow the deer to the village",
            "deer_flee":"Find a tent", "find_tent":"Find a tent",
            "rhea_approaches":"Rhea is coming to speak with you...",
            "fix_tent":"Fix the tent", "rhea_congrats_approaches":"Rhea is coming to speak with you...",
            "go_to_sleep":"Get some sleep — press Enter on the tent",
            "talk_to_rhea":"Talk to Rhea — approach her and press Enter",
            "walk_to_field":"Follow Rhea to the field",
            "equip_hoe":"Equip the Hoe in Inventory",
            "clear_weeds":"Clear the field of weeds",
            "rhea_weeds_approaches":"Rhea is coming to speak with you...",
            "ask_villagers":"Ask villagers about the farm",
            "enter_farmhouse":"Enter the Farmhouse and find the old book",
            "open_book":"Open the old book — right-click it in your inventory",
        }
        dialogs = {
            "hunger_dialog":"(Stomach rumble) ... uhhh I'm getting hungry, I need to eat. I'll check what is in my bag",
            "last_berry_dialog":"Well that was the last of the berries. I should look for some more",
            "found_berries_dialog":"There's some more! So that's where they come from!",
            "traveller_reply":"Well you can't stay here. Try up at the village to the north west if you need a place to stay.",
            "deer_dialog":"Oh it's an animal! Maybe he lives near the village. I'll follow him",
            "shelter_greeting":"Hi there, can I help you?",
            "shelter_request":"I'm looking for a place to stay for the night",
            "shelter_offer":"This tent is already occupied, but there's an old collapsed tent back there. It needs a new support. If you can fix it, it's yours. You should be able to find some wood in the forest to the North.",
            "tent_repaired_dialog":"Great! You fixed it. Get some rest and we can talk in the morning.",
            "morning_greeting":"Hey there, can I help you?",
            "morning_thanks":"Thanks for the place to stay.",
            "morning_invitation":"No problem! We are a small community here, maybe you can help us out with some tasks and you can stay a while longer?",
            "morning_accept":"Sure! How can I help?",
            "farm_history":"Well... we need help with our farm. This used to be a prosperous village with abundant food. But for the past years our harvest is poor and the landscape is barren of wildlife.",
            "weed_request":"But I don't want to bore you with our tale of woe. Weeds! That's how you can help! Our fields are overrun with weeds and we need help clear them. Dogs know, the harvest is poor enough without the weeds taking over our soils. I'll show you.",
            "field_reaction":"Oh wow. Yes, this needs some work. I'll be glad to help.",
            "hoe_gift":"Here, take this.",
            "weeds_complete_dialog":"Wow, you made light work of that. We'll have to find something else for you to do to keep you around!",
        }
        self.prompt = prompts.get(self.state.step)
        if self.state.step == "traveller_accuses":
            self._request_dialog("Hey! You're eating all my berries!", (
                "I'm sorry, I didn't know they belonged to anyone", "Get lost! I'm hungry"))
        elif self.state.step in dialogs:
            self._request_dialog(dialogs[self.state.step])

    def apply_checkpoint(self, game, checkpoint: dict) -> None:
        """Apply a lightweight tutorial_intro_N developer checkpoint."""
        step = str(checkpoint.get("step", "hunger_dialog"))
        position = checkpoint.get("player", self.layout.get("player_start", [90, 69]))
        game.player.reset(int(position[0]), int(position[1]))
        game.discovered_cells = set()
        game._reveal_around_player()
        post_sleep = step in {
            "talk_to_rhea", "morning_greeting", "walk_to_field", "equip_hoe", "clear_weeds",
            "weeds_complete_dialog", "ask_villagers", "gwen_intro", "joss_intro",
            "enter_farmhouse", "open_book", "complete",
        }
        if step in {"fix_tent", "go_to_sleep"} or post_sleep:
            self._join_rhea_to_village(game)
        if step in {"follow_deer", "find_tent", "fix_tent", "go_to_sleep"} or post_sleep:
            self._join_berry_traveller(game)
        if step == "go_to_sleep" or post_sleep:
            site = game.construction_sites.get(self.state.broken_tent_site_id or -1)
            if site is not None:
                site.have_wood = site.need_wood
                site.build_progress = site.build_required_ticks()
                game._complete_construction(site)
                repaired = self._repaired_tent(game)
                self.state.repaired_tent_id = repaired.id if repaired is not None else None
        if post_sleep:
            self.state.intro_clock_released = True
            game.calendar_day = 0
            game.day_tick = round(game.ticks_per_day * (1.0 - 8.0 / 24.0))
            game.finish_tutorial_village_sleep()
        if step in {"equip_hoe", "clear_weeds"}:
            field = self._village_field(game)
            if field is not None:
                self._seed_field_weeds(game, field)
            game.player.inventory.add_item("hoe", 1)
        if step == "clear_weeds":
            game.player.inventory.equip_tool("hoe")
        self.state.gwen_asked = bool(checkpoint.get("gwen_asked", False))
        self.state.joss_asked = bool(checkpoint.get("joss_asked", False))
        self.state.field_planner_unlocked = bool(checkpoint.get("field_planner_unlocked", False))
        if bool(checkpoint.get("has_book", False)):
            game.player.inventory.add_item("book", 1)
        self.state.step = step
        self.state.completed = step == "complete"
        self._restore_presentation()
        px, py = game._player_camera_point()
        game.camera.center_on(px, py, game.world.cols, game.world.rows)
