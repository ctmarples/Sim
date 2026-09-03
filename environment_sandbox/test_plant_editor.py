import tempfile
import unittest
from pathlib import Path

from developer_tools.plant_editor import PlantDef,PlantEditorService


class PlantEditorTests(unittest.TestCase):
    def setUp(self):
        import crops,wild_species,trees
        self.runtime=(crops.CROPS,crops.CROP_BY_KEY,wild_species.WILD_SPECIES,wild_species.WILD_BY_KEY,trees.TREES,trees.TREE_BY_KEY)
    def tearDown(self):
        import crops,wild_species,trees
        crops.CROPS,crops.CROP_BY_KEY,wild_species.WILD_SPECIES,wild_species.WILD_BY_KEY,trees.TREES,trees.TREE_BY_KEY=self.runtime
    def test_existing_crop_and_wild_species_merge_by_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root)
            wheat=[p for p in service.records if p.key=="wheat"]
            self.assertEqual(len(wheat),1);self.assertTrue(wheat[0].can_be_cultivated);self.assertTrue(wheat[0].can_grow_wild)

    def test_unselected_plant_page_accepts_input(self):
        import pygame
        from developer_tools.authoring_ui import PlantAuthoringPage
        from developer_tools.icons_browser import IconBrowserService
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();page=PlantAuthoringPage(PlantEditorService(root),IconBrowserService())
            consumed,result=page.handle_event(pygame.event.Event(pygame.MOUSEMOTION,{"pos":(1,1)}))
            self.assertFalse(consumed);self.assertIsNone(result)

    def test_plant_page_new_and_duplicate_actions(self):
        from developer_tools.authoring_ui import PlantAuthoringPage
        from developer_tools.icons_browser import IconBrowserService
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();page=PlantAuthoringPage(PlantEditorService(root),IconBrowserService())
            page.act("new");self.assertEqual(page.service.candidate.key,"new_plant");self.assertFalse(page.controls["key"].disabled)
            page.controls["key"].text="mint";page.sync();self.assertEqual(page.service.candidate.key,"mint")
            page.act("duplicate");self.assertEqual(page.service.candidate.key,"mint_copy");self.assertFalse(page.controls["key"].disabled)

    def test_resource_page_initialises_search_control(self):
        import pygame
        from developer_tools.authoring_ui import ResourceAuthoringPage
        from developer_tools.icons_browser import IconBrowserService
        from developer_tools.resources_browser import ResourceEditorService
        page=ResourceAuthoringPage(ResourceEditorService(),IconBrowserService())
        consumed=page.handle_event(pygame.event.Event(pygame.MOUSEMOTION,{"pos":(1,1)}))
        self.assertFalse(consumed)

    def test_new_dual_mode_herb_persists_and_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);service.new()
            service.update(key="pumpkin",label="Pumpkin",short="pump",produce_resource="pumpkin",seed_resource="pumpkin_seeds",can_be_cultivated=True,can_grow_wild=True,cultivated={"plant_season":"SPRING","harvest_seasons":["AUTUMN"],"growth_days":60,"year_phases":["PLOUGH_PLANT","GROW","HARVEST","FALLOW"],"seed_amounts":[1,2],"sparse_icon":"crop_vine","dense_icon":"vine_plant_dense","stem_colour":[55,135,55],"flower_colour":[235,180,60],"footprint":list(range(9)),"seasonal_recolour":{}},wild={"feature":"WILD_CROP","terrains":["GRASS"],"icon":"crop_vine","recolour":{"stem":[55,135,55]},"footprint":[4]},harvest_outputs={"pumpkin":2})
            self.assertTrue(service.save()[0])
            import crops,wild_species
            self.assertIn("pumpkin",crops.CROP_BY_KEY);self.assertIn("pumpkin",wild_species.WILD_BY_KEY)
            self.assertTrue(service.path.exists())

    def test_new_tree_is_one_plant_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);service.new()
            service.update(key="apple",label="Apple",short="appl",growth_form="tree",produce_resource="apple",seed_resource="apple_saplings",perennial=True,can_be_cultivated=True,can_grow_wild=True,tree={"growth_years":3,"wood_resource":"logs","wood_yield":2,"canopy_colour":[45,125,55],"sapling_colour":[110,185,80],"shape":"round","cone_scale":1},wild={"terrains":["GRASS"],"footprint":list(range(9))},harvest_outputs={"apple":3})
            self.assertTrue(service.save()[0])
            import trees
            self.assertIn("apple",trees.TREE_BY_KEY)
            self.assertEqual(sum(p.key=="apple" for p in service.records),1)

    def test_duplicate_and_tombstone_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);service.select(next(p for p in service.records if p.key=="wheat"))
            self.assertTrue(service.duplicate()[0]);self.assertEqual(service.candidate.key,"wheat_copy");self.assertTrue(service.save()[0]);self.assertTrue(service.delete()[0])
            self.assertNotIn("wheat_copy",{p.key for p in service.records});self.assertTrue(service.load()[0]);self.assertNotIn("wheat_copy",{p.key for p in service.records})

    def test_svg_classes_and_single_season_plan(self):
        from developer_tools.authoring_ui import PlantAuthoringPage
        from icons import icon_svg_classes
        self.assertEqual(set(icon_svg_classes("crop_plant")),{"stem","flower"})
        self.assertEqual(PlantAuthoringPage._derived_year_phases("AUTUMN","SUMMER"),["GROW","HARVEST","PLOUGH_PLANT","GROW"])

    def test_harvest_maxima_project_to_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);service.new()
            service.update(key="testleaf",label="Testleaf",short="tst",produce_resource="testleaf",seed_resource="testleaf_seeds",can_be_cultivated=True,can_grow_wild=True,cultivated={"plant_season":"SPRING","harvest_season":"SUMMER","harvest_seasons":["SUMMER"],"harvest_max":9,"growth_days":30,"year_phases":["PLOUGH_PLANT","HARVEST","FALLOW","FALLOW"],"seed_amounts":[1,2],"sparse_icon":"crop_plant","dense_icon":"crop_plant_dense"},wild={"terrains":["GRASS"],"icon":"crop_plant","harvest_max":3,"seed_amount_max":2},harvest_outputs={"testleaf":3})
            self.assertTrue(service.save()[0])
            import crops,wild_species
            self.assertEqual(crops.CROP_HARVEST_MAX["testleaf"],9);self.assertEqual(wild_species.WILD_BY_KEY["testleaf"].yield_amount,3);self.assertEqual(wild_species.WILD_BY_KEY["testleaf"].seed_amount_max,2)

    def test_non_plants_are_runtime_passthrough_not_editor_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);keys={p.key for p in service.records}
            self.assertNotIn("mushroom",keys);self.assertNotIn("wood_bush",keys)
            import wild_species
            self.assertIn("mushroom",wild_species.WILD_BY_KEY);self.assertIn("wood_bush",wild_species.WILD_BY_KEY)

    def test_terrain_editor_updates_same_plant_terrain_lists(self):
        from developer_tools.terrain_editor import TerrainEditorService
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();plants=PlantEditorService(root);terrain=TerrainEditorService(plants,root)
            chosen={next(p.key for p in plants.records if p.can_grow_wild)}
            values={"soil_moisture":.6,"fertility":.7,"temperature_offset_c":1.2,"rainfall_multiplier":.9}
            self.assertTrue(terrain.save(values,chosen)[0])
            self.assertEqual({p.key for p in plants.records if p.can_grow_wild and "GRASS" in p.wild.get("terrains",[])},chosen)
            import world
            expected={p.key for p in plants.records if p.key in chosen and p.wild.get("feature")=="WILD_CROP"}
            self.assertEqual(set(world.WILD_CROPS_BY_TERRAIN.get(world.TerrainType.GRASS,())),expected)
            reloaded=PlantEditorService(root)
            self.assertEqual({p.key for p in reloaded.records if p.can_grow_wild and "GRASS" in p.wild.get("terrains",[])},chosen)

    def test_wild_footprint_projects_to_runtime_layout(self):
        from subtile_layout import feature_subtile_layout
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"objects_data").mkdir();service=PlantEditorService(root);item=next(p for p in service.records if p.key=="wheat");service.select(item)
            service.candidate.wild["footprint"]=[4];self.assertTrue(service.save()[0])
            slots,_u,_v=feature_subtile_layout("WILD_CROP",1,1,crop_kind="wheat")
            self.assertEqual(slots,1)

    def test_tree_renderer_keeps_tree_icon(self):
        import icons,pygame,ui
        from unittest.mock import patch
        from world import FeatureType
        with patch.object(icons,"blit_icon") as blit:
            ui.draw_feature(pygame.Surface((64,64)),FeatureType.TREE,32,32,32,tree_species="oak")
        self.assertEqual(blit.call_args.args[1],icons.ICON_TREE_ROUND)

    def test_svg_original_colour_and_alpha_are_discovered(self):
        from icons import _as_paint,icon_svg_class_styles
        styles=icon_svg_class_styles("tree_round")
        self.assertEqual(styles["shadow"],(51,51,51,128))
        self.assertEqual(styles["trunk"][:3],(90,55,30))
        self.assertEqual(_as_paint((10,20,30,77),.5),(10,20,30,77))


if __name__=="__main__":unittest.main()
