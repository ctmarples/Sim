import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pygame

from developer_tools.crop_editor import CropEditorService,_apply_registry,_base_registry,reload_crops


class CropEditorTests(unittest.TestCase):
    def setUp(self):self.original=tuple(_base_registry())
    def tearDown(self):_apply_registry(self.original,{})

    def test_save_reload_seasonality_and_presentation(self):
        from crops import SeasonPhase
        from seasons import Season
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=CropEditorService(root);item=next(c for c in service.records if c.key=="wheat");service.select(item)
            phases=(SeasonPhase.GROW,SeasonPhase.HARVEST,SeasonPhase.PLOUGH_PLANT,SeasonPhase.DORMANT)
            service.update(growth_days=77,plant_season=Season.AUTUMN,harvest_seasons=(Season.SUMMER,),year_phases=phases)
            service.candidate_seasonal={"AUTUMN":{"stem_colour":[12,34,56],"flower_colour":None}}
            ok,_=service.save();self.assertTrue(ok);self.assertTrue(reload_crops(service.path)[0])
            import crops
            self.assertEqual(crops.CROP_BY_KEY["wheat"].growth_days,77)
            self.assertEqual(crops.crop_presentation(crops.CROP_BY_KEY["wheat"],Season.AUTUMN)[1],(12,34,56))

    def test_renderer_uses_active_season_palette(self):
        import crops,icons,ui
        from world import FeatureType
        _apply_registry(self.original,{"wheat":{"_seasonal_presentation":{"WINTER":{"stem_colour":[9,19,29],"flower_colour":None}}}})
        with patch.object(icons,"blit_icon") as blit:
            ui.draw_feature(pygame.Surface((64,64)),FeatureType.CROP_HERB,32,32,32,crop_kind="wheat",season_name="WINTER")
        self.assertEqual(blit.call_args.kwargs["recolour"],{"stem":(9,19,29)})
        self.assertEqual(blit.call_args.kwargs["omit_classes"],("flower",))

    def test_invalid_crop_does_not_replace_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=CropEditorService(root);item=next(c for c in service.records if c.key=="barley");service.select(item);service.update(growth_days=0)
            self.assertFalse(service.save()[0]);self.assertFalse(service.path.exists())

    def test_legacy_wild_seed_chance_override_is_not_applied_to_crop(self):
        from crops import CROP_BY_KEY
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/"objects_data";data.mkdir();path=data/"crop_overrides.json"
            path.write_text('{"wheat":{"wild_seed_chance":0.99}}',encoding="utf-8")
            self.assertTrue(reload_crops(path)[0])
            self.assertNotEqual(CROP_BY_KEY["wheat"].wild_seed_chance,0.99)


if __name__=="__main__":unittest.main()
