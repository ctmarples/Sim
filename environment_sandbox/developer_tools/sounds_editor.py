"""Event-binding sound library and extensible parameter editor."""
from __future__ import annotations
import json, re
from dataclasses import asdict, dataclass, field
from pathlib import Path
import pygame
from settings import COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, COLOUR_TOOLBAR_BTN
from sound_system import CATALOGUE, SOUNDS, load_sound_catalogue
from .widgets import Checkbox, Dropdown, FloatField, TextField

CATEGORIES=("Villager Voice","UI","Environment","Effects");BUSES=("sfx","ambience")
SOURCE_TYPES=("none","event","terrain","wildlife")
SOURCE_KEYS=("soil","forest_floor","grass","meadow","riparian","water","river","rock","urban","path","deer","boar","bee","rabbit","frog","vole","wolf","fox","owl","hawk","carp","perch","pike","roach")

@dataclass
class SoundDef:
    key:str;label:str;category:str;file:str;trigger:str="";bus:str="sfx";volume:float=1.0;weight:float=1.0
    conditions:dict=field(default_factory=dict);parameters:dict=field(default_factory=dict)

class SoundEditorService:
    def __init__(self,path:Path=CATALOGUE):self.path=Path(path);self.records=[];self.selected=None;self.load()
    def load(self):
        order={name:i for i,name in enumerate(CATEGORIES)};self.records=[]
        for key,value in load_sound_catalogue(self.path).items():
            params=dict(value.get("parameters",{}))
            if "loop" in value:params.setdefault("loop",bool(value["loop"]))
            self.records.append(SoundDef(key,str(value.get("label",key)),str(value.get("category","Effects")),str(value.get("file","")),str(value.get("trigger","")),str(value.get("bus","sfx")),float(value.get("volume",1)),float(value.get("weight",1)),dict(value.get("conditions",{})),params))
        self.records.sort(key=lambda x:(order.get(x.category,99),x.label.casefold()))
    def new(self):self.selected=SoundDef("new_sound","New Sound","Effects","",trigger="game.notification")
    def save(self,record):
        if not re.fullmatch(r"[a-z][a-z0-9_]*",record.key):return False,"Key must use lowercase letters, numbers, and underscores."
        if not record.label.strip():return False,"Label is required."
        if record.category not in CATEGORIES:return False,"Choose a sound category."
        if record.bus not in BUSES:return False,"Choose a volume bus."
        if not re.fullmatch(r"[a-z][a-z0-9_.]*",record.trigger):return False,"Trigger must be a dot-separated event name."
        audio=(SOUNDS/record.file).resolve()
        try:audio.relative_to(SOUNDS.resolve())
        except ValueError:return False,"Audio file must remain inside the sounds library."
        if not record.file or not audio.is_file():return False,f"Audio file was not found in {SOUNDS.name}/."
        try:raw=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError):raw={}
        raw[record.key]={k:v for k,v in asdict(record).items() if k!="key"};self.path.write_text(json.dumps(raw,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        self.load();self.selected=next(x for x in self.records if x.key==record.key);return True,"Sound event binding saved. Restart the game to reload its audio file."

class SoundEditorPage:
    def __init__(self):
        self.service=SoundEditorService();self.message="Select a sound or add an event binding.";r=pygame.Rect(0,0,1,1)
        self.key=TextField(r);self.label=TextField(r);self.filename=TextField(r);self.trigger=TextField(r,placeholder="villager.acknowledgement")
        self.volume=FloatField(r,"1",minimum=0,maximum=1);self.weight=FloatField(r,"1",minimum=0)
        self.category=Dropdown(r,[(x,x) for x in CATEGORIES],"Effects");self.bus=Dropdown(r,[(x,x.title()) for x in BUSES],"sfx")
        self.source_type=Dropdown(r,[(x,x.title()) for x in SOURCE_TYPES],"none");self.source_key=Dropdown(r,[(x,x.replace("_"," ").title()) for x in SOURCE_KEYS],"forest_floor")
        self.loop=Checkbox(r);self.menu_allowed=Checkbox(r);self.conditions=TextField(r,"{}",placeholder='{"actor":"villager"}');self.extra=TextField(r,"{}",placeholder='{"future_parameter":1}')
        specs={"cooldown":(0,None),"sample_interval":(.01,None),"search_radius":(1,None),"audible_distance":(0,None),"falloff_distance":(.01,None),"easing_speed":(.01,None),"start_threshold":(0,1),"fade_in_ms":(0,None),"fade_out_ms":(0,None),"menu_fade_out_ms":(0,None),"min_interval":(0,None),"max_interval":(0,None)}
        self.param_fields={key:FloatField(r,"",minimum=limits[0],maximum=limits[1],nullable=True) for key,limits in specs.items()}
        self._buttons=[];self._rows=[]
    def _select(self,item):
        self.service.selected=item
        for control,value in ((self.key,item.key),(self.label,item.label),(self.filename,item.file),(self.trigger,item.trigger),(self.volume,str(item.volume)),(self.weight,str(item.weight))):control.text=value;control.cursor=len(value)
        self.category.select(item.category);self.bus.select(item.bus);self.loop.checked=bool(item.parameters.get("loop",False));self.menu_allowed.checked=bool(item.parameters.get("menu_allowed",False))
        self.source_type.select(str(item.parameters.get("source_type","none")));source_key=str(item.parameters.get("source_key","forest_floor"))
        if not self.source_key.select(source_key):self.source_key.options.insert(0,(source_key,source_key.replace(","," + ").replace("_"," ").title()));self.source_key.select(source_key)
        self.conditions.text=json.dumps(item.conditions,separators=(",",":"));known={"loop","menu_allowed","source_type","source_key",*self.param_fields};extra={k:v for k,v in item.parameters.items() if k not in known};self.extra.text=json.dumps(extra,separators=(",",":"))
        for key,control in self.param_fields.items():control.text="" if key not in item.parameters else str(item.parameters[key]);control.cursor=len(control.text)
    @staticmethod
    def _object(control):
        try:value=json.loads(control.text or "{}");return value if isinstance(value,dict) else None
        except (ValueError,TypeError):return None
    def handle_event(self,event):
        for control in (self.key,self.label,self.filename,self.trigger,self.volume,self.weight,self.conditions,self.extra,*self.param_fields.values()):
            if control.handle_event(event):return True
        for control in (self.category,self.bus,self.source_type,self.source_key,self.loop,self.menu_allowed):
            if control.handle_event(event):return True
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            action=next((a for rect,a in self._buttons if rect.collidepoint(event.pos)),None)
            if action=="new":self.service.new();self._select(self.service.selected);return True
            if action=="save":
                volume=self.volume.parse();weight=self.weight.parse();conditions=self._object(self.conditions);params=self._object(self.extra)
                if volume is None or weight is None:self.message=self.volume.error or self.weight.error or "Invalid number.";return True
                if conditions is None or params is None:self.message="Conditions and extra parameters must be JSON objects.";return True
                for key,control in self.param_fields.items():
                    value=control.parse()
                    if control.text.strip() and value is None:self.message=f"{key}: {control.error}";return True
                    if control.text.strip():params[key]=value
                params.update(loop=self.loop.checked,menu_allowed=self.menu_allowed.checked)
                if self.source_type.value!="none":
                    params["source_type"]=self.source_type.value
                    if self.source_type.value in ("terrain","wildlife"):params["source_key"]=self.source_key.value
                    else:params.pop("source_key",None)
                _ok,self.message=self.service.save(SoundDef(self.key.text.strip(),self.label.text.strip(),self.category.value,self.filename.text.strip(),self.trigger.text.strip(),self.bus.value,volume,weight,conditions,params));return True
            for rect,item in self._rows:
                if rect.collidepoint(event.pos):self._select(item);return True
        return False
    def _field(self,surface,font,label,control,x,y,w):
        surface.blit(font.render(label,True,COLOUR_TEXT_DIM),(x,y));control.rect=pygame.Rect(x,y+17,w,27);control.draw(surface,font)
    def draw(self,surface,panel,font,small):
        left=pygame.Rect(panel.x+30,panel.y+72,260,panel.h-125);area=pygame.Rect(left.right+18,left.y,panel.right-left.right-48,left.h)
        pygame.draw.rect(surface,(23,29,31),left);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,left,1);self._rows=[];y=left.y+8;grouped={c:[] for c in CATEGORIES}
        for item in self.service.records:grouped.setdefault(item.category,[]).append(item)
        for category,items in grouped.items():
            surface.blit(font.render(category,True,COLOUR_TEXT_DIM),(left.x+9,y));y+=21
            for item in items:
                rect=pygame.Rect(left.x+8,y,left.w-16,23);self._rows.append((rect,item))
                if self.service.selected and item.key==self.service.selected.key:pygame.draw.rect(surface,COLOUR_TOOLBAR_BTN,rect)
                surface.blit(small.render(f"{item.label} · {item.trigger}",True,COLOUR_TEXT),(rect.x+6,rect.y+4));y+=24
        gap=12;w=(area.w-gap*2)//3;x1=area.x;x2=x1+w+gap;x3=x2+w+gap
        surface.blit(font.render("BINDING",True,COLOUR_TEXT),(x1,area.y));y=area.y+25
        for label,control in (("Key",self.key),("Label",self.label),("Audio filename",self.filename),("Event trigger",self.trigger),("Conditions JSON",self.conditions),("Future parameters JSON",self.extra)):
            self._field(surface,small,label,control,x1,y,w);y+=48
        surface.blit(font.render("SOURCE & MIX",True,COLOUR_TEXT),(x2,area.y));y=area.y+25
        for label,control in (("Category",self.category),("Volume bus",self.bus),("Source type",self.source_type),("Terrain / wildlife source",self.source_key),("Volume 0–1",self.volume),("Probability weight",self.weight)):
            self._field(surface,small,label,control,x2,y,w);y+=48
        self.loop.rect=pygame.Rect(x2,y,19,19);self.loop.draw(surface);surface.blit(small.render("Loop",True,COLOUR_TEXT_DIM),(x2+27,y+2));y+=29
        self.menu_allowed.rect=pygame.Rect(x2,y,19,19);self.menu_allowed.draw(surface);surface.blit(small.render("Allowed in menus",True,COLOUR_TEXT_DIM),(x2+27,y+2))
        surface.blit(font.render("PROXIMITY & TIMING",True,COLOUR_TEXT),(x3,area.y));y=area.y+25
        labels=(("Cooldown seconds","cooldown"),("Sample interval","sample_interval"),("Search radius cells","search_radius"),("Audible distance","audible_distance"),("Falloff distance","falloff_distance"),("Easing speed","easing_speed"),("Start threshold","start_threshold"),("Fade in ms","fade_in_ms"),("Fade out ms","fade_out_ms"),("Menu fade ms","menu_fade_out_ms"),("Min repeat seconds","min_interval"),("Max repeat seconds","max_interval"))
        for label,key in labels:self._field(surface,small,label,self.param_fields[key],x3,y,w);y+=43
        self._buttons=[(pygame.Rect(x1,area.bottom-38,100,32),"new"),(pygame.Rect(x1+110,area.bottom-38,100,32),"save")]
        for rect,action in self._buttons:pygame.draw.rect(surface,COLOUR_TOOLBAR_BTN,rect,border_radius=3);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,rect,1,border_radius=3);surface.blit(font.render(action.title(),True,COLOUR_TEXT),(rect.x+20,rect.y+7))
        surface.blit(small.render(self.message,True,COLOUR_TEXT_DIM),(x1,area.bottom-62))
        for dropdown in (self.category,self.bus,self.source_type,self.source_key):
            if dropdown.open:dropdown.draw(surface,small)
