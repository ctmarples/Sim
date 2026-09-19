from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from developer_tools.content_io import (
    ContentPathError,
    DiskConflictError,
    atomic_write_csv,
    is_writable_source_tree,
    resolve_content_path,
    snapshot_file,
)
from developer_tools.reload import reload_recipes, reload_traveller_templates
from developer_tools.validation import (
    ValidationReport,
    ValidationSeverity,
    validate_icons,
    validate_recipe_catalogue,
    validate_traveller_catalogue,
)
from developer_tools.widgets import Checkbox, Dropdown, FloatField, IntegerField, TextField, ValidationSummary


def source_root(path: Path) -> Path:
    for marker in ("game.py", "recipes.py", "society.py"):
        (path / marker).write_text("# marker\n", encoding="utf-8")
    return path


class ContentIOTests(unittest.TestCase):
    def test_path_safety_and_writable_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = source_root(Path(tmp))
            self.assertTrue(is_writable_source_tree(root))
            self.assertEqual(resolve_content_path("data/file.csv", root=root), root.resolve() / "data/file.csv")
            with self.assertRaises(ContentPathError):
                resolve_content_path("../escape.csv", root=root)
            with self.assertRaises(ContentPathError):
                resolve_content_path(Path(tmp).parent / "outside.csv", root=root)
            with mock.patch("developer_tools.content_io.os.access", return_value=False):
                self.assertFalse(is_writable_source_tree(root))

    def test_atomic_csv_order_utf8_conflict_and_validation_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = source_root(Path(tmp))
            path = root / "rows.csv"
            path.write_text("second,first\nold,x\n", encoding="utf-8")
            snap = snapshot_file(path, root=root)
            rows = [{"second": "β", "first": "2"}, {"second": "α", "first": "1"}]
            atomic_write_csv(path, ["second", "first"], rows, root=root, expected_snapshot=snap)
            with path.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(reader.fieldnames, ["second", "first"])
                self.assertEqual([r["second"] for r in reader], ["β", "α"])
            self.assertTrue(path.with_name("rows.csv.bak").is_file())
            self.assertFalse(list(root.glob(".rows.csv.*.tmp")))
            stale = snapshot_file(path, root=root)
            path.write_text("second,first\nexternal,change\n", encoding="utf-8")
            with self.assertRaises(DiskConflictError):
                atomic_write_csv(path, ["second", "first"], rows, root=root, expected_snapshot=stale)
            before = path.read_text(encoding="utf-8")
            report = ValidationReport(); report.add(ValidationSeverity.ERROR, "bad", "bad")
            with self.assertRaises(ValueError):
                atomic_write_csv(path, ["second", "first"], rows, root=root, validation_report=report)
            self.assertEqual(path.read_text(encoding="utf-8"), before)


class ValidationReloadTests(unittest.TestCase):
    def _recipe_tree(self, root: Path, duplicate: bool = False) -> Path:
        import recipes
        for folder in recipes._BUILDING_RECIPE_ATTR:
            directory = root / folder; directory.mkdir(parents=True)
            content = "name,label,inputs,outputs,icon_key\n"
            if folder == "mill":
                content += "test_recipe,Test,wood:1,wood:1,wood\n"
            if duplicate and folder == "kitchen":
                content += "test_recipe,Duplicate,wood:1,wood:1,wood\n"
            (directory / "recipes.csv").write_text(content, encoding="utf-8")
        return root

    def test_recipe_duplicate_and_failed_reload_preserves_registry(self):
        import recipes
        with tempfile.TemporaryDirectory() as tmp:
            root = self._recipe_tree(Path(tmp), duplicate=True)
            report = validate_recipe_catalogue(root)
            self.assertTrue(any(i.code == "duplicate_recipe_key" for i in report.errors))
            previous = recipes.MILL_RECIPES
            result = reload_recipes(root)
            self.assertFalse(result.success)
            self.assertIs(recipes.MILL_RECIPES, previous)

    def test_valid_recipe_reload_updates_future_lookup_and_revision(self):
        import recipes
        from entities import Building, BuildingKind
        with tempfile.TemporaryDirectory() as tmp:
            root = self._recipe_tree(Path(tmp))
            previous = {attr: getattr(recipes, attr) for attr in recipes._BUILDING_RECIPE_ATTR.values()}
            previous_revision = recipes.RECIPE_REGISTRY_REVISION
            result = reload_recipes(root)
            try:
                self.assertTrue(result.success)
                self.assertTrue(any(r.name == "test_recipe" for r in Building(1, BuildingKind.MILL, 0, 0).known_recipes()))
            finally:
                for attr, value in previous.items():
                    setattr(recipes, attr, value)
                recipes.RECIPE_REGISTRY_REVISION = previous_revision
                recipes.rebuild_recipe_derived_keys()

    def _traveller_csv(self, path: Path, duplicate: bool = False) -> Path:
        from society import SKILL_ORDER
        fields = ["template_id", "name", "tier", "housing_need", "required_foods", "favourite_foods", "favourite_is_junk", "virtues", "vices"]
        fields += [s.name.lower() for s in SKILL_ORDER] + [f"{s.name.lower()}_cap" for s in SKILL_ORDER]
        fields += ["required_workplace", "signing_fee"]
        row = {key: "" for key in fields}; row.update(template_id="one", name="One", tier="1", housing_need="1", required_foods="t1", favourite_foods="meat_stew", favourite_is_junk="0", virtues="Steady", vices="Moody", signing_fee="0")
        for skill in SKILL_ORDER: row[skill.name.lower()] = "1"; row[f"{skill.name.lower()}_cap"] = "2"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerow(row)
            if duplicate: writer.writerow(row)
        return path

    def test_traveller_duplicate_and_reload(self):
        import society
        with tempfile.TemporaryDirectory() as tmp:
            path = self._traveller_csv(Path(tmp) / "travellers.csv", duplicate=True)
            self.assertTrue(any(i.code == "duplicate_template_id" for i in validate_traveller_catalogue(path).errors))
            previous = society._TRAVELLER_TEMPLATES
            failed = reload_traveller_templates(path); self.assertFalse(failed.success); self.assertIs(society._TRAVELLER_TEMPLATES, previous)
            self._traveller_csv(path)
            succeeded = reload_traveller_templates(path)
            try:
                self.assertTrue(succeeded.success)
                self.assertEqual(society.traveller_templates()[0].template_id, "one")
            finally:
                society._TRAVELLER_TEMPLATES = previous

    def test_icon_validation_isolated_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "a").mkdir(); (root / "b").mkdir()
            (root / "a" / "same.svg").write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
            (root / "b" / "same.svg").write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
            (root / "broken.svg").write_text("<svg>", encoding="utf-8")
            (root / "thing_1.svg").write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
            (root / "thing_3.svg").write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
            codes = {i.code for i in validate_icons(root, render=False).issues}
            self.assertTrue({"duplicate_icon_stem", "invalid_svg", "broken_icon_variant_sequence"} <= codes)

    def test_icon_cache_clear_rediscovers_added_file(self):
        import icons
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_root = icons._ICONS_DIR
            try:
                icons._ICONS_DIR = root
                icons.clear_cache()
                self.assertNotIn("new_icon", icons.list_icon_names())
                (root / "new_icon.svg").write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
                icons.clear_cache()
                self.assertIn("new_icon", icons.list_icon_names())
            finally:
                icons._ICONS_DIR = old_root
                icons.clear_cache()


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init(); pygame.display.set_mode((1, 1))

    def test_fields_dropdown_checkbox_and_summary(self):
        rect = pygame.Rect(0, 0, 100, 24)
        field = TextField(rect, max_length=3); field.focused = True
        field.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, unicode="a")); self.assertEqual(field.text, "a")
        integer = IntegerField(rect, "12", minimum=1, maximum=10); self.assertIsNone(integer.parse()); self.assertIn("at most", integer.error)
        floating = FloatField(rect, "1.5", minimum=0, maximum=2); self.assertEqual(floating.parse(), 1.5)
        dropdown = Dropdown(rect, [("a", "A"), ("b", "B")]); self.assertTrue(dropdown.select("b")); self.assertEqual(dropdown.value, "b"); self.assertFalse(dropdown.select("x"))
        checkbox = Checkbox(rect); checkbox.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1, 1))); self.assertTrue(checkbox.checked)
        report = ValidationReport(); report.add(ValidationSeverity.WARNING, "warn", "warning")
        summary = ValidationSummary(rect, report); self.assertEqual(summary.severity_counts()[ValidationSeverity.WARNING], 1)


if __name__ == "__main__":
    unittest.main()
