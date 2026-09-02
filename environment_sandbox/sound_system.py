"""Small, failure-tolerant sound-effects and positional ambience controller."""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import pygame


SOUNDS = Path(__file__).resolve().parent / "assets" / "sounds"
PREFS = SOUNDS / "sound_settings.json"
CATALOGUE = SOUNDS / "sounds.json"

DEFAULT_SOUNDS = {
    "door": {"label":"Door","category":"Effects","file":"effects/dragon-studio-open-door-sfx-454245.mp3","trigger":"player.enter_building","bus":"sfx","volume":1.0,"parameters":{}},
    "page": {"label":"Book page turn","category":"UI","file":"ui/xpmonster-turning-page-in-a-book-419580.mp3","trigger":"ui.window.change","bus":"sfx","volume":1.0,"parameters":{"menu_allowed":True}},
    "book_close": {"label":"Book closing","category":"UI","file":"ui/freesound_community-book-closing-48184.mp3","trigger":"ui.window.close","bus":"sfx","volume":1.0,"parameters":{"menu_allowed":True}},
    "forest": {"label":"Forest ambience","category":"Environment","file":"environment/terrain/bbc_forest-atm_nhu9679709.mp3","trigger":"ambience.proximity","bus":"ambience","volume":1.0,"weight":1.0,"parameters":{"source_type":"terrain","source_key":"forest_floor","loop":True,"sample_interval":0.2,"search_radius":12,"audible_distance":10.0,"falloff_distance":8.0,"easing_speed":2.5,"start_threshold":0.002,"fade_in_ms":600,"fade_out_ms":500,"menu_fade_out_ms":150,"min_interval":4.0,"max_interval":8.0}},
    "stream": {"label":"Water stream","category":"Environment","file":"environment/terrain/26327991-water-stream-108384.mp3","trigger":"ambience.proximity","bus":"ambience","volume":1.0,"weight":1.0,"parameters":{"source_type":"terrain","source_key":"water,river","loop":True,"sample_interval":0.2,"search_radius":12,"audible_distance":8.0,"falloff_distance":6.0,"easing_speed":2.5,"start_threshold":0.002,"fade_in_ms":600,"fade_out_ms":500,"menu_fade_out_ms":150,"min_interval":4.0,"max_interval":8.0}},
    "build": {"label":"Build","category":"Effects","file":"effects/freesound_community-wooden-mallet-38769.mp3","trigger":"work.build","bus":"sfx","volume":1.0,"parameters":{"cooldown":0.25,"source_type":"event","audible_distance":14.0,"falloff_distance":12.0,"fade_out_ms":250}},
    "craft": {"label":"Craft","category":"Effects","file":"effects/freesound_community-deeper-saw-wood-37224.mp3","trigger":"work.craft","bus":"sfx","volume":1.0,"parameters":{"cooldown":0.35,"source_type":"event","audible_distance":12.0,"falloff_distance":10.0,"fade_out_ms":250}},
    "plant": {"label":"Plant","category":"Effects","file":"effects/freesound_community-digging-with-shovel-63069.mp3","trigger":"work.plant","bus":"sfx","volume":1.0,"parameters":{"cooldown":0.25,"source_type":"event","audible_distance":10.0,"falloff_distance":8.0,"fade_out_ms":200}},
    "cook": {"label":"Cook","category":"Effects","file":"effects/freesound_community-cooking-onions-72799.mp3","trigger":"work.cook","bus":"sfx","volume":1.0,"parameters":{"cooldown":0.35,"source_type":"event","audible_distance":10.0,"falloff_distance":8.0,"fade_out_ms":250}},
    "chop": {"label":"Chop wood","category":"Effects","file":"effects/wings_of_freedom-chopping-wood-435769.mp3","trigger":"work.chop","bus":"sfx","volume":1.0,"parameters":{"cooldown":0.20,"source_type":"event","audible_distance":14.0,"falloff_distance":12.0,"fade_out_ms":250}},
}


def load_sound_catalogue(path: Path = CATALOGUE) -> dict[str, dict]:
    records = {key: dict(value) for key, value in DEFAULT_SOUNDS.items()}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key,value in raw.items():
                if not isinstance(value,dict):continue
                merged=dict(records.get(key,{}));merged.update(value)
                if key in records and isinstance(records[key].get("parameters"),dict):
                    params=dict(records[key]["parameters"]);params.update(value.get("parameters",{}));merged["parameters"]=params
                records[key]=merged
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return records


class SoundSystem:
    def __init__(self, *, enabled: bool = True) -> None:
        self.sfx_volume = 0.7
        self.ambience_volume = 0.55
        self.enabled = False
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._forest_channel: pygame.mixer.Channel | None = None
        self._stream_channel: pygame.mixer.Channel | None = None
        self._forest_level = 0.0
        self._stream_level = 0.0
        self._sample_wait = 0.0
        self._last_played: dict[str, float] = {}
        self._proximity_channels: dict[tuple[str,str], pygame.mixer.Channel] = {}
        self._proximity_levels: dict[tuple[str,str], float] = {}
        self._proximity_next: dict[tuple[str,str], float] = {}
        self._proximity_variant_volume: dict[tuple[str,str], float] = {}
        self._proximity_sample_wait = 0.0
        self._listener_position: tuple[float,float] | None = None
        self._active_spatial: list[dict[str,object]] = []
        self.menu_mode = False
        self.catalogue = load_sound_catalogue()
        self._load_prefs()
        if not enabled:
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            groups=self._proximity_groups();reserved=2+len(groups)
            pygame.mixer.set_num_channels(max(reserved + 8, pygame.mixer.get_num_channels()))
            self._sounds = {
                key: pygame.mixer.Sound(str(SOUNDS / str(record.get("file", ""))))
                for key, record in self.catalogue.items()
                if (SOUNDS / str(record.get("file", ""))).is_file()
            }
            for index,group in enumerate(groups):self._proximity_channels[group]=pygame.mixer.Channel(2+index)
            self._forest_channel=self._proximity_channels.get(("terrain","forest_floor"));self._stream_channel=self._proximity_channels.get(("terrain","water,river"))
            pygame.mixer.set_reserved(reserved)
            self.enabled = True
        except (pygame.error, OSError):
            self.enabled = False

    def _load_prefs(self) -> None:
        try:
            raw = json.loads(PREFS.read_text(encoding="utf-8"))
            self.sfx_volume = max(0.0, min(1.0, float(raw.get("sfx", self.sfx_volume))))
            self.ambience_volume = max(0.0, min(1.0, float(raw.get("ambience", self.ambience_volume))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        try:
            PREFS.write_text(
                json.dumps({"sfx": self.sfx_volume, "ambience": self.ambience_volume}, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def play(self, name: str, *, cooldown: float | None = None, context: dict[str,object] | None = None) -> None:
        record = self.catalogue.get(name, {})
        params = record.get("parameters", {}) if isinstance(record.get("parameters", {}), dict) else {}
        bus_volume = self.ambience_volume if record.get("bus") == "ambience" else self.sfx_volume
        if not self.enabled or bus_volume <= 0.0:
            return
        if self.menu_mode and not params.get("menu_allowed", False):
            return
        spatial_volume=1.0
        if params.get("source_type")=="event":
            context=context or {};listener=self._listener_position
            if listener is None or "x" not in context or "y" not in context:return
            distance=math.hypot(float(context["x"])-listener[0],float(context["y"])-listener[1])
            audible=float(params.get("audible_distance",12));falloff=max(.01,float(params.get("falloff_distance",10)))
            spatial_volume=max(0.0,min(1.0,(audible-distance)/falloff))
            if spatial_volume<=0:return
        sound = self._sounds.get(name)
        if sound is not None:
            cooldown = float(params.get("cooldown", 0.0) if cooldown is None else cooldown)
            now = time.monotonic()
            if now - self._last_played.get(name, -1e9) < cooldown:
                return
            self._last_played[name] = now
            sound.set_volume(bus_volume * max(0.0, min(1.0, float(record.get("volume", 1.0)))))
            channel=sound.play(loops=-1 if params.get("loop", False) and not self.menu_mode else 0)
            if params.get("source_type")=="event" and channel is not None:
                channel.set_volume(spatial_volume);self._active_spatial.append({"channel":channel,"x":float(context["x"]),"y":float(context["y"]),"parameters":params})

    def emit(self, trigger: str, **context: object) -> str | None:
        """Play one matching binding. Unknown context and parameters are future-safe."""
        matches = []
        for key, record in self.catalogue.items():
            if record.get("trigger") != trigger:
                continue
            conditions = record.get("conditions", {})
            if isinstance(conditions, dict) and all(context.get(k) == v for k, v in conditions.items()):
                matches.append((key, max(0.0, float(record.get("weight", 1.0))), len(conditions)))
        if not matches:
            return None
        specificity=max(item[2] for item in matches);matches=[item for item in matches if item[2]==specificity]
        weights = [weight for _key, weight, _specificity in matches]
        key = random.choices([key for key, _weight, _specificity in matches], weights=weights if any(weights) else None, k=1)[0]
        self.play(key,context=context)
        return key

    def _proximity_groups(self) -> list[tuple[str,str]]:
        groups=set()
        for record in self.catalogue.values():
            params=record.get("parameters",{})
            if record.get("trigger")=="ambience.proximity" and isinstance(params,dict):
                source_type=str(params.get("source_type",""));source_key=str(params.get("source_key",""))
                if source_type and source_key:groups.add((source_type,source_key))
        return sorted(groups)

    @staticmethod
    def _nearby_wildlife(wildlife: object, fish: object | None):
        for animal in getattr(wildlife,"animals",()):yield str(animal.kind.name).lower(),float(animal.x),float(animal.y)
        for colony in getattr(wildlife,"colonies",()):yield str(colony.kind.name).lower(),float(colony.x),float(colony.y)
        for pack in getattr(wildlife,"wolf_packs",()):
            for member in getattr(pack,"members",()):yield str(pack.kind.name).lower(),float(member.x),float(member.y)
        for animal in getattr(fish,"fish",()) if fish is not None else ():
            yield str(animal.kind.name).lower(),float(animal.x),float(animal.y)

    def update_proximity(self,dt:float,world:object,wildlife:object|None,fish:object|None,focus_x:float,focus_y:float)->None:
        """Mix authored terrain/wildlife emitters around the camera focus."""
        if self.menu_mode or not self.enabled:return
        self._listener_position=(float(focus_x),float(focus_y))
        active=[]
        for item in self._active_spatial:
            channel=item["channel"];params=item["parameters"]
            if not channel.get_busy():continue
            distance=math.hypot(float(item["x"])-focus_x,float(item["y"])-focus_y);audible=float(params.get("audible_distance",12));falloff=max(.01,float(params.get("falloff_distance",10)));level=max(0.0,min(1.0,(audible-distance)/falloff))
            if level<=0:channel.fadeout(int(params.get("fade_out_ms",250)))
            else:channel.set_volume(level);active.append(item)
        self._active_spatial=active
        groups=self._proximity_groups()
        # Hot-added bindings receive a channel without disturbing existing loops.
        for group in groups:
            if group not in self._proximity_channels:
                channel=pygame.mixer.find_channel(True)
                if channel is not None:self._proximity_channels[group]=channel
        self._proximity_sample_wait-=max(0.0,dt);sample=self._proximity_sample_wait<=0
        if sample:self._proximity_sample_wait=min((float(r.get("parameters",{}).get("sample_interval",.2)) for r in self.catalogue.values() if r.get("trigger")=="ambience.proximity"),default=.2)
        wildlife_points=list(self._nearby_wildlife(wildlife,fish)) if wildlife is not None else []
        now=time.monotonic()
        for group in groups:
            records=[(key,r) for key,r in self.catalogue.items() if r.get("trigger")=="ambience.proximity" and (str(r.get("parameters",{}).get("source_type","")),str(r.get("parameters",{}).get("source_key","")))==group]
            if not records:continue
            params=records[0][1].get("parameters",{});nearest=float("inf")
            if sample:
                radius=max(1,int(params.get("search_radius",12)));source_keys={x.strip().lower() for x in group[1].split(",")}
                if group[0]=="terrain":
                    cx,cy=int(focus_x),int(focus_y)
                    for y in range(max(0,cy-radius),min(world.rows,cy+radius+1)):
                        for x in range(max(0,cx-radius),min(world.cols,cx+radius+1)):
                            if world.cells[y][x].terrain.name.lower() in source_keys:nearest=min(nearest,math.hypot(x+.5-focus_x,y+.5-focus_y))
                elif group[0]=="wildlife":
                    for kind,x,y in wildlife_points:
                        if kind in source_keys:nearest=min(nearest,math.hypot(x-focus_x,y-focus_y))
                audible=float(params.get("audible_distance",10));falloff=max(.01,float(params.get("falloff_distance",8)))
                targets=self.__dict__.setdefault("_proximity_targets",{});previous=targets.get(group,0.0);targets[group]=self.ambience_volume*max(0.0,min(1.0,(audible-nearest)/falloff))
                if previous>0 and targets[group]<=0 and self._proximity_channels.get(group) is not None:self._proximity_channels[group].fadeout(int(params.get("fade_out_ms",500)))
            target=getattr(self,"_proximity_targets",{}).get(group,0.0);level=self._proximity_levels.get(group,0.0)
            level+=(target-level)*(1-math.exp(-float(params.get("easing_speed",2.5))*max(0.0,dt)));self._proximity_levels[group]=level
            channel=self._proximity_channels.get(group)
            if channel is None:continue
            if level>float(params.get("start_threshold",.002)) and not channel.get_busy() and now>=self._proximity_next.get(group,0):
                weights=[max(0,float(r.get("weight",1))) for _key,r in records];key,record=random.choices(records,weights=weights if any(weights) else None,k=1)[0];chosen=record.get("parameters",{})
                sound=self._sounds.get(key)
                if sound is not None:
                    channel.play(sound,loops=-1 if chosen.get("loop",False) else 0,fade_ms=int(chosen.get("fade_in_ms",params.get("fade_in_ms",600))))
                    self._proximity_variant_volume[group]=float(record.get("volume",1.0))
                self._proximity_next[group]=now+random.uniform(float(chosen.get("min_interval",4)),max(float(chosen.get("min_interval",4)),float(chosen.get("max_interval",8))))
            # Variant volume is applied on its next selection; group level remains spatial.
            channel.set_volume(level*self._proximity_variant_volume.get(group,float(records[0][1].get("volume",1.0))))

    def set_menu_mode(self, active: bool) -> None:
        self.menu_mode = bool(active)
        if active:
            fades=[int(r.get("parameters",{}).get("menu_fade_out_ms",150)) for r in self.catalogue.values() if r.get("bus")=="ambience"]
            for channel in self._proximity_channels.values():
                if channel is not None:
                    channel.fadeout(max(fades,default=150))
            for item in self._active_spatial:item["channel"].fadeout(int(item["parameters"].get("fade_out_ms",250)))
            self._active_spatial=[]
            self._forest_level = self._stream_level = 0.0
