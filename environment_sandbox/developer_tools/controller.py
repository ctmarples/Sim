"""Developer Tools launcher and interactive content-authoring pages."""

from __future__ import annotations

from pathlib import Path

import pygame

from settings import COLOUR_MENU_BG, COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_HOVER, WINDOW_HEIGHT, WINDOW_WIDTH
from resources import RESOURCE_KEYS
from .content_io import get_content_root, is_writable_source_tree
from .reload import load_recipe_catalogue_from_disk, load_traveller_templates_from_disk, refresh_icons, reload_recipes, reload_traveller_templates
from .validation import ValidationReport, ValidationSeverity, validate_all, validate_icons, validate_recipe_catalogue, validate_traveller_catalogue
from .widgets import ScrollableList, ValidationSummary
from .editors import RecipeEditorService, TravellerEditorService
from .icons_browser import IconBrowserService
from .resources_browser import ResourceEditorService, resource_entries
from .wild_species_editor import WildSpeciesEditorService
from .crop_editor import CropEditorService
from .authoring_ui import CropAuthoringPage, IconImportPage, RecipeAuthoringPage, ResourceAuthoringPage, TravellerAuthoringPage, WildSpeciesAuthoringPage


class DeveloperToolsController:
    def __init__(self) -> None:
        self.page = "home"
        self.report = ValidationReport()
        self.message = ""
        self.write_enabled = is_writable_source_tree()
        self.recipe_revision = 0
        self.traveller_revision = 0
        self.icon_revision = 0
        self.items = ScrollableList[str](pygame.Rect(0, 0, 1, 1))
        self.summary = ValidationSummary(pygame.Rect(0, 0, 1, 1))
        self._buttons: list[tuple[pygame.Rect, str, str, bool]] = []
        self.font = pygame.font.SysFont("menlo", 14)
        self.small = pygame.font.SysFont("menlo", 12)
        self.title_font = pygame.font.SysFont("menlo", 25, bold=True)
        self.recipe_editor = RecipeEditorService()
        self.traveller_editor = TravellerEditorService()
        self.icon_browser = IconBrowserService()
        self.recipe_page = RecipeAuthoringPage(self.recipe_editor, self.icon_browser)
        self.traveller_page = TravellerAuthoringPage(self.traveller_editor)
        self.icon_page = IconImportPage(self.icon_browser)
        self.resource_editor = ResourceEditorService()
        self.resource_page = ResourceAuthoringPage(self.resource_editor, self.icon_browser, self._resources_saved)
        self.wild_species_editor = WildSpeciesEditorService()
        self.crop_editor = CropEditorService()
        self.wild_object_page = WildSpeciesAuthoringPage(self.wild_species_editor, self.icon_browser)
        self.crop_object_page = CropAuthoringPage(self.crop_editor, self.icon_browser)
        self.object_page = self.wild_object_page
        self.pending_lab_recipe: tuple[str, str] | None = None
        self.pending_lab_species: str | None = None
        self.refresh_page()

    def _resources_saved(self) -> None:
        import resources
        from . import authoring_ui
        authoring_ui.RESOURCE_KEYS = resources.RESOURCE_KEYS
        self.recipe_page = RecipeAuthoringPage(self.recipe_editor, self.icon_browser)
        self.traveller_page = TravellerAuthoringPage(self.traveller_editor)

    def refresh_page(self) -> None:
        if self.page == "recipes":
            self.items.set_items(self.recipe_editor.records)
        elif self.page == "travellers":
            self.items.set_items(self.traveller_editor.records)
        elif self.page == "icons":
            self.items.set_items(self.icon_browser.entries())
        elif self.page == "resources":
            self.items.set_items(resource_entries())
        elif self.page == "objects":
            if self.object_page is self.wild_object_page:self.wild_species_editor.load()
            else:self.crop_editor.load()
            self.object_page.refresh()

    def _panel(self) -> pygame.Rect:
        return pygame.Rect(15, 15, WINDOW_WIDTH - 30, WINDOW_HEIGHT - 30)

    def _layout_buttons(self, panel: pygame.Rect) -> None:
        self._buttons = []
        def add(y: int, action: str, label: str, enabled: bool = True, x: int | None = None, w: int = 230):
            self._buttons.append((pygame.Rect(x if x is not None else panel.x + 40, y, w, 36), action, label, enabled))
        if self.page == "home":
            y = panel.y + 175
            for action, label in (("recipes", "Recipes"), ("travellers", "Travellers"), ("icons", "Icons"), ("resources", "Resources"), ("objects", "Map Objects"), ("content_lab", "Content Lab")):
                add(y, action, label); y += 46
            add(y + 4, "validate_all", "Validate All")
            add(panel.bottom - 55, "launcher", "Back")
        elif self.page in ("recipes", "travellers", "icons", "resources", "objects"):
            add(panel.y + 27, "home", "Back", x=panel.right - 150, w=110)
        else:
            add(panel.y + 105, f"reload_{self.page}", "Refresh Icons" if self.page == "icons" else f"Reload {self.page.title()}", self.page != "resources")
            add(panel.y + 105, f"validate_{self.page}", f"Validate {self.page.title()}", self.page != "resources", x=panel.x + 285)
            add(panel.bottom - 55, "home", "Back")

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if self.page == "recipes":
            consumed, result = self.recipe_page.handle_event(event)
            if result and result[0] == "save_test":
                self.pending_lab_recipe = (result[1], result[2])
                return "content_lab"
            if consumed:
                self.message = self.recipe_page.message
                return None
        elif self.page == "travellers" and self.traveller_page.handle_event(event):
            self.message = self.traveller_page.message; return None
        elif self.page == "icons" and self.icon_page.handle_event(event):
            self.message = self.icon_page.message; return None
        elif self.page == "resources" and self.resource_page.handle_event(event):
            self.message = self.resource_page.message; return None
        elif self.page == "objects":
            consumed,result=self.object_page.handle_event(event)
            if result and result[0]=="test_species":self.pending_lab_species=result[1];return "content_lab"
            if result and result[0]=="test_crop":self.pending_lab_species=("crop",result[1]);return "content_lab"
            if result and result[0]=="show_crops":self.object_page=self.crop_object_page;self.object_page.refresh();return None
            if result and result[0]=="show_wild":self.object_page=self.wild_object_page;self.object_page.refresh();return None
            if consumed:self.message=self.object_page.message;return None
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.page == "home":
                return "launcher"
            self.page = "home"; self.refresh_page(); return None
        old_selection = self.items.selected_index
        if self.summary.handle_event(event) or self.items.handle_event(event):
            if self.items.selected_index != old_selection and self.items.selected is not None:
                if self.page == "recipes": self.recipe_editor.select(self.items.selected)
                elif self.page == "travellers": self.traveller_editor.select(self.items.selected)
            return None
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        action = next((action for rect, action, _label, enabled in self._buttons if enabled and rect.collidepoint(event.pos)), None)
        if action in ("recipes", "travellers", "icons", "resources", "objects", "home"):
            self.page = action; self.refresh_page(); return None
        if action == "content_lab":
            return "content_lab"
        if action == "launcher":
            return "launcher"
        if action == "validate_all":
            self.report = validate_all(); self.summary.set_report(self.report); self.message = "Validation complete."
        elif action == "validate_recipes":
            self.report = validate_recipe_catalogue(); self.summary.set_report(self.report); self.message = "Recipe validation complete."
        elif action == "validate_travellers":
            self.report = validate_traveller_catalogue(); self.summary.set_report(self.report); self.message = "Traveller validation complete."
        elif action == "validate_icons":
            self.report = validate_icons(); self.summary.set_report(self.report); self.message = "Icon validation complete."
        elif action == "reload_recipes":
            result = reload_recipes(); self.recipe_revision = result.revision; self.report = result.report; self.summary.set_report(self.report); self.message = result.message; self.refresh_page()
        elif action == "reload_travellers":
            result = reload_traveller_templates(); self.traveller_revision = result.revision; self.report = result.report; self.summary.set_report(self.report); self.message = result.message; self.refresh_page()
        elif action == "reload_icons":
            result = refresh_icons(); self.icon_revision = result.revision; self.report = result.report; self.summary.set_report(self.report); self.message = result.message; self.refresh_page()
        return None

    def draw(self, surface: pygame.Surface) -> None:
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA); shade.fill((9, 14, 18, 240)); surface.blit(shade, (0, 0))
        panel = self._panel(); pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=10); pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=10)
        self._layout_buttons(panel)
        title = "DEVELOPER TOOLS" if self.page == "home" else self.page.upper()
        surface.blit(self.title_font.render(title, True, COLOUR_TEXT), (panel.x + 40, panel.y + 28))
        if self.page == "home":
            surface.blit(self.font.render("Development environment only. Changes may modify project content files.", True, COLOUR_TEXT_DIM), (panel.x + 40, panel.y + 70))
            status = "YES" if self.write_enabled else "NO — Developer Tools is read-only."
            surface.blit(self.font.render(f"Writable source tree: {status}", True, (115, 190, 125) if self.write_enabled else (225, 105, 95)), (panel.x + 40, panel.y + 105))
            surface.blit(self.small.render(f"Source root: {get_content_root()}", True, COLOUR_TEXT_DIM), (panel.x + 40, panel.y + 130))
        elif self.page in ("recipes", "travellers", "icons", "resources", "objects"):
            if self.page == "recipes": self.recipe_page.draw(surface, panel, self.font, self.small)
            elif self.page == "travellers": self.traveller_page.draw(surface, panel, self.font, self.small)
            elif self.page == "icons": self.icon_page.draw(surface, panel, self.font, self.small)
            elif self.page == "resources": self.resource_page.draw(surface, panel, self.font, self.small)
            else: self.object_page.draw(surface, panel, self.font, self.small)
        else:
            revisions = {"recipes": self.recipe_revision, "travellers": self.traveller_revision, "icons": self.icon_revision}
            surface.blit(self.font.render(f"Loaded entries: {len(self.items.items)}   Registry revision: {revisions.get(self.page, 0)}", True, COLOUR_TEXT_DIM), (panel.x + 40, panel.y + 72))
            self.items.rect = pygame.Rect(panel.x + 40, panel.y + 160, panel.w - 80, 235)
            if self.page == "recipes":
                self.items.draw(surface, self.small, lambda r: f"{r.workstation}: {r.key}")
            elif self.page == "travellers":
                self.items.draw(surface, self.small, lambda r: f"T{r.row.get('tier', '?')}  {r.key} — {r.label}")
            elif self.page == "icons":
                self.items.draw(surface, self.small, lambda i: f"{i.key}  ({'/'.join(i.formats)})")
            elif self.page == "resources":
                self.items.draw(surface, self.small, lambda r: f"{r.key} — {r.label}  [{r.group}]")
                note_y = panel.y + 408
                surface.blit(self.font.render("Resources are currently read-only.", True, (226, 183, 80)), (panel.x + 40, note_y))
                surface.blit(self.small.render("New arbitrary resource types require the planned dynamic storage/resource refactor.", True, COLOUR_TEXT_DIM), (panel.x + 40, note_y + 24))
                selected = self.items.selected
                if selected:
                    details = (
                        f"Key: {selected.key}", f"Label: {selected.label}", f"Group: {selected.group}",
                        f"Food: {'yes' if selected.food else 'no'}  Edible: {'yes' if selected.edible else 'no'}",
                        f"Icon: {selected.icon}", f"Definition source: {selected.source}",
                    )
                    for index, line in enumerate(details):
                        surface.blit(self.small.render(line, True, COLOUR_TEXT), (panel.x + 40, note_y + 58 + index * 19))
            else:
                self.items.draw(surface, self.small)
        self.summary.list.rect = pygame.Rect(panel.x + 40, panel.bottom - 190, panel.w - 80, 115)
        counts = self.summary.severity_counts()
        count_text = f"Errors {counts.get(ValidationSeverity.ERROR, 0)} · Warnings {len(self.report.warnings)} · Info {len(self.report.infos)}"
        footer = self.message if self.page in ("recipes", "travellers", "icons", "resources", "objects") else (self.message + "  " + count_text).strip()
        surface.blit(self.small.render(footer, True, COLOUR_TEXT_DIM), (panel.x + 40, panel.bottom - 30))
        if self.report.issues and self.page in ("home", "resources"):
            self.summary.draw(surface, self.font, self.small)
        mouse = pygame.mouse.get_pos()
        for rect, _action, label, enabled in self._buttons:
            colour = COLOUR_TOOLBAR_BTN_HOVER if enabled and rect.collidepoint(mouse) else COLOUR_TOOLBAR_BTN
            if not enabled: colour = (42, 47, 47)
            pygame.draw.rect(surface, colour, rect, border_radius=4); pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
            text = self.font.render(label, True, COLOUR_TEXT if enabled else COLOUR_TEXT_DIM); surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))
