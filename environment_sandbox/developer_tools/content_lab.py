"""Disposable recipe test harness built on the production simulation objects."""

from __future__ import annotations

from dataclasses import dataclass

from entities import (
    Building,
    BuildingKind,
    Villager,
    WORKPLACE_TOOL,
    apply_building_storage,
    default_building_plot,
)
from recipes import Recipe, recipe_ready
from society import SkillState, recipe_skill_gate


WORKSTATION_KINDS = {
    "mill": BuildingKind.MILL,
    "kitchen": BuildingKind.KITCHEN,
    "craft_bench": BuildingKind.CRAFT_BENCH,
    "alchemist": BuildingKind.ALCHEMIST,
    "tailor": BuildingKind.TAILOR,
    "cobbler": BuildingKind.COBBLER,
    "forester": BuildingKind.FORESTER,
    "forester_plant": BuildingKind.FORESTER,
    "forester_split": BuildingKind.FORESTER,
    "hunter": BuildingKind.HUNTER,
    "forager": BuildingKind.FORAGER,
    "fisher": BuildingKind.FISHER,
    "barn": BuildingKind.BARN,
    "compost_heap": BuildingKind.COMPOST_HEAP,
    "drying_rack": BuildingKind.DRYING_RACK,
}


@dataclass(frozen=True)
class LabRecipe:
    workstation: str
    recipe: Recipe


@dataclass(frozen=True)
class LabDiagnostics:
    recipe: str | None
    workstation: str | None
    building_id: int | None
    worker_id: int | None
    inputs_ready: bool
    skill_ready: bool
    progress: int
    status: str


def recipe_catalogue() -> list[LabRecipe]:
    """Return the currently loaded registry, including post-reload changes."""
    import recipes

    return [
        LabRecipe(folder, recipe)
        for folder, attr in recipes._BUILDING_RECIPE_ATTR.items()
        for recipe in getattr(recipes, attr)
    ]


class ContentLabSession:
    """Own disposable scenario objects while the normal game loop performs work."""

    def __init__(self, game):
        self.game = game
        self.selected: LabRecipe | None = None
        self.building: Building | None = None
        self.worker: Villager | None = None

    def start(self) -> None:
        self.game._open_subtile_test()
        self.game._content_lab_active = True
        self.game._content_lab_session = self
        catalogue = recipe_catalogue()
        if catalogue:
            self.selected = catalogue[0]

    def reset(self) -> None:
        self.start()

    def leave(self) -> None:
        self.game._content_lab_active = False
        self.game._content_lab_session = None
        self.game.developer_tools = None
        self.game._launch_menu = "developer_tools"

    def select_recipe(self, name: str, workstation: str | None = None) -> LabRecipe:
        matches = [item for item in recipe_catalogue() if item.recipe.name == name and (workstation is None or item.workstation == workstation)]
        if not matches:
            raise KeyError(f"Unknown loaded recipe: {name}")
        self.selected = matches[0]
        self.building = None
        self.worker = None
        return self.selected

    def create_workstation(self) -> Building:
        if self.selected is None:
            raise ValueError("Select a recipe first")
        kind = WORKSTATION_KINDS[self.selected.workstation]
        next_id = max(self.game.buildings, default=0) + 1
        anchor = next(iter(self.game.buildings.values()), None)
        x, y = ((anchor.x + 5, anchor.y) if anchor else (4, 4))
        width, height = default_building_plot(kind)
        building = Building(next_id, kind, x, y, plot_w=width, plot_h=height)
        apply_building_storage(building)
        self.game.buildings[building.id] = building
        self.building = building
        return building

    def supply_inputs(self) -> None:
        if self.selected is None or self.building is None:
            raise ValueError("Create the selected recipe's workstation first")
        for key, amount in self.selected.recipe.inputs.items():
            have = self.building.recipe_storage_amount(key)
            if have < amount:
                self.building.add_recipe_output(key, amount - have)

    def spawn_worker(self) -> Villager:
        if self.selected is None or self.building is None:
            raise ValueError("Create the selected recipe's workstation first")
        next_id = max((v.id for v in self.game.villagers), default=0) + 1
        worker = Villager(next_id, self.building.x, self.building.y, name="Content Lab Worker")
        for skill, required in self.selected.recipe.skill_reqs:
            level = max(1, int(required))
            worker.skills[skill] = SkillState(level=level, potential=max(5, level), peak=level)
        tool = WORKPLACE_TOOL.get(self.building.kind)
        if tool:
            worker.inventory.add_item(tool)
            worker.inventory.equip_tool(tool)
        self.game.villagers.append(worker)
        self.game._set_primary_workplace(worker, self.building.id)
        worker.craft_recipe_name = self.selected.recipe.name
        self.worker = worker
        return worker

    def prepare(self) -> LabDiagnostics:
        if self.building is None:
            self.create_workstation()
        self.supply_inputs()
        if self.worker is None:
            self.spawn_worker()
        return self.diagnostics()

    def diagnostics(self) -> LabDiagnostics:
        if self.selected is None:
            return LabDiagnostics(None, None, None, None, False, False, 0, "Select a recipe")
        inputs_ready = bool(self.building and recipe_ready(self.building, self.selected.recipe))
        skill_ready = bool(self.worker and recipe_skill_gate(self.selected.recipe, worker=self.worker))
        progress = int(self.building.recipe_progress.get(self.selected.recipe.name, 0)) if self.building else 0
        if not self.building:
            status = "Create workstation"
        elif not inputs_ready:
            status = "Supply inputs"
        elif not self.worker:
            status = "Spawn worker"
        elif not skill_ready:
            status = "Worker skill gate blocked"
        else:
            status = "Ready — running through normal simulation"
        return LabDiagnostics(self.selected.recipe.name, self.selected.workstation, getattr(self.building, "id", None), getattr(self.worker, "id", None), inputs_ready, skill_ready, progress, status)

    def handle_event(self, event) -> bool:
        """Compact lab controls; all simulation events not consumed continue normally."""
        import pygame

        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_ESCAPE:
            self.leave(); return True
        catalogue = recipe_catalogue()
        if event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET) and catalogue:
            try: index = next(i for i, item in enumerate(catalogue) if self.selected and item.workstation == self.selected.workstation and item.recipe.name == self.selected.recipe.name)
            except StopIteration: index = 0
            index = (index + (-1 if event.key == pygame.K_LEFTBRACKET else 1)) % len(catalogue)
            self.selected = catalogue[index]; self.building = self.worker = None; return True
        if event.key == pygame.K_p:
            self.prepare(); return True
        if event.key == pygame.K_r:
            self.reset(); return True
        return False

    def draw(self, surface) -> None:
        import pygame

        diag = self.diagnostics()
        panel = pygame.Rect(12, 92, 500, 116)
        pygame.draw.rect(surface, (24, 31, 35), panel, border_radius=6)
        pygame.draw.rect(surface, (108, 132, 120), panel, 1, border_radius=6)
        title = pygame.font.SysFont("menlo", 16, bold=True)
        body = pygame.font.SysFont("menlo", 12)
        surface.blit(title.render("CONTENT LAB — disposable, saving disabled", True, (235, 235, 225)), (panel.x + 12, panel.y + 9))
        recipe = f"{diag.workstation or '—'} / {diag.recipe or '—'}"
        surface.blit(body.render(recipe, True, (205, 215, 205)), (panel.x + 12, panel.y + 38))
        surface.blit(body.render(diag.status, True, (135, 195, 145)), (panel.x + 12, panel.y + 59))
        surface.blit(body.render("[ / ] recipe   P prepare & run   R reset   Esc return", True, (165, 170, 170)), (panel.x + 12, panel.y + 87))
