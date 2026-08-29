"""Read-only resource-reference view model."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from copy import deepcopy

from .content_io import atomic_write_csv, get_content_root, snapshot_file
from .validation import ValidationReport, ValidationSeverity
from .editors import ID_RE


@dataclass(frozen=True)
class ResourceEntry:
    key: str
    label: str
    group: str
    short: str
    icon: str
    food: bool
    edible: bool
    source: str


def resource_entries(search: str = "") -> list[ResourceEntry]:
    from resource_balance import FOOD_BY_KEY, VILLAGER_FOOD_KEYS
    from resources import RESOURCES, resource_icon

    needle = search.casefold().strip(); result = []
    for item in RESOURCES:
        if needle and needle not in f"{item.key} {item.label} {item.group}".casefold(): continue
        source = "crops.py (derived)" if item.key.endswith("_seeds") else "resources.py / recipe metadata"
        result.append(ResourceEntry(item.key, item.label, item.group, item.short, resource_icon(item.key), item.key in FOOD_BY_KEY, item.key in VILLAGER_FOOD_KEYS, source))
    return result


class ResourceEditorService:
    """CRUD for authored resources; built-ins are persisted as CSV overrides."""
    header = ["key", "label", "group", "short", "icon_key", "usage", "stack_size", "tool_effectiveness", "tool_targets"]
    def __init__(self, content_root=None):
        self.root=Path(content_root or get_content_root()); self.path=self.root/"resources_data"/"resources.csv"; self.rows=[]; self.records=[]; self.candidate=None; self.original=None; self.is_new=False; self.load()
    def load(self):
        from resources import RESOURCES, resource_icon
        self.rows=[]
        if self.path.is_file():
            with self.path.open(encoding="utf-8",newline="") as fh:self.rows=[{k:str(r.get(k) or "") for k in self.header} for r in csv.DictReader(fh)]
        self.snapshot=snapshot_file(self.path,root=self.root)
        self.records=[]
        builtin_tools={"axe","spear","fishing_rod","hoe","knife","bow"}
        for r in RESOURCES:
            row={k:str(getattr(r,k,"")) for k in self.header}
            row["icon_key"]=row["icon_key"] or resource_icon(r.key)
            if r.key in builtin_tools and row["usage"]=="resource":row["usage"]="tool"
            self.records.append(row)
    def select(self,row):self.candidate=deepcopy(row);self.original=deepcopy(row);self.is_new=False
    def new(self):self.candidate={k:"" for k in self.header};self.candidate.update(group="wares",usage="resource",stack_size="1",tool_effectiveness="1.0");self.original=None;self.is_new=True
    def duplicate(self):
        if not self.candidate:return
        self.candidate=deepcopy(self.candidate);self.candidate["key"]="";self.candidate["label"]+=" Copy";self.original=None;self.is_new=True
    def validate(self):
        r=ValidationReport();c=self.candidate or {};key=c.get("key","")
        if not ID_RE.fullmatch(key):r.add(ValidationSeverity.ERROR,"invalid_resource_key","Resource ID must be snake_case",field="key")
        if not self.is_new and self.original and key!=self.original["key"]:r.add(ValidationSeverity.ERROR,"immutable_resource_key","Existing resource IDs cannot be renamed",field="key")
        if self.is_new and any(x["key"]==key for x in self.records):r.add(ValidationSeverity.ERROR,"duplicate_resource_key","Resource ID already exists",field="key")
        try:
            if int(c.get("stack_size") or 1)<1:raise ValueError
            if float(c.get("tool_effectiveness") or 1)<=0:raise ValueError
        except ValueError:r.add(ValidationSeverity.ERROR,"invalid_resource_number","Stack size and effectiveness must be positive",field="stack_size")
        return r
    def save(self):
        report=self.validate()
        if not report.ok:return False,report,"Resource save blocked by validation errors."
        c={k:self.candidate.get(k,"") for k in self.header};rows=deepcopy(self.rows);i=next((i for i,r in enumerate(rows) if r["key"]==c["key"]),None)
        if i is None:rows.append(c)
        else:rows[i]=c
        atomic_write_csv(self.path,self.header,rows,root=self.root,expected_snapshot=self.snapshot,validation_report=report)
        from resources import reload_authored_resources
        reload_authored_resources(self.path)
        from .reload import reload_recipes
        recipe_dir=self.root/"recipes_data"
        if recipe_dir.is_dir():reload_recipes(recipe_dir)
        try:
            import entities
            from entities import ensure_storage_item_fields
            ensure_storage_item_fields()
            entities.TOOL_KEYS = tuple(dict.fromkeys((*entities.TOOL_KEYS, *(r.key for r in __import__("resources").RESOURCES if r.usage == "tool"))))
        except ImportError:pass
        self.load();self.select(next(r for r in self.records if r["key"]==c["key"]));return True,report,"Resource saved; registry reloaded and Recipe Editor selectors refreshed."
    def delete(self):
        if not self.candidate:return False,"Select a resource first."
        key=self.candidate["key"];rows=[r for r in self.rows if r["key"]!=key]
        if len(rows)==len(self.rows):return False,"Built-in resources cannot be deleted; they can be edited through an override."
        atomic_write_csv(self.path,self.header,rows,root=self.root,expected_snapshot=self.snapshot,validation_report=ValidationReport())
        from resources import reload_authored_resources
        reload_authored_resources(self.path)
        from .reload import reload_recipes
        recipe_dir=self.root/"recipes_data"
        if recipe_dir.is_dir():reload_recipes(recipe_dir)
        self.candidate=None;self.load();return True,"Authored resource deleted and registry reloaded."
