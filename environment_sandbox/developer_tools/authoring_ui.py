"""Interactive catalogue forms used by the Developer Tools launcher."""

from __future__ import annotations

from pathlib import Path

import pygame

from icons import blit_icon, get_icon, has_icon, variant_names
from resources import resource_icon, resource_label
from settings import COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_ACTIVE
from .widgets import Checkbox, ColourField, Dropdown, FloatField, IntegerField, ScrollableList, TextField


NICHE_VALUE_LABELS = ("Min", "Ideal from", "Ideal to", "Max")
NICHE_DESCRIPTIONS = {
    "temperature_niche": "0 = -10 C, 1 = 35 C; values between are proportional.",
    "moisture_niche": "0 = driest soil, 1 = fully waterlogged soil. Local rainfall recharges this.",
    "fertility_niche": "0 = depleted soil, 1 = richest soil.",
    "disturbance_niche": "0 = untouched ground, 1 = heavily worked or disrupted ground.",
    "texture_niche": "0 = sandy/coarse soil, 1 = clayey/fine soil.",
}


BG = (25, 31, 34)
GOOD = (115, 190, 125)
BAD = (230, 95, 95)
SKILLS = ("extraction", "farming", "hunting", "crafting", "labour", "transport")
FOOD_FIELDS = ("food_satiation", "food_walk_speed", "food_work_efficiency", "food_hunger_rate")
CLOTHING_FIELDS = ("walk_speed", "capacity_bonus", "heat_protection", "cold_protection")


def _resource_options():
    """Resolve at use time so resource-editor reloads appear immediately."""
    import resources
    by_key = {item.key: item for item in resources.RESOURCES}
    order={name:i for i,name in enumerate(resources.GROUP_ORDER)}
    keys=sorted((key for key in resources.RESOURCE_KEYS if key in by_key),key=lambda key:(order.get(by_key[key].group,99),by_key[key].label.casefold()))
    return [(key, f"[{by_key[key].group.title()}] {by_key[key].label}") for key in keys]


def _button(surface, font, rect, label, *, enabled=True, hot=False):
    colour = COLOUR_TOOLBAR_BTN_ACTIVE if hot else COLOUR_TOOLBAR_BTN
    if not enabled:
        colour = (43, 47, 49)
    pygame.draw.rect(surface, colour, rect, border_radius=4)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
    text = font.render(label, True, COLOUR_TEXT if enabled else COLOUR_TEXT_DIM)
    surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))


def _preview_cell_px(icon: str, target_cells: int, grid_cell_px: int) -> int:
    """Scale an icon's native viewBox extent to the selected footprint."""
    try:
        image=get_icon(icon,40)
        native=max(1.0,image.surface.get_width()/40.0,image.surface.get_height()/40.0)
    except (FileNotFoundError,OSError):native=1.0
    return max(1,round(grid_cell_px*max(1,target_cells)/native))


class RecipeAuthoringPage:
    """A structured recipe form; CSV amount syntax never reaches the user."""

    def __init__(self, service, icons):
        self.service = service
        self.icons = icons
        self.list = ScrollableList(pygame.Rect(0, 0, 1, 1), row_height=25)
        self.list.category = lambda item: item.workstation
        self.workstation = Dropdown(pygame.Rect(0, 0, 1, 1), [(None, "All workstations")] + [(v, v.replace("_", " ").title()) for v in service.documents], None)
        self.search = TextField(pygame.Rect(0, 0, 1, 1), placeholder="Search recipes")
        self.fields: dict[str, TextField] = {}
        self.building = Dropdown(pygame.Rect(0, 0, 1, 1), [(v, v.replace("_", " ").title()) for v in service.documents])
        self.input_rows: list[tuple[Dropdown, IntegerField]] = []
        self.output_rows: list[tuple[Dropdown, IntegerField]] = []
        self.form_scroll = 0
        self.actions: list[tuple[pygame.Rect, str, bool]] = []
        self.icon_picker = False
        self.icon_list = ScrollableList(pygame.Rect(0, 0, 1, 1), row_height=24)
        self.message = "Select a recipe or click New Recipe."
        self.refresh_list()

    def refresh_list(self, selected_key=None):
        records = self.service.filtered(self.workstation.value, self.search.text)
        self.list.set_items(records)
        if selected_key:
            self.list.selected_index = next((i for i, r in enumerate(records) if r.key == selected_key), None)

    def load_candidate(self):
        c = self.service.state.candidate
        self.fields = {}
        self.input_rows = []
        self.output_rows = []
        self.form_scroll = 0
        if c is None:
            return
        self.building.value = c.workstation
        self.building.disabled = not self.service.state.is_new
        for key in c.row:
            if key not in ("inputs", "outputs"):
                value=c.row.get(key, "")
                if key == "category":
                    from recipes import CATEGORY_LABELS
                    options=[("", "None")]+[(k,v) for k,v in CATEGORY_LABELS.items()]
                    if value and not any(k==value for k,_ in options):options.append((value,value.replace("_"," ").title()))
                    self.fields[key]=Dropdown(pygame.Rect(0,0,1,1),options,value)
                elif key == "clothing_slot":
                    from entities import CLOTHING_SLOTS
                    self.fields[key]=Dropdown(pygame.Rect(0,0,1,1),[("","None")]+[(v,v.title()) for v in CLOTHING_SLOTS],value)
                elif key == "food_edible":
                    self.fields[key]=Dropdown(pygame.Rect(0,0,1,1),[("","Unspecified"),("1","Yes"),("0","No")],value)
                else:
                    cls = IntegerField if key == "steps" or key in SKILLS else FloatField if key in FOOD_FIELDS + CLOTHING_FIELDS else TextField
                    kwargs = {"minimum": 0, "nullable": True} if cls is not TextField else {}
                    self.fields[key] = cls(pygame.Rect(0, 0, 1, 1), value, **kwargs)
        options = _resource_options()
        for key, qty in c.inputs:
            self.input_rows.append((Dropdown(pygame.Rect(0, 0, 1, 1), options, key), IntegerField(pygame.Rect(0, 0, 1, 1), str(qty), minimum=1)))
        for key, qty in c.outputs:
            self.output_rows.append((Dropdown(pygame.Rect(0, 0, 1, 1), options, key), IntegerField(pygame.Rect(0, 0, 1, 1), str(qty), minimum=1)))

    def _sync(self):
        c = self.service.state.candidate
        if c is None:
            return
        for key, field in self.fields.items():
            c.row[key] = str(field.value if isinstance(field, Dropdown) else field.text).strip()
        c.inputs = [(d.value, int(q.text or 0)) for d, q in self.input_rows if d.value and q.text.isdigit()]
        c.outputs = [(d.value, int(q.text or 0)) for d, q in self.output_rows if d.value and q.text.isdigit()]
        self.service.state.mark_changed()
        self.service.state.validation = self.service.validate_candidate()

    def _change_new_workstation(self, workstation: str) -> None:
        """Move an unsaved candidate to another canonical workstation schema."""
        current = self.service.state.candidate
        if current is None or not self.service.state.is_new or workstation == current.workstation:
            return
        old_row = dict(current.row)
        old_inputs, old_outputs = current.inputs, current.outputs
        self.service.new(workstation)
        replacement = self.service.state.candidate
        assert replacement is not None
        for key in replacement.row:
            if key in old_row:
                replacement.row[key] = old_row[key]
        replacement.inputs = old_inputs
        replacement.outputs = old_outputs
        self.load_candidate()
        self.message = f"Building changed to {workstation.replace('_', ' ').title()}; the form now uses that workstation's schema."

    def _act(self, action):
        c = self.service.state.candidate
        if action == "new":
            workstation = self.workstation.value or ("kitchen" if "kitchen" in self.service.documents else next(iter(self.service.documents)))
            self.service.new(workstation); self.load_candidate(); self.message = "New unsaved recipe. Nothing is written until Save."
        elif action == "duplicate" and c:
            self.service.duplicate(); self.load_candidate(); self.message = "Duplicated as an unsaved recipe; enter a unique ID."
        elif action == "cancel" and c:
            if self.service.state.original:
                self.service.select(self.service.state.original); self.load_candidate()
            else:
                self.service.state.candidate = None; self.fields.clear()
            self.message = "Changes cancelled."
        elif action in ("save", "save_test") and c:
            self._sync()
            try:
                result = self.service.save()
            except Exception as exc:
                self.message = f"Recipe save failed: {type(exc).__name__}: {exc}"
                return None
            self.message = result.message
            if result.success:
                key = c.key; self.load_candidate(); self.refresh_list(key)
                self.message = f"Saved to recipes_data/{c.workstation}/recipes.csv. Registry reloaded; recipe is available in game."
                if action == "save_test":
                    return ("save_test", key, c.workstation)
            elif result.report.errors:
                self.message += " " + " | ".join(issue.message for issue in result.report.errors[:3])
        elif action == "delete" and c and not self.service.state.is_new:
            result, refs = self.service.delete(); self.message = result.message + (f" ({len(refs)} references found.)" if refs else "")
            self.fields.clear(); self.refresh_list()
        elif action == "add_input" and c:
            opts = _resource_options()
            self.input_rows.append((Dropdown(pygame.Rect(0, 0, 1, 1), opts), IntegerField(pygame.Rect(0, 0, 1, 1), "1", minimum=1))); self._sync()
        elif action == "add_output" and c:
            opts = _resource_options()
            self.output_rows.append((Dropdown(pygame.Rect(0, 0, 1, 1), opts), IntegerField(pygame.Rect(0, 0, 1, 1), "1", minimum=1))); self._sync()
        elif action.startswith("remove_input_"):
            del self.input_rows[int(action.rsplit("_", 1)[1])]; self._sync()
        elif action.startswith("remove_output_"):
            del self.output_rows[int(action.rsplit("_", 1)[1])]; self._sync()
        elif action == "choose_icon":
            self.icon_picker = True; self.icon_list.set_items(self.icons.entries())
        return None

    def handle_event(self, event):
        if self.icon_picker:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.icon_picker = False; return True, None
            old = self.icon_list.selected_index
            if self.icon_list.handle_event(event):
                if self.icon_list.selected_index != old and self.icon_list.selected:
                    self.fields["icon_key"].text = self.icon_list.selected.key; self.icon_picker = False; self._sync()
                return True, None
        # Footer buttons are fixed above a scrollable form. Dispatch them before
        # any field: scrolled controls retain absolute rects and must never
        # intercept a visible Save/Cancel click.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action, enabled in reversed(self.actions):
                if action in ("save", "save_test", "cancel") and enabled and rect.collidepoint(event.pos):
                    return True, self._act(action)
        old_ws, old_search = self.workstation.value, self.search.text
        if self.workstation.handle_event(event) or self.search.handle_event(event):
            if old_ws != self.workstation.value or old_search != self.search.text: self.refresh_list()
            return True, None
        old_building = self.building.value
        if self.building.handle_event(event):
            if self.building.value != old_building and self.building.value:
                self._change_new_workstation(self.building.value)
            return True, None
        old = self.list.selected_index
        if self.list.handle_event(event):
            if old != self.list.selected_index and self.list.selected:
                self.service.select(self.list.selected); self.load_candidate()
            return True, None
        controls = list(self.fields.values()) + [v for row in self.input_rows + self.output_rows for v in row]
        # Open dropdowns receive the event first so their popup rows are clickable.
        controls.sort(key=lambda x: not isinstance(x, Dropdown) or not x.open)
        for control in controls:
            before = getattr(control, "text", getattr(control, "value", None))
            if control.handle_event(event):
                after = getattr(control, "text", getattr(control, "value", None))
                if before != after: self._sync()
                return True, None
        if event.type == pygame.MOUSEWHEEL:
            self.form_scroll = max(0, self.form_scroll - event.y * 35); return True, None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Fixed footer controls are appended last. Test them first so
            # scrolled/off-screen row buttons cannot steal a Save click.
            for rect, action, enabled in reversed(self.actions):
                if enabled and rect.collidepoint(event.pos): return True, self._act(action)
        return False, None

    def draw(self, surface, panel, font, small):
        left = pygame.Rect(panel.x + 24, panel.y + 92, 330, panel.h - 160)
        right = pygame.Rect(left.right + 14, left.y, panel.right - left.right - 38, left.h)
        self.workstation.rect = pygame.Rect(left.x, left.y, 158, 30); self.search.rect = pygame.Rect(left.x + 166, left.y, 164, 30)
        self.workstation.draw(surface, small); self.search.draw(surface, small)
        self.actions = []
        for i, (action, label, enabled) in enumerate((("new", "New Recipe", True), ("duplicate", "Duplicate", self.service.state.candidate is not None), ("delete", "Delete", self.service.state.candidate is not None and not self.service.state.is_new))):
            rect = pygame.Rect(left.x + i * 108, left.y + 38, 102, 30); self.actions.append((rect, action, enabled)); _button(surface, small, rect, label, enabled=enabled)
        self.list.rect = pygame.Rect(left.x, left.y + 76, left.w, left.h - 76); self.list.draw(surface, small, lambda r: f"{r.workstation}: {r.label}")
        pygame.draw.rect(surface, BG, right); pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, right, 1)
        c = self.service.state.candidate
        surface.blit(font.render("RECIPE EDITOR", True, COLOUR_TEXT), (right.x + 14, right.y + 10))
        if c is None:
            surface.blit(small.render("Select an entry or create a new recipe.", True, COLOUR_TEXT_DIM), (right.x + 14, right.y + 42)); return
        dirty = "● Unsaved changes" if self.service.state.dirty else "Saved"
        surface.blit(small.render(f"{c.workstation.replace('_', ' ').title()}   {dirty}", True, (226, 183, 80) if self.service.state.dirty else GOOD), (right.x + 180, right.y + 13))
        fallback_icon = resource_icon(c.outputs[0][0]) if c.outputs else ""
        header_icon = fallback_icon
        if header_icon and has_icon(header_icon):
            blit_icon(surface, header_icon, right.right - 35, right.y + 25, 42)
        else:
            pygame.draw.rect(surface, (48, 52, 54), pygame.Rect(right.right - 57, right.y + 4, 44, 44), border_radius=4)
            surface.blit(small.render("?", True, COLOUR_TEXT_DIM), (right.right - 39, right.y + 17))
        clip = pygame.Rect(right.x + 2, right.y + 38, right.w - 4, right.h - 92); old_clip = surface.get_clip(); surface.set_clip(clip)
        x, y, field_x = right.x + 14, right.y + 44 - self.form_scroll, right.x + 162
        def heading(label):
            nonlocal y
            surface.blit(font.render(label, True, (150, 190, 165)), (x, y)); y += 27
        def field(key, label, width=260):
            nonlocal y
            if key not in self.fields: return
            surface.blit(small.render(label, True, COLOUR_TEXT_DIM), (x, y + 6)); f = self.fields[key]; f.rect = pygame.Rect(field_x, y, width, 26); f.disabled = key == "name" and not self.service.state.is_new; f.draw(surface, small); y += 32
        heading("PRODUCTION")
        surface.blit(small.render("Building", True, COLOUR_TEXT_DIM), (x, y + 6))
        self.building.rect = pygame.Rect(field_x, y, 260, 26)
        self.building.draw(surface, small)
        y += 32
        field("name", "ID"); field("label", "Name"); field("category", "Category"); field("steps", "Steps")
        for title, rows, prefix in (("INPUTS", self.input_rows, "input"), ("OUTPUTS", self.output_rows, "output")):
            heading(title)
            for i, (drop, qty) in enumerate(rows):
                drop.rect = pygame.Rect(x, y, 250, 26); qty.rect = pygame.Rect(x + 258, y, 60, 26)
                drop.draw(surface, small); qty.draw(surface, small)
                rect = pygame.Rect(x + 326, y, 28, 26); self.actions.append((rect, f"remove_{prefix}_{i}", True)); _button(surface, small, rect, "×")
                y += 31
            rect = pygame.Rect(x, y, 128, 27); self.actions.append((rect, f"add_{prefix}", True)); _button(surface, small, rect, f"+ Add {title[:-1].title()}"); y += 36
        heading("SKILL REQUIREMENTS")
        for key in SKILLS: field(key, key.title(), 90)
        edible_control = self.fields.get("food_edible")
        edible_value = getattr(edible_control, "value", getattr(edible_control, "text", ""))
        if any(key in self.fields for key in FOOD_FIELDS) and (c.workstation == "kitchen" or str(edible_value).strip()):
            heading("FOOD EFFECTS")
            for key in FOOD_FIELDS: field(key, key.removeprefix("food_").replace("_", " ").title(), 110)
            field("food_edible", "Edible (0/1)", 110)
        if any(key in self.fields for key in CLOTHING_FIELDS):
            heading("CLOTHING EFFECTS")
            field("clothing_slot", "Slot", 150)
            for key in CLOTHING_FIELDS: field(key, key.replace("_", " ").title(), 110)
        heading("DISPLAY")
        field("resource_group", "Resource group", 180); field("resource_short", "Short label", 180)
        surface.blit(small.render("Icon is owned by the primary output in Resources.", True, COLOUR_TEXT_DIM), (x, y)); y += 30
        y += 40
        report = self.service.state.validation
        status = "✓ Valid" if report.ok else f"✕ {report.errors[0].message}"
        surface.blit(small.render(status, True, GOOD if report.ok else BAD), (x, y)); y += 28
        for control in [v for row in self.input_rows + self.output_rows for v in row]:
            if isinstance(control, Dropdown) and control.open: control.draw(surface, small)
        if self.building.open:
            self.building.draw(surface, small)
        surface.set_clip(old_clip)
        save_y = right.bottom - 43
        for i, (action, label, enabled) in enumerate((("save", "Save", report.ok), ("save_test", "Save + Test", report.ok), ("cancel", "Cancel", True))):
            rect = pygame.Rect(right.x + 14 + i * 126, save_y, 116, 30); self.actions.append((rect, action, enabled)); _button(surface, small, rect, label, enabled=enabled)
        if self.icon_picker:
            modal = pygame.Rect(panel.centerx - 270, panel.centery - 260, 540, 520); pygame.draw.rect(surface, BG, modal); pygame.draw.rect(surface, (160, 190, 170), modal, 2)
            surface.blit(font.render("CHOOSE ICON", True, COLOUR_TEXT), (modal.x + 16, modal.y + 14)); self.icon_list.rect = pygame.Rect(modal.x + 16, modal.y + 48, modal.w - 32, modal.h - 64)
            self.icon_list.draw(surface, small, lambda i: i.key)
        # The filter also chooses the target building for New Recipe. Paint its
        # popup last so the recipe list cannot cover its options.
        if self.workstation.open:
            self.workstation.draw(surface, small)


class TravellerAuthoringPage:
    def __init__(self, service):
        self.service = service; self.list = ScrollableList(pygame.Rect(0,0,1,1), row_height=25)
        self.list.category=lambda item:f"Tier {item.row.get('tier','?')}"
        self.search = TextField(pygame.Rect(0,0,1,1), placeholder="Search travellers")
        self.tier = Dropdown(pygame.Rect(0,0,1,1), [(None, "All tiers"), (1,"Tier 1"),(2,"Tier 2"),(3,"Tier 3")], None)
        self.fields = {}; self.requirements = []; self.traits = {}; self.actions = []; self.form_scroll = 0; self.message = "Select a traveller or click New Traveller."
        self.refresh_list()

    def refresh_list(self, key=None):
        rows = self.service.filtered(self.tier.value, self.search.text); self.list.set_items(rows)
        if key: self.list.selected_index = next((i for i,r in enumerate(rows) if r.key == key), None)

    def load_candidate(self):
        from society import VICE_POOL, VIRTUE_POOL
        c = self.service.state.candidate; self.fields={}; self.requirements=[]; self.traits={}; self.form_scroll=0
        if not c: return
        numeric = {"tier","housing_need","signing_fee", *SKILLS, *(f"{s}_cap" for s in SKILLS)}
        for key, value in c.row.items():
            if key in ("required_foods","virtues","vices","favourite_is_junk"): continue
            if key == "favourite_foods":
                self.fields[key] = Dropdown(pygame.Rect(0,0,1,1), [("", "None")] + _resource_options(), value)
            elif key == "required_workplace":
                from entities import BuildingKind
                self.fields[key] = Dropdown(pygame.Rect(0,0,1,1), [("", "None")] + [(k.name.lower(), k.name.replace("_", " ").title()) for k in BuildingKind], value)
            else:
                cls = IntegerField if key in numeric else TextField; kwargs={"minimum":0} if cls is IntegerField else {}
                self.fields[key]=cls(pygame.Rect(0,0,1,1), value, **kwargs)
        opts=_resource_options()
        for clause in c.required_food_clauses:
            self.requirements.append([Dropdown(pygame.Rect(0,0,1,1),opts,key) for key in clause])
        selected={"virtues":set(filter(None,c.row.get("virtues","").split(";"))),"vices":set(filter(None,c.row.get("vices","").split(";")))}
        self.traits={"virtues":[(v,Checkbox(pygame.Rect(0,0,1,1),v in selected["virtues"])) for v in VIRTUE_POOL],"vices":[(v,Checkbox(pygame.Rect(0,0,1,1),v in selected["vices"])) for v in VICE_POOL]}
        self.junk=Checkbox(pygame.Rect(0,0,1,1),c.row.get("favourite_is_junk")=="1")

    def _sync(self):
        c=self.service.state.candidate
        if not c:return
        for k,f in self.fields.items(): c.row[k]=str(f.value if isinstance(f, Dropdown) else f.text).strip()
        c.required_food_clauses=[[d.value for d in clause if d.value] for clause in self.requirements]
        c.row["favourite_is_junk"]="1" if self.junk.checked else "0"
        for kind,rows in self.traits.items(): c.row[kind]=";".join(name for name,box in rows if box.checked)
        self.service.state.mark_changed(); self.service.state.validation=self.service.validate_candidate()

    def _act(self,a):
        c=self.service.state.candidate
        if a=="new": self.service.new(); self.load_candidate(); self.message="New unsaved traveller. Nothing is written until Save."
        elif a=="duplicate" and c:self.service.duplicate();self.load_candidate();self.message="Duplicated; enter a unique ID."
        elif a=="save" and c:
            self._sync();r=self.service.save();self.message=r.message
            if r.success:key=c.key;self.load_candidate();self.refresh_list(key);self.message="Traveller saved to society_data/travellers.csv. Traveller pool reloaded."
        elif a=="delete" and c and not self.service.state.is_new:r=self.service.delete();self.message=r.message;self.fields={};self.refresh_list()
        elif a=="cancel" and c:
            if self.service.state.original:self.service.select(self.service.state.original);self.load_candidate()
            else:self.service.state.candidate=None;self.fields={}
        elif a=="add_requirement":
            opts=_resource_options();self.requirements.append([Dropdown(pygame.Rect(0,0,1,1),opts)]);self._sync()
        elif a.startswith("add_or_"):
            opts=_resource_options();self.requirements[int(a.rsplit('_',1)[1])].append(Dropdown(pygame.Rect(0,0,1,1),opts));self._sync()
        elif a.startswith("remove_req_"):del self.requirements[int(a.rsplit('_',1)[1])];self._sync()

    def handle_event(self,event):
        old=(self.tier.value,self.search.text)
        if self.tier.handle_event(event) or self.search.handle_event(event):
            if old!=(self.tier.value,self.search.text):self.refresh_list()
            return True
        oi=self.list.selected_index
        if self.list.handle_event(event):
            if oi!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load_candidate()
            return True
        controls=list(self.fields.values())+[d for clause in self.requirements for d in clause]+[b for rows in self.traits.values() for _,b in rows]+([self.junk] if hasattr(self,"junk") else [])
        controls.sort(key=lambda x:not isinstance(x,Dropdown) or not x.open)
        for ctl in controls:
            before=(getattr(ctl,"text",None),getattr(ctl,"value",None),getattr(ctl,"checked",None))
            if ctl.handle_event(event):
                after=(getattr(ctl,"text",None),getattr(ctl,"value",None),getattr(ctl,"checked",None))
                if before!=after:self._sync()
                return True
        if event.type==pygame.MOUSEWHEEL:self.form_scroll=max(0,self.form_scroll-event.y*35);return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for rect,a,en in self.actions:
                if en and rect.collidepoint(event.pos):self._act(a);return True
        return False

    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+24,panel.y+92,330,panel.h-160);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h)
        self.tier.rect=pygame.Rect(left.x,left.y,120,30);self.search.rect=pygame.Rect(left.x+128,left.y,202,30);self.tier.draw(surface,small);self.search.draw(surface,small);self.actions=[]
        for i,(a,l,en) in enumerate((("new","New Traveller",True),("duplicate","Duplicate",self.service.state.candidate is not None),("delete","Delete",self.service.state.candidate is not None and not self.service.state.is_new))):
            r=pygame.Rect(left.x+i*108,left.y+38,102,30);self.actions.append((r,a,en));_button(surface,small,r,l,enabled=en)
        self.list.rect=pygame.Rect(left.x,left.y+76,left.w,left.h-76);self.list.draw(surface,small,lambda r:f"T{r.row.get('tier','?')} {r.label}")
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);surface.blit(font.render("TRAVELLER EDITOR",True,COLOUR_TEXT),(right.x+14,right.y+10));c=self.service.state.candidate
        if not c:surface.blit(small.render("Select an entry or create a traveller.",True,COLOUR_TEXT_DIM),(right.x+14,right.y+42));return
        surface.blit(small.render("● Unsaved changes" if self.service.state.dirty else "Saved",True,(226,183,80) if self.service.state.dirty else GOOD),(right.x+220,right.y+13))
        clip=pygame.Rect(right.x+2,right.y+38,right.w-4,right.h-92);old=surface.get_clip();surface.set_clip(clip);x,y,fx=right.x+14,right.y+44-self.form_scroll,right.x+170
        def head(t):
            nonlocal y;surface.blit(font.render(t,True,(150,190,165)),(x,y));y+=27
        def field(k,l,w=250):
            nonlocal y
            if k not in self.fields:return
            surface.blit(small.render(l,True,COLOUR_TEXT_DIM),(x,y+6));f=self.fields[k];f.rect=pygame.Rect(fx,y,w,26);f.disabled=k=="template_id" and not self.service.state.is_new;f.draw(surface,small);y+=32
        head("IDENTITY & REQUIREMENTS");field("template_id","ID");field("name","Name");field("tier","Tier",80);field("housing_need","Housing",80);field("favourite_foods","Favourite foods");
        surface.blit(small.render("Favourite junk",True,COLOUR_TEXT_DIM),(x,y+4));self.junk.rect=pygame.Rect(fx,y,20,20);self.junk.draw(surface);y+=30;field("required_workplace","Workplace");field("signing_fee","Signing fee",100)
        head("REQUIRED FOODS (rows are AND; choices in a row are OR)")
        for i,clause in enumerate(self.requirements):
            for j,d in enumerate(clause):d.rect=pygame.Rect(x+j*142,y,136,25);d.draw(surface,small)
            ar=pygame.Rect(x+len(clause)*142,y,54,25);self.actions.append((ar,f"add_or_{i}",True));_button(surface,small,ar,"+ OR")
            rr=pygame.Rect(ar.right+5,y,26,25);self.actions.append((rr,f"remove_req_{i}",True));_button(surface,small,rr,"×");y+=30
        r=pygame.Rect(x,y,150,26);self.actions.append((r,"add_requirement",True));_button(surface,small,r,"+ Add requirement");y+=36
        head("TRAITS")
        for kind,rows in self.traits.items():
            surface.blit(small.render(kind.title(),True,COLOUR_TEXT_DIM),(x,y));y+=22
            for i,(name,box) in enumerate(rows):
                col=i%3;row=i//3;box.rect=pygame.Rect(x+col*145,y+row*24,18,18);box.draw(surface);surface.blit(small.render(name,True,COLOUR_TEXT),(box.rect.right+4,box.rect.y+2))
            y+=((len(rows)+2)//3)*24+5
        head("SKILLS — START / CAP")
        surface.blit(small.render("Start     Cap",True,COLOUR_TEXT_DIM),(fx,y));y+=20
        for s in SKILLS:
            surface.blit(small.render(s.title(),True,COLOUR_TEXT_DIM),(x,y+5));a,b=self.fields[s],self.fields[f"{s}_cap"];a.rect=pygame.Rect(fx,y,65,25);b.rect=pygame.Rect(fx+82,y,65,25);a.draw(surface,small);b.draw(surface,small);y+=30
        report=self.service.state.validation;surface.blit(small.render("✓ Valid" if report.ok else f"✕ {report.errors[0].message}",True,GOOD if report.ok else BAD),(x,y))
        for ctl in [*self.fields.values(), *(d for clause in self.requirements for d in clause)]:
            if isinstance(ctl,Dropdown) and ctl.open:ctl.draw(surface,small)
        surface.set_clip(old)
        sy=right.bottom-43
        for i,(a,l,en) in enumerate((("save","Save",report.ok),("cancel","Cancel",True))):r=pygame.Rect(right.x+14+i*126,sy,116,30);self.actions.append((r,a,en));_button(surface,small,r,l,enabled=en)


class IconImportPage:
    def __init__(self,service):
        self.service=service;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=25);self.source=TextField(pygame.Rect(0,0,1,1),placeholder="/path/to/icon.svg");self.key=TextField(pygame.Rect(0,0,1,1),placeholder="snake_case_key");self.category=Dropdown(pygame.Rect(0,0,1,1),[(v,v) for v in service.categories],".");self.importing=False;self.actions=[];self.message="Browse canonical icons or click Import Icon.";self.refresh()
        self.list.category=lambda item:str(item.paths[0].parent.relative_to(service.icon_root)) if item.paths else "Other"
    def refresh(self):self.list.set_items(self.service.entries())
    def handle_event(self,event):
        if self.importing:
            for c in (self.source,self.key,self.category):
                if c.handle_event(event):return True
        if self.list.handle_event(event):return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for r,a,en in self.actions:
                if en and r.collidepoint(event.pos):
                    if a=="open":self.importing=True
                    elif a=="cancel":self.importing=False
                    elif a=="preview":
                        _dest,rep=self.service.validate_import(Path(self.source.text),self.key.text,self.category.value);self.message="Preview valid." if rep.ok else (rep.errors[0].message if rep.errors else "Preview failed.")
                    elif a=="import":
                        result=self.service.import_file(Path(self.source.text),self.key.text,self.category.value);self.message=result.message
                        if result.success:self.importing=False;self.refresh()
                    return True
        return False
    def draw(self,surface,panel,font,small):
        self.actions=[];r=pygame.Rect(panel.x+24,panel.y+92,130,31);self.actions.append((r,"open",True));_button(surface,small,r,"Import Icon")
        self.list.rect=pygame.Rect(panel.x+24,panel.y+134,panel.w-48,panel.h-200);self.list.draw(surface,small,lambda i:f"{i.key}  ({'/'.join(i.formats)})")
        if self.list.selected:
            blit_icon(surface,self.list.selected.key,panel.right-79,panel.y+113,42)
        if self.importing:
            modal=pygame.Rect(panel.centerx-290,panel.centery-180,580,360);pygame.draw.rect(surface,BG,modal);pygame.draw.rect(surface,(150,190,165),modal,2);surface.blit(font.render("IMPORT ICON",True,COLOUR_TEXT),(modal.x+20,modal.y+18));y=modal.y+65
            for label,ctl,w in (("Source file",self.source,370),("Icon key",self.key,260),("Destination",self.category,220)):
                surface.blit(small.render(label,True,COLOUR_TEXT_DIM),(modal.x+20,y+7));ctl.rect=pygame.Rect(modal.x+150,y,w,28);ctl.draw(surface,small);y+=45
            # A destination key is not registered until Import succeeds. Never
            # ask the canonical renderer for that not-yet-existing key.
            if self.key.text and has_icon(self.key.text):
                blit_icon(surface,self.key.text,modal.x+44,y+24,48)
            for i,(a,l) in enumerate((("preview","Preview"),("import","Import"),("cancel","Cancel"))):r=pygame.Rect(modal.x+150+i*110,modal.bottom-55,100,30);self.actions.append((r,a,True));_button(surface,small,r,l)


class ResourceAuthoringPage:
    def __init__(self,service,icons,on_saved=None):
        self.service=service;self.icons=icons;self.on_saved=on_saved;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=25);self.search=TextField(pygame.Rect(0,0,1,1),placeholder="Search resources");self.icon_list=ScrollableList(pygame.Rect(0,0,1,1),row_height=24);self.icon_picker=False;self.fields={};self.actions=[];self.message="Select a resource or click New Resource.";self.refresh()
        self.list.category=lambda item:item.get("group","Other")
    def refresh(self,key=None):
        query=self.search.text.strip().casefold();self.list.set_items([r for r in self.service.records if not query or query in r["key"].casefold() or query in r["label"].casefold()])
        if key:self.list.selected_index=next((i for i,r in enumerate(self.list.items) if r["key"]==key),None)
    def load(self):
        c=self.service.candidate;self.fields={}
        if not c:return
        for k,v in c.items():
            if k=="group":self.fields[k]=Dropdown(pygame.Rect(0,0,1,1),[(x,x.title()) for x in ("food","wares","agriculture","construction")],v)
            elif k=="usage":self.fields[k]=Dropdown(pygame.Rect(0,0,1,1),[(x,x.replace("_"," ").title()) for x in ("resource","food","tool","clothing","construction","agriculture")],v)
            else:self.fields[k]=TextField(pygame.Rect(0,0,1,1),v)
    def sync(self):
        for k,f in self.fields.items():self.service.candidate[k]=str(f.value if isinstance(f,Dropdown) else f.text).strip()
    def act(self,a):
        if a=="new":self.service.new();self.load();self.message="New unsaved resource."
        elif a=="duplicate" and self.service.candidate:self.service.duplicate();self.load()
        elif a=="save":
            self.sync();ok,rep,msg=self.service.save();self.message=msg
            if ok:
                key=self.service.candidate["key"];self.load();self.refresh(key)
                if self.on_saved:self.on_saved()
        elif a=="delete":
            ok,self.message=self.service.delete()
            if ok:self.fields={};self.refresh();self.on_saved and self.on_saved()
        elif a=="cancel":self.service.candidate=None;self.fields={}
        elif a=="choose_icon":self.icon_picker=True;self.icon_list.set_items(self.icons.entries())
    def handle_event(self,event):
        if self.icon_picker:
            if event.type==pygame.KEYDOWN and event.key==pygame.K_ESCAPE:self.icon_picker=False;return True
            old=self.icon_list.selected_index
            if self.icon_list.handle_event(event):
                if old!=self.icon_list.selected_index and self.icon_list.selected:
                    self.fields["icon_key"].text=self.icon_list.selected.key;self.sync();self.icon_picker=False
                return True
        old_query=self.search.text
        if self.search.handle_event(event):
            if self.search.text!=old_query:self.refresh()
            return True,None
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load()
            return True
        controls=list(self.fields.values());controls.sort(key=lambda x:not isinstance(x,Dropdown) or not x.open)
        for f in controls:
            if f.handle_event(event):self.sync();return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for r,a,en in self.actions:
                if en and r.collidepoint(event.pos):self.act(a);return True
        return False
    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+24,panel.y+92,330,panel.h-160);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h);self.actions=[]
        for i,(a,l,en) in enumerate((("new","New Resource",True),("duplicate","Duplicate",self.service.candidate is not None),("delete","Delete",self.service.candidate is not None))):r=pygame.Rect(left.x+i*110,left.y,103,30);self.actions.append((r,a,en));_button(surface,small,r,l,enabled=en)
        self.search.rect=pygame.Rect(left.x,left.y+40,left.w,28);self.search.draw(surface,small)
        self.list.rect=pygame.Rect(left.x,left.y+76,left.w,left.h-76);self.list.draw(surface,small,lambda r:f"{r['key']} — {r['label']}")
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);surface.blit(font.render("RESOURCE EDITOR",True,COLOUR_TEXT),(right.x+14,right.y+10))
        if not self.service.candidate:return
        x,y,fx=right.x+14,right.y+50,right.x+175
        labels=(("key","ID"),("label","Label"),("short","Short label"),("group","Display group"),("icon_key","Icon key"),("usage","Used as"),("stack_size","Stack size"),("tool_effectiveness","Tool effectiveness"),("tool_targets","Tool targets"))
        for k,label in labels:
            if k not in self.fields:continue
            if k.startswith("tool_") and self.fields["usage"].value!="tool":continue
            surface.blit(small.render(label,True,COLOUR_TEXT_DIM),(x,y+6));f=self.fields[k];f.rect=pygame.Rect(fx,y,300,27);f.disabled=k=="key" and not self.service.is_new;f.draw(surface,small);y+=35
            if k=="icon_key":
                r=pygame.Rect(fx+306,y-35,92,27);self.actions.append((r,"choose_icon",True));_button(surface,small,r,"Choose")
        icon=self.fields.get("icon_key");name=icon.text if icon and hasattr(icon,"text") else ""
        if name and has_icon(name):blit_icon(surface,name,right.right-42,right.y+28,42)
        report=self.service.validate();surface.blit(small.render("✓ Valid" if report.ok else f"✕ {report.errors[0].message}",True,GOOD if report.ok else BAD),(x,right.bottom-78))
        for i,(a,l,en) in enumerate((("save","Save",report.ok),("cancel","Cancel",True))):r=pygame.Rect(right.x+14+i*126,right.bottom-43,116,30);self.actions.append((r,a,en));_button(surface,small,r,l,enabled=en)
        for f in self.fields.values():
            if isinstance(f,Dropdown) and f.open:f.draw(surface,small)
        if self.icon_picker:
            modal=pygame.Rect(panel.centerx-270,panel.centery-260,540,520);pygame.draw.rect(surface,BG,modal);pygame.draw.rect(surface,(150,190,165),modal,2);surface.blit(font.render("CHOOSE RESOURCE ICON",True,COLOUR_TEXT),(modal.x+16,modal.y+14));self.icon_list.rect=pygame.Rect(modal.x+16,modal.y+48,modal.w-32,modal.h-64);self.icon_list.draw(surface,small,lambda i:i.key)


class ObjectAuthoringPage:
    def __init__(self,service,icons):
        self.service=service;self.icons=icons;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=25);self.kind=Dropdown(pygame.Rect(0,0,1,1),[("all","All objects"),("feature","Map features"),("wild","Wild plants"),("crop","Crops"),("tree","Trees")],"all");self.fields={};self.actions=[];self.scroll=0;self.message="Select a map object.";self.grid_rects=[];self.refresh()
        self.list.category=lambda item:item.get("category","Other")
    def refresh(self):
        if self.kind.value=="all":rows=self.service.records
        elif self.kind.value=="crop":rows=[r for r in self.service.records if r["kind"]=="crop" or r.get("category")=="Wild crops"]
        else:rows=[r for r in self.service.records if r["kind"]==self.kind.value]
        self.list.set_items(rows)
    def load(self):
        import json
        c=self.service.candidate;self.fields={};self.scroll=0
        if not c:return
        self.fields["icon_key"]=TextField(pygame.Rect(0,0,1,1),c["icon_key"])
        for key,value in c["params"].items():
            if "colour" in key and isinstance(value, (list, tuple)) and len(value) == 3:
                self.fields[key]=ColourField(pygame.Rect(0,0,1,1),value)
            else:self.fields[key]=TextField(pygame.Rect(0,0,1,1),json.dumps(value) if isinstance(value,(list,dict)) else str(value) if value is not None else "null")
    def sync(self):
        import json
        c=self.service.candidate;c["icon_key"]=self.fields["icon_key"].text.strip()
        for key,f in self.fields.items():
            if key=="icon_key":continue
            if isinstance(f,ColourField):c["params"][key]=list(f.value);continue
            raw=f.text.strip()
            try:c["params"][key]=json.loads(raw)
            except Exception:c["params"][key]=raw
    def handle_event(self,event):
        oldkind=self.kind.value
        if self.kind.handle_event(event):
            if oldkind!=self.kind.value:self.refresh()
            return True
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load()
            return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1 and self.service.candidate:
            for r,a,en in reversed(self.actions):
                if en and r.collidepoint(event.pos):
                    if a=="save":self.sync();self.message=self.service.save();self.load()
                    elif a.startswith("footprint_"):
                        size=int(a.rsplit("_",1)[1]);self.service.candidate["slots"]={1:[4],2:[0,1,3,4],3:list(range(9))}[size]
                    return True
        for f in self.fields.values():
            if f.handle_event(event):self.sync();return True
        if event.type==pygame.MOUSEWHEEL:self.scroll=max(0,self.scroll-event.y*35);return True
        return False
    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+24,panel.y+92,330,panel.h-160);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h);self.actions=[];self.kind.rect=pygame.Rect(left.x,left.y,180,30);self.kind.draw(surface,small);self.list.rect=pygame.Rect(left.x,left.y+40,left.w,left.h-40);self.list.draw(surface,small,lambda r:r["label"])
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);surface.blit(font.render("MAP OBJECT EDITOR",True,COLOUR_TEXT),(right.x+14,right.y+10));c=self.service.candidate
        if not c:return
        # Real map icon over the same 3x3 subtile grid used by the renderer.
        gx,gy,cell=right.right-205,right.y+54,54;self.grid_rects=[]
        for i in range(9):
            r=pygame.Rect(gx+(i%3)*cell,gy+(i//3)*cell,cell-3,cell-3);self.grid_rects.append(r);pygame.draw.rect(surface,(55,75,62) if i in c["slots"] else (39,44,47),r);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,r,1)
        uses=c.get("icon_uses") or []
        icon=c["icon_key"] or (uses[0]["icon"] if uses else c.get("automatic_icon_key",""));footprint_size=3 if len(c["slots"])>=9 else 2 if len(c["slots"])>=4 else 1
        recolour=dict(uses[0].get("recolour",{})) if uses else {};edited_recolour={}
        for key,css_class in (("stem_colour","stem"),("flower_colour","flower"),("canopy","leaves"),("sapling_colour","leaves"),("fruit_colour","fruit")):
            field=self.fields.get(key)
            if isinstance(field,ColourField):recolour[css_class]=field.value;edited_recolour[css_class]=field.value
        if icon and variant_names(icon):blit_icon(surface,icon,gx+cell*3//2,gy+cell*3//2,_preview_cell_px(icon,footprint_size,cell),recolour=recolour or None)
        selected_label=f"Selected {footprint_size}×{footprint_size}"
        surface.blit(small.render(selected_label+" · "+c.get("footprint_label","Map icon footprint"),True,COLOUR_TEXT_DIM),(gx,gy+cell*3+5))
        for index,size in enumerate((1,2,3)):
            r=pygame.Rect(gx+index*55,gy+cell*3+25,50,26);selected=footprint_size==size;self.actions.append((r,f"footprint_{size}",True));_button(surface,small,r,f"{size}×{size}" if not selected else f"[{size}×{size}]")
        # Each object remains one list item; all runtime-selected icon/stage
        # combinations are shown here with the season that uses them.
        py=gy+cell*3+60
        for index,use in enumerate(uses[:4]):
            px=gx+index*41;selected_icon=c["icon_key"] or use["icon"];use_recolour=dict(use.get("recolour",{}));use_recolour.update(edited_recolour)
            surface.blit(small.render(use["season"][:3],True,COLOUR_TEXT),(px+7,py))
            if selected_icon and variant_names(selected_icon):blit_icon(surface,selected_icon,px+20,py+34,17,recolour=use_recolour or None)
            surface.blit(small.render(use.get("stage","")[:3],True,COLOUR_TEXT_DIM),(px+7,py+49))
        if uses:surface.blit(small.render("Selected icons · season · stage",True,COLOUR_TEXT_DIM),(gx,py+66))
        clip=pygame.Rect(right.x+2,right.y+42,right.w-230,right.h-95);old=surface.get_clip();surface.set_clip(clip);x,y,fx=right.x+14,right.y+50-self.scroll,right.x+145
        surface.blit(small.render(f"Type: {c['kind']}   Key: {c['key']}",True,(150,190,165)),(x,y));y+=30
        for key,f in self.fields.items():
            surface.blit(small.render(key.replace("_"," ").title(),True,COLOUR_TEXT_DIM),(x,y+6));f.rect=pygame.Rect(fx,y,max(120,clip.right-fx-8),27);f.draw(surface,small);y+=34
        surface.set_clip(old);r=pygame.Rect(right.x+14,right.bottom-43,116,30);self.actions.append((r,"save",True));_button(surface,small,r,"Save")


class WildSpeciesAuthoringPage:
    """Typed form adapter for the existing immutable WildSpeciesDef registry."""
    GROUPS=(
        ("Identity / resource",("key","label","feature","resource_key","yield_amount","crop_key")),
        ("Habitat",("terrains","edge_terrains","seed_near_feature","near_feature","ecology_tags")),
        ("Environmental niche",("temperature_niche","moisture_niche","fertility_niche","disturbance_niche","texture_niche")),
        ("Spawn / spread",("initial_count","initial_fraction","seed_near_chance","spawn_peak","spawn_rise","spawn_fall","spawn_activity","spread_chance","patch_extras","spawn_group")),
        ("Despawn",("despawn_fade","despawn_fade_end","despawn_fade_chance","despawn_leftover_from","despawn_leftover_chance","clear_from_day","clear_ramp_days","counts_toward_cap")),
        ("Fruiting / harvest",("fruiting","fruit_rise","fruit_fall","seed_drop_chance","fruit_class","fruit_colour","empty_fruit_colour")),
        ("Presentation",("icon_recolour",)),
    )
    BOOLS={"counts_toward_cap","fruiting"}
    INTS={"yield_amount","initial_count"}
    PAIRS={"spawn_rise","spawn_fall","patch_extras","despawn_fade","despawn_fade_end","fruit_rise","fruit_fall"}
    NICHES={"temperature_niche","moisture_niche","fertility_niche","disturbance_niche","texture_niche"}
    FLOATS={"initial_fraction","seed_near_chance","spawn_peak","spawn_activity","spread_chance","despawn_fade_chance","despawn_leftover_from","despawn_leftover_chance","clear_from_day","clear_ramp_days","seed_drop_chance"}
    def __init__(self,service,icons):
        self.service=service;self.icons=icons;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=25);self.list.category=lambda s:"Wild crops" if s.crop_key else s.feature.replace("_"," ").title();self.controls={};self.optional_enabled={};self.terrains={};self.icon_colours=[];self.icon_colour_enabled={};self.actions=[];self.scroll=0;self.message="Select a wild species.";self.refresh()
    def refresh(self,key=None):
        self.list.set_items(sorted(self.service.records,key=lambda s:("0" if s.crop_key else s.feature,s.label.casefold())))
        if key:self.list.selected_index=next((i for i,s in enumerate(self.list.items) if s.key==key),None)
    def load(self):
        import re
        from resources import RESOURCES
        from world import FeatureType,TerrainType
        import crops
        c=self.service.candidate;self.controls={};self.optional_enabled={};self.terrains={};self.icon_colours=[];self.icon_colour_enabled={};self.scroll=0
        if c is None:return
        resources=[("","None")]+[(r.key,r.label) for r in RESOURCES]
        # Collapse numbered variants into their logical base and retain the
        # physical folder as a first-class selector category.
        grouped={}
        for entry in self.icons.entries():
            folder=str(entry.paths[0].parent.relative_to(self.icons.icon_root)) if entry.paths else "Other"
            match=re.match(r"^(.*)_([1-9][0-9]*)$",entry.key);logical=match.group(1) if match else entry.key
            grouped.setdefault(folder,set()).add(logical)
        self.icon_by_folder={folder:sorted(names) for folder,names in sorted(grouped.items())}
        current_folder=next((folder for folder,names in self.icon_by_folder.items() if c.icon_base in names),next(iter(self.icon_by_folder),"Other"))
        self.controls["icon_folder"]=Dropdown(pygame.Rect(0,0,1,1),[(folder,folder.replace("_"," ").title()) for folder in self.icon_by_folder],current_folder)
        icons=[(name,name) for name in self.icon_by_folder.get(current_folder,[])]
        crops_opts=[(None,"None")]+[(x.key,x.label) for x in crops.CROPS]
        self.controls["key"]=TextField(pygame.Rect(0,0,1,1),c.key);self.controls["key"].disabled=True
        self.controls["label"]=TextField(pygame.Rect(0,0,1,1),c.label)
        self.controls["feature"]=Dropdown(pygame.Rect(0,0,1,1),[(x.name,x.name.replace("_"," ").title()) for x in FeatureType],c.feature)
        self.controls["resource_key"]=Dropdown(pygame.Rect(0,0,1,1),resources,c.resource_key)
        self.controls["crop_key"]=Dropdown(pygame.Rect(0,0,1,1),crops_opts,c.crop_key)
        self.controls["icon_base"]=Dropdown(pygame.Rect(0,0,1,1),icons,c.icon_base)
        for key in self.INTS:self.controls[key]=IntegerField(pygame.Rect(0,0,1,1),str(getattr(c,key)),minimum=0)
        for key in self.FLOATS:self.controls[key]=FloatField(pygame.Rect(0,0,1,1),str(getattr(c,key)))
        for key in self.BOOLS:self.controls[key]=Checkbox(pygame.Rect(0,0,1,1),getattr(c,key))
        for key in self.PAIRS:self.controls[key]=tuple(FloatField(pygame.Rect(0,0,1,1),str(v)) for v in getattr(c,key))
        for key in self.NICHES:
            n=getattr(c,key);values=(n.minimum,n.optimum_low,n.optimum_high,n.maximum) if n else (0,.25,.75,1);self.controls[key]=tuple(FloatField(pygame.Rect(0,0,1,1),str(v),minimum=0,maximum=1) for v in values);self.optional_enabled[key]=Checkbox(pygame.Rect(0,0,1,1),n is not None)
        for key in ("seed_near_feature","near_feature"):
            value=getattr(c,key);self.controls[key]=Dropdown(pygame.Rect(0,0,1,1),[(None,"None")]+[(x.name,x.name.replace("_"," ").title()) for x in FeatureType],value)
        for key in ("spawn_group","fruit_class"):
            self.controls[key]=TextField(pygame.Rect(0,0,1,1),getattr(c,key) or "")
        self.controls["ecology_tags"]=TextField(pygame.Rect(0,0,1,1),", ".join(c.ecology_tags),placeholder="comma-separated tags")
        for key in ("fruit_colour","empty_fruit_colour"):
            value=getattr(c,key);self.controls[key]=ColourField(pygame.Rect(0,0,1,1),value or (255,255,255));self.optional_enabled[key]=Checkbox(pygame.Rect(0,0,1,1),value is not None)
        self.terrains={"terrains":{},"edge_terrains":{}}
        for group in self.terrains:
            selected=set(getattr(c,group));self.terrains[group]={name:Checkbox(pygame.Rect(0,0,1,1),name in selected) for name in TerrainType.__members__}
        colours=dict(c.icon_recolour)
        if c.crop_key:colours.setdefault("flower",(255,255,255))
        self.icon_colours=[(name,ColourField(pygame.Rect(0,0,1,1),rgb)) for name,rgb in colours.items()]
        self.icon_colour_enabled={name:Checkbox(pygame.Rect(0,0,1,1),name not in self.service.candidate_omit) for name in colours}
    def sync(self):
        from wild_species import NicheRange
        c=self.service.candidate
        if c is None:return
        values={"label":self.controls["label"].text.strip(),"feature":self.controls["feature"].value,"resource_key":self.controls["resource_key"].value or "","crop_key":self.controls["crop_key"].value,"icon_base":self.controls["icon_base"].value or ""}
        for key in self.INTS|self.FLOATS:
            parsed=self.controls[key].parse()
            if parsed is not None:values[key]=parsed
        for key in self.BOOLS:values[key]=self.controls[key].checked
        for key in self.PAIRS:
            parsed=tuple(x.parse() for x in self.controls[key])
            if all(v is not None for v in parsed):values[key]=tuple(int(v) for v in parsed) if key=="patch_extras" else parsed
        for key in self.NICHES:
            controls=self.controls[key]
            if self.optional_enabled[key].checked:
                parsed=tuple(x.parse() for x in controls)
                if all(v is not None for v in parsed):values[key]=NicheRange(*parsed)
            else:values[key]=None
        for key in ("seed_near_feature","near_feature"):values[key]=self.controls[key].value
        for key in ("spawn_group","fruit_class"):values[key]=self.controls[key].text.strip() or None if key=="spawn_group" else self.controls[key].text.strip()
        values["ecology_tags"]=tuple(x.strip() for x in self.controls["ecology_tags"].text.split(",") if x.strip())
        for key in ("fruit_colour","empty_fruit_colour"):
            ctl=self.controls[key];values[key]=ctl.value if self.optional_enabled[key].checked else None
        for group,boxes in self.terrains.items():values[group]=tuple(name for name,box in boxes.items() if box.checked)
        values["icon_recolour"]=tuple((name,ctl.value) for name,ctl in self.icon_colours if self.icon_colour_enabled[name].checked)
        self.service.candidate_omit=[name for name,_ in self.icon_colours if not self.icon_colour_enabled[name].checked]
        self.service.update(**values)
    def act(self,action):
        if action=="crops":return ("show_crops",)
        if action.startswith("footprint_"):
            size=int(action.rsplit("_",1)[1]);self.service.candidate_slots={1:[4],2:[0,1,3,4],3:list(range(9))}[size];return None
        if action=="save":self.sync();result=self.service.save();self.message=result.message;self.refresh(self.service.candidate.key if self.service.candidate else None);self.load();return None
        if action=="cancel":self.service.cancel();self.load();self.message="Unsaved changes cancelled.";return None
        if action=="reload":
            key=self.service.candidate.key if self.service.candidate else None;result=self.service.load();self.message=result.message;self.refresh(key)
            if key:
                item=next((x for x in self.service.records if x.key==key),None)
                if item:self.service.select(item);self.load()
            return None
        if action=="test" and self.service.candidate:return ("test_species",self.service.candidate.key)
    def _all_controls(self):
        out=[]
        for ctl in self.controls.values():
            if isinstance(ctl,tuple):out.extend(ctl)
            elif ctl is not None:out.append(ctl)
        out.extend(self.optional_enabled.values());out.extend(self.icon_colour_enabled.values());out.extend(box for group in self.terrains.values() for box in group.values());out.extend(ctl for _,ctl in self.icon_colours);return out
    def handle_event(self,event):
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for rect,action,enabled in reversed(self.actions):
                if enabled and rect.collidepoint(event.pos):return True,self.act(action)
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load()
            return True,None
        controls=self._all_controls();controls.sort(key=lambda x:not isinstance(x,Dropdown) or not x.open)
        for ctl in controls:
            old_folder=self.controls["icon_folder"].value
            if ctl.handle_event(event):
                if ctl is self.controls["icon_folder"] and ctl.value!=old_folder:
                    names=self.icon_by_folder.get(ctl.value,[]);icon_ctl=self.controls["icon_base"];icon_ctl.options=[(name,name) for name in names]
                    if icon_ctl.value not in names:icon_ctl.value=names[0] if names else None
                self.sync();return True,None
        if event.type==pygame.MOUSEWHEEL:self.scroll=max(0,self.scroll-event.y*40);return True,None
        return False,None
    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+24,panel.y+92,300,panel.h-160);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h);self.actions=[]
        surface.blit(font.render("WILD SPECIES",True,(150,190,165)),(left.x,left.y))
        tab=pygame.Rect(left.right-100,left.y-3,100,28);self.actions.append((tab,"crops",True));_button(surface,small,tab,"Farm Crops")
        # Always-visible presentation controls: icon and footprint should not
        # require scrolling through ecology parameters.
        c=self.service.candidate;preview=pygame.Rect(left.x,left.y+30,left.w,176);pygame.draw.rect(surface,BG,preview);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,preview,1)
        if c is not None:
            icon=c.icon_base
            if not icon and c.crop_key:
                import crops
                crop=crops.CROP_BY_KEY.get(c.crop_key);icon=crop.plant_icon(dense=False) if crop else ""
            slots=self.service.candidate_slots;size=3 if len(slots)>=9 else 2 if len(slots)>=4 else 1;gx,gy,cell=preview.x+12,preview.y+12,32
            for i in range(9):
                rect=pygame.Rect(gx+(i%3)*cell,gy+(i//3)*cell,cell-2,cell-2);pygame.draw.rect(surface,(55,75,62) if i in slots else (39,44,47),rect);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,rect,1)
            recolour=dict(c.icon_recolour)
            if icon and variant_names(icon):blit_icon(surface,icon,gx+cell*3//2,gy+cell*3//2,_preview_cell_px(icon,size,cell),recolour=recolour or None,omit_classes=self.service.candidate_omit)
            surface.blit(small.render("Icon folder",True,COLOUR_TEXT_DIM),(preview.x+120,preview.y+4));folder_ctl=self.controls.get("icon_folder")
            if folder_ctl:folder_ctl.rect=pygame.Rect(preview.x+120,preview.y+21,165,25);folder_ctl.draw(surface,small)
            surface.blit(small.render("Icon",True,COLOUR_TEXT_DIM),(preview.x+120,preview.y+49));icon_ctl=self.controls.get("icon_base")
            if icon_ctl:icon_ctl.rect=pygame.Rect(preview.x+120,preview.y+66,165,25);icon_ctl.draw(surface,small)
            surface.blit(small.render(f"Footprint: {size}×{size}",True,COLOUR_TEXT_DIM),(preview.x+120,preview.y+98))
            for i,n in enumerate((1,2,3)):
                rect=pygame.Rect(preview.x+120+i*55,preview.y+119,50,26);self.actions.append((rect,f"footprint_{n}",True));_button(surface,small,rect,f"[{n}×{n}]" if size==n else f"{n}×{n}")
        self.list.rect=pygame.Rect(left.x,left.y+216,left.w,left.h-216);self.list.draw(surface,small,lambda s:s.label)
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);surface.blit(font.render("WILD SPECIES EDITOR",True,COLOUR_TEXT),(right.x+14,right.y+10))
        if c is None:return
        clip=pygame.Rect(right.x+2,right.y+40,right.w-4,right.h-94);old_clip=surface.get_clip();surface.set_clip(clip);x=right.x+14;fx=right.x+210;y=right.y+47-self.scroll
        def label(text):surface.blit(small.render(text,True,COLOUR_TEXT_DIM),(x,y+5))
        for heading,keys in self.GROUPS:
            surface.blit(font.render(heading.upper(),True,(150,190,165)),(x,y));y+=28
            if heading == "Environmental niche":
                surface.blit(small.render("Four points define tolerance: outside Min/Max = unsuitable; between Ideal from/to = best.",True,COLOUR_TEXT_DIM),(x,y));y+=22
                for i,text in enumerate(NICHE_VALUE_LABELS):surface.blit(small.render(text,True,COLOUR_TEXT_DIM),(fx+25+i*72,y))
                y+=20
            for key in keys:
                label(key.replace("_"," ").title())
                if key in self.terrains:
                    boxes=self.terrains[key]
                    for i,(name,box) in enumerate(boxes.items()):
                        col=i%3;row=i//3;box.rect=pygame.Rect(fx+col*105,y+row*23,17,17);box.draw(surface);surface.blit(small.render(name.title(),True,COLOUR_TEXT),(box.rect.right+3,box.rect.y+1))
                    y+=((len(boxes)+2)//3)*23+5;continue
                if key=="icon_recolour":
                    for name,ctl in self.icon_colours:
                        enabled=self.icon_colour_enabled[name];enabled.rect=pygame.Rect(fx,y+4,18,18);enabled.draw(surface);surface.blit(small.render(name,True,COLOUR_TEXT),(fx+24,y+5));ctl.rect=pygame.Rect(fx+105,y,170,26);ctl.draw(surface,small);surface.blit(small.render("colour" if enabled.checked else "no fill",True,COLOUR_TEXT_DIM),(fx+280,y+5));y+=31
                    if not self.icon_colours:surface.blit(small.render("No recolour classes",True,COLOUR_TEXT_DIM),(fx,y+5));y+=30
                    continue
                ctl=self.controls.get(key)
                if isinstance(ctl,tuple):
                    offset=25 if key in self.optional_enabled else 0
                    if key in self.optional_enabled:self.optional_enabled[key].rect=pygame.Rect(fx,y+3,18,18);self.optional_enabled[key].draw(surface)
                    for i,item in enumerate(ctl):item.rect=pygame.Rect(fx+offset+i*72,y,66,26);item.draw(surface,small)
                    if key in self.NICHES:
                        y+=27;surface.blit(small.render(NICHE_DESCRIPTIONS[key],True,COLOUR_TEXT_DIM),(fx,y));y+=18;continue
                elif isinstance(ctl,Checkbox):ctl.rect=pygame.Rect(fx,y+3,20,20);ctl.draw(surface)
                else:
                    offset=25 if key in self.optional_enabled else 0
                    if key in self.optional_enabled:self.optional_enabled[key].rect=pygame.Rect(fx,y+3,18,18);self.optional_enabled[key].draw(surface)
                    ctl.rect=pygame.Rect(fx+offset,y,min(390-offset,right.right-fx-16-offset),26);ctl.draw(surface,small)
                y+=32
            y+=8
        for ctl in self._all_controls():
            if isinstance(ctl,Dropdown) and ctl.open:ctl.draw(surface,small)
            if isinstance(ctl,ColourField) and ctl.open:ctl.draw(surface,small)
        surface.set_clip(old_clip)
        report=self.service.report;status="✓ Valid" if report.ok else f"✕ {report.errors[0].message}"
        surface.blit(small.render(status,True,GOOD if report.ok else BAD),(right.x+14,right.bottom-69));surface.blit(small.render("● Unsaved" if self.service.dirty else "Saved",True,(226,183,80) if self.service.dirty else GOOD),(right.x+120,right.bottom-69))
        for i,(action,text,enabled) in enumerate((("save","Save",report.ok),("cancel","Cancel",self.service.dirty),("reload","Reload",True),("test","Test",report.ok))):
            rect=pygame.Rect(right.x+14+i*105,right.bottom-40,96,29);self.actions.append((rect,action,enabled));_button(surface,small,rect,text,enabled=enabled)


class CropAuthoringPage:
    """Typed CropDef form with four-season schedule and presentation controls."""
    def __init__(self,service,icons):
        self.service=service;self.icons=icons;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=26);self.list.category=lambda c:"Perennial" if c.perennial else "Annual";self.controls={};self.harvest={};self.phase={};self.season_colour={};self.season_enabled={};self.actions=[];self.scroll=0;self.message="Select a farm crop.";self.refresh()
    def refresh(self,key=None):
        self.list.set_items(sorted(self.service.records,key=lambda c:(not c.perennial,c.label.casefold())))
        if key:self.list.selected_index=next((i for i,c in enumerate(self.list.items) if c.key==key),None)
    def load(self):
        import re
        from crops import SeasonPhase
        from seasons import Season
        c=self.service.candidate;self.controls={};self.scroll=0
        if c is None:return
        grouped={}
        for entry in self.icons.entries():
            folder=str(entry.paths[0].parent.relative_to(self.icons.icon_root)) if entry.paths else "Other";match=re.match(r"^(.*)_([1-9][0-9]*)$",entry.key);grouped.setdefault(folder,set()).add(match.group(1) if match else entry.key)
        self.icon_by_folder={k:sorted(v) for k,v in sorted(grouped.items())};folder=next((k for k,v in self.icon_by_folder.items() if c.icon_base in v),next(iter(self.icon_by_folder),"Other"))
        self.controls["icon_folder"]=Dropdown(pygame.Rect(0,0,1,1),[(x,x.title()) for x in self.icon_by_folder],folder)
        self.controls["icon_base"]=Dropdown(pygame.Rect(0,0,1,1),[(x,x) for x in self.icon_by_folder.get(folder,[])],c.icon_base)
        dense=c.dense_icon_base or f"{c.icon_base}_dense";dense_folder=next((k for k,v in self.icon_by_folder.items() if dense in v),folder)
        self.controls["dense_folder"]=Dropdown(pygame.Rect(0,0,1,1),[(x,x.title()) for x in self.icon_by_folder],dense_folder)
        self.controls["dense_icon_base"]=Dropdown(pygame.Rect(0,0,1,1),[(x,x) for x in self.icon_by_folder.get(dense_folder,[])],dense)
        for key in ("key","label","produce_key","seed_key","short"):self.controls[key]=TextField(pygame.Rect(0,0,1,1),str(getattr(c,key)))
        self.controls["key"].disabled=True
        self.controls["growth_days"]=IntegerField(pygame.Rect(0,0,1,1),str(c.growth_days),minimum=1)
        self.controls["farm_seed_amounts"]=TextField(pygame.Rect(0,0,1,1),", ".join(str(v) for v in c.farm_seed_amounts))
        self.controls["fertility_effect"]=FloatField(pygame.Rect(0,0,1,1),str(c.fertility_effect or 0))
        self.controls["perennial"]=Checkbox(pygame.Rect(0,0,1,1),c.perennial)
        self.controls["plant_season"]=Dropdown(pygame.Rect(0,0,1,1),[(s,s.name.title()) for s in Season],c.plant_season)
        self.controls["stem_colour"]=ColourField(pygame.Rect(0,0,1,1),c.stem_colour)
        self.controls["flower_colour"]=ColourField(pygame.Rect(0,0,1,1),c.flower_colour or (255,255,255));self.controls["flower_fill"]=Checkbox(pygame.Rect(0,0,1,1),c.flower_colour is not None)
        self.harvest={s:Checkbox(pygame.Rect(0,0,1,1),s in c.harvest_seasons) for s in Season}
        self.phase={s:Dropdown(pygame.Rect(0,0,1,1),[(p,p.name.replace("_"," ").title()) for p in SeasonPhase],c.year_phases[list(Season).index(s)]) for s in Season}
        self.season_colour={};self.season_enabled={}
        for s in Season:
            row=self.service.candidate_seasonal.get(s.name,{})
            self.season_enabled[s]=Checkbox(pygame.Rect(0,0,1,1),bool(row))
            self.season_colour[s]={"stem":ColourField(pygame.Rect(0,0,1,1),row.get("stem_colour",c.stem_colour)),"flower":ColourField(pygame.Rect(0,0,1,1),row.get("flower_colour",c.flower_colour or (255,255,255)))}
    def sync(self):
        from seasons import Season
        c=self.service.candidate
        if c is None:return
        amounts=[]
        try:amounts=tuple(int(v.strip()) for v in self.controls["farm_seed_amounts"].text.split(",") if v.strip())
        except ValueError:amounts=c.farm_seed_amounts
        values={k:self.controls[k].text.strip() for k in ("label","produce_key","seed_key","short")};values.update(growth_days=self.controls["growth_days"].parse() or c.growth_days,farm_seed_amounts=amounts,perennial=self.controls["perennial"].checked,plant_season=self.controls["plant_season"].value,harvest_seasons=tuple(s for s,b in self.harvest.items() if b.checked),year_phases=tuple(self.phase[s].value for s in Season),stem_colour=self.controls["stem_colour"].value,flower_colour=self.controls["flower_colour"].value if self.controls["flower_fill"].checked else None,icon_base=self.controls["icon_base"].value or c.icon_base,dense_icon_base=self.controls["dense_icon_base"].value or None,fertility_effect=self.controls["fertility_effect"].parse())
        seasonal={}
        for s in Season:
            # Fallow means no crop object is present, so it cannot own visual
            # overrides. Changing a phase to Fallow removes stale JSON data.
            if self.phase[s].value.name!="FALLOW" and self.season_enabled[s].checked:seasonal[s.name]={"stem_colour":list(self.season_colour[s]["stem"].value),"flower_colour":list(self.season_colour[s]["flower"].value) if self.controls["flower_fill"].checked else None}
        self.service.candidate_seasonal=seasonal;self.service.update(**values)
    def controls_all(self):
        from crops import SeasonPhase
        visible=[s for s,ctl in self.phase.items() if ctl.value!=SeasonPhase.FALLOW]
        return list(self.controls.values())+list(self.harvest.values())+list(self.phase.values())+[self.season_enabled[s] for s in visible]+[v for s in visible for v in self.season_colour[s].values()]
    def act(self,action):
        if action=="wild":return ("show_wild",)
        if action.startswith("footprint_"):self.service.candidate_slots={1:[4],2:[0,1,3,4],3:list(range(9))}[int(action[-1])];return None
        if action=="save":self.sync();ok,msg=self.service.save();self.message=msg;self.refresh(self.service.candidate.key);self.load();return None
        if action=="cancel":self.service.cancel();self.load();self.message="Unsaved changes cancelled.";return None
        if action=="reload":key=self.service.candidate.key if self.service.candidate else None;ok,self.message=self.service.load();self.refresh(key);item=next((x for x in self.service.records if x.key==key),None);self.service.select(item) if item else None;self.load();return None
        if action=="test" and self.service.candidate:return ("test_crop",self.service.candidate.key)
    def handle_event(self,event):
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for rect,action,enabled in reversed(self.actions):
                if enabled and rect.collidepoint(event.pos):return True,self.act(action)
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load()
            return True,None
        controls=self.controls_all();controls.sort(key=lambda x:not isinstance(x,Dropdown) or not x.open)
        for ctl in controls:
            if ctl.handle_event(event):
                if ctl is self.controls.get("icon_folder"):
                    names=self.icon_by_folder.get(ctl.value,[]);target=self.controls["icon_base"];target.options=[(x,x) for x in names]
                    if target.value not in names:target.value=names[0] if names else None
                elif ctl is self.controls.get("dense_folder"):
                    names=self.icon_by_folder.get(ctl.value,[]);target=self.controls["dense_icon_base"];target.options=[(x,x) for x in names]
                    if target.value not in names:target.value=names[0] if names else None
                self.sync();return True,None
        if event.type==pygame.MOUSEWHEEL:self.scroll=max(0,self.scroll-event.y*40);return True,None
        return False,None
    def draw(self,surface,panel,font,small):
        from seasons import Season
        left=pygame.Rect(panel.x+24,panel.y+92,300,panel.h-160);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h);self.actions=[]
        surface.blit(font.render("FARM CROPS",True,(150,190,165)),(left.x,left.y));tab=pygame.Rect(left.right-110,left.y-3,110,28);self.actions.append((tab,"wild",True));_button(surface,small,tab,"Wild Species")
        self.list.rect=pygame.Rect(left.x,left.y+36,left.w,left.h-36);self.list.draw(surface,small,lambda c:c.label)
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);surface.blit(font.render("FARM CROP EDITOR",True,COLOUR_TEXT),(right.x+14,right.y+10));c=self.service.candidate
        if c is None:return
        clip=pygame.Rect(right.x+2,right.y+40,right.w-4,right.h-94);old=surface.get_clip();surface.set_clip(clip);x=right.x+14;fx=right.x+190;y=right.y+48-self.scroll
        def row(label,ctl):
            nonlocal y
            surface.blit(small.render(label,True,COLOUR_TEXT_DIM),(x,y+5));ctl.rect=pygame.Rect(fx,y,min(370,right.right-fx-14),26);ctl.draw(surface,small) if not isinstance(ctl,Checkbox) else ctl.draw(surface);y+=32
        for heading,keys in (("Identity / resource",("key","label","produce_key","seed_key","short")),("Growth / yield",("growth_days","farm_seed_amounts","fertility_effect","perennial")),("Presentation",("icon_folder","icon_base","dense_folder","dense_icon_base","stem_colour","flower_fill","flower_colour"))):
            surface.blit(font.render(heading.upper(),True,(150,190,165)),(x,y));y+=28
            for key in keys:row(key.replace("_"," ").title(),self.controls[key])
            y+=8
        surface.blit(font.render("SEASONALITY",True,(150,190,165)),(x,y));y+=30
        row("Plant season",self.controls["plant_season"])
        for s in Season:
            surface.blit(small.render(s.name.title(),True,COLOUR_TEXT),(x,y+5));self.harvest[s].rect=pygame.Rect(fx,y+3,18,18);self.harvest[s].draw(surface);surface.blit(small.render("Harvest",True,COLOUR_TEXT_DIM),(fx+23,y+5));self.phase[s].rect=pygame.Rect(fx+100,y,190,26);self.phase[s].draw(surface,small);y+=32
        surface.blit(font.render("SEASONAL COLOURS",True,(150,190,165)),(x,y));y+=30
        for s in Season:
            if self.phase[s].value.name=="FALLOW":continue
            enabled=self.season_enabled[s];enabled.rect=pygame.Rect(x,y+3,18,18);enabled.draw(surface);surface.blit(small.render(s.name.title(),True,COLOUR_TEXT),(x+24,y+5));stem=self.season_colour[s]["stem"];flower=self.season_colour[s]["flower"];stem.rect=pygame.Rect(fx,y,145,26);flower.rect=pygame.Rect(fx+153,y,145,26);stem.draw(surface,small);flower.draw(surface,small)
            icon=c.plant_icon(dense=self.phase[s].value.name.startswith("HARVEST"));palette={"stem":stem.value};omit=()
            if self.controls["flower_fill"].checked:palette["flower"]=flower.value
            else:omit=("flower",)
            if icon and variant_names(icon):blit_icon(surface,icon,right.right-38,y+13,24,recolour=palette,omit_classes=omit)
            y+=34
        surface.set_clip(old);report=self.service.report;surface.blit(small.render("✓ Valid" if report.ok else "✕ Invalid",True,GOOD if report.ok else BAD),(right.x+14,right.bottom-69));surface.blit(small.render("● Unsaved" if self.service.dirty else "Saved",True,(226,183,80) if self.service.dirty else GOOD),(right.x+110,right.bottom-69))
        for i,(action,text,enabled) in enumerate((("save","Save",report.ok),("cancel","Cancel",self.service.dirty),("reload","Reload",True),("test","Test",report.ok))):
            rect=pygame.Rect(right.x+14+i*105,right.bottom-40,96,29);self.actions.append((rect,action,enabled));_button(surface,small,rect,text,enabled=enabled)


class PlantAuthoringPage:
    """One editor record projected into cultivated, wild, and tree runtimes."""
    WILD_FLOATS=("initial_fraction","seed_near_chance","spawn_peak","spawn_activity","spread_chance","despawn_fade_chance","despawn_leftover_from","despawn_leftover_chance","clear_from_day","clear_ramp_days","seed_drop_chance")
    NICHES=("temperature_niche","moisture_niche","fertility_niche","disturbance_niche","texture_niche")
    def __init__(self,service,icons):self.service=service;self.icons=icons;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=26);self.list.category=lambda p:p.growth_form.title();self.search=TextField(pygame.Rect(0,0,1,1),placeholder="Search plants");self.controls={};self.harvest={};self.phases={};self.season_colours={};self.presentation_colours={};self.presentation_enabled={};self.season_presentation={};self.season_presentation_enabled={};self.terrains={};self.edge_terrains={};self.niches={};self.collapsed={"cultivation":False,"wild":False};self.delete_armed=False;self.actions=[];self.scroll=0;self.message="Select a plant or create a new one.";self.refresh()
    def refresh(self,key=None):
        query=self.search.text.strip().casefold();order={"annual herb":0,"perennial herb":1,"shrub":2,"tree":3};items=[p for p in self.service.records if not query or query in p.label.casefold() or query in p.key.casefold()];self.list.set_items(sorted(items,key=lambda p:(order.get(p.growth_form,99),p.label.casefold())))
        if key:self.list.selected_index=next((i for i,p in enumerate(self.list.items) if p.key==key),None)
    def load(self):
        from crops import SeasonPhase
        from seasons import Season
        from world import TerrainType
        p=self.service.candidate;self.controls={};self.harvest={};self.phases={};self.season_colours={};self.presentation_colours={};self.presentation_enabled={};self.season_presentation={};self.season_presentation_enabled={};self.terrains={};self.edge_terrains={};self.niches={};self.scroll=0
        if not p:return
        rect=pygame.Rect(0,0,1,1);text=lambda v:TextField(rect,str(v or ""))
        for k in ("key","label","short","produce_resource","seed_resource"):self.controls[k]=text(getattr(p,k))
        if self.service.original:self.controls["key"].disabled=True
        self.controls["growth_form"]=Dropdown(rect,[(x,x.title()) for x in ("annual herb","perennial herb","shrub","tree")],p.growth_form)
        self.controls["perennial"]=Checkbox(rect,p.perennial);self.controls["can_be_cultivated"]=Checkbox(rect,p.can_be_cultivated);self.controls["can_grow_wild"]=Checkbox(rect,p.can_grow_wild)
        self.controls["harvest_amount"]=IntegerField(rect,str((p.harvest_outputs or {}).get(p.produce_resource,1)),minimum=0)
        c=p.cultivated
        amounts=c.get("seed_amounts",[1,2,3]) or [1]
        harvest_name=c.get("harvest_season") or next(iter(c.get("harvest_seasons",["SUMMER"])),"SUMMER")
        self.controls["plant_season"]=Dropdown(rect,[(s.name,s.name.title()) for s in Season],c.get("plant_season","SPRING"));self.controls["harvest_season"]=Dropdown(rect,[(s.name,s.name.title()) for s in Season],harvest_name);self.controls["growth_days"]=IntegerField(rect,str(c.get("growth_days",32)),minimum=1);self.controls["seed_min"]=IntegerField(rect,str(min(amounts)),minimum=0);self.controls["seed_max"]=IntegerField(rect,str(max(amounts)),minimum=0);self.controls["cultivated_harvest_max"]=IntegerField(rect,str(c.get("harvest_max",9)),minimum=1);self.controls["fertility_effect"]=FloatField(rect,str(c.get("fertility_effect") or 0));self.controls["sparse_icon"]=Dropdown(rect,self._icon_options(),c.get("sparse_icon","crop_plant"));self.controls["dense_icon"]=Dropdown(rect,self._icon_options(),c.get("dense_icon","crop_plant_dense"));self.controls["stem_colour"]=ColourField(rect,c.get("stem_colour",(80,140,70)));self.controls["flower_colour"]=ColourField(rect,c.get("flower_colour") or (255,255,255));self.controls["flower_fill"]=Checkbox(rect,c.get("flower_colour") is not None)
        harvest=set(c.get("harvest_seasons",["SUMMER"]));phases=c.get("year_phases",["PLOUGH_PLANT","HARVEST","FALLOW","FALLOW"]);self.harvest={s:Checkbox(rect,s.name in harvest) for s in Season};self.phases={s:Dropdown(rect,[(x,x.name.replace("_"," ").title()) for x in SeasonPhase],SeasonPhase[phases[i]] if isinstance(phases[i],str) else phases[i]) for i,s in enumerate(Season)};seasonal=c.get("seasonal_recolour",{});self.season_colours={s:(ColourField(rect,seasonal.get(s.name,{}).get("stem_colour",c.get("stem_colour",(80,140,70)))),ColourField(rect,seasonal.get(s.name,{}).get("flower_colour") or c.get("flower_colour") or (255,255,255))) for s in Season}
        w=p.wild;tree_icon=p.tree.get("wild_icon") or ("tree_cone" if p.tree.get("shape")=="cone" else "tree_round");wild_icon=w.get("icon") or (tree_icon if p.growth_form=="tree" else "flower_plant")
        if p.growth_form=="tree" and not w.get("recolour"):w=dict(w);w["recolour"]={"canopy":p.tree.get("canopy_colour",(50,130,60)),"trunk":(105,75,45)}
        self.terrains={name:Checkbox(rect,name in w.get("terrains",["GRASS"])) for name in TerrainType.__members__};self.edge_terrains={name:Checkbox(rect,name in w.get("edge_terrains",[])) for name in TerrainType.__members__};self.controls["wild_icon"]=Dropdown(rect,self._icon_options(),wild_icon);self.controls["wild_stem"]=ColourField(rect,w.get("recolour",{}).get("stem",(70,140,70)));self.controls["wild_flower"]=ColourField(rect,w.get("recolour",{}).get("flower",(230,230,220)));self.controls["wild_flower_fill"]=Checkbox(rect,"flower" not in w.get("omit_classes",[]));self.controls["wild_harvest_max"]=IntegerField(rect,str(w.get("harvest_max",3)),minimum=1);self.controls["wild_seed_amount_max"]=IntegerField(rect,str(w.get("seed_amount_max",1)),minimum=1);self.controls["counts_toward_cap"]=Checkbox(rect,w.get("counts_toward_cap",True));self.controls["initial_count"]=IntegerField(rect,str(w.get("initial_count",0)),minimum=0);self.controls["patch_extras"]=text(", ".join(str(x) for x in w.get("patch_extras",[0,0])))
        for k in self.WILD_FLOATS:self.controls[k]=FloatField(rect,str(w.get(k,1/3 if k=="seed_drop_chance" else 0)))
        self.niches={k:tuple(FloatField(rect,str(x),minimum=0,maximum=1) for x in (w.get(k) or [0,.25,.75,1])) for k in self.NICHES}
        t=p.tree;self.controls["growth_years"]=FloatField(rect,str(t.get("growth_years",2)),minimum=.01);self.controls["wood_resource"]=text(t.get("wood_resource","logs"));self.controls["wood_yield"]=IntegerField(rect,str(t.get("wood_yield",2)),minimum=0);self.controls["canopy_colour"]=ColourField(rect,t.get("canopy_colour",(50,130,60)));self.controls["sapling_colour"]=ColourField(rect,t.get("sapling_colour",(120,190,90)));self.controls["tree_shape"]=Dropdown(rect,[("round","Round"),("cone","Cone")],t.get("shape","round"));self.controls["cone_scale"]=FloatField(rect,str(t.get("cone_scale",1)),minimum=.1)
        self._build_presentation_controls()
    def _icon_options(self):
        import re
        out=[]
        for e in self.icons.entries():
            folder=str(e.paths[0].parent.relative_to(self.icons.icon_root)) if e.paths else "Other";m=re.match(r"^(.*)_([1-9][0-9]*)$",e.key);key=m.group(1) if m else e.key
            if (key,f"[{folder}] {key}") not in out:out.append((key,f"[{folder}] {key}"))
        return out
    def _build_presentation_controls(self):
        from icons import icon_svg_classes,icon_svg_class_styles
        from seasons import Season
        rect=pygame.Rect(0,0,1,1);p=self.service.candidate
        if p is None:return
        wild_classes=icon_svg_classes(self.controls["wild_icon"].value or "") or ("fill",)
        farm_classes=tuple(sorted(set(icon_svg_classes(self.controls["sparse_icon"].value or ""))|set(icon_svg_classes(self.controls["dense_icon"].value or "")))) or ("fill",)
        wild_styles=icon_svg_class_styles(self.controls["wild_icon"].value or "");farm_styles={**icon_svg_class_styles(self.controls["sparse_icon"].value or ""),**icon_svg_class_styles(self.controls["dense_icon"].value or "")}
        self.presentation_colours={"wild":{},"farm":{}};self.presentation_enabled={"wild":{},"farm":{}}
        wild_data=p.wild
        if p.growth_form=="tree" and not wild_data.get("recolour"):wild_data={**wild_data,"recolour":{"canopy":p.tree.get("canopy_colour",(50,130,60)),"trunk":(105,75,45)}}
        for mode,classes,data,defaults,styles in (("wild",wild_classes,wild_data,{"stem":(70,140,70),"flower":(230,230,220),"canopy":(50,130,60),"trunk":(105,75,45)},wild_styles),("farm",farm_classes,p.cultivated,{"stem":(80,140,70),"flower":(255,255,255)},farm_styles)):
            colours=data.get("recolour",{});omit=set(data.get("omit_classes",()))
            for name in classes:
                authored=styles.get(name,(255,255,255,255));value=colours.get(name,data.get(name+"_colour")) or defaults.get(name,authored)
                if len(value)==3:value=tuple(value)+(authored[3],)
                self.presentation_colours[mode][name]=ColourField(rect,value);self.presentation_enabled[mode][name]=Checkbox(rect,name not in omit)
        seasonal=p.cultivated.get("seasonal_recolour",{});self.season_presentation={};self.season_presentation_enabled={}
        for season in Season:
            row=seasonal.get(season.name,{}) or {};recolour=row.get("recolour",{})
            explicit=set(recolour)
            if not recolour:
                recolour={name:row.get(name+"_colour",self.presentation_colours["farm"][name].value) for name in farm_classes}
                explicit={name for name in farm_classes if name+"_colour" in row and row.get(name+"_colour") is not None}
            omit=set(row.get("omit_classes",p.cultivated.get("omit_classes",())))
            for name in explicit:omit.discard(name)
            self.season_presentation[season]={name:ColourField(rect,recolour.get(name,self.presentation_colours["farm"][name].value)) for name in farm_classes}
            self.season_presentation_enabled[season]={name:Checkbox(rect,name not in omit) for name in farm_classes}
    def sync(self):
        from seasons import Season
        p=self.service.candidate
        if not p:return
        key=self.controls["key"].text.strip();produce=self.controls["produce_resource"].text.strip();amount=self.controls["harvest_amount"].parse() or 0
        seed_min=self.controls["seed_min"].parse();seed_max=self.controls["seed_max"].parse();seed_min=seed_min if seed_min is not None else 1;seed_max=max(seed_min,seed_max if seed_max is not None else seed_min)
        plant=self.controls["plant_season"].value;harvest_season=self.controls["harvest_season"].value;year_phases=self._derived_year_phases(plant,harvest_season)
        farm_recolour={name:list(ctl.value) for name,ctl in self.presentation_colours["farm"].items() if self.presentation_enabled["farm"][name].checked};farm_omit=[name for name,ctl in self.presentation_enabled["farm"].items() if not ctl.checked]
        c=dict(p.cultivated);c.update(plant_season=plant,harvest_season=harvest_season,harvest_seasons=[harvest_season],harvest_max=self.controls["cultivated_harvest_max"].parse() or 9,growth_days=self.controls["growth_days"].parse() or 1,year_phases=year_phases,seed_amounts=list(range(seed_min,seed_max+1)),fertility_effect=self.controls["fertility_effect"].parse(),sparse_icon=self.controls["sparse_icon"].value,dense_icon=self.controls["dense_icon"].value,recolour=farm_recolour,omit_classes=farm_omit,stem_colour=farm_recolour.get("stem",list(self.controls["stem_colour"].value)),flower_colour=farm_recolour.get("flower"))
        c["seasonal_recolour"]={s.name:{"recolour":{name:list(ctl.value) for name,ctl in self.season_presentation[s].items() if self.season_presentation_enabled[s][name].checked},"omit_classes":[name for name,ctl in self.season_presentation_enabled[s].items() if not ctl.checked]} for s,phase in zip(Season,year_phases) if phase!="FALLOW"}
        wild_recolour={name:list(ctl.value) for name,ctl in self.presentation_colours["wild"].items() if self.presentation_enabled["wild"][name].checked};wild_omit=[name for name,ctl in self.presentation_enabled["wild"].items() if not ctl.checked]
        w=dict(p.wild);w.update(terrains=[k for k,b in self.terrains.items() if b.checked],edge_terrains=[k for k,b in self.edge_terrains.items() if b.checked],icon=self.controls["wild_icon"].value,recolour=wild_recolour,omit_classes=wild_omit,harvest_max=self.controls["wild_harvest_max"].parse() or 3,seed_amount_max=self.controls["wild_seed_amount_max"].parse() or 1,counts_toward_cap=self.controls["counts_toward_cap"].checked,initial_count=self.controls["initial_count"].parse() or 0,patch_extras=self._ints(self.controls["patch_extras"].text,[0,0]))
        for k in self.WILD_FLOATS:
            v=self.controls[k].parse()
            if v is not None:w[k]=v
        for k,items in self.niches.items():w[k]=[x.parse() for x in items]
        t=dict(p.tree);t.update(growth_years=self.controls["growth_years"].parse() or 1,wood_resource=self.controls["wood_resource"].text.strip(),wood_yield=self.controls["wood_yield"].parse() or 0,canopy_colour=list(self.controls["canopy_colour"].value),sapling_colour=list(self.controls["sapling_colour"].value),shape=self.controls["tree_shape"].value,cone_scale=self.controls["cone_scale"].parse() or 1)
        self.service.update(key=key,label=self.controls["label"].text.strip(),short=self.controls["short"].text.strip(),growth_form=self.controls["growth_form"].value,produce_resource=produce,seed_resource=self.controls["seed_resource"].text.strip(),perennial=self.controls["perennial"].checked,harvest_outputs={produce:amount} if produce else {},can_be_cultivated=self.controls["can_be_cultivated"].checked,can_grow_wild=self.controls["can_grow_wild"].checked,cultivated=c,wild=w,tree=t)
    @staticmethod
    def _derived_year_phases(plant,harvest):
        names=("SPRING","SUMMER","AUTUMN","WINTER");pi=names.index(plant);hi=names.index(harvest);out=[]
        for i,name in enumerate(names):
            if i==pi==hi:out.append("HARVEST_PLOUGH_PLANT")
            elif i==pi:out.append("PLOUGH_PLANT")
            elif i==hi:out.append("HARVEST")
            elif (i-pi)%4 < (hi-pi)%4:out.append("GROW")
            else:out.append("FALLOW")
        return out
    @staticmethod
    def _ints(text,default):
        try:return [int(x.strip()) for x in text.split(",") if x.strip()]
        except ValueError:return default
    def _all(self):return list(self.controls.values())+list(self.harvest.values())+list(self.phases.values())+[x for pair in self.season_colours.values() for x in pair]+[x for mode in self.presentation_colours.values() for x in mode.values()]+[x for mode in self.presentation_enabled.values() for x in mode.values()]+[x for season in self.season_presentation.values() for x in season.values()]+[x for season in self.season_presentation_enabled.values() for x in season.values()]+list(self.terrains.values())+list(self.edge_terrains.values())+[x for group in self.niches.values() for x in group]
    def handle_event(self,event):
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for r,a,en in reversed(self.actions):
                if en and r.collidepoint(event.pos):return True,self.act(a)
        old_query=self.search.text
        if self.search.handle_event(event):
            if self.search.text!=old_query:self.refresh()
            return True,None
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.service.select(self.list.selected);self.load()
            return True,None
        controls=self._all();controls.sort(key=lambda x:not isinstance(x,Dropdown) or not x.open)
        for ctl in controls:
            if ctl.handle_event(event):
                icon_changed=ctl in (self.controls.get("wild_icon"),self.controls.get("sparse_icon"),self.controls.get("dense_icon"))
                self.sync()
                if icon_changed:
                    saved_scroll=self.scroll;self._build_presentation_controls();self.scroll=saved_scroll
                return True,None
        if event.type==pygame.MOUSEWHEEL:self.scroll=max(0,self.scroll-event.y*40);return True,None
        return False,None
    def act(self,a):
        if a=="new":self.service.new();self.load();self.message="New unsaved plant.";return None
        if a=="duplicate":
            ok,self.message=self.service.duplicate()
            if ok:self.load()
            return None
        if a=="delete":
            if not self.delete_armed:self.delete_armed=True;self.message="Click Delete again to confirm.";return None
            ok,self.message=self.service.delete();self.delete_armed=False;self.refresh();self.load();return None
        if a in ("collapse_cultivation","collapse_wild"):
            key=a.removeprefix("collapse_");self.collapsed[key]=not self.collapsed[key];return None
        if a.startswith("fp_"):
            _,mode,size=a.split("_");target=self.service.candidate.cultivated if mode=="farm" else self.service.candidate.wild;target["footprint"]={"1":[4],"2":[0,1,3,4],"3":list(range(9))}[size];self.sync();return None
        if a=="save":self.sync();ok,self.message=self.service.save();self.refresh(self.service.candidate.key);return None
        if a=="cancel":self.service.cancel();self.load();return None
        if a=="reload":ok,self.message=self.service.load();self.refresh();return None
        if a=="test" and self.service.candidate:return ("test_plant",self.service.candidate.key)
    def draw(self,surface,panel,font,small):
        from seasons import Season
        left=pygame.Rect(panel.x+24,panel.y+72,245,panel.h-140);right=pygame.Rect(left.right+12,left.y,panel.right-left.right-36,left.h);self.actions=[]
        for i,(action,label,enabled) in enumerate((("new","New Plant",True),("duplicate","Duplicate",self.service.candidate is not None))):
            rect=pygame.Rect(left.x+i*124,left.y,117,29);self.actions.append((rect,action,enabled));_button(surface,small,rect,label,enabled=enabled)
        self.search.rect=pygame.Rect(left.x,left.y+37,left.w,29);self.search.draw(surface,small)
        self.list.rect=pygame.Rect(left.x,left.y+74,left.w,left.h-74);self.list.draw(surface,small,lambda item:item.label)
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1);p=self.service.candidate
        if not p:
            surface.blit(font.render("Select a plant or choose New Plant",True,COLOUR_TEXT_DIM),(right.x+18,right.y+55));return
        surface.blit(font.render(p.label,True,COLOUR_TEXT),(right.x+16,right.y+12));surface.blit(small.render(f"key: {p.key}  {'🔒' if self.service.original else '(new)' }",True,COLOUR_TEXT_DIM),(right.x+16,right.y+38))
        delete=pygame.Rect(right.right-126,right.y+65,110,27);self.actions.append((delete,"delete",True));_button(surface,small,delete,"Confirm Delete" if self.delete_armed else "Delete",hot=self.delete_armed)
        self.controls["growth_form"].rect=pygame.Rect(right.x+190,right.y+10,190,27);self.controls["growth_form"].draw(surface,small)
        for i,(key,label) in enumerate((("can_be_cultivated","Cultivated"),("can_grow_wild","Wild"))):
            ctl=self.controls[key];ctl.rect=pygame.Rect(right.x+400+i*120,right.y+14,18,18);ctl.draw(surface);surface.blit(small.render(label,True,COLOUR_TEXT),(ctl.rect.right+4,ctl.rect.y+1))
        report=self.service.report
        for i,(action,label,enabled) in enumerate((("save","Save",report.ok),("cancel","Cancel",self.service.dirty),("test","Test",report.ok))):
            rect=pygame.Rect(right.x+16+i*91,right.y+66,84,27);self.actions.append((rect,action,enabled));_button(surface,small,rect,label,enabled=enabled)
        clip=pygame.Rect(right.x+2,right.y+105,right.w-4,right.h-109);old=surface.get_clip();surface.set_clip(clip);x=right.x+16;fx=right.x+190;y=right.y+112-self.scroll
        def divider(title,collapse=None):
            nonlocal y
            pygame.draw.line(surface,COLOUR_TOOLBAR_BORDER,(x,y+8),(right.right-16,y+8));y+=18;surface.blit(font.render(title,True,(150,190,165)),(x,y));
            if collapse:
                rect=pygame.Rect(right.right-112,y-2,96,25);self.actions.append((rect,"collapse_"+collapse,True));_button(surface,small,rect,"Expand" if self.collapsed[collapse] else "Collapse")
            y+=31
        def row(label,ctl,width=None):
            nonlocal y
            surface.blit(small.render(label,True,COLOUR_TEXT_DIM),(x,y+5));ctl.rect=pygame.Rect(fx,y,width or min(380,right.right-fx-18),26);ctl.draw(surface,small) if not isinstance(ctl,Checkbox) else ctl.draw(surface);y+=32
        def footprint(mode,slots):
            nonlocal y
            size=3 if len(slots)>=9 else 2 if len(slots)>=4 else 1;surface.blit(small.render("Footprint",True,COLOUR_TEXT_DIM),(x,y+5))
            for index,n in enumerate((1,2,3)):
                rect=pygame.Rect(fx+index*61,y,55,25);self.actions.append((rect,f"fp_{mode}_{n}",True));_button(surface,small,rect,f"[{n}×{n}]" if n==size else f"{n}×{n}")
            y+=33
        divider("SHARED")
        row("ID / key",self.controls["key"])
        for key in ("label","short","produce_resource","seed_resource","perennial","harvest_amount"):row(key.replace("_"," ").title(),self.controls[key])
        divider("PRESENTATION")
        if p.can_grow_wild:
            surface.blit(font.render("Wild",True,COLOUR_TEXT),(x,y));y+=27;row("Icon",self.controls["wild_icon"],300)
            icon=self.controls["wild_icon"].value
            wild_palette={name:ctl.value for name,ctl in self.presentation_colours["wild"].items() if self.presentation_enabled["wild"][name].checked};wild_omit=[name for name,ctl in self.presentation_enabled["wild"].items() if not ctl.checked]
            if icon and variant_names(icon):blit_icon(surface,icon,right.right-45,y-14,34,recolour=wild_palette,omit_classes=wild_omit)
            for name,ctl in self.presentation_colours["wild"].items():
                enabled=self.presentation_enabled["wild"][name];enabled.rect=pygame.Rect(x,y+4,18,18);enabled.draw(surface);surface.blit(small.render(name,True,COLOUR_TEXT),(x+25,y+5));ctl.rect=pygame.Rect(fx,y,180,26);ctl.draw(surface,small);surface.blit(small.render("on" if enabled.checked else "off",True,COLOUR_TEXT_DIM),(fx+188,y+5));y+=31
            footprint("wild",p.wild.get("footprint",[4]))
        if p.can_be_cultivated:
            surface.blit(font.render("Cultivated",True,COLOUR_TEXT),(x,y));y+=27
            for key,label in (("sparse_icon","Sparse icon"),("dense_icon","Dense icon")):
                row(label,self.controls[key],300);icon=self.controls[key].value
                cultivated_recolour={name:ctl.value for name,ctl in self.presentation_colours["farm"].items() if self.presentation_enabled["farm"][name].checked};cultivated_omit=[name for name,ctl in self.presentation_enabled["farm"].items() if not ctl.checked]
                if icon and variant_names(icon):blit_icon(surface,icon,right.right-45,y-16,34,recolour=cultivated_recolour,omit_classes=cultivated_omit)
            for name,ctl in self.presentation_colours["farm"].items():
                enabled=self.presentation_enabled["farm"][name];enabled.rect=pygame.Rect(x,y+4,18,18);enabled.draw(surface);surface.blit(small.render(name,True,COLOUR_TEXT),(x+25,y+5));ctl.rect=pygame.Rect(fx,y,180,26);ctl.draw(surface,small);surface.blit(small.render("on" if enabled.checked else "off",True,COLOUR_TEXT_DIM),(fx+188,y+5));y+=31
            footprint("farm",p.cultivated.get("footprint",list(range(9))))
            surface.blit(small.render("Seasonal colours",True,COLOUR_TEXT_DIM),(x,y+7))
            y+=27;derived=self._derived_year_phases(self.controls["plant_season"].value,self.controls["harvest_season"].value)
            for s,phase in zip(Season,derived):
                if phase=="FALLOW":continue
                surface.blit(small.render(s.name.title(),True,COLOUR_TEXT),(x,y+5));seasonal_recolour={};seasonal_omit=[]
                for index,(name,ctl) in enumerate(self.season_presentation[s].items()):
                    enabled=self.season_presentation_enabled[s][name];enabled.rect=pygame.Rect(fx+index*145,y+4,17,17);enabled.draw(surface);surface.blit(small.render(name[:5],True,COLOUR_TEXT),(enabled.rect.right+2,y+5));ctl.rect=pygame.Rect(enabled.rect.x+60,y,78,26);ctl.draw(surface,small)
                    if enabled.checked:seasonal_recolour[name]=ctl.value
                    else:seasonal_omit.append(name)
                icon=self.controls["dense_icon"].value if phase.startswith("HARVEST") else self.controls["sparse_icon"].value
                if icon and variant_names(icon):blit_icon(surface,icon,right.right-35,y+13,24,recolour=seasonal_recolour,omit_classes=seasonal_omit)
                y+=32
        if p.can_be_cultivated:
            divider("CULTIVATION","cultivation")
            if not self.collapsed["cultivation"]:
                row("Plant season",self.controls["plant_season"])
                row("Harvest season",self.controls["harvest_season"]);row("Growth duration (days)",self.controls["growth_days"]);row("Maximum harvest",self.controls["cultivated_harvest_max"])
                surface.blit(small.render("Seed amount",True,COLOUR_TEXT_DIM),(x,y+5));self.controls["seed_min"].rect=pygame.Rect(fx,y,75,26);self.controls["seed_min"].draw(surface,small);surface.blit(small.render("–",True,COLOUR_TEXT),(fx+82,y+5));self.controls["seed_max"].rect=pygame.Rect(fx+100,y,75,26);self.controls["seed_max"].draw(surface,small);y+=32
                row("Fertility effect",self.controls["fertility_effect"]);surface.blit(small.render("Year plan is derived from plant and harvest season.",True,COLOUR_TEXT_DIM),(x,y));y+=27
        if p.can_grow_wild:
            divider("WILD ECOLOGY","wild")
            if not self.collapsed["wild"]:
                for title,boxes in (("Terrains",self.terrains),("Edge terrains",self.edge_terrains)):
                    surface.blit(small.render(title,True,COLOUR_TEXT_DIM),(x,y+4))
                    for index,(name,ctl) in enumerate(boxes.items()):col=index%4;line=index//4;ctl.rect=pygame.Rect(fx+col*92,y+line*22,17,17);ctl.draw(surface);surface.blit(small.render(name[:7].title(),True,COLOUR_TEXT),(ctl.rect.right+2,ctl.rect.y))
                    y+=((len(boxes)+3)//4)*22+7
                surface.blit(font.render("Environmental niche",True,COLOUR_TEXT),(x,y));y+=28
                surface.blit(small.render("Outside Min/Max: cannot establish. Ideal from-to: full suitability.",True,COLOUR_TEXT_DIM),(x,y));y+=20
                for i,text in enumerate(NICHE_VALUE_LABELS):surface.blit(small.render(text,True,COLOUR_TEXT_DIM),(fx+i*76,y))
                y+=20
                for name,items in self.niches.items():
                    surface.blit(small.render(name.replace("_niche","").title(),True,COLOUR_TEXT_DIM),(x,y+5))
                    for i,item in enumerate(items):item.rect=pygame.Rect(fx+i*76,y,69,25);item.draw(surface,small)
                    y+=27;surface.blit(small.render(NICHE_DESCRIPTIONS[name],True,COLOUR_TEXT_DIM),(fx,y));y+=19
                for key,label in (("spawn_peak","Spawn chance"),("spread_chance","Spread chance"),("patch_extras","Patch extras"),("wild_harvest_max","Maximum wild harvest"),("seed_drop_chance","Seed drop chance"),("wild_seed_amount_max","Maximum wild seed amount")):row(label,self.controls[key])
                surface.blit(font.render("Advanced spawn / despawn",True,COLOUR_TEXT),(x,y));y+=27
                for key in self.WILD_FLOATS:
                    if key not in {"spawn_peak","spread_chance","seed_drop_chance"}:row(key.replace("_"," ").title(),self.controls[key])
        if p.growth_form=="tree":divider("TREE");[row(k.replace("_"," ").title(),self.controls[k]) for k in ("growth_years","wood_resource","wood_yield","canopy_colour","sapling_colour","tree_shape","cone_scale")]
        for ctl in self._all():
            if isinstance(ctl,(Dropdown,ColourField)) and ctl.open:ctl.draw(surface,small)
        surface.set_clip(old)


class TerrainAuthoringPage:
    """Terrain-centric ecology values and the inverse wild-plant matrix."""
    FIELDS=(
        ("soil_moisture","Initial soil moisture centre","0 = dry, 1 = saturated"),
        ("fertility","Initial fertility centre","0 = depleted, 1 = richest"),
        ("temperature_offset_c","Temperature offset centre (C)","Added to local air temperature"),
        ("rainfall_multiplier","Rainfall multiplier centre","1 = unchanged local rainfall"),
    )
    def __init__(self,service):
        from world import TerrainType
        rect=pygame.Rect(0,0,1,1);self.service=service;self.list=ScrollableList(rect,row_height=30);self.list.set_items(list(TerrainType));self.list.selected_index=list(TerrainType).index(TerrainType.GRASS);self.controls={};self.spreads={};self.plants={};self.actions=[];self.scroll=0;self.message="Select a terrain type.";self.load(TerrainType.GRASS)
    def load(self,terrain):
        self.service.select(terrain.name);row=self.service.values[terrain.name];rect=pygame.Rect(0,0,1,1)
        self.controls={};self.spreads={}
        for k,_,_ in self.FIELDS:
            band=row[k] if isinstance(row[k],dict) else {"centre":float(row[k]),"spread":0.0}
            self.controls[k]=FloatField(rect,str(band["centre"]),minimum=0 if k!="temperature_offset_c" else None,maximum=2 if k=="rainfall_multiplier" else 1 if k!="temperature_offset_c" else None)
            self.spreads[k]=FloatField(rect,str(band.get("spread",0.0)),minimum=0,maximum=5 if k=="temperature_offset_c" else 1)
        selected=self.service.selected_plants();self.plants={p.key:Checkbox(rect,p.key in selected) for p in self.service.wild_plants()};self.scroll=0
    def _all(self):return list(self.controls.values())+list(self.spreads.values())+list(self.plants.values())
    def handle_event(self,event):
        old=self.list.selected_index
        if self.list.handle_event(event):
            if old!=self.list.selected_index and self.list.selected:self.load(self.list.selected)
            return True
        for ctl in self._all():
            if ctl.handle_event(event):return True
        if event.type==pygame.MOUSEWHEEL:self.scroll=max(0,self.scroll-event.y*35);return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            for rect,action in self.actions:
                if rect.collidepoint(event.pos) and action=="save":
                    values={}
                    for k,_,_ in self.FIELDS:
                        centre=self.controls[k].parse();spread=self.spreads[k].parse()
                        if centre is None or spread is None:self.message="Enter valid numeric terrain values.";return True
                        values[k]={"centre":centre,"spread":spread}
                    _ok,self.message=self.service.save(values,{k for k,b in self.plants.items() if b.checked})
                    return True
        return False
    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+24,panel.y+82,250,panel.h-145);right=pygame.Rect(left.right+14,left.y,panel.right-left.right-38,left.h);self.actions=[]
        self.list.rect=left;self.list.draw(surface,small,lambda t:t.name.replace("_"," ").title())
        pygame.draw.rect(surface,BG,right);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,right,1)
        terrain=self.list.selected or __import__("world").TerrainType.GRASS
        surface.blit(font.render(terrain.name.replace("_"," ").title(),True,COLOUR_TEXT),(right.x+16,right.y+12))
        clip=pygame.Rect(right.x+2,right.y+43,right.w-4,right.h-92);old=surface.get_clip();surface.set_clip(clip);x=right.x+16;fx=right.x+230;y=right.y+52-self.scroll
        surface.blit(font.render("ECOLOGICAL BANDS (CENTRE ± SPREAD)",True,(150,190,165)),(x,y));y+=31
        for key,label,hint in self.FIELDS:
            surface.blit(small.render(label,True,COLOUR_TEXT_DIM),(x,y+5));ctl=self.controls[key];ctl.rect=pygame.Rect(fx,y,70,26);ctl.draw(surface,small)
            surface.blit(small.render("±",True,COLOUR_TEXT_DIM),(fx+76,y+5));spread=self.spreads[key];spread.rect=pygame.Rect(fx+94,y,66,26);spread.draw(surface,small);y+=28;surface.blit(small.render(hint,True,COLOUR_TEXT_DIM),(fx,y));y+=22
        surface.blit(font.render("WILD PLANTS ALLOWED ON THIS TERRAIN",True,(150,190,165)),(x,y));y+=30
        for p in self.service.wild_plants():
            ctl=self.plants[p.key];ctl.rect=pygame.Rect(x,y+2,18,18);ctl.draw(surface);surface.blit(small.render(p.label,True,COLOUR_TEXT),(x+26,y+2));y+=25
        surface.set_clip(old);save=pygame.Rect(right.x+16,right.bottom-39,110,28);self.actions.append((save,"save"));_button(surface,small,save,"Save")
