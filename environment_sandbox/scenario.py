"""Persistent, data-friendly scenario runtime and the first player tutorial."""

from __future__ import annotations

from dataclasses import dataclass


TUTORIAL_KEY = "tutorial_slice"


@dataclass
class ScenarioState:
    key: str | None = None
    step: str = "inactive"
    completed: bool = False
    starting_berries: int = 0


class ScenarioDirector:
    """Advance narrative steps from observable game state.

    This deliberately owns no pygame UI. Later scenario files can map the same
    step/condition/action vocabulary onto this runtime.
    """

    def __init__(self) -> None:
        self.state = ScenarioState()
        self.prompt: str | None = None
        self._dialog_request: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.state.key and not self.state.completed)

    def configure_after_load(self, game, save_stem: str, *, restored: bool) -> None:
        if restored:
            self._restore_presentation()
            return
        if save_stem == TUTORIAL_KEY:
            self.start_tutorial(game)
        else:
            self.state = ScenarioState()
            self.prompt = None
            self._dialog_request = None

    def start_tutorial(self, game) -> None:
        from settings import MAP_DISCOVERY_RADIUS
        from world import FeatureType

        self.state = ScenarioState(key=TUTORIAL_KEY,step="hunger_dialog",starting_berries=1)
        game.player.inventory.berries = 1
        # Keep the initial view useful, but ensure its food lesson requires
        # exploration rather than exposing a bush beside the player.
        px,py=int(game.player.x),int(game.player.y)
        radius=max(0,int(MAP_DISCOVERY_RADIUS))
        for y in range(max(0,py-radius),min(game.world.rows,py+radius+1)):
            for x in range(max(0,px-radius),min(game.world.cols,px+radius+1)):
                if (x-px)**2+(y-py)**2>radius*radius:continue
                cell=game.world.get_cell(x,y)
                if cell is not None and cell.feature==FeatureType.BERRY_BUSH:
                    cell.feature=FeatureType.NONE;cell.crop_kind=None
                    cell.deposit=0;cell.growth_ticks=0
        game.discovered_cells=set()
        game._reveal_around_player()
        if hasattr(game,"_invalidate_forage_index"):
            game._invalidate_forage_index()
        self.prompt = None
        self._dialog_request = "(Stomach rumble) ... uhhh I'm getting hungry, I need to eat. I'll check what is in my bag"

    def take_dialog_request(self) -> str | None:
        text = self._dialog_request
        self._dialog_request = None
        return text

    def dismiss_dialog(self) -> None:
        step=self.state.step
        if step=="hunger_dialog":
            self.state.step="open_inventory";self.prompt="Press I to open inventory"
        elif step=="last_berry_dialog":
            self.state.step="find_food";self.prompt="Look around for some more food"
        elif step=="found_berries_dialog":
            self.state.step="complete";self.state.completed=True;self.prompt=None

    def update(self, game) -> None:
        if not self.active:return
        step=self.state.step
        if step=="open_inventory" and game.player_inventory.open:
            self.state.step="eat_berries";self.prompt="Right click on the berries to eat."
        elif step=="eat_berries" and int(game.player.inventory.berries)<=0:
            self.state.step="last_berry_dialog";self.prompt=None
            self._dialog_request="Well that was the last of the berries. I should look for some more"
        elif step=="find_food" and self._discovered_fruiting_bush(game):
            self.state.step="found_berries_dialog";self.prompt=None
            self._dialog_request="Hey some more! So that's where they come from!"

    @staticmethod
    def _discovered_fruiting_bush(game) -> bool:
        from world import FeatureType
        for x,y in game.discovered_cells:
            cell=game.world.get_cell(x,y)
            if cell is not None and cell.feature==FeatureType.BERRY_BUSH and cell.deposit>0:
                return True
        return False

    def to_dict(self) -> dict:
        return {"key":self.state.key,"step":self.state.step,"completed":self.state.completed,
                "starting_berries":self.state.starting_berries}

    def load_dict(self, data: object) -> None:
        if not isinstance(data,dict):
            self.state=ScenarioState();self.prompt=None;self._dialog_request=None;return
        self.state=ScenarioState(key=data.get("key"),step=str(data.get("step","inactive")),
                                 completed=bool(data.get("completed",False)),
                                 starting_berries=int(data.get("starting_berries",0)))
        self._restore_presentation()

    def _restore_presentation(self) -> None:
        self._dialog_request=None
        prompts={"open_inventory":"Press I to open inventory",
                 "eat_berries":"Right click on the berries to eat.",
                 "find_food":"Look around for some more food"}
        dialogs={"hunger_dialog":"(Stomach rumble) ... uhhh I'm getting hungry, I need to eat. I'll check what is in my bag",
                 "last_berry_dialog":"Well that was the last of the berries. I should look for some more",
                 "found_berries_dialog":"Hey some more! So that's where they come from!"}
        self.prompt=prompts.get(self.state.step)
        self._dialog_request=dialogs.get(self.state.step)
