"""Typed adapter, persistence and atomic reload for ``WildSpeciesDef``."""
from __future__ import annotations

import json, os, sys, tempfile
from dataclasses import asdict, fields, replace
from pathlib import Path

from .content_io import get_content_root
from .reload import ReloadResult
from .validation import ValidationReport, ValidationSeverity

PATH = Path(__file__).resolve().parents[1] / "objects_data" / "wild_species_overrides.json"
REVISION = 0
_BASE = None


def _base_registry():
    global _BASE
    import wild_species
    if _BASE is None:
        import crops
        normalized=[]
        for item in wild_species.WILD_SPECIES:
            icon=item.icon_base
            recolour=item.icon_recolour
            if not icon and item.crop_key:
                crop=crops.CROP_BY_KEY.get(item.crop_key);icon=crop.plant_icon(dense=False) if crop else ""
            if item.crop_key and not recolour:
                crop=crops.CROP_BY_KEY.get(item.crop_key)
                if crop:
                    colours=[("stem",crop.stem_colour)]
                    if crop.flower_colour is not None:colours.append(("flower",crop.flower_colour))
                    recolour=tuple(colours)
            normalized.append(replace(item,icon_base=icon,icon_recolour=recolour,terrains=(item.terrains,) if isinstance(item.terrains,str) else item.terrains,edge_terrains=(item.edge_terrains,) if isinstance(item.edge_terrains,str) else item.edge_terrains))
        _BASE=tuple(normalized)
    return _BASE


def _encode(value):
    if hasattr(value, "__dataclass_fields__"): return {f.name:_encode(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value,tuple): return [_encode(v) for v in value]
    return value


def _coerce(value,current):
    if hasattr(current,"__dataclass_fields__"):
        if type(current).__name__=="NicheRange":return type(current)(*(float(value[f.name]) for f in fields(current)))
        return replace(current,**{f.name:_coerce(value[f.name],getattr(current,f.name)) for f in fields(current) if f.name in value})
    if isinstance(current,tuple):
        if not current:return tuple(value)
        return tuple(_coerce(v,current[min(i,len(current)-1)]) for i,v in enumerate(value))
    if current is None:return value
    if isinstance(current,bool):return bool(value)
    if isinstance(current,int):return int(value)
    if isinstance(current,float):return float(value)
    return str(value)


def load_overrides(path=PATH):
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (FileNotFoundError,json.JSONDecodeError,OSError):return {}


def validate_species(item) -> ValidationReport:
    from icons import has_icon, variant_names
    from resources import RESOURCE_KEYS
    from world import FeatureType, TerrainType
    report=ValidationReport(); key=item.key
    if item.feature not in FeatureType.__members__:report.add(ValidationSeverity.ERROR,"invalid_feature",f"Unknown feature {item.feature}",field="feature")
    known_terrains=set(TerrainType.__members__)
    for value in (*item.terrains,*item.edge_terrains):
        if value not in known_terrains:report.add(ValidationSeverity.ERROR,"invalid_terrain",f"Unknown terrain {value}",field="terrains")
    if item.resource_key and item.resource_key not in RESOURCE_KEYS:report.add(ValidationSeverity.ERROR,"invalid_resource",f"Unknown resource {item.resource_key}",field="resource_key")
    if item.icon_base and not (has_icon(item.icon_base) or variant_names(item.icon_base)):report.add(ValidationSeverity.ERROR,"invalid_icon",f"Unknown icon {item.icon_base}",field="icon_base")
    for name in ("temperature_niche","moisture_niche","fertility_niche","disturbance_niche","texture_niche"):
        niche=getattr(item,name)
        if niche is not None:
            values=(niche.minimum,niche.optimum_low,niche.optimum_high,niche.maximum)
            if not (0<=values[0]<=values[1]<=values[2]<=values[3]<=1):report.add(ValidationSeverity.ERROR,"invalid_niche",f"{name} must satisfy 0 ≤ min ≤ optimum low ≤ optimum high ≤ max ≤ 1",field=name)
    for name in ("seed_near_chance","spawn_peak","spawn_activity","spread_chance","despawn_fade_chance","despawn_leftover_chance","seed_drop_chance"):
        value=float(getattr(item,name))
        if not 0<=value<=1:report.add(ValidationSeverity.ERROR,"invalid_probability",f"{name} must be between 0 and 1",field=name)
    if item.yield_amount<0 or item.initial_count<0 or item.initial_fraction<0:report.add(ValidationSeverity.ERROR,"negative_value","Counts, yield and initial fraction cannot be negative",field=key)
    for name in ("spawn_rise","spawn_fall","despawn_fade","despawn_fade_end","fruit_rise","fruit_fall"):
        a,b=getattr(item,name)
        if a>b:report.add(ValidationSeverity.ERROR,"invalid_range",f"{name} start must not exceed end",field=name)
    return report


def candidate_registry(overrides):
    report=ValidationReport(); result=[]
    for base in _base_registry():
        updates=overrides.get(base.key,{})
        try:item=replace(base,**{f.name:_coerce(updates[f.name],getattr(base,f.name)) for f in fields(base) if f.name in updates})
        except Exception as exc:
            report.add(ValidationSeverity.ERROR,"wild_species_parse",f"{base.key}: {exc}",field=base.key);item=base
        report.extend(validate_species(item));result.append(item)
    unknown=set(overrides)-{x.key for x in _base_registry()}
    for key in sorted(unknown):report.add(ValidationSeverity.ERROR,"unknown_species",f"Unknown wild species {key}",field=key)
    return tuple(result),report


def _apply_registry(items,overrides=None):
    import wild_species
    old_seq=wild_species.WILD_SPECIES;old_map=wild_species.WILD_BY_KEY
    new=tuple(items);new_map={x.key:x for x in new}
    wild_species.WILD_SPECIES=new;wild_species.WILD_BY_KEY=new_map
    omit_map={key:tuple(row.get("_omit_icon_classes",())) for key,row in (overrides or {}).items() if row.get("_omit_icon_classes")}
    for item in new:
        if item.crop_key and not any(name=="flower" for name,_ in item.icon_recolour):omit_map.setdefault(item.key,("flower",))
    wild_species.WILD_ICON_OMIT_BY_KEY=omit_map
    for module in tuple(sys.modules.values()):
        if module is None:continue
        if getattr(module,"WILD_SPECIES",None) is old_seq:setattr(module,"WILD_SPECIES",new)
        if getattr(module,"WILD_BY_KEY",None) is old_map:setattr(module,"WILD_BY_KEY",new_map)


def reload_wild_species(path=PATH) -> ReloadResult:
    global REVISION
    target=Path(path)
    if target.is_file():
        try:
            raw=json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw,dict):raise ValueError("override root must be an object")
            overrides=raw
        except (json.JSONDecodeError,OSError,UnicodeError,ValueError) as exc:
            report=ValidationReport();report.add(ValidationSeverity.ERROR,"wild_species_file",str(exc),file=str(target))
            return ReloadResult(False,REVISION,len(_base_registry()),report,"Wild Species reload rejected; working registry is unchanged.")
    else:overrides={}
    items,report=candidate_registry(overrides)
    if not report.ok:return ReloadResult(False,REVISION,len(items),report,"Wild Species reload rejected; working registry is unchanged.")
    _apply_registry(items,overrides);REVISION+=1
    return ReloadResult(True,REVISION,len(items),report,"Wild Species overrides reloaded into the active registry.")


class WildSpeciesEditorService:
    def __init__(self,root=None):
        self.root=Path(root or get_content_root());self.path=self.root/"objects_data"/"wild_species_overrides.json";self.candidate=None;self.original=None;self.candidate_slots=[0,1,3,4];self.original_slots=[0,1,3,4];self.candidate_omit=[];self.original_omit=[];self.overrides={};self.report=ValidationReport();self.load()
    @property
    def records(self):
        import wild_species
        return list(wild_species.WILD_SPECIES)
    @property
    def dirty(self):return self.candidate is not None and (self.candidate!=self.original or self.candidate_slots!=self.original_slots or self.candidate_omit!=self.original_omit)
    def load(self):
        result=reload_wild_species(self.path)
        if result.success:self.overrides=load_overrides(self.path)
        self.report=result.report;return result
    def select(self,item):
        self.original=item;self.candidate=item;row=self.overrides.get(item.key,{});slots=row.get("_footprint_slots",[0,1,3,4]);self.original_slots=list(slots);self.candidate_slots=list(slots)
        omit=list(row.get("_omit_icon_classes",()))
        if not omit and item.crop_key and not any(name=="flower" for name,_ in item.icon_recolour):omit=["flower"]
        self.original_omit=list(omit);self.candidate_omit=list(omit);self.report=validate_species(item)
    def update(self,**values):
        self.candidate=replace(self.candidate,**values);self.report=validate_species(self.candidate);return self.report
    def cancel(self):self.candidate=self.original;self.candidate_slots=list(self.original_slots);self.candidate_omit=list(self.original_omit);self.report=validate_species(self.candidate) if self.candidate else ValidationReport()
    def save(self):
        global REVISION
        if self.candidate is None:return ReloadResult(False,REVISION,0,ValidationReport(),"Select a species first.")
        report=validate_species(self.candidate)
        if not report.ok:return ReloadResult(False,REVISION,len(self.records),report,"Save blocked by validation errors.")
        base=next(x for x in _base_registry() if x.key==self.candidate.key)
        changed={f.name:_encode(getattr(self.candidate,f.name)) for f in fields(base) if f.name!="key" and getattr(self.candidate,f.name)!=getattr(base,f.name)}
        # Presentation is deliberately explicit in the JSON. There is no
        # hidden CropDef fallback after a species has been saved in this editor.
        changed["icon_base"]=self.candidate.icon_base
        changed["icon_recolour"]=_encode(self.candidate.icon_recolour)
        if self.candidate_slots!=[0,1,3,4]:changed["_footprint_slots"]=sorted(set(int(x) for x in self.candidate_slots))
        if self.candidate_omit:changed["_omit_icon_classes"]=sorted(set(self.candidate_omit))
        proposed=dict(self.overrides)
        if changed:proposed[self.candidate.key]=changed
        else:proposed.pop(self.candidate.key,None)
        items,whole_report=candidate_registry(proposed)
        if not whole_report.ok:return ReloadResult(False,REVISION,len(items),whole_report,"Save blocked; candidate file would not produce a valid registry.")
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=".wild_species.",suffix=".tmp",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as fh:json.dump(proposed,fh,indent=2,sort_keys=True);fh.flush();os.fsync(fh.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.overrides=proposed;_apply_registry(items,proposed)
        self.original=next(x for x in items if x.key==self.candidate.key);self.candidate=self.original;self.original_slots=list(self.candidate_slots);self.original_omit=list(self.candidate_omit);self.report=whole_report
        REVISION+=1
        return ReloadResult(True,REVISION,len(items),whole_report,"Wild Species saved and active registry reloaded.")
