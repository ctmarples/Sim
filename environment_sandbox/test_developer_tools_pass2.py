from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from developer_tools.content_lab import WORKSTATION_KINDS, recipe_catalogue
from developer_tools.editor_state import DirtyNavigationGuard, EditorState
from developer_tools.editors import (
    parse_amount_rows,
    parse_food_requirements,
    serialize_amount_rows,
    serialize_food_requirements,
)
from developer_tools.icons_browser import IconBrowserService
from developer_tools.references import find_content_references
from developer_tools.resources_browser import resource_entries
from developer_tools.validation import validate_recipe_catalogue, validate_traveller_catalogue


class Pass2DeveloperToolsTests(unittest.TestCase):
    def test_structured_rows_round_trip_without_raw_editor_syntax(self):
        amounts = [("fish", 2), ("garlic", 1)]
        self.assertEqual(parse_amount_rows(serialize_amount_rows(amounts)), amounts)
        clauses = [["stew", "fish_stew"], ["bread"]]
        self.assertEqual(parse_food_requirements(serialize_food_requirements(clauses)), clauses)

    def test_shared_state_tracks_dirty_and_navigation_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "content.csv"; path.touch()
            from developer_tools.content_io import snapshot_file
            state = EditorState[dict]()
            state.select({"id": "stable"}, source_file=path, row_index=0, snapshot=snapshot_file(path, root=Path(tmp)))
            state.candidate["name"] = "Changed"; state.mark_changed()
            self.assertTrue(state.dirty)
            guard = DirtyNavigationGuard()
            self.assertFalse(guard.request("home", dirty=state.dirty))
            self.assertEqual(guard.discard(), "home")

    def test_canonical_catalogues_have_no_errors(self):
        self.assertEqual(validate_recipe_catalogue().errors, [])
        self.assertEqual(validate_traveller_catalogue().errors, [])

    def test_resources_are_read_only_registry_entries(self):
        entries = resource_entries("fish")
        self.assertTrue(entries)
        self.assertTrue(all(entry.key and entry.label and entry.source for entry in entries))

    def test_reference_scan_finds_known_recipe_uses(self):
        refs = find_content_references("meat")
        self.assertTrue(any(ref.kind == "recipe" for ref in refs))

    def test_icon_import_rejects_unsafe_or_malformed_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); icons = root / "assets" / "icons"; icons.mkdir(parents=True)
            bad = root / "bad.svg"; bad.write_text("<svg><script/></svg>", encoding="utf-8")
            service = IconBrowserService(content_root=root, icon_root=icons)
            _dest, report = service.validate_import(bad, "Bad Key")
            codes = {issue.code for issue in report.errors}
            self.assertIn("invalid_icon_key", codes)
            self.assertIn("svg_script_forbidden", codes)

    def test_every_loaded_lab_recipe_has_a_production_building_mapping(self):
        catalogue = recipe_catalogue()
        self.assertTrue(catalogue)
        self.assertTrue(all(item.workstation in WORKSTATION_KINDS for item in catalogue))


if __name__ == "__main__":
    unittest.main()
