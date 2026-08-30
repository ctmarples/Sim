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
from resources import RESOURCE_KEYS, resource_label
from .widgets import Dropdown, FloatField, IntegerField


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
        self.recipe_dropdown = Dropdown(__import__("pygame").Rect(0, 0, 1, 1), [])
        self.resource_dropdown = Dropdown(__import__("pygame").Rect(0, 0, 1, 1), [(k, resource_label(k)) for k in RESOURCE_KEYS])
        self.resource_qty = IntegerField(__import__("pygame").Rect(0, 0, 1, 1), "10", minimum=1)
        self.skill_fields = {skill.name.lower(): IntegerField(__import__("pygame").Rect(0, 0, 1, 1), "1", minimum=1, maximum=10) for skill in __import__("society").SKILL_ORDER}
        self._buttons = []
        self.message = "Choose a recipe, then set up the scenario."
        self.species_key: str | None = None
        self.crop_key: str | None = None
        self.tree_key: str | None = None
        self.environment_fields = {name:FloatField(__import__("pygame").Rect(0,0,1,1),"0.5",minimum=0,maximum=1) for name in ("moisture","temperature","fertility","rainfall","disturbance")}

    def _refresh_recipe_dropdown(self) -> None:
        catalogue = recipe_catalogue()
        self.recipe_dropdown.options = [((item.workstation, item.recipe.name), f"{item.workstation}: {item.recipe.name.replace('_', ' ').title()}") for item in catalogue]
        if self.selected:
            self.recipe_dropdown.value = (self.selected.workstation, self.selected.recipe.name)

    def start(self) -> None:
        self.game._open_subtile_test()
        self.game._content_lab_active = True
        self.game._content_lab_session = self
        catalogue = recipe_catalogue()
        if catalogue:
            self.selected = catalogue[0]
        self._refresh_recipe_dropdown()

    def reset(self) -> None:
        self.start()

    def leave(self) -> None:
        self.game._content_lab_active = False
        self.game._content_lab_session = None
        self.game.developer_tools = None
        self.game._launch_menu = "developer_tools"

    def select_recipe(self, name: str, workstation: str | None = None) -> LabRecipe:
        self.species_key=None
        matches = [item for item in recipe_catalogue() if item.recipe.name == name and (workstation is None or item.workstation == workstation)]
        if not matches:
            raise KeyError(f"Unknown loaded recipe: {name}")
        self.selected = matches[0]
        self.building = None
        self.worker = None
        self._refresh_recipe_dropdown()
        return self.selected

    def select_species(self,key: str):
        from wild_species import WILD_BY_KEY
        if key not in WILD_BY_KEY:raise KeyError(f"Unknown loaded wild species: {key}")
        self.crop_key=None;self.tree_key=None;self.species_key=key;self.message=f"Wild Species test selected: {WILD_BY_KEY[key].label}."
        return WILD_BY_KEY[key]

    def select_crop(self,key: str):
        from crops import CROP_BY_KEY
        if key not in CROP_BY_KEY:raise KeyError(f"Unknown loaded farm crop: {key}")
        self.species_key=None;self.tree_key=None;self.crop_key=key;self.message=f"Farm Crop test selected: {CROP_BY_KEY[key].label}."
        return CROP_BY_KEY[key]

    def select_plant(self,key: str):
        import crops,wild_species,trees
        if key in crops.CROP_BY_KEY:return self.select_crop(key)
        if key in wild_species.WILD_BY_KEY:return self.select_species(key)
        if key in trees.TREE_BY_KEY:
            self.species_key=None;self.crop_key=None;self.tree_key=key;self.message=f"Tree test selected: {trees.TREE_BY_KEY[key].label}.";return trees.TREE_BY_KEY[key]
        raise KeyError(f"Unknown loaded plant: {key}")

    def spawn_crop(self):
        from world import FeatureType,TerrainType
        for y,row in enumerate(self.game.world.cells):
            for x,cell in enumerate(row):
                if cell.terrain in (TerrainType.GRASS,TerrainType.MEADOW,TerrainType.SOIL) and cell.feature==FeatureType.NONE:
                    cell.feature=FeatureType.CROP_HERB;cell.crop_kind=self.crop_key;cell.growth_ticks=0;cell.object_anchor_slot=4
                    self.message=f"Spawned ripe {self.crop_key} at {x}, {y} through the normal farm-crop renderer.";return cell
        self.message=f"No empty test-map placement found for {self.crop_key}.";return None

    def spawn_tree(self):
        from world import FeatureType,TerrainType
        for y,row in enumerate(self.game.world.cells):
            for x,cell in enumerate(row):
                if cell.terrain in (TerrainType.GRASS,TerrainType.MEADOW,TerrainType.FOREST_FLOOR) and cell.feature==FeatureType.NONE:
                    cell.feature=FeatureType.TREE;cell.tree_species=self.tree_key;cell.tree_age_years=8;cell.object_anchor_slot=4;self.message=f"Spawned mature {self.tree_key} at {x}, {y}.";return cell
        self.message=f"No empty test-map placement found for {self.tree_key}.";return None

    def species_suitability(self):
        from wild_species import WILD_BY_KEY,species_environment_suitability
        if not self.species_key:return None
        values={name:field.parse() for name,field in self.environment_fields.items()}
        if any(v is None for v in values.values()):return None
        return species_environment_suitability(WILD_BY_KEY[self.species_key],temperature=values["temperature"],rainfall=values["rainfall"],soil_moisture=values["moisture"],fertility=values["fertility"],disturbance=values["disturbance"])

    def spawn_species(self):
        from wild_species import WILD_BY_KEY
        from world import FeatureType
        species=WILD_BY_KEY[self.species_key]
        feature=FeatureType[species.feature]
        crop_kind=species.crop_key or species.key
        for y,row in enumerate(self.game.world.cells):
            for x,cell in enumerate(row):
                if not species.terrains or cell.terrain.name in species.terrains:
                    obj=self.game.world.add_natural_object(x,y,feature,crop_kind=crop_kind,deposit=max(1,species.yield_amount))
                    if obj is not None:
                        self.message=f"Spawned {species.label} at {x}, {y} through the normal World placement path.";return obj
        self.message=f"No legal test-map placement found for {species.label}.";return None

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

    def add_resource(self) -> None:
        if self.building is None:
            self.create_workstation()
        amount = self.resource_qty.parse()
        if self.resource_dropdown.value and amount:
            self.building.add_recipe_output(self.resource_dropdown.value, int(amount))
            self.message = f"Added {int(amount)} {resource_label(self.resource_dropdown.value)} to workstation storage."

    def apply_skill_preset(self, preset: str) -> None:
        if self.building is None: self.create_workstation()
        if self.worker is None: self.spawn_worker()
        from society import SKILL_ORDER
        required = {skill.name.lower(): int(level) for skill, level in (self.selected.recipe.skill_reqs if self.selected else ())}
        for skill in SKILL_ORDER:
            key = skill.name.lower()
            level = required.get(key, 1) if preset == "qualified" else (10 if preset == "all_10" else 1)
            self.skill_fields[key].text = str(level)
        self.apply_skills()

    def apply_skills(self) -> None:
        if self.worker is None: return
        from society import SKILL_ORDER
        for skill in SKILL_ORDER:
            value = self.skill_fields[skill.name.lower()].parse()
            if value is not None:
                self.worker.skills[skill] = SkillState(level=int(value), potential=max(5, int(value)), peak=int(value))
        self.message = "Worker skills applied."

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

        if self.species_key or self.crop_key or self.tree_key:
            for control in self.environment_fields.values():
                if control.handle_event(event):return True
            if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
                action=next((a for rect,a in self._buttons if rect.collidepoint(event.pos)),None)
                if action=="spawn_species":self.spawn_species();return True
                if action=="spawn_crop":self.spawn_crop();return True
                if action=="spawn_tree":self.spawn_tree();return True
                if action=="back":self.leave();return True
            if event.type==pygame.KEYDOWN and event.key==pygame.K_ESCAPE:self.leave();return True
            return False
        old_recipe = self.recipe_dropdown.value
        if self.recipe_dropdown.handle_event(event):
            if self.recipe_dropdown.value != old_recipe and self.recipe_dropdown.value:
                workstation, name = self.recipe_dropdown.value; self.select_recipe(name, workstation)
            return True
        for control in (self.resource_dropdown, self.resource_qty, *self.skill_fields.values()):
            if control.handle_event(event): return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = next((a for rect, a in self._buttons if rect.collidepoint(event.pos)), None)
            if action is None:
                return False
            if action == "setup": self.prepare(); self.game.sim_speed = 0; self.message = "Recipe test prepared and paused. Press a simulation speed to run."
            elif action == "workstation": self.create_workstation(); self.message = "Workstation created."
            elif action == "worker":
                if self.building is None: self.create_workstation()
                self.spawn_worker(); self.apply_skill_preset("qualified"); self.message = "Qualified worker spawned."
            elif action == "inputs": self.supply_inputs(); self.message = "Recipe inputs supplied."
            elif action == "add_resource": self.add_resource()
            elif action in ("qualified", "all_10", "all_1"): self.apply_skill_preset(action)
            elif action == "apply_skills": self.apply_skills()
            elif action.startswith("speed_"): self.game.sim_speed = int(action.split("_", 1)[1]); self.message = f"Simulation speed set to {self.game.sim_speed}x."
            elif action == "reset": self.reset(); self.game.sim_speed = 0; self.message = "Lab reset."
            elif action == "back": self.leave()
            return True
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

        if self.species_key:return self._draw_species(surface)
        if self.crop_key:return self._draw_crop(surface)
        if self.tree_key:return self._draw_tree(surface)
        diag = self.diagnostics()
        panel = pygame.Rect(12, 92, 570, 650)
        pygame.draw.rect(surface, (24, 31, 35), panel, border_radius=6)
        pygame.draw.rect(surface, (108, 132, 120), panel, 1, border_radius=6)
        title = pygame.font.SysFont("menlo", 16, bold=True)
        body = pygame.font.SysFont("menlo", 12)
        surface.blit(title.render("CONTENT LAB — disposable, saving disabled", True, (235, 235, 225)), (panel.x + 12, panel.y + 9))
        self._buttons = []
        def button(x, y, w, label, action):
            rect = pygame.Rect(x, y, w, 27); self._buttons.append((rect, action)); pygame.draw.rect(surface, (58, 70, 70), rect, border_radius=3); pygame.draw.rect(surface, (108, 132, 120), rect, 1, border_radius=3); text=body.render(label, True, (230,235,228)); surface.blit(text,(rect.centerx-text.get_width()//2,rect.centery-text.get_height()//2))
        y = panel.y + 42
        surface.blit(body.render("Selected recipe", True, (165,170,170)), (panel.x+12,y+6)); self.recipe_dropdown.rect=pygame.Rect(panel.x+135,y,410,28); self.recipe_dropdown.draw(surface,body); y+=38
        button(panel.x+12,y,170,"Setup Selected Recipe","setup"); button(panel.x+190,y,112,"Workstation","workstation"); button(panel.x+310,y,105,"Worker","worker"); button(panel.x+423,y,122,"Supply Inputs","inputs"); y+=40
        surface.blit(body.render("Inventory injection", True, (150,190,165)), (panel.x+12,y)); y+=23
        self.resource_dropdown.rect=pygame.Rect(panel.x+12,y,250,27);self.resource_dropdown.draw(surface,body);self.resource_qty.rect=pygame.Rect(panel.x+270,y,70,27);self.resource_qty.draw(surface,body);button(panel.x+348,y,90,"Add","add_resource");y+=40
        surface.blit(body.render("Worker skill presets", True, (150,190,165)), (panel.x+12,y));y+=22
        button(panel.x+12,y,150,"Qualified","qualified");button(panel.x+170,y,100,"All 10","all_10");button(panel.x+278,y,100,"All 1","all_1");y+=36
        for i,(key,field) in enumerate(self.skill_fields.items()):
            col=i%2;row=i//2;xx=panel.x+12+col*210;yy=y+row*31;surface.blit(body.render(key.title(),True,(205,215,205)),(xx,yy+5));field.rect=pygame.Rect(xx+105,yy,62,25);field.draw(surface,body)
        y+=96;button(panel.x+12,y,130,"Apply Skills","apply_skills");y+=39
        surface.blit(body.render("Simulation",True,(150,190,165)),(panel.x+12,y+5))
        for i,speed in enumerate((0,1,5,20)):button(panel.x+115+i*72,y,65,"Pause" if speed==0 else f"{speed}x",f"speed_{speed}")
        y+=42
        surface.blit(body.render("RECIPE STATUS",True,(150,190,165)),(panel.x+12,y));y+=23
        lines=(f"Workstation  {'✓ '+str(diag.workstation) if diag.building_id else '✕ missing'}",f"Worker       {'✓ #'+str(diag.worker_id) if diag.worker_id else '✕ missing'}",f"Inputs       {'✓' if diag.inputs_ready else '✕'}",f"Skills       {'✓' if diag.skill_ready else '✕'}",f"Progress     {diag.progress}",f"State: {diag.status}")
        for line in lines:surface.blit(body.render(line,True,(135,195,145) if '✕' not in line else (225,115,100)),(panel.x+20,y));y+=19
        surface.blit(body.render(self.message,True,(190,195,190)),(panel.x+12,panel.bottom-65))
        button(panel.x+12,panel.bottom-37,105,"Reset Lab","reset");button(panel.x+125,panel.bottom-37,190,"Back to Developer Tools","back")
        # Draw open dropdowns last so their popup menus remain above the panel.
        if self.resource_dropdown.open:self.resource_dropdown.draw(surface,body)
        if self.recipe_dropdown.open:self.recipe_dropdown.draw(surface,body)

    def _draw_species(self,surface):
        import pygame
        from wild_species import WILD_BY_KEY
        species=WILD_BY_KEY[self.species_key];score=self.species_suitability()
        panel=pygame.Rect(12,92,570,470);pygame.draw.rect(surface,(24,31,35),panel,border_radius=6);pygame.draw.rect(surface,(108,132,120),panel,1,border_radius=6)
        title=pygame.font.SysFont("menlo",16,bold=True);body=pygame.font.SysFont("menlo",12);surface.blit(title.render(f"CONTENT LAB — WILD SPECIES: {species.label}",True,(235,235,225)),(panel.x+12,panel.y+10));self._buttons=[]
        def button(x,y,w,label,action):
            rect=pygame.Rect(x,y,w,27);self._buttons.append((rect,action));pygame.draw.rect(surface,(58,70,70),rect,border_radius=3);pygame.draw.rect(surface,(108,132,120),rect,1,border_radius=3);text=body.render(label,True,(230,235,228));surface.blit(text,(rect.centerx-text.get_width()//2,rect.centery-text.get_height()//2))
        y=panel.y+52
        for name,field in self.environment_fields.items():
            surface.blit(body.render(name.title(),True,(180,190,185)),(panel.x+18,y+5));field.rect=pygame.Rect(panel.x+145,y,90,26);field.draw(surface,body);value=getattr(score,"moisture" if name=="moisture" else name,0) if score else 0;surface.blit(body.render(f"response {value:.3f}",True,(145,195,150)),(panel.x+250,y+5));y+=34
        combined=score.combined if score else 0;surface.blit(title.render(f"Combined niche suitability: {combined:.3f}",True,(145,205,155)),(panel.x+18,y+8));y+=48
        button(panel.x+18,y,150,"Spawn Species","spawn_species");button(panel.x+178,y,190,"Back to Developer Tools","back")
        surface.blit(body.render(self.message,True,(190,195,190)),(panel.x+18,panel.bottom-42))

    def _draw_crop(self,surface):
        import pygame
        from crops import CROP_BY_KEY,PHASE_LABELS
        from seasons import Season
        crop=CROP_BY_KEY[self.crop_key];panel=pygame.Rect(12,92,570,390);pygame.draw.rect(surface,(24,31,35),panel,border_radius=6);pygame.draw.rect(surface,(108,132,120),panel,1,border_radius=6)
        title=pygame.font.SysFont("menlo",16,bold=True);body=pygame.font.SysFont("menlo",12);surface.blit(title.render(f"CONTENT LAB — FARM CROP: {crop.label}",True,(235,235,225)),(panel.x+12,panel.y+10));self._buttons=[]
        def button(x,y,w,label,action):
            rect=pygame.Rect(x,y,w,27);self._buttons.append((rect,action));pygame.draw.rect(surface,(58,70,70),rect,border_radius=3);pygame.draw.rect(surface,(108,132,120),rect,1,border_radius=3);text=body.render(label,True,(230,235,228));surface.blit(text,(rect.centerx-text.get_width()//2,rect.centery-text.get_height()//2))
        y=panel.y+55
        for index,season in enumerate(Season):
            phase=crop.year_phases[index];harvest=" · harvest" if season in crop.harvest_seasons else ""
            surface.blit(body.render(f"{season.name.title():8} {PHASE_LABELS[phase]}{harvest}",True,(185,205,190)),(panel.x+20,y));y+=27
        surface.blit(body.render(f"Plant: {crop.plant_season.name.title()}   Growth: {crop.growth_days} days   Seeds: {crop.farm_seed_amounts}",True,(185,190,185)),(panel.x+20,y+8));y+=48
        button(panel.x+18,y,150,"Spawn Ripe Crop","spawn_crop");button(panel.x+178,y,190,"Back to Developer Tools","back")
        surface.blit(body.render(self.message,True,(190,195,190)),(panel.x+18,panel.bottom-42))

    def _draw_tree(self,surface):
        import pygame
        from trees import TREE_BY_KEY
        tree=TREE_BY_KEY[self.tree_key];panel=pygame.Rect(12,92,570,280);pygame.draw.rect(surface,(24,31,35),panel,border_radius=6);pygame.draw.rect(surface,(108,132,120),panel,1,border_radius=6);title=pygame.font.SysFont("menlo",16,bold=True);body=pygame.font.SysFont("menlo",12);surface.blit(title.render(f"CONTENT LAB — TREE: {tree.label}",True,(235,235,225)),(panel.x+12,panel.y+10));self._buttons=[]
        def button(x,y,w,label,action):
            rect=pygame.Rect(x,y,w,27);self._buttons.append((rect,action));pygame.draw.rect(surface,(58,70,70),rect,border_radius=3);pygame.draw.rect(surface,(108,132,120),rect,1,border_radius=3);text=body.render(label,True,(230,235,228));surface.blit(text,(rect.centerx-text.get_width()//2,rect.centery-text.get_height()//2))
        surface.blit(body.render(f"Growth {tree.growth_years} years · yield {tree.yield_amount} {tree.yield_key} · {tree.shape}",True,(185,205,190)),(panel.x+20,panel.y+62));button(panel.x+18,panel.y+105,150,"Spawn Mature Tree","spawn_tree");button(panel.x+178,panel.y+105,190,"Back to Developer Tools","back");surface.blit(body.render(self.message,True,(190,195,190)),(panel.x+18,panel.bottom-42))
