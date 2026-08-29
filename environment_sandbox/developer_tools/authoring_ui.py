"""Interactive catalogue forms used by the Developer Tools launcher."""

from __future__ import annotations

from pathlib import Path

import pygame

from icons import blit_icon, has_icon
from resources import resource_icon, resource_label
from settings import COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_ACTIVE
from .widgets import Checkbox, Dropdown, FloatField, IntegerField, ScrollableList, TextField


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


class RecipeAuthoringPage:
    """A structured recipe form; CSV amount syntax never reaches the user."""

    def __init__(self, service, icons):
        self.service = service
        self.icons = icons
        self.list = ScrollableList(pygame.Rect(0, 0, 1, 1), row_height=25)
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
        self.service=service;self.icons=icons;self.on_saved=on_saved;self.list=ScrollableList(pygame.Rect(0,0,1,1),row_height=25);self.icon_list=ScrollableList(pygame.Rect(0,0,1,1),row_height=24);self.icon_picker=False;self.fields={};self.actions=[];self.message="Select a resource or click New Resource.";self.refresh()
    def refresh(self,key=None):
        self.list.set_items(self.service.records)
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
        self.list.rect=pygame.Rect(left.x,left.y+40,left.w,left.h-40);self.list.draw(surface,small,lambda r:f"{r['key']} — {r['label']}")
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
