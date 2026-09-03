"""Terrain ecology authoring and shared terrain-to-wild-plant membership."""
from __future__ import annotations

import json, os, tempfile
import hashlib
from pathlib import Path

from .content_io import get_content_root


DEFAULTS = {
    "SOIL": {"soil_moisture": .48, "fertility": 1.0, "temperature_offset_c": .8, "rainfall_multiplier": 1.0},
    "FOREST_FLOOR": {"soil_moisture": .62, "fertility": 1.0, "temperature_offset_c": -.8, "rainfall_multiplier": 1.0},
    "GRASS": {"soil_moisture": .43, "fertility": 1.0, "temperature_offset_c": 0.0, "rainfall_multiplier": 1.0},
    "MEADOW": {"soil_moisture": .47, "fertility": 1.0, "temperature_offset_c": .2, "rainfall_multiplier": 1.0},
    "RIPARIAN": {"soil_moisture": .76, "fertility": .8, "temperature_offset_c": -.8, "rainfall_multiplier": 1.06},
    "WATER": {"soil_moisture": 1.0, "fertility": 0.0, "temperature_offset_c": 0.0, "rainfall_multiplier": 1.0},
    "RIVER": {"soil_moisture": 1.0, "fertility": 0.0, "temperature_offset_c": 0.0, "rainfall_multiplier": 1.0},
    "ROCK": {"soil_moisture": .08, "fertility": 0.0, "temperature_offset_c": 1.5, "rainfall_multiplier": 1.0},
    "URBAN": {"soil_moisture": .04, "fertility": 0.0, "temperature_offset_c": 2.0, "rainfall_multiplier": 1.0},
    "PATH": {"soil_moisture": .12, "fertility": 0.0, "temperature_offset_c": .8, "rainfall_multiplier": 1.0},
}
PATH = Path(get_content_root()) / "objects_data" / "terrain_ecology.json"
_VALUES = None


def load_values(path=PATH):
    values={key:dict(row) for key,row in DEFAULTS.items()}
    try: raw=json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):raw={}
    if isinstance(raw,dict):
        for key,row in raw.items():
            if key in values and isinstance(row,dict):values[key].update({k:float(v) for k,v in row.items() if k in values[key]})
    return values


def terrain_value(terrain, field):
    global _VALUES
    if _VALUES is None:_VALUES=load_values()
    key=getattr(terrain,"name",str(terrain));return _VALUES.get(key,DEFAULTS.get(key,{})).get(field,0.0)


def ecology_signature():
    """Stable fingerprint used to reject stale terrain-derived save grids."""
    global _VALUES
    if _VALUES is None:_VALUES=load_values()
    raw=json.dumps(_VALUES,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class TerrainEditorService:
    def __init__(self,plants,root=None):
        self.plants=plants;self.path=Path(root or get_content_root())/"objects_data"/"terrain_ecology.json";self.values=load_values(self.path);self.terrain="GRASS"
    def select(self,key):self.terrain=key
    def wild_plants(self):return [p for p in self.plants.records if p.can_grow_wild]
    def selected_plants(self):return {p.key for p in self.wild_plants() if self.terrain in p.wild.get("terrains",[])}
    def save(self,values,plant_keys):
        global _VALUES
        row=dict(self.values[self.terrain]);row.update(values)
        if not (0<=row["soil_moisture"]<=1 and 0<=row["fertility"]<=1 and 0<=row["rainfall_multiplier"]<=2):return False,"Moisture/fertility must be 0–1; rainfall multiplier 0–2."
        self.values[self.terrain]=row;self.path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix="terrain_ecology.",suffix=".tmp")
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as h:json.dump(self.values,h,indent=2,sort_keys=True);h.write("\n")
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.plants.save_terrain_membership(self.terrain,set(plant_keys))
        if self.path == PATH:_VALUES={key:dict(row) for key,row in self.values.items()}
        return True,f"Saved {self.terrain.replace('_',' ').title()} ecology and wild plants."
