"""Unified map-object catalogue and persistent dataclass overrides."""
from __future__ import annotations

import copy, json, os, sys, tempfile
from dataclasses import asdict, fields, is_dataclass, replace
from pathlib import Path

from .content_io import get_content_root

PATH = Path(__file__).resolve().parents[1] / "objects_data" / "objects.json"
FIXED = (
    ("feature:rock", "Rock", "feature", "rock", "ROCK"),
    ("feature:fallen_wood", "Fallen wood", "feature", "wood_loose", "WOOD_BUSH"),
    ("feature:mushroom", "Mushroom", "feature", "mushroom", "MUSHROOM"),
)

ONE_BY_ONE = [4]
TWO_BY_TWO = [0, 1, 3, 4]
THREE_BY_THREE = list(range(9))


def _footprint_name(slots):
    return "3×3" if len(slots) >= 9 else "2×2" if len(slots) >= 4 else "1×1"


def _default_slots(kind, item, crops_module):
    """Mirror the map's built-in footprint rules before an override exists."""
    if kind == "tree":
        # Runtime trees occupy 2x2 until the old-growth (6 year) presentation.
        return TWO_BY_TWO.copy()
    if kind == "crop":
        return THREE_BY_THREE.copy()
    feature = str(getattr(item, "feature", "")).upper()
    if feature in {"REED", "HERB", "WILD_CROP", "BERRY_BUSH"}:
        return TWO_BY_TWO.copy()
    if getattr(item, "crop_key", ""):
        crop = crops_module.CROP_BY_KEY.get(item.crop_key)
        if crop is not None:return TWO_BY_TWO.copy()
    return ONE_BY_ONE.copy()

def _jsonable(value):
    if is_dataclass(value): return {f.name:_jsonable(getattr(value,f.name)) for f in fields(value)}
    if hasattr(value, "name"): return value.name
    if isinstance(value, list): return [_jsonable(v) for v in value]
    if isinstance(value, tuple): return [_jsonable(v) for v in value]
    if isinstance(value, dict): return {k:_jsonable(v) for k,v in value.items()}
    return value

def saved(path=PATH):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return {}

def _coerce(value, current):
    from enum import Enum
    if isinstance(current, Enum): return type(current)[str(value)]
    if is_dataclass(current) and isinstance(value, dict):
        updates={f.name:_coerce(value[f.name],getattr(current,f.name)) for f in fields(current) if f.name in value}
        return replace(current,**updates)
    if isinstance(current, tuple):
        sample=current[0] if current else ""
        return tuple(_coerce(v,sample) for v in value)
    if isinstance(current, bool):return value if isinstance(value,bool) else str(value).strip().lower() in {"1","true","yes","on"}
    if isinstance(current, int):return int(value)
    if isinstance(current, float):return float(value)
    return value

def apply_saved_overrides(path=PATH):
    data=saved(path)
    import crops,trees,wild_species
    mappings=(("crop",crops,"CROPS","CROP_BY_KEY"),("tree",trees,"TREES","TREE_BY_KEY"),("wild",wild_species,"WILD_SPECIES","WILD_BY_KEY"))
    for kind,module,seq_name,map_name in mappings:
        seq=list(getattr(module,seq_name));changed=False
        for i,item in enumerate(seq):
            row=data.get(f"{kind}:{item.key}")
            if not row:continue
            params=row.get("params",{});updates={}
            for f in fields(item):
                if f.name in params:
                    try:updates[f.name]=_coerce(params[f.name],getattr(item,f.name))
                    except Exception:pass
            seq[i]=replace(item,**updates);changed=True
        if changed:
            old_seq=getattr(module,seq_name);old_map=getattr(module,map_name);new=tuple(seq);new_map={x.key:x for x in new}
            setattr(module,seq_name,new);setattr(module,map_name,new_map)
            # Several gameplay modules import these registries directly. Keep a
            # live save truly live instead of requiring a restart.
            for loaded in tuple(sys.modules.values()):
                if loaded is None:continue
                if getattr(loaded,seq_name,None) is old_seq:setattr(loaded,seq_name,new)
                if getattr(loaded,map_name,None) is old_map:setattr(loaded,map_name,new_map)
    return data

class ObjectEditorService:
    def __init__(self,root=None):
        self.root=Path(root or get_content_root());self.path=self.root/"objects_data"/"objects.json";self.overrides=saved(self.path);self.records=[];self.candidate=None;self.load()
    def load(self):
        import crops,trees,wild_species
        def crop_icons(item):
            """Icons actually selected by the renderer for each visible season."""
            rows=[]
            for season,phase in zip(("Spring","Summer","Autumn","Winter"),item.year_phases):
                name=phase.name
                if name in {"FALLOW","DORMANT"}:continue
                dense=name in {"HARVEST","HARVEST_PLOUGH_PLANT"}
                recolour={"stem":item.stem_colour}
                if item.flower_colour is not None:recolour["flower"]=item.flower_colour
                rows.append({"season":season,"stage":name.replace("_"," ").title(),"icon":item.plant_icon(dense=dense),"recolour":recolour})
            return rows
        self.records=[]
        for kind,items in (("crop",crops.CROPS),("tree",trees.TREES),("wild",wild_species.WILD_SPECIES)):
            for item in items:
                ident=f"{kind}:{item.key}";params={f.name:_jsonable(getattr(item,f.name)) for f in fields(item)}
                icon=(item.plant_icon() if kind=="crop" else ("tree_cone" if kind=="tree" and item.shape=="cone" else "tree_round" if kind=="tree" else item.icon_base or (getattr(crops.CROP_BY_KEY.get(item.crop_key),"icon_base","") if item.crop_key else "")))
                feature="TREE" if kind=="tree" else "WILD_CROP" if kind=="crop" else item.feature
                override=self.overrides.get(ident,{})
                if kind=="crop":icon_uses=crop_icons(item);category="Farm crops"
                elif kind=="wild":
                    crop=crops.CROP_BY_KEY.get(item.crop_key or "")
                    if crop:
                        recolour={"stem":crop.stem_colour}
                        if crop.flower_colour is not None:recolour["flower"]=crop.flower_colour
                        # Wild crops never switch to the farmed dense/harvest
                        # art. Their wild presentation remains stable while visible.
                        icon_uses=[{"season":"Wild window","stage":"Wild","icon":crop.plant_icon(dense=False),"recolour":recolour}]
                    else:icon_uses=[{"season":"Seasonal window","stage":"Wild","icon":icon,"recolour":dict(item.icon_recolour)}]
                    category="Wild crops" if item.crop_key else "Wild plants"
                else:
                    sapling="sapling_cone" if item.shape=="cone" else "sapling_round"
                    icon_uses=[{"season":"All seasons","stage":"Sapling","icon":sapling,"recolour":{"canopy":item.sapling_colour}},{"season":"All seasons","stage":"Mature","icon":icon,"recolour":{"canopy":item.canopy}}];category="Trees"
                # An explicit override replaces every runtime-selected icon;
                # otherwise retain the sparse/dense seasonal choices above.
                selected=override.get("icon_key")
                if selected:icon_uses=[dict(row,icon=selected) for row in icon_uses]
                slots=override.get("slots",_default_slots(kind,item,crops))
                if "slots" in override:footprint_label=f"Custom {_footprint_name(slots)} footprint"
                elif kind=="tree":footprint_label="2×2 tree; 3×3 at 6+ years"
                else:footprint_label=f"{_footprint_name(slots)} runtime footprint"
                self.records.append({"id":ident,"kind":kind,"category":category,"key":item.key,"label":item.label,"params":params,"icon_key":selected or "","automatic_icon_key":icon,"icon_uses":icon_uses,"feature":feature,"slots":slots,"footprint_label":footprint_label})
        for ident,label,kind,icon,feature in FIXED:
            override=self.overrides.get(ident,{})
            slots=ONE_BY_ONE.copy()
            selected=override.get("icon_key",icon)
            slots=override.get("slots",slots)
            footprint_label=f"Custom {len(slots)}-cell footprint" if "slots" in override else ("1×1 small; 2×2 large" if feature=="ROCK" else "1×1 runtime footprint")
            self.records.append({"id":ident,"kind":kind,"category":"Map features","key":ident.split(":",1)[1],"label":label,"params":{},"icon_key":override.get("icon_key","") ,"automatic_icon_key":icon,"icon_uses":[{"season":"All seasons","stage":"Map feature","icon":selected}],"feature":feature,"slots":slots,"footprint_label":footprint_label})
    def select(self,row):self.candidate=copy.deepcopy(row)
    def save(self):
        c=self.candidate;self.overrides[c["id"]]={"params":c["params"],"icon_key":c["icon_key"],"slots":sorted(set(int(x) for x in c["slots"]))}
        self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=".objects.",suffix=".tmp",dir=self.path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as fh:json.dump(self.overrides,fh,indent=2,sort_keys=True);fh.flush();os.fsync(fh.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        apply_saved_overrides(self.path);self.load();self.select(next(r for r in self.records if r["id"]==c["id"]));return "Object saved and runtime catalogue reloaded."
