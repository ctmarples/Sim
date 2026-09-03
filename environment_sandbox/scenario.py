"""Persistent, data-friendly scenario runtime and the first player tutorial."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random

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
    deer_id: int | None = None
    wildlife_seeded: bool = False
    deer_move_wait: int = 0
    deer_move_serial: int = 0
    deer_migrate_x: int | None = None
    deer_migrate_y: int | None = None
    deer_migrate_patch: int | None = None


class ScenarioDirector:
    """Advance narrative steps from observable game state."""

    def __init__(self) -> None:
        self.state = ScenarioState()
        self.prompt: str | None = None
        self._dialog_request: tuple[str, tuple[str, ...]] | None = None

    @property
    def active(self) -> bool:
        return bool(self.state.key and not self.state.completed)

    def configure_after_load(self, game, save_stem: str, *, restored: bool) -> None:
        if restored:
            self._restore_presentation()
        elif save_stem == TUTORIAL_KEY:
            self.start_tutorial(game)
        else:
            self.state = ScenarioState()
            self.prompt = None
            self._dialog_request = None
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
        px = max(0, game.world.cols-6)
        py = max(0, game.world.rows-3)
        game.world.start_pos = (px, py)
        game.player.reset(px, py)
        game.player.inventory.berries = 1
        game.player.energy = .5
        game.player.satiation = .5
        game.control_mode = "dog"
        game.sim_speed = 1
        game.fast_forward = False
        game.overlay_mode = OverlayMode.NONE
        game.habitat_view_mode = False
        game.height_edit_mode = False
        if hasattr(game, "_clear_selection"):
            game._clear_selection()
        self._prepare_tutorial_people(game)
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
            self.state.step, self.prompt = "find_village", "Find the village to the north west"
        elif step == "deer_dialog":
            self.state.step, self.prompt = "follow_deer", "Follow the deer to the village"

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
            self.state.step, self.state.completed, self.prompt = "complete", True, None

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
            villager.clear_assignment()
            villager.inventory.reset()
            villager.state = VillagerState.IDLE
            villager.move_cooldown = villager.work_cooldown = 0
            bx, by = building.center_cell()
            villager.x, villager.y = bx, by
            villager.world_x, villager.world_y = float(bx), float(by)
            snap_entity_visual(villager)
            game._set_primary_workplace(villager, building.id, slot=0)
        game.next_villager_id = max([v.id for v in villagers] + [0]) + 1

        candidates = list(getattr(game, "hire_candidates", ()))
        traveller = next(
            (candidate for candidate in candidates if candidate.community_id == 0),
            candidates[0] if candidates else None,
        )
        game.hire_candidates = [traveller] if traveller is not None else []
        if traveller is not None:
            traveller.x, traveller.y = 62, 63
            traveller.world_x, traveller.world_y = 62.0, 63.0
            self.state.traveller_id = traveller.id

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
        found = next((a for a in game.wildlife.animals if a.id == self.state.deer_id), None)
        if found is None:
            found = next(
                (a for a in game.wildlife.animals
                 if a.kind == AnimalKind.DEER and (a.x, a.y) == (36, 60)),
                None,
            )
        if found is not None:
            self.state.deer_id = found.id
            found._scenario_controlled = True
            return found
        next_id = max([a.id for a in game.wildlife.animals] + [0]) + 1
        found = Animal(next_id, 36, 60, kind=AnimalKind.DEER, sex=AnimalSex.MALE,
                       move_cooldown=10**9, world_x=36.0, world_y=60.0)
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
            building.kind == BuildingKind.TENT
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
        }
        dialogs = {
            "hunger_dialog":"(Stomach rumble) ... uhhh I'm getting hungry, I need to eat. I'll check what is in my bag",
            "last_berry_dialog":"Well that was the last of the berries. I should look for some more",
            "found_berries_dialog":"There's some more! So that's where they come from!",
            "traveller_reply":"Well you can't stay here. Try up at the village to the north west if you need a place to stay.",
            "deer_dialog":"Oh it's an animal! Maybe he lives near the village. I'll follow him",
        }
        self.prompt = prompts.get(self.state.step)
        if self.state.step == "traveller_accuses":
            self._request_dialog("Hey! You're eating all my berries!", (
                "I'm sorry, I didn't know they belonged to anyone", "Get lost! I'm hungry"))
        elif self.state.step in dialogs:
            self._request_dialog(dialogs[self.state.step])
