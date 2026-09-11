"""Unified editor-facing plant catalogue projected into legacy registries."""
from __future__ import annotations

from dataclasses import asdict,dataclass,fields,replace
from enum import Enum
import json,os,re,sys,tempfile
from pathlib import Path

from .content_io import get_content_root
from .validation import ValidationIssue,ValidationReport,ValidationSeverity

PATH=Path(get_content_root())/"objects_data"/"plants.json"
REVISION=0
_PASSTHROUGH_WILD=()


def _enc(v):
    if isinstance(v,Enum):return v.name
    if isinstance(v,tuple):return [_enc(x) for x in v]
    if hasattr(v,"minimum") and hasattr(v,"optimum_low"):return [v.minimum,v.optimum_low,v.optimum_high,v.maximum]
    return v


@dataclass
class PlantDef:
    key:str;label:str;short:str;growth_form:str
    produce_resource:str="";seed_resource:str="";perennial:bool=False
    harvest_outputs:dict[str,int]|None=None
    can_be_cultivated:bool=False;can_grow_wild:bool=False
    cultivated:dict|None=None;wild:dict|None=None;tree:dict|None=None

    def __post_init__(self):
        self.harvest_outputs=dict(self.harvest_outputs or {})
        self.cultivated=dict(self.cultivated or {})
        self.wild=dict(self.wild or {})
        self.tree=dict(self.tree or {})


def _crop_data(c):
    import crops
    seasonal=getattr(crops,"CROP_SEASONAL_PRESENTATION",{}).get(c.key,{})
    footprint=list(getattr(crops,"CROP_FOOTPRINTS",{}).get(c.key,range(9)))
    return {"plant_season":c.plant_season.name,"harvest_season":c.harvest_seasons[0].name if c.harvest_seasons else "SUMMER","harvest_seasons":[s.name for s in c.harvest_seasons],"harvest_max":9,"growth_days":c.growth_days,"year_phases":[p.name for p in c.year_phases],"seed_amounts":list(c.farm_seed_amounts),"fertility_effect":c.fertility_effect,"sparse_icon":c.icon_base,"dense_icon":c.dense_icon_base or f"{c.icon_base}_dense","stem_colour":list(c.stem_colour),"flower_colour":list(c.flower_colour) if c.flower_colour else None,"recolour":{"stem":list(c.stem_colour),**({"flower":list(c.flower_colour)} if c.flower_colour else {})},"omit_classes":[] if c.flower_colour else ["flower"],"seasonal_recolour":seasonal,"footprint":footprint}


def _wild_data(w):
    import crops,wild_species
    excluded={"key","label","resource_key","crop_key","yield_amount","icon_base","icon_recolour"}
    out={f.name:_enc(getattr(w,f.name)) for f in fields(w) if f.name not in excluded}
    crop=crops.CROP_BY_KEY.get(w.crop_key or "");icon=w.icon_base or (crop.icon_base if crop else "");recolour={k:list(v) for k,v in w.icon_recolour}
    if not recolour and crop:
        recolour={"stem":list(crop.stem_colour)}
        if crop.flower_colour is not None:recolour["flower"]=list(crop.flower_colour)
    omit=list(getattr(wild_species,"WILD_ICON_OMIT_BY_KEY",{}).get(w.key,()))
    if crop and crop.flower_colour is None and "flower" not in omit:omit.append("flower")
    out.update(icon=icon,recolour=recolour,footprint=list(__import__("subtile_layout")._editor_slots(w.feature,crop_kind=w.crop_key,object_key=w.key) or [4]),omit_classes=omit)
    return out


def _tree_data(t):return {"growth_years":t.growth_years,"wood_resource":t.yield_key,"wood_yield":t.yield_amount,"canopy_colour":list(t.canopy),"sapling_colour":list(t.sapling_colour),"shape":t.shape,"cone_scale":t.cone_scale,"wild_icon":"tree_cone" if t.shape=="cone" else "tree_round","wild_footprint":list(range(9))}


def registry_records():
    global _PASSTHROUGH_WILD
    import crops,wild_species,trees
    crop={x.key:x for x in crops.CROPS};_PASSTHROUGH_WILD=tuple(x for x in wild_species.WILD_SPECIES if x.feature in {"MUSHROOM","WOOD_BUSH"});wild={x.key:x for x in wild_species.WILD_SPECIES if x.feature not in {"MUSHROOM","WOOD_BUSH"}};tree={x.key:x for x in trees.TREES};records=[]
    for key in sorted(set(crop)|set(wild)|set(tree)):
        c= crop.get(key);w=wild.get(key);t=tree.get(key);is_tree=t is not None
        growth="tree" if is_tree else "shrub" if w and w.feature=="BERRY_BUSH" else "perennial herb" if (c and c.perennial) or (w and not c) else "annual herb"
        records.append(PlantDef(key,(c or w or t).label,(c or t).short if c or t else key[:4],growth,c.produce_key if c else w.resource_key if w else t.yield_key,c.seed_key if c else f"{key}_saplings" if t else "",bool(c.perennial) if c else is_tree or growth in {"perennial herb","shrub"},{(c.produce_key if c else w.resource_key if w else t.yield_key):(w.yield_amount if w else t.yield_amount if t else 1)},c is not None,w is not None or is_tree,_crop_data(c) if c else {},_wild_data(w) if w else {},_tree_data(t) if t else {}))
    return records


def load_file(path=PATH):
    path=Path(path)
    if not path.exists():return {}
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,dict):raise ValueError("Plant data root must be an object")
    return raw


def validate_plant(p):
    issues=[]
    def err(field,msg):issues.append(ValidationIssue(ValidationSeverity.ERROR,"plants",p.key,field,msg))
    if not re.fullmatch(r"[a-z][a-z0-9_]*",p.key):err("key","Use a lowercase resource-style key.")
    if not p.label.strip():err("label","Label is required.")
    if p.growth_form not in {"annual herb","perennial herb","shrub","tree"}:err("growth_form","Select a supported growth form.")
    if not (p.can_be_cultivated or p.can_grow_wild):err("modes","Enable cultivated and/or wild existence.")
    if p.can_be_cultivated and p.growth_form!="tree" and not p.seed_resource:err("seed_resource","Cultivated herbs require a seed resource.")
    return ValidationReport(issues)


def _project(records):
    import crops,wild_species,trees,resources
    from crops import CropDef,SeasonPhase
    from seasons import Season
    from wild_species import NicheRange,WildSpeciesDef
    from trees import TreeDef
    crop_items=[];wild_items=[];tree_items=[];seasonal={};crop_fp={};crop_presentation={};crop_harvest={};tree_presentation={};wild_omit={};wild_fp={}
    for p in records:
        if p.produce_resource and p.produce_resource not in resources.RESOURCE_KEYS:resources.register_resource(p.produce_resource,label=p.label,group="food",short=p.short)
        if p.seed_resource and p.seed_resource not in resources.RESOURCE_KEYS:resources.register_resource(p.seed_resource,label=f"{p.label} seeds",group="agriculture",short=p.short+".s")
        if p.can_be_cultivated and p.growth_form!="tree":
            d=p.cultivated;stem=tuple(d.get("stem_colour",(80,140,70)));flower=d.get("flower_colour")
            crop_items.append(CropDef(p.key,p.label,p.produce_resource,p.seed_resource,p.short,stem,tuple(flower) if flower else None,Season[d.get("plant_season","SPRING")],tuple(Season[x] for x in d.get("harvest_seasons",["SUMMER"])),int(d.get("growth_days",32)),1/3,tuple(d.get("seed_amounts",[1,2,3])),tuple(SeasonPhase[x] for x in d.get("year_phases",["PLOUGH_PLANT","HARVEST","FALLOW","FALLOW"])),d.get("sparse_icon","crop_plant"),d.get("dense_icon") or None,p.perennial,d.get("fertility_effect")))
            seasonal[p.key]=d.get("seasonal_recolour",{});crop_fp[p.key]=tuple(d.get("footprint",range(9)));crop_presentation[p.key]={"recolour":d.get("recolour",{}),"omit_classes":d.get("omit_classes",[])};crop_harvest[p.key]=max(1,int(d.get("harvest_max",9)))
        if p.growth_form=="tree":
            d=p.tree;tree_items.append(TreeDef(p.key,p.label,p.short,float(d.get("growth_years",2)),int(d.get("wood_yield",2)),d.get("wood_resource") or p.produce_resource or "logs",tuple(d.get("canopy_colour",(50,130,60))),tuple(d.get("sapling_colour",(120,190,90))),d.get("shape","round"),float(d.get("cone_scale",1))))
            tree_presentation[p.key]={"icon":p.wild.get("icon") or d.get("wild_icon") or ("tree_cone" if d.get("shape")=="cone" else "tree_round"),"recolour":p.wild.get("recolour",{}),"omit_classes":p.wild.get("omit_classes",[])}
        if p.can_grow_wild and p.growth_form!="tree":
            d=p.wild;kwargs={}
            for f in fields(WildSpeciesDef):
                if f.name in {"key","label","feature","terrains","resource_key","yield_amount","crop_key","icon_base","icon_recolour"} or f.name not in d:continue
                v=d[f.name]
                if f.name.endswith("_niche") and v is not None:v=NicheRange(*v)
                elif f.name in {"terrains","edge_terrains","ecology_tags","spawn_rise","spawn_fall","patch_extras","despawn_fade","despawn_fade_end","fruit_rise","fruit_fall","activity_profile"}:v=tuple(v)
                elif f.name.endswith("colour") and v is not None:v=tuple(v)
                kwargs[f.name]=v
            feature=d.get("feature","WILD_CROP" if p.can_be_cultivated else "HERB")
            wild_items.append(WildSpeciesDef(p.key,p.label,feature,tuple(d.get("terrains",["GRASS"])),resource_key=p.produce_resource,yield_amount=int(d.get("harvest_max",3)),crop_key=p.key if p.can_be_cultivated else None,icon_base=d.get("icon","flower_plant"),icon_recolour=tuple((k,tuple(v)) for k,v in d.get("recolour",{}).items()),**kwargs));wild_omit[p.key]=tuple(d.get("omit_classes",()))
            wild_fp[p.key]=tuple(d.get("footprint",[4]))
    old=(crops.CROPS,crops.CROP_BY_KEY,wild_species.WILD_SPECIES,wild_species.WILD_BY_KEY,trees.TREES,trees.TREE_BY_KEY)
    crops.CROPS=tuple(crop_items);crops.CROP_BY_KEY={x.key:x for x in crop_items};crops.CROP_SEASONAL_PRESENTATION=seasonal;crops.CROP_FOOTPRINTS=crop_fp;crops.CROP_PRESENTATION=crop_presentation;crops.CROP_HARVEST_MAX=crop_harvest
    wild_items.extend(x for x in _PASSTHROUGH_WILD if x.key not in {item.key for item in wild_items})
    wild_species.WILD_SPECIES=tuple(wild_items);wild_species.WILD_BY_KEY={x.key:x for x in wild_items};wild_species.WILD_ICON_OMIT_BY_KEY=wild_omit;wild_species.WILD_FOOTPRINTS=wild_fp
    world_module=sys.modules.get("world")
    if world_module is not None and hasattr(world_module,"refresh_wild_crops_by_terrain"):
        world_module.refresh_wild_crops_by_terrain()
    try:
        __import__("subtile_layout").invalidate_layout_cache()
    except (ImportError,AttributeError):
        pass
    trees.TREES=tuple(tree_items);trees.TREE_BY_KEY={x.key:x for x in tree_items};trees.TREE_KEYS=tuple(x.key for x in tree_items);trees.SAPLING_ITEM_KEYS=tuple(f"{x.key}_saplings" for x in tree_items);trees.TREE_PRESENTATION=tree_presentation
    for module in tuple(sys.modules.values()):
        if module is None:continue
        for before,after,name in ((old[0],crops.CROPS,"CROPS"),(old[1],crops.CROP_BY_KEY,"CROP_BY_KEY"),(old[2],wild_species.WILD_SPECIES,"WILD_SPECIES"),(old[3],wild_species.WILD_BY_KEY,"WILD_BY_KEY"),(old[4],trees.TREES,"TREES"),(old[5],trees.TREE_BY_KEY,"TREE_BY_KEY")):
            if getattr(module,name,None) is before:setattr(module,name,after)


class PlantEditorService:
    def __init__(self,root=None):self.root=Path(root or get_content_root());self.path=self.root/"objects_data"/"plants.json";self.items=[];self.original=None;self.candidate=None;self.report=ValidationReport();self.load()
    @property
    def records(self):return self.items
    @property
    def dirty(self):return self.candidate is not None and self.candidate!=self.original
    def load(self):
        base={p.key:p for p in registry_records()}
        try:rows=load_file(self.path)
        except Exception as exc:return False,f"Plant reload rejected: {exc}"
        for key,row in rows.items():
            if row.get("_deleted") is True:base.pop(key,None);continue
            base[key]=PlantDef(key=key,**{k:v for k,v in row.items() if k!="key"})
        items=list(base.values());reports=[validate_plant(x) for x in items];issues=[i for r in reports for i in r.issues]
        if issues:return False,"Plant reload rejected; runtime registries unchanged."
        self.items=sorted(items,key=lambda p:p.label.casefold());_project(self.items);return True,"Plants reloaded into crop, wild-species, and tree registries."
    def select(self,item):self.original=PlantDef(**asdict(item));self.candidate=PlantDef(**asdict(item));self.report=validate_plant(self.candidate)
    def new(self):
        used={p.key for p in self.items};i=1;key="new_plant"
        while key in used:i+=1;key=f"new_plant_{i}"
        self.original=None;self.candidate=PlantDef(key,"New Plant","new","annual herb",can_be_cultivated=True,cultivated={});self.report=validate_plant(self.candidate)
    def duplicate(self):
        if self.candidate is None:return False,"Select a plant first."
        used={p.key for p in self.items};base=f"{self.candidate.key}_copy";key=base;i=1
        while key in used:i+=1;key=f"{base}_{i}"
        data=asdict(self.candidate);data.update(key=key,label=f"{self.candidate.label} Copy");self.original=None;self.candidate=PlantDef(**data);self.report=validate_plant(self.candidate);return True,"Duplicated as an unsaved plant."
    def update(self,**values):
        for k,v in values.items():setattr(self.candidate,k,v)
        self.report=validate_plant(self.candidate);return self.report
    def cancel(self):self.candidate=PlantDef(**asdict(self.original)) if self.original else None;self.report=validate_plant(self.candidate) if self.candidate else ValidationReport()
    def save(self):
        global REVISION
        report=validate_plant(self.candidate)
        if not report.ok:self.report=report;return False,"Plant save rejected."
        rows=load_file(self.path);rows[self.candidate.key]={k:_enc(v) for k,v in asdict(self.candidate).items() if k!="key"}
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix="plants.",suffix=".tmp")
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:json.dump(rows,h,indent=2,sort_keys=True);h.write("\n")
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        by={p.key:p for p in self.items};by[self.candidate.key]=PlantDef(**asdict(self.candidate));self.items=sorted(by.values(),key=lambda p:p.label.casefold());_project(self.items);self.original=PlantDef(**asdict(self.candidate));REVISION+=1;return True,"Plant saved and projected into active runtime registries."
    def save_terrain_membership(self,terrain,enabled_keys):
        global REVISION
        rows=load_file(self.path)
        for p in self.items:
            if not p.can_grow_wild:continue
            terrains=set(p.wild.get("terrains",[]))
            if p.key in enabled_keys:terrains.add(terrain)
            else:terrains.discard(terrain)
            p.wild["terrains"]=sorted(terrains);rows[p.key]={k:_enc(v) for k,v in asdict(p).items() if k!="key"}
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix="plants.",suffix=".tmp")
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:json.dump(rows,h,indent=2,sort_keys=True);h.write("\n")
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        _project(self.items);REVISION+=1
    def delete(self):
        global REVISION
        if self.candidate is None:return False,"Select a plant first."
        key=self.candidate.key;rows=load_file(self.path);rows[key]={"_deleted":True}
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix="plants.",suffix=".tmp")
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:json.dump(rows,h,indent=2,sort_keys=True);h.write("\n")
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.items=[p for p in self.items if p.key!=key];self.original=None;self.candidate=None;self.report=ValidationReport();_project(self.items);REVISION+=1;return True,f"Deleted {key}. The plants.json tombstone can be removed to restore a built-in plant."
