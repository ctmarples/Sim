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
    handbook_completed: int = 0
    quest_checks: list[str] = field(default_factory=list)
    inspected_species: list[str] = field(default_factory=list)
    quest_no_hives: bool = False
    handbook_example_seasons: list[str] = field(default_factory=list)
    quest_shroud_checked: bool = False
    quest_cells: dict[str, list] = field(default_factory=dict)
    discovered_flora: list[str] = field(default_factory=list)
    forager_unlocked: bool = False
    village_buildings_unlocked: bool = False
    forage_known: list[str] = field(default_factory=list)
    foraged_species: list[str] = field(default_factory=list)
    forage_food: int = 0
    forage_herbs: int = 0
    diversity_remaining: list[str] = field(default_factory=list)
    hotspot_x: int | None = None
    hotspot_y: int | None = None
    hotspot_flora: list[str] = field(default_factory=list)
    hotspot_wildlife_found: bool = False
    hotspot_wildlife_absent: bool = False


class ScenarioDirector:
    """Advance narrative steps from observable game state."""

    def __init__(self) -> None:
        self.state = ScenarioState()
        self.prompt: str | None = None
        self._dialog_request: tuple[str, tuple[str, ...]] | None = None
        from quest_feedback import QuestFeedback
        self.quest_feedback = QuestFeedback()
        from quest_navigation import QuestNavigation
        self.quest_navigation = QuestNavigation()
        self.layout: dict = {}
        self.building_groups: dict[int, str] = {}
        self.person_groups: dict[str, str] = {}

    def objectives(self) -> list[dict]:
        from objectives import scenario_objectives
        return self.quest_feedback.rows(scenario_objectives(self.state))

    @property
    def active(self) -> bool:
        return bool(self.state.key and not self.state.completed)

    def configure_after_load(self, game, save_stem: str, *, restored: bool) -> None:
        from quest_feedback import QuestFeedback
        self.quest_feedback = QuestFeedback()
        from quest_navigation import QuestNavigation
        self.quest_navigation = QuestNavigation()
        game._tutorial_alert_queue = []
        game._tutorial_unlock_popup = None
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
        from quest_feedback import QuestFeedback
        self.quest_feedback = QuestFeedback()
        from quest_navigation import QuestNavigation
        self.quest_navigation = QuestNavigation()
        game._tutorial_alert_queue = []
        game._tutorial_unlock_popup = None
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
        elif step == "rhea_forage_intro":
            self.state.step = "rhea_forage_reply"
            self._request_dialog("Sure! I've been waiting all day for someone to take me for a walk")
        elif step == "rhea_forage_reply":
            self.state.step, self.prompt = "gwen_forage_approaches", "Gwen is coming to speak with you..."
        elif step == "diversity_quiz":
            from quest_progress import (
                DIVERSITY_CORRECT, DIVERSITY_WRONG, diversity_option_key,
            )
            key = diversity_option_key(self.state, choice)
            if key == DIVERSITY_CORRECT:
                self.state.step = "diversity_correct"
                self._request_dialog(
                    "Yes here it is most diverse! At the border between the forest and the meadow."
                )
            elif key in DIVERSITY_WRONG:
                remaining = list(self.state.diversity_remaining or [])
                if key in remaining:
                    remaining.remove(key)
                self.state.diversity_remaining = remaining
                self.state.step = "diversity_wrong"
                self._request_dialog(DIVERSITY_WRONG[key])
        elif step == "gwen_forager_intro":
            self.state.forager_unlocked = True
            self.state.step = "gwen_forager_haulers"
            self._request_dialog(
                "The haulers will then transport all the resources back to the Storehouse. "
                "Let's head out to the meadow and I'll show you what to collect"
            )
        elif step == "gwen_forager_haulers":
            self.state.step, self.prompt = "walk_to_meadow", "Follow Gwen to the meadow"
        elif step == "gwen_meadow_intro":
            self.state.step, self.prompt = "give_satchel", None
        elif step == "gwen_forage_ready":
            from quest_progress import begin_forage
            begin_forage(self.state)
            self.state.village_buildings_unlocked = True
            self.state.step, self.prompt = "forage_meadow", "Find 6 new wild plants and gather food for dinner"
        elif step == "abundance_dialog":
            self.state.step, self.prompt = (
                "find_diversity_hotspot",
                "Identify where the highest species diversity is located",
            )
        elif step == "diversity_wrong":
            from quest_progress import diversity_option_labels
            self.state.step = "diversity_quiz"
            self._request_dialog(
                "So here is the hotspot. Hmm, I wonder why there are so many species here.",
                diversity_option_labels(self.state),
            )
        elif step == "diversity_correct":
            self.state.step, self.prompt = (
                "inspect_hotspot_flora",
                "Inspect the flora at the hotspot — find 5 species",
            )
        elif step == "wildlife_footprints":
            self.state.hotspot_wildlife_absent = True
            self.state.step, self.prompt = "return_to_rhea", "Return to the village and find Rhea"
        elif step == "knowledge_thanks":
            self.state.step = "knowledge_player_glad"
            self._request_dialog(
                "My pleasure, I'm glad to be put to work. But there is so much food up there "
                "I wonder why you even bother with the farm."
            )
        elif step == "knowledge_player_glad":
            self.state.step = "knowledge_rhea_winter"
            self._request_dialog(
                "Ah yes. Foraging there can provide enough for a small community to get by during "
                "the warmer months. But come winter time the forage dies back and we were left with "
                "only what we can store. Farming closer to the village helps us plan what we need "
                "for the year and if done well will feed us easily for years to come."
            )
        elif step == "knowledge_rhea_winter":
            self.state.step = "knowledge_player_edge"
            self._request_dialog(
                "You know, I noticed something up there in the meadow with so many wild plants and "
                "animals around. Everything seems so much healthier. Particularly the transitions "
                "between different terrains. The forest edge was teeming with life! Maybe we can "
                "apply that to our field here!"
            )
        elif step == "knowledge_player_edge":
            self.state.step = "knowledge_rhea_we"
            self._request_dialog("We? Our? So you're planning to stay here then?")
        elif step == "knowledge_rhea_we":
            self.state.step = "knowledge_player_hesitate"
            self._request_dialog("Well... I...")
        elif step == "knowledge_player_hesitate":
            self.state.step = "knowledge_rhea_stay"
            self._request_dialog(
                "I'm only yanking your tail. Of course you can stay! And good idea to try to "
                "recreate the healthy environment from the meadow and forests. Now that you mention "
                "it, there always were lines of trees and shrubs around the field before we cleared "
                "it for wood. Plenty of delicious berries were growing there too! But those trees "
                "would take many seasons to grow back. (sigh)"
            )
        elif step == "knowledge_rhea_stay":
            self.state.step = "knowledge_player_berries"
            self._request_dialog(
                "Berries? They grow on bushes, I've seen them! They must be faster growing than "
                "growing a new forest. In fact, I think I know just where to go to find some berry bushes!"
            )
        elif step == "knowledge_player_berries":
            self.state.step, self.prompt = (
                "visit_berry_traveller",
                "Return to the berries traveller to get some berry bushes",
            )
        elif step == "berry_trade_accuse":
            self.state.step = "berry_trade_player_stay"
            self._request_dialog(
                "Yes, yes. I know. I can't stay here. I'm staying up at the village. "
                "I only came to ask about your berry bushes."
            )
        elif step == "berry_trade_player_stay":
            self.state.step = "berry_trade_mine"
            self._request_dialog("They're mine!")
        elif step == "berry_trade_mine":
            self.state.step = "berry_trade_offer"
            self._request_dialog(
                "Yes, yes. I know. But I was wondering, don't you get tired of only eating berries. "
                "What if I found you some other food, maybe we can make a trade?"
            )
        elif step == "berry_trade_offer":
            self.state.step = "berry_trade_listening"
            self._request_dialog("Hmm... I'm listening.")
        elif step == "berry_trade_listening":
            self.state.step = "berry_trade_terms"
            self._request_dialog("I'll bring you 20 food and you give me some berry seeds.")
        elif step == "berry_trade_terms":
            self.state.step, self.prompt = (
                "collect_trade_food",
                "Collect 20 food and bring it back to the traveller",
            )
            self._request_dialog("Hmm... let's see.")
        elif step == "berry_trade_delivery":
            self.state.step, self.prompt = (
                "create_orchard_field",
                "Create a 1×6 orchard field along the west border of the wheat field",
            )
            self._request_dialog(
                "Those seeds will want a proper orchard. Mark a strip of field "
                "along the west side of the wheat, then plan the bushes."
            )

    def begin_diversity_quiz(self, game, x: int, y: int) -> bool:
        """Open the hotspot location quiz after the player inspects the meadow edge."""
        from quest_progress import diversity_option_labels, note_diversity_cell
        if not note_diversity_cell(game, x, y):
            return False
        self.state.step, self.prompt = "diversity_quiz", None
        self._request_dialog(
            "So here is the hotspot. Hmm, I wonder why there are so many species here.",
            diversity_option_labels(self.state),
        )
        return True

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
        if step == "field_handbook":
            panel = game.field_plan_dialog
            panel.handbook_stage = self.state.handbook_completed
            from quest_progress import mark, ready, check_shroud
            if self.state.handbook_completed == 0:
                check_shroud(game)
            if self.state.handbook_completed == 4:
                for season in getattr(panel, '_example_seen_seasons', set()):
                    if season.name not in self.state.handbook_example_seasons:
                        self.state.handbook_example_seasons.append(season.name)
                if len(self.state.handbook_example_seasons) == 4:
                    mark(self.state, 'read')
                panel.rotation_unlocked = 'handbook_5:read' in self.state.quest_checks
                if panel.open and panel.tab == 'rotation':
                    mark(self.state, 'rotation')
            if ready(self.state):
                self.state.handbook_completed = min(5, self.state.handbook_completed + 1)
                panel.handbook_stage = self.state.handbook_completed
                panel.tab = "rotation" if self.state.handbook_completed == 5 else "status"
                panel._scroll = 0
                if self.state.handbook_completed == 5:
                    rhea = self._rhea_villager(game)
                    self._take_control_of_villager(game, rhea)
                    self.state.step, self.prompt = "rhea_forage_approaches", "Rhea is coming to speak with you..."
                else:
                    self._restore_presentation()
            return
        if step == "found_berries_dialog" and self.state.bush_x is not None:
            self._pan_camera_toward(game, self.state.bush_x+.5, self.state.bush_y+.5)
        if step == "open_inventory" and (
            game.player_inventory.open
            or (
                game.management.open
                and getattr(game.management.tab, "name", None) == "PLAYER"
            )
        ):
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
        elif step == "rhea_forage_approaches":
            rhea = self._rhea_villager(game)
            self._take_control_of_villager(game, rhea)
            if rhea is None or self._walk_toward_player(rhea, game.player):
                self.state.step, self.prompt = "rhea_forage_intro", None
                self._request_dialog(
                    "Great to see you're getting to know the old farm. We need all the help we can get. "
                    "Say... would you mind helping Gwen with the foraging? We're running low on provisions "
                    "and need to gather enough food for dinner."
                )
        elif step == "gwen_forage_approaches":
            self._release_villager_control(self._rhea_villager(game))
            gwen = self._gwen_villager(game)
            self._take_control_of_villager(game, gwen)
            if gwen is None or self._walk_toward_player(gwen, game.player):
                self.state.step, self.prompt = "walk_to_forager", "Follow Gwen to the forager hut"
        elif step == "walk_to_forager":
            gwen = self._gwen_villager(game)
            hut = self._village_forager(game)
            self._take_control_of_villager(game, gwen)
            if gwen is not None and hut is not None:
                hx, hy = hut.center_cell()
                gwen_done = self._walk_toward_point(gwen, hx, hy)
                player_done = self._walk_player_with_camera(game, hx + 1, hy)
                if gwen_done and player_done:
                    self.state.step, self.prompt = "gwen_forager_intro", None
                    self._request_dialog("This is where we bring all our foraged goods together.")
            elif hut is None:
                self.state.step, self.prompt = "gwen_forager_intro", None
                self._request_dialog("This is where we bring all our foraged goods together.")
        elif step == "walk_to_meadow":
            from quest_progress import MEADOW_CELL
            gwen = self._gwen_villager(game)
            self._take_control_of_villager(game, gwen)
            mx, my = MEADOW_CELL
            gwen_done = gwen is None or self._walk_toward_point(gwen, mx - 1, my)
            player_done = self._walk_player_with_camera(game, mx, my)
            if gwen_done and player_done:
                self.state.step, self.prompt = "gwen_meadow_intro", None
                self._request_dialog(
                    "Here is the local meadow I come to forage. The soils here are very fertile and moist, "
                    "so you'll find many different wild plants here. Here, take this."
                )
        elif step == "give_satchel":
            game.player.inventory.add_item("leather_satchel", 1)
            self.state.step, self.prompt = "equip_satchel", "Wear the leather satchel — right-click it in your inventory"
        elif step == "equip_satchel" and game.player.inventory.equipped_in_slot("bag") == "leather_satchel":
            self._release_villager_control(self._gwen_villager(game))
            self.state.step, self.prompt = "gwen_forage_ready", None
            self._request_dialog("Great, now you're set to forage! Let's see what you can find.")
        elif step == "forage_meadow":
            from quest_progress import forage_ready
            if forage_ready(self.state):
                self.state.step, self.prompt = "abundance_dialog", None
                self._request_dialog(
                    "Wow there really is an abundance of food and plants here! "
                    "I wonder how many different species there are..."
                )
        elif step == "inspect_hotspot_flora":
            from quest_progress import hotspot_flora_ready
            if hotspot_flora_ready(self.state):
                self.state.step, self.prompt = (
                    "find_hotspot_wildlife",
                    "Can I find any wildlife here as well?",
                )
        elif step == "find_hotspot_wildlife":
            from quest_progress import wildlife_near_hotspot
            if self.state.hotspot_wildlife_found:
                self.state.step, self.prompt = "return_to_rhea", "Return to the village and find Rhea"
            elif not wildlife_near_hotspot(game):
                self.state.step, self.prompt = "wildlife_footprints", None
                self._request_dialog(
                    "Hmm, I guess they're not around at the moment. "
                    "But I can see their footprints here!"
                )
        elif step == "visit_berry_traveller":
            self._release_villager_control(self._rhea_villager(game))
        elif step == "collect_trade_food":
            self._release_villager_control(self._berry_villager(game))
        elif step == "create_orchard_field":
            if self._quest_orchard(game) is not None:
                self.state.step, self.prompt = (
                    "plan_orchard_crops",
                    "Plan 2 blackberry, 2 sloe berry, and 2 elder berry bushes",
                )
        elif step == "plan_orchard_crops":
            orchard = self._quest_orchard(game)
            if self._orchard_plan_ready(orchard):
                self.state.step, self.prompt = (
                    "plant_orchard_bushes",
                    "Plant the planned orchard bushes",
                )
        elif step == "plant_orchard_bushes":
            orchard = self._quest_orchard(game)
            if self._orchard_planted_ready(game, orchard):
                self.state.step, self.state.completed, self.prompt = "complete", True, None
                self._request_dialog(
                    "The bushes are in. They'll need a change of season to mature, "
                    "and the orchard ground will shape how much they give."
                )

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
        if self.state.village_buildings_unlocked:
            allowed = {self.state.repaired_tent_id}
            allowed.update(
                bid for bid, group in self.building_groups.items() if group == "village"
            )
            allowed.update(
                b.id for b in game.buildings.values() if b.kind.name == "ORCHARD"
            )
            return {bid: b for bid, b in game.buildings.items() if bid in allowed}
        allowed = {self.state.repaired_tent_id}
        if self.state.joss_asked:
            allowed.update(b.id for b in game.buildings.values() if b.kind.name == "FARM")
        if self.state.field_planner_unlocked:
            for building in game.buildings.values():
                if building.kind.name == "FIELD":
                    building._tutorial_planner_entry = True
                    allowed.add(building.id)
        if self.state.forager_unlocked:
            allowed.update(b.id for b in game.buildings.values() if b.kind.name == "FORAGER")
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
            "enter_farmhouse", "open_book", "field_handbook", "complete",
        }
        from objectives import FORAGE_STEPS
        wheat_steps.update(FORAGE_STEPS)
        keys = {"wild:wheat"} if self.state.step in wheat_steps else set()
        if self.state.step in wheat_steps - {
            "clear_weeds", "rhea_weeds_approaches", "weeds_complete_dialog", "farm_question"
        }:
            keys.update(("wild:dandelion", "wild:daisy"))
        keys.update(self.state.discovered_flora)
        keys.update(key.replace("plant:", "wild:", 1) for key in self.state.inspected_species
                    if key.startswith(("plant:", "tree:")))
        return keys

    def _sync_management_unlocks(self, game, *, announce: bool = True) -> None:
        """Queue a separate notification for each newly available entry."""
        candidates: list[tuple[str, str, str, str]] = []
        if self.state.rhea_villager_id is not None:
            candidates.append(("rhea", "Rhea added to People", "villager", "people"))
        if self.state.repaired_tent_id is not None:
            candidates.append(("tent", "Personal tent added to Buildings", "tent", "buildings"))
        flora = self.tutorial_management_flora()
        from wild_species import WILD_BY_KEY
        from trees import TREE_BY_KEY
        for flora_key in sorted(flora):
            group, key = flora_key.split(":", 1)
            species = (TREE_BY_KEY if group == "tree" else WILD_BY_KEY).get(key)
            if species is not None:
                alert_key = "wheat" if flora_key == "wild:wheat" else f"flora:{flora_key}"
                if key in ("dandelion", "daisy") and "flowers" in self.state.announced_unlocks:
                    if alert_key not in self.state.announced_unlocks:
                        self.state.announced_unlocks.append(alert_key)
                candidates.append((alert_key, f"{species.label} added to Flora",
                                   "tree_round_1" if group == "tree" else "crop_plant",
                                   f"flora:{flora_key}"))
        if self.state.gwen_asked:
            candidates.append(("gwen", "Gwen Hill added to People", "villager", "people"))
        if self.state.joss_asked:
            candidates.extend((("joss", "Joss Fern added to People", "villager", "people"),
                               ("farm", "Farmhouse added to Buildings", "farm", "buildings")))
        if self.state.forager_unlocked:
            hut = self._village_forager(game)
            target = f"building:{hut.id}" if hut is not None else "buildings"
            candidates.append(("forager", "Forager huts unlocked", "forager", target))
        if self.state.village_buildings_unlocked:
            candidates.append(("village", "Village buildings unlocked", "farm", "buildings"))
        announced = self.state.announced_unlocks
        for key, label, icon, target in candidates:
            if key not in announced:
                announced.append(key)
                if announce:
                    from quest_feedback import queue_alert
                    queue_alert(game, label, icon, target)

    def can_player_interact_building(self, building) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        if building.id == self.state.repaired_tent_id:
            return True
        if self.state.village_buildings_unlocked and self.building_groups.get(building.id) == "village":
            return True
        if self.state.joss_asked and building.kind.name == "FARM":
            return True
        if self.state.forager_unlocked and building.kind.name == "FORAGER":
            return True
        if building.kind.name == "ORCHARD":
            return self.state.village_buildings_unlocked or self.state.field_planner_unlocked
        return self.state.field_planner_unlocked and building.kind.name == "FIELD"

    def can_player_interact_site(self, site) -> bool:
        if self.state.key != TUTORIAL_KEY:
            return True
        if site.id == self.state.broken_tent_site_id:
            return True
        if site.kind.name in ("FIELD", "ORCHARD") and self.state.village_buildings_unlocked:
            return True
        return False

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

    def _walk_player_with_camera(self, game, x: float, y: float) -> bool:
        done = self._walk_toward_point(game.player, x, y)
        if hasattr(game, "_reveal_around_player"):
            game._reveal_around_player()
        if hasattr(game, "_ensure_player_in_view"):
            game._ensure_player_in_view()
        return done

    def _rhea_villager(self, game):
        return next((v for v in getattr(game, "villagers", ()) if v.id == self.state.rhea_villager_id), None)

    def _gwen_villager(self, game):
        return next((v for v in getattr(game, "villagers", ()) if v.name == "Gwen Hill"), None)

    def _berry_villager(self, game):
        return next((v for v in getattr(game, "villagers", ()) if v.id == self.state.berry_villager_id), None)

    @staticmethod
    def _player_food_count(game) -> int:
        from resource_balance import VILLAGER_FOOD_KEYS
        inv = game.player.inventory
        return sum(int(getattr(inv, key, 0) or 0) for key in VILLAGER_FOOD_KEYS)

    @staticmethod
    def _consume_player_food(game, amount: int) -> int:
        from resource_balance import VILLAGER_FOOD_KEYS
        inv = game.player.inventory
        left = int(amount)
        taken = 0
        for key in VILLAGER_FOOD_KEYS:
            have = int(getattr(inv, key, 0) or 0)
            if have <= 0:
                continue
            use = min(have, left)
            if inv.consume_item(key, use):
                taken += use
                left -= use
            if left <= 0:
                break
        return taken

    def deliver_berry_trade(self, game) -> bool:
        """Exchange 20 food for the agreed berry seeds."""
        from berry_bushes import TRADE_FOOD_COST, TRADE_SEED_REWARDS
        if self.state.step != "collect_trade_food":
            return False
        if self._player_food_count(game) < TRADE_FOOD_COST:
            return False
        if self._consume_player_food(game, TRADE_FOOD_COST) < TRADE_FOOD_COST:
            return False
        for key, n in TRADE_SEED_REWARDS:
            game.player.inventory.add_item(key, n)
        self.state.step = "berry_trade_delivery"
        self._request_dialog("Ohhh my, that does look good. (woof). Fine here take these.")
        return True

    @staticmethod
    def _village_forager(game):
        from entities import BuildingKind
        return next((b for b in getattr(game, "buildings", {}).values() if b.kind == BuildingKind.FORAGER), None)

    @staticmethod
    def _take_control_of_villager(game, villager) -> None:
        """Stop ordinary AI and collapse all visual/logical motion to one point."""
        if villager is None:
            return
        if getattr(villager, "_scenario_controlled", False):
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
    def _orchard_quest_target(wheat) -> tuple[int, int, int, int] | None:
        """Return (x, y, w, h) for the 1×N orchard strip west of the wheat field."""
        if wheat is None:
            return None
        return int(wheat.x) - 1, int(wheat.y), 1, max(1, int(wheat.plot_h))

    def validate_orchard_placement(self, game, x0: int, y0: int, plot_w: int, plot_h: int):
        """During the orchard quest, only accept the west-border 1×N strip."""
        if self.state.key != TUTORIAL_KEY or self.state.step != "create_orchard_field":
            return True, None
        wheat = self._village_field(game)
        target = self._orchard_quest_target(wheat)
        if target is None:
            return False, "Need the wheat field before placing an orchard."
        tx, ty, tw, th = target
        if (x0, y0, plot_w, plot_h) != (tx, ty, tw, th):
            return (
                False,
                f"Orchard must be {tw}×{th} along the west border of the wheat field. Try again.",
            )
        return True, None

    def _quest_orchard(self, game):
        from entities import BuildingKind
        wheat = self._village_field(game)
        target = self._orchard_quest_target(wheat)
        if target is None:
            return None
        tx, ty, tw, th = target
        for building in game.buildings.values():
            if building.kind != BuildingKind.ORCHARD:
                continue
            if (building.x, building.y, building.plot_w, building.plot_h) == (tx, ty, tw, th):
                return building
        return None

    def _ensure_quest_orchard(self, game, wheat):
        """Create the west-border orchard plot for later orchard checkpoints."""
        from entities import Building, BuildingKind, TaskType, apply_building_storage
        existing = self._quest_orchard(game)
        if existing is not None:
            return existing
        target = self._orchard_quest_target(wheat)
        if target is None:
            return None
        tx, ty, tw, th = target
        building = Building(
            id=game.next_building_id,
            kind=BuildingKind.ORCHARD,
            x=tx,
            y=ty,
            plot_w=tw,
            plot_h=th,
            draw_task_type=TaskType.FARM_FIELD,
        )
        apply_building_storage(building)
        building.sync_draw_task_from_mode()
        game.next_building_id += 1
        game.buildings[building.id] = building
        self.building_groups[building.id] = "personal"
        return building

    @staticmethod
    def _orchard_plan_counts(orchard) -> dict[str, int]:
        counts: dict[str, int] = {}
        if orchard is None:
            return counts
        for plan in orchard.plans:
            n = len(plan.cells())
            counts[plan.crop_kind] = counts.get(plan.crop_kind, 0) + n
        return counts

    def _orchard_plan_ready(self, orchard) -> bool:
        counts = self._orchard_plan_counts(orchard)
        return (
            counts.get("blackberry", 0) >= 2
            and counts.get("sloe", 0) >= 2
            and counts.get("elderberry", 0) >= 2
        )

    def _orchard_planted_ready(self, game, orchard) -> bool:
        if orchard is None or not self._orchard_plan_ready(orchard):
            return False
        from world import FeatureType
        needed = {"blackberry": 2, "sloe": 2, "elderberry": 2}
        planted = {key: 0 for key in needed}
        for plan in orchard.plans:
            if plan.crop_kind not in needed:
                continue
            for x, y in plan.cells():
                cell = game.world.get_cell(x, y)
                if (
                    cell is not None
                    and cell.feature == FeatureType.CROP_HERB
                    and (cell.crop_kind or "") == plan.crop_kind
                ):
                    planted[plan.crop_kind] = planted.get(plan.crop_kind, 0) + 1
        return all(planted.get(key, 0) >= need for key, need in needed.items())

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
        if villager.id == self.state.rhea_villager_id and self.state.step == "return_to_rhea":
            self._take_control_of_villager(game, villager)
            self.state.step, self.prompt = "knowledge_thanks", None
            self._request_dialog("Thanks for collecting all that food, we'll eat well tonight!")
            return True
        if (
            villager.id == self.state.berry_villager_id
            and self.state.step == "visit_berry_traveller"
        ):
            self._take_control_of_villager(game, villager)
            self.state.step, self.prompt = "berry_trade_accuse", None
            self._request_dialog(
                "You again! Did I not make myself clear?! You're not welcome here! (bark)"
            )
            return True
        if villager.id == self.state.berry_villager_id and self.state.step == "collect_trade_food":
            if self.deliver_berry_trade(game):
                return True
            have = self._player_food_count(game)
            game._set_status(f"Need 20 food for the trade ({have}/20).")
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
        from quest_feedback import queue_alert
        queue_alert(game, "Field Planner added under the Farmhouse", "field", f"building:{field.id}")
        self.state.step, self.state.completed = "field_handbook", False
        game.field_plan_dialog.handbook_stage = 0
        game.field_plan_dialog.tab = "handbook"
        self._restore_presentation()
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
        from quest_feedback import QuestFeedback
        self.quest_feedback = QuestFeedback()
        from quest_navigation import QuestNavigation
        self.quest_navigation = QuestNavigation()
        if not isinstance(data, dict):
            self.state, self.prompt, self._dialog_request = ScenarioState(), None, None
            return
        fields = ScenarioState.__dataclass_fields__
        self.state = ScenarioState(**{k: data[k] for k in fields if k in data})
        if self.state.step == 'field_handbook':
            if self.state.handbook_completed == 0 and not self.state.quest_shroud_checked:
                self.state.quest_checks = [key for key in self.state.quest_checks if key != 'handbook_1:hive']
            if self.state.handbook_completed == 4 and len(self.state.handbook_example_seasons) < 4:
                self.state.quest_checks = [key for key in self.state.quest_checks if key not in ('handbook_5:read', 'handbook_5:rotation')]
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
            "rhea_forage_approaches":"Rhea is coming to speak with you...",
            "gwen_forage_approaches":"Gwen is coming to speak with you...",
            "walk_to_forager":"Follow Gwen to the forager hut",
            "walk_to_meadow":"Follow Gwen to the meadow",
            "equip_satchel":"Wear the leather satchel — right-click it in your inventory",
            "forage_meadow":"Find 6 new wild plants and gather food for dinner",
            "find_diversity_hotspot":"Identify where the highest species diversity is located",
            "inspect_hotspot_flora":"Inspect the flora at the hotspot — find 5 species",
            "find_hotspot_wildlife":"Can I find any wildlife here as well?",
            "return_to_rhea":"Return to the village and find Rhea",
            "visit_berry_traveller":"Return to the berries traveller to get some berry bushes",
            "collect_trade_food":"Collect 20 food and bring it back to the traveller",
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
            "rhea_forage_intro":(
                "Great to see you're getting to know the old farm. We need all the help we can get. "
                "Say... would you mind helping Gwen with the foraging? We're running low on provisions "
                "and need to gather enough food for dinner."
            ),
            "rhea_forage_reply":"Sure! I've been waiting all day for someone to take me for a walk",
            "gwen_forager_intro":"This is where we bring all our foraged goods together.",
            "gwen_forager_haulers":(
                "The haulers will then transport all the resources back to the Storehouse. "
                "Let's head out to the meadow and I'll show you what to collect"
            ),
            "gwen_meadow_intro":(
                "Here is the local meadow I come to forage. The soils here are very fertile and moist, "
                "so you'll find many different wild plants here. Here, take this."
            ),
            "gwen_forage_ready":"Great, now you're set to forage! Let's see what you can find.",
            "abundance_dialog":(
                "Wow there really is an abundance of food and plants here! "
                "I wonder how many different species there are..."
            ),
            "diversity_correct":(
                "Yes here it is most diverse! At the border between the forest and the meadow."
            ),
            "wildlife_footprints":(
                "Hmm, I guess they're not around at the moment. "
                "But I can see their footprints here!"
            ),
        }
        self.prompt = prompts.get(self.state.step)
        if self.state.step == "field_handbook":
            from field_handbook import HANDBOOK_STEPS
            self.prompt = HANDBOOK_STEPS[min(4, self.state.handbook_completed)][2]
        if self.state.step == "traveller_accuses":
            self._request_dialog("Hey! You're eating all my berries!", (
                "I'm sorry, I didn't know they belonged to anyone", "Get lost! I'm hungry"))
        elif self.state.step in dialogs:
            self._request_dialog(dialogs[self.state.step])

    def apply_checkpoint(self, game, checkpoint: dict) -> None:
        """Apply a lightweight tutorial_intro_N developer checkpoint.

        Unlocks, quest items, and map reveals are applied from story chronology
        so loading a late quest always carries earlier progress.
        """
        from tutorial_progress import apply_cumulative_progress, reached

        step = str(checkpoint.get("step", "hunger_dialog"))
        position = checkpoint.get("player", self.layout.get("player_start", [90, 69]))
        game.player.reset(int(position[0]), int(position[1]))
        game.discovered_cells = set()
        game._reveal_around_player()

        post_sleep = reached(step, "talk_to_rhea")
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
            self._seed_forest_animals(game)
            self.state.wildlife_seeded = True

        # Active weeding stage still has weeds; everything after is cleared.
        field = self._village_field(game)
        if step in {"equip_hoe", "clear_weeds"}:
            if field is not None:
                self._seed_field_weeds(game, field)
        elif reached(step, "weeds_complete_dialog") and field is not None:
            for x, y in field.plot_cells():
                game.world.get_cell(x, y).weeds = 0.0
            for villager in game.villagers:
                self._release_villager_control(villager)

        self.state.step = step
        self.state.completed = step == "complete"
        if checkpoint.get("hotspot_x") is not None:
            self.state.hotspot_x = int(checkpoint["hotspot_x"])
        if checkpoint.get("hotspot_y") is not None:
            self.state.hotspot_y = int(checkpoint["hotspot_y"])

        # Orchard work teleports beside the wheat field before inventory grants.
        if reached(step, "create_orchard_field") and not reached(step, "complete"):
            wheat = self._village_field(game)
            if wheat is not None:
                game.player.reset(max(0, wheat.x - 2), wheat.y)

        # Chronological unlocks, items, and reveals (after final player.reset).
        apply_cumulative_progress(self, game, step, checkpoint)

        if self.state.field_planner_unlocked:
            self._apply_field_checkpoint(game, checkpoint)

        if reached(step, "forage_meadow"):
            from quest_progress import (
                FORAGE_FOOD_GOAL,
                FORAGE_HERB_GOAL,
                FORAGE_SPECIES_GOAL,
                begin_forage,
            )
            begin_forage(self.state)
            if step != "forage_meadow":
                if len(self.state.foraged_species) < FORAGE_SPECIES_GOAL:
                    self.state.foraged_species = [
                        f"plant:checkpoint_{i}" for i in range(FORAGE_SPECIES_GOAL)
                    ]
                self.state.forage_food = max(self.state.forage_food, FORAGE_FOOD_GOAL)
                self.state.forage_herbs = max(self.state.forage_herbs, FORAGE_HERB_GOAL)

        if reached(step, "inspect_hotspot_flora"):
            from quest_progress import DIVERSITY_OPTIONS, MEADOW_CELL
            self.state.diversity_remaining = [DIVERSITY_OPTIONS[-1][0]]
            if self.state.hotspot_x is None:
                self.state.hotspot_x, self.state.hotspot_y = MEADOW_CELL

        if reached(step, "find_hotspot_wildlife"):
            from quest_progress import HOTSPOT_FLORA_GOAL
            if len(self.state.hotspot_flora) < HOTSPOT_FLORA_GOAL:
                self.state.hotspot_flora = [
                    f"plant:hotspot_{i}" for i in range(HOTSPOT_FLORA_GOAL)
                ]

        if reached(step, "return_to_rhea"):
            self.state.hotspot_wildlife_found = True
            self.state.hotspot_wildlife_absent = bool(
                checkpoint.get("hotspot_wildlife_absent", False)
            )
        if bool(checkpoint.get("hotspot_wildlife_absent", False)):
            self.state.hotspot_wildlife_absent = True
            self.state.hotspot_wildlife_found = False

        if reached(step, "plan_orchard_crops"):
            wheat = self._village_field(game)
            if wheat is not None:
                self._ensure_quest_orchard(game, wheat)
        if reached(step, "plant_orchard_bushes"):
            orchard = self._quest_orchard(game)
            if orchard is not None and not self._orchard_plan_ready(orchard):
                orchard.plans.clear()
                orchard.next_plan_id = 1
                for kind, y0, y1 in (
                    ("blackberry", orchard.y, orchard.y + 1),
                    ("sloe", orchard.y + 2, orchard.y + 3),
                    ("elderberry", orchard.y + 4, orchard.y + 5),
                ):
                    orchard.add_field_plan(orchard.x, y0, orchard.x, y1, kind)

        self._restore_presentation()
        # Historical discoveries are already recorded; don't flood a checkpoint
        # with notifications for every preceding tutorial event.
        self._sync_management_unlocks(game, announce=False)
        game._tutorial_unlock_popup = None
        game._tutorial_alert_queue = []
        game._layer_pulse_button = False
        game._layer_pulse_mode = None
        px, py = game._player_camera_point()
        game.camera.center_on(px, py, game.world.cols, game.world.rows)

    def _apply_field_checkpoint(self, game, checkpoint: dict) -> None:
        from quest_progress import FIELD_OBJECTIVES, check_key, overlapping_hives, near_field
        from world import FeatureType
        from wild_species import resolve_species
        from trees import resolve_tree

        stage = max(0, min(5, int(checkpoint.get("handbook_completed", 5 if self.state.completed else 0))))
        self.state.handbook_completed = stage
        self.state.quest_checks = [check_key(index, key)
            for index in range(stage) for key, _ in FIELD_OBJECTIVES[index]]
        self.state.quest_checks.extend(key for key in checkpoint.get("quest_checks", [])
                                       if key not in self.state.quest_checks)
        self.state.handbook_example_seasons = list(checkpoint.get("handbook_example_seasons", []))
        if stage == 5:
            self.state.handbook_example_seasons = ["SPRING", "SUMMER", "AUTUMN", "WINTER"]
        field = self._village_field(game)
        if field is None:
            return
        cells = list(field.plot_cells())
        if stage >= 1:
            left, top, right, bottom = field.plot_bounds()
            game.discovered_cells.update((x,y)
                for y in range(max(0, top-10), min(game.world.rows, bottom+11))
                for x in range(max(0, left-10), min(game.world.cols, right+11)))
            self.state.quest_shroud_checked = True
            self.state.quest_no_hives = not bool(overlapping_hives(game))
            # Backfill actual nearby species rather than invented catalogue keys.
            for y in range(game.world.rows):
                for x in range(game.world.cols):
                    if not near_field(game,x,y) or field.contains_plot(x,y):
                        continue
                    cell = game.world.get_cell(x,y)
                    for obj in [cell, *cell.extra_objects]:
                        species = resolve_species(obj.feature.name, getattr(obj,"crop_kind",None))
                        key = ("tree:" + resolve_tree(getattr(obj,"tree_species",None)).key
                               if obj.feature == FeatureType.TREE else
                               "plant:" + species.key if species is not None else None)
                        if key and key not in self.state.inspected_species and len(self.state.inspected_species) < 4:
                            self.state.inspected_species.append(key)
                            self._reveal_clearing(game,(x,y),2)
        if stage >= 2:
            self.state.quest_cells["crop"] = [list(cell) for cell in cells[:2]]
        if stage >= 3:
            self.state.quest_cells["traffic"] = [list(cell) for cell in cells[:4]]
        if stage >= 4:
            self.state.quest_cells["soil"] = [list(cell) for cell in cells[:4]]
        self.state.discovered_flora = [key.replace("plant:", "wild:", 1) for key in self.state.inspected_species]
        game._select_building(field, show_player=True, detail_only=True)
        panel = game.field_plan_dialog
        panel.handbook_stage = stage
        panel.rotation_unlocked = "handbook_5:read" in self.state.quest_checks
        panel.tab = checkpoint.get("planner_tab", "handbook" if stage == 0 else "status")
        if panel.tab == "rotation" and not panel.rotation_unlocked:
            panel.tab = "handbook"
        self.quest_navigation.focused(self.objectives())
