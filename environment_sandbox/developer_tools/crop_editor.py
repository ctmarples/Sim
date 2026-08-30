"""External authoring adapter for the existing immutable CropDef catalogue."""

from __future__ import annotations

from dataclasses import fields, replace
import json
import os
from pathlib import Path
import sys
import tempfile

from .content_io import get_content_root
from .validation import ValidationIssue, ValidationReport, ValidationSeverity

PATH=Path(get_content_root())/"objects_data"/"crop_overrides.json"
REVISION=0
_BASE=None


def _base_registry():
    global _BASE
    if _BASE is None:
        import crops
        _BASE=tuple(crops.CROPS)
    return _BASE


def load_overrides(path=PATH):
    path=Path(path)
    if not path.exists():return {}
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,dict):raise ValueError("Crop override root must be an object")
    return raw


def _decode(base,row):
    from crops import SeasonPhase
    from seasons import Season
    # Wild-foraging behaviour belongs to WildSpeciesDef. CropDef retains its
    # legacy field for compatibility, but the farm-crop adapter neither reads
    # nor writes it.
    known={f.name for f in fields(base)}-{"key","wild_seed_chance"}
    values={k:v for k,v in row.items() if k in known}
    if "stem_colour" in values:values["stem_colour"]=tuple(values["stem_colour"])
    if "flower_colour" in values and values["flower_colour"] is not None:values["flower_colour"]=tuple(values["flower_colour"])
    if "plant_season" in values:values["plant_season"]=Season[str(values["plant_season"])]
    if "harvest_seasons" in values:values["harvest_seasons"]=tuple(Season[str(v)] for v in values["harvest_seasons"])
    if "year_phases" in values:values["year_phases"]=tuple(SeasonPhase[str(v)] for v in values["year_phases"])
    if "farm_seed_amounts" in values:values["farm_seed_amounts"]=tuple(int(v) for v in values["farm_seed_amounts"])
    return replace(base,**values)


def validate_crop(crop):
    issues=[]
    def error(field,message):issues.append(ValidationIssue(ValidationSeverity.ERROR,"farm_crops",crop.key,field,message))
    if not crop.label.strip():error("label","Label is required.")
    if crop.growth_days<=0:error("growth_days","Growth days must be greater than zero.")
    if not crop.harvest_seasons:error("harvest_seasons","Select at least one harvest season.")
    if len(crop.year_phases)!=4:error("year_phases","Exactly four seasonal phases are required.")
    if not crop.farm_seed_amounts or any(v<0 for v in crop.farm_seed_amounts):error("farm_seed_amounts","Seed yields must be non-negative integers.")
    return ValidationReport(issues)


def candidate_registry(overrides):
    items=[];issues=[]
    bases={item.key:item for item in _base_registry()}
    for key in overrides:
        if key not in bases:issues.append(ValidationIssue(ValidationSeverity.ERROR,"farm_crops",key,"key","Unknown immutable crop key."))
    for key,base in bases.items():
        try:item=_decode(base,overrides.get(key,{}));report=validate_crop(item);issues.extend(report.issues);items.append(item)
        except (KeyError,TypeError,ValueError) as exc:issues.append(ValidationIssue(ValidationSeverity.ERROR,"farm_crops",key,"override",str(exc)));items.append(base)
    return tuple(items),ValidationReport(issues)


def _apply_registry(items,overrides=None):
    import crops
    old_seq=crops.CROPS;old_map=crops.CROP_BY_KEY
    new=tuple(items);new_map={x.key:x for x in new}
    crops.CROPS=new;crops.CROP_BY_KEY=new_map
    presentation={}
    footprints={}
    for key,row in (overrides or {}).items():
        if isinstance(row.get("_seasonal_presentation"),dict):presentation[key]=row["_seasonal_presentation"]
        if isinstance(row.get("_footprint_slots"),list):footprints[key]=tuple(row["_footprint_slots"])
    crops.CROP_SEASONAL_PRESENTATION=presentation;crops.CROP_FOOTPRINTS=footprints
    for module in tuple(sys.modules.values()):
        if module is None:continue
        if getattr(module,"CROPS",None) is old_seq:setattr(module,"CROPS",new)
        if getattr(module,"CROP_BY_KEY",None) is old_map:setattr(module,"CROP_BY_KEY",new_map)


def reload_crops(path=PATH):
    global REVISION
    try:overrides=load_overrides(path)
    except (OSError,json.JSONDecodeError,ValueError) as exc:return False,f"Farm Crop reload rejected: {exc}"
    items,report=candidate_registry(overrides)
    if not report.ok:return False,"Farm Crop reload rejected; working registry is unchanged."
    _apply_registry(items,overrides);REVISION+=1
    return True,"Farm Crop overrides reloaded into the active registry."


def _encode(value):
    from enum import Enum
    if isinstance(value,Enum):return value.name
    if isinstance(value,tuple):return [_encode(v) for v in value]
    return value


class CropEditorService:
    def __init__(self,root=None):
        self.root=Path(root or get_content_root());self.path=self.root/"objects_data"/"crop_overrides.json";self.overrides={};self.original=None;self.candidate=None;self.original_slots=list(range(9));self.candidate_slots=list(range(9));self.original_seasonal={};self.candidate_seasonal={};self.report=ValidationReport();self.load()
    @property
    def records(self):
        import crops
        return list(crops.CROPS)
    @property
    def dirty(self):return self.candidate is not None and (self.candidate!=self.original or self.candidate_slots!=self.original_slots or self.candidate_seasonal!=self.original_seasonal)
    def load(self):
        ok,message=reload_crops(self.path)
        if ok:self.overrides=load_overrides(self.path)
        return ok,message
    def select(self,item):
        self.original=item;self.candidate=item;row=self.overrides.get(item.key,{})
        slots=row.get("_footprint_slots",list(range(9)));self.original_slots=list(slots);self.candidate_slots=list(slots)
        seasonal=row.get("_seasonal_presentation",{});self.original_seasonal=json.loads(json.dumps(seasonal));self.candidate_seasonal=json.loads(json.dumps(seasonal));self.report=validate_crop(item)
    def update(self,**values):self.candidate=replace(self.candidate,**values);self.report=validate_crop(self.candidate);return self.report
    def cancel(self):self.candidate=self.original;self.candidate_slots=list(self.original_slots);self.candidate_seasonal=json.loads(json.dumps(self.original_seasonal));self.report=validate_crop(self.candidate) if self.candidate else ValidationReport()
    def save(self):
        global REVISION
        if self.candidate is None:return False,"Select a crop first."
        report=validate_crop(self.candidate)
        if not report.ok:self.report=report;return False,"Farm Crop save rejected; working registry is unchanged."
        base=next(x for x in _base_registry() if x.key==self.candidate.key);changed={}
        for f in fields(base):
            if f.name not in {"key","wild_seed_chance"} and getattr(self.candidate,f.name)!=getattr(base,f.name):changed[f.name]=_encode(getattr(self.candidate,f.name))
        changed["icon_base"]=self.candidate.icon_base;changed["dense_icon_base"]=self.candidate.dense_icon_base
        changed["stem_colour"]=list(self.candidate.stem_colour);changed["flower_colour"]=list(self.candidate.flower_colour) if self.candidate.flower_colour is not None else None
        changed["_footprint_slots"]=sorted(set(self.candidate_slots));changed["_seasonal_presentation"]=self.candidate_seasonal
        proposed=dict(self.overrides);proposed[self.candidate.key]=changed
        items,whole=candidate_registry(proposed)
        if not whole.ok:self.report=whole;return False,"Farm Crop save rejected; working registry is unchanged."
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",suffix=".tmp",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as handle:json.dump(proposed,handle,indent=2,sort_keys=True);handle.write("\n")
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.overrides=proposed;_apply_registry(items,proposed);self.original=next(x for x in items if x.key==self.candidate.key);self.candidate=self.original;self.original_slots=list(self.candidate_slots);self.original_seasonal=json.loads(json.dumps(self.candidate_seasonal));self.report=whole;REVISION+=1
        return True,"Farm Crop saved and active registry reloaded."
