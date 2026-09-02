from __future__ import annotations
import unittest
from unittest import mock
from types import SimpleNamespace
from sound_system import SoundSystem

class FakeSound:
    def __init__(self):self.volume=None;self.plays=[]
    def set_volume(self,value):self.volume=value
    def play(self,**kwargs):self.plays.append(kwargs)

class ChannelSound(FakeSound):
    def __init__(self,channel):super().__init__();self.channel=channel
    def play(self,**kwargs):super().play(**kwargs);return self.channel

class FakeChannel:
    def __init__(self):self.busy=False;self.plays=[];self.volume=0
    def get_busy(self):return self.busy
    def play(self,sound,**kwargs):self.busy=True;self.plays.append((sound,kwargs))
    def set_volume(self,value):self.volume=value
    def fadeout(self,_milliseconds):self.busy=False

class SoundEventTests(unittest.TestCase):
    def system(self,catalogue):
        sounds=SoundSystem(enabled=False);sounds.enabled=True;sounds.catalogue=catalogue;sounds._sounds={key:FakeSound() for key in catalogue};return sounds
    def test_specific_context_binding_wins_over_fallback(self):
        sounds=self.system({
            "fallback":{"trigger":"villager.acknowledgement","volume":1,"parameters":{}},
            "farmer":{"trigger":"villager.acknowledgement","volume":1,"conditions":{"job":"farmer"},"parameters":{}},
        })
        self.assertEqual(sounds.emit("villager.acknowledgement",job="farmer"),"farmer")
        self.assertEqual(len(sounds._sounds["fallback"].plays),0)
    def test_binding_parameters_control_menu_cooldown_volume_and_loop(self):
        sounds=self.system({"voice":{"trigger":"work.assigned.response","bus":"sfx","volume":.5,"parameters":{"menu_allowed":True,"cooldown":2,"loop":True}}})
        sounds.sfx_volume=.6;sounds.menu_mode=True
        with mock.patch("sound_system.time.monotonic",side_effect=[10,11,13]):
            sounds.emit("work.assigned.response");sounds.emit("work.assigned.response");sounds.emit("work.assigned.response")
        sound=sounds._sounds["voice"];self.assertAlmostEqual(sound.volume,.3);self.assertEqual(len(sound.plays),2)
        self.assertEqual(sound.plays[0]["loops"],0) # menu sounds can never become stuck loops

    def test_weighted_terrain_proximity_variant(self):
        params={"source_type":"terrain","source_key":"meadow","audible_distance":5,"falloff_distance":5,"loop":True}
        sounds=self.system({"day":{"trigger":"ambience.proximity","bus":"ambience","volume":.8,"weight":1,"parameters":params},"birds":{"trigger":"ambience.proximity","bus":"ambience","volume":.5,"weight":3,"parameters":params}})
        group=("terrain","meadow");channel=FakeChannel();sounds._proximity_channels={group:channel};sounds._proximity_levels={};sounds._proximity_next={};sounds._proximity_variant_volume={};sounds._proximity_sample_wait=0
        terrain=SimpleNamespace(name="MEADOW");world=SimpleNamespace(rows=1,cols=1,cells=[[SimpleNamespace(terrain=terrain)]])
        with mock.patch("sound_system.random.choices",return_value=[("birds",sounds.catalogue["birds"])]),mock.patch("sound_system.time.monotonic",return_value=10):sounds.update_proximity(.2,world,None,None,.5,.5)
        self.assertEqual(channel.plays[0][0],sounds._sounds["birds"]);self.assertGreater(channel.volume,0)

    def test_wildlife_sources_include_animals_colonies_packs_and_fish(self):
        kind=lambda name:SimpleNamespace(name=name)
        wildlife=SimpleNamespace(animals=[SimpleNamespace(kind=kind("DEER"),x=1,y=2)],colonies=[SimpleNamespace(kind=kind("BEE"),x=3,y=4)],wolf_packs=[SimpleNamespace(kind=kind("WOLF"),members=[SimpleNamespace(x=5,y=6)])])
        fish=SimpleNamespace(fish=[SimpleNamespace(kind=kind("PIKE"),x=7,y=8)])
        self.assertEqual({row[0] for row in SoundSystem._nearby_wildlife(wildlife,fish)},{"deer","bee","wolf","pike"})

    def test_event_position_effect_attenuates_and_fades_out(self):
        sounds=self.system({"build":{"trigger":"work.build","volume":1,"parameters":{"source_type":"event","audible_distance":10,"falloff_distance":8,"fade_out_ms":200}}})
        channel=FakeChannel();sounds._sounds["build"]=ChannelSound(channel);sounds._listener_position=(0,0)
        sounds.emit("work.build",x=4,y=0);self.assertAlmostEqual(channel.volume,.75)
        world=SimpleNamespace(rows=0,cols=0,cells=[]);sounds.update_proximity(.1,world,None,None,20,0)
        self.assertFalse(channel.busy)

if __name__ == "__main__":unittest.main()
