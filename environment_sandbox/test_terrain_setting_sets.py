import tempfile
import unittest
from pathlib import Path
from unittest import mock

import terrain_settings
from world import TerrainType


class TerrainSettingSetTests(unittest.TestCase):
    def test_named_sets_save_load_and_become_active(self):
        original = terrain_settings.snapshot()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                mock.patch.object(terrain_settings, "_SETTINGS_PATH", root / "terrain_look.json"),
                mock.patch.object(terrain_settings, "_SETS_DIR", root / "sets"),
                mock.patch.object(terrain_settings, "_ACTIVE_SET_PATH", root / "active.json"),
            ):
                terrain_settings.reset_defaults()
                terrain_settings.save_settings()
                terrain_settings.update_mottle(TerrainType.GRASS, coarse_amp=0.123)
                saved = terrain_settings.save_setting_set("Tutorial Hills")
                self.assertEqual(saved.name, "Tutorial_Hills.json")
                self.assertEqual(terrain_settings.active_setting_set(), "Tutorial_Hills")

                terrain_settings.update_mottle(TerrainType.GRASS, coarse_amp=0.456)
                self.assertTrue(terrain_settings.load_setting_set("Tutorial_Hills"))
                self.assertAlmostEqual(
                    terrain_settings.get_mottle(TerrainType.GRASS).coarse_amp, 0.123
                )
                self.assertIn("Tutorial_Hills", terrain_settings.list_setting_sets())
                self.assertTrue((root / "sets" / "default.json").is_file())
                self.assertTrue((root / "terrain_look.json").is_file())
        terrain_settings.import_dict(original)


if __name__ == "__main__":
    unittest.main()
