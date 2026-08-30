from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pygame

from developer_tools.wild_species_editor import WildSpeciesEditorService, _apply_registry, _base_registry, reload_wild_species
from wild_species import NicheRange


class WildSpeciesEditorTests(unittest.TestCase):
    def setUp(self): self.original=tuple(_base_registry())
    def tearDown(self): _apply_registry(self.original)

    def test_save_reload_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=WildSpeciesEditorService(root)
            item=next(x for x in service.records if x.key=="meadowsweet");service.select(item)
            service.update(spread_chance=.0123,moisture_niche=NicheRange(.44,.59,.88,.99))
            self.assertTrue(service.save().success)
            self.assertTrue(reload_wild_species(service.path).success)
            import wild_species
            active=wild_species.WILD_BY_KEY["meadowsweet"]
            self.assertEqual(active.spread_chance,.0123);self.assertEqual(active.moisture_niche.optimum_low,.59)

    def test_footprint_metadata_round_trip(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=WildSpeciesEditorService(root)
            item=next(x for x in service.records if x.key=="meadowsweet");service.select(item);service.candidate_slots=list(range(9))
            self.assertTrue(service.save().success)
            self.assertEqual(json.loads(service.path.read_text())["meadowsweet"]["_footprint_slots"],list(range(9)))
            service.load();service.select(next(x for x in service.records if x.key=="meadowsweet"));self.assertEqual(service.candidate_slots,list(range(9)))

    def test_invalid_candidate_does_not_replace_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=WildSpeciesEditorService(root)
            item=next(x for x in service.records if x.key=="meadowsweet");service.select(item)
            service.update(moisture_niche=NicheRange(.8,.2,.9,1.0))
            self.assertFalse(service.save().success)
            import wild_species
            self.assertEqual(wild_species.WILD_BY_KEY["meadowsweet"].moisture_niche,item.moisture_niche)
            self.assertFalse(service.path.exists())

    def test_malformed_file_does_not_replace_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/"objects_data";data.mkdir();path=data/"wild_species_overrides.json";path.write_text("{broken",encoding="utf-8")
            before=__import__("wild_species").WILD_SPECIES
            result=reload_wild_species(path)
            self.assertFalse(result.success);self.assertIs(__import__("wild_species").WILD_SPECIES,before)

    def test_cereal_flower_no_fill_persists(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=WildSpeciesEditorService(root)
            for key in ("wheat","rye","barley"):
                item=next(x for x in service.records if x.key==key);service.select(item)
                self.assertIn("flower",service.candidate_omit);self.assertTrue(service.save().success)
            data=json.loads(service.path.read_text())
            self.assertTrue(all("flower" in data[key]["_omit_icon_classes"] for key in ("wheat","rye","barley")))

    def test_wild_cereal_renderer_receives_species_palette(self):
        import icons
        import ui
        from world import FeatureType

        _apply_registry(self.original)
        surface=pygame.Surface((64,64))
        with patch.object(icons,"blit_icon") as blit:
            ui.draw_feature(surface,FeatureType.WILD_CROP,32,32,32,crop_kind="wheat")
        self.assertEqual(blit.call_args.kwargs["recolour"],{"stem":(200,170,55)})
        self.assertEqual(blit.call_args.kwargs["omit_classes"],("flower",))


if __name__=="__main__":unittest.main()
