"""Explicit, validation-gated catalogue reload APIs."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .validation import (
    ValidationReport,
    ValidationSeverity,
    validate_icons,
    validate_recipe_catalogue,
    validate_traveller_catalogue,
)

log = logging.getLogger(__name__)

RECIPE_REGISTRY_REVISION = 0
TRAVELLER_REGISTRY_REVISION = 0
ICON_REGISTRY_REVISION = 0


@dataclass(frozen=True)
class ReloadResult:
    success: bool
    revision: int
    count: int
    report: ValidationReport
    message: str


@dataclass(frozen=True)
class RecipeCatalogue:
    by_workstation: dict[str, tuple[object, ...]]

    @property
    def count(self) -> int:
        return sum(len(items) for items in self.by_workstation.values())


def load_recipe_catalogue_from_disk(data_dir: Path | None = None) -> tuple[RecipeCatalogue, ValidationReport]:
    """Parse recognized recipe files without changing runtime registries."""
    import recipes

    base = Path(data_dir or recipes._RECIPES_DATA_DIR)
    report = validate_recipe_catalogue(base)
    result: dict[str, list[object]] = {folder: [] for folder in recipes._BUILDING_RECIPE_ATTR}
    routed: dict[str, list[object]] = {}
    for folder in recipes._BUILDING_RECIPE_ATTR:
        loaded = result[folder]
        directory = base / folder
        csv_path = directory / "recipes.csv"
        if csv_path.is_file():
            try:
                with csv_path.open(encoding="utf-8", newline="") as fh:
                    for row_no, row in enumerate(csv.DictReader(fh), 2):
                        if not row or not recipes._cell(row, "name"):
                            continue
                        try:
                            recipe = recipes._recipe_from_row(row)
                        except Exception as exc:
                            report.add(ValidationSeverity.ERROR, "recipe_parse_error", str(exc), file=str(csv_path), row=row_no)
                            continue
                        station = recipes._cell(row, "station").lower()
                        if (
                            folder == "kitchen"
                            and station
                            and station != folder
                            and station in recipes._BUILDING_RECIPE_ATTR
                        ):
                            routed.setdefault(station, []).append(recipe)
                            continue
                        loaded.append(recipe)
            except Exception as exc:
                report.add(ValidationSeverity.ERROR, "recipe_file_error", str(exc), file=str(csv_path))
        for json_path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("name"):
                    loaded.append(recipes._recipe_from_json(data))
            except Exception as exc:
                report.add(ValidationSeverity.ERROR, "recipe_json_error", str(exc), file=str(json_path))
        if folder == "forager":
            seen = {item.name for item in loaded}
            recipes._append_forager_crop_produce(loaded, seen)
    for station, recipes_list in routed.items():
        if station not in result:
            continue
        existing = result[station]
        by_name = {item.name: index for index, item in enumerate(existing)}
        for recipe in recipes_list:
            if recipe.name in by_name:
                existing[by_name[recipe.name]] = recipe
            else:
                by_name[recipe.name] = len(existing)
                existing.append(recipe)
    return RecipeCatalogue({folder: tuple(items) for folder, items in result.items()}), report


def _apply_recipe_metadata(data_dir: Path) -> None:
    """Apply optional metadata only after the complete candidate passed validation."""
    import recipes

    for folder in recipes._BUILDING_RECIPE_ATTR:
        directory = data_dir / folder
        csv_path = directory / "recipes.csv"
        if csv_path.is_file():
            with csv_path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if row and recipes._cell(row, "name"):
                        recipe = recipes._recipe_from_row(row)
                        recipes._apply_row_metadata(row, recipe)
        for json_path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("name"):
                recipe = recipes._recipe_from_json(data)
                recipes._apply_json_metadata(data, recipe)


def reload_recipes(data_dir: Path | None = None) -> ReloadResult:
    """Atomically replace recipe tuple definitions after successful validation."""
    global RECIPE_REGISTRY_REVISION
    import recipes

    base = Path(data_dir or recipes._RECIPES_DATA_DIR)
    catalogue, report = load_recipe_catalogue_from_disk(base)
    if not report.ok:
        log.warning("Recipe reload rejected: %s validation errors", len(report.errors))
        return ReloadResult(False, RECIPE_REGISTRY_REVISION, catalogue.count, report, "Recipe reload failed; previous definitions remain active.")
    try:
        previous = {attr: getattr(recipes, attr) for attr in recipes._BUILDING_RECIPE_ATTR.values()}
        _apply_recipe_metadata(base)
        for folder, attr in recipes._BUILDING_RECIPE_ATTR.items():
            setattr(recipes, attr, catalogue.by_workstation[folder])
        recipes.rebuild_recipe_derived_keys()
        # entities historically imported these tuples by value. Keep active
        # buildings' capacity, pantry and transfer rules on the new registry.
        import entities
        for name in (
            "MILL_INPUT_KEYS", "MILL_OUTPUT_KEYS", "CRAFT_BENCH_INPUT_KEYS",
            "CRAFT_BENCH_OUTPUT_KEYS", "ALCHEMIST_INPUT_KEYS", "ALCHEMIST_OUTPUT_KEYS",
            "TAILOR_INPUT_KEYS", "TAILOR_OUTPUT_KEYS", "COBBLER_INPUT_KEYS",
            "COBBLER_OUTPUT_KEYS", "KITCHEN_INPUT_KEYS", "KITCHEN_OUTPUT_KEYS",
            "PROCESSED_KEYS",
        ):
            setattr(entities, name, getattr(recipes, name))
        entities.ensure_storage_item_fields()
        RECIPE_REGISTRY_REVISION += 1
        recipes.RECIPE_REGISTRY_REVISION = RECIPE_REGISTRY_REVISION
        log.info("Recipe reload succeeded: %s recipes, revision %s", catalogue.count, RECIPE_REGISTRY_REVISION)
        return ReloadResult(True, RECIPE_REGISTRY_REVISION, catalogue.count, report, "Recipe definitions reloaded. Restart active test worlds to refresh existing objects.")
    except Exception as exc:
        for attr, value in locals().get("previous", {}).items():
            setattr(recipes, attr, value)
        recipes.rebuild_recipe_derived_keys()
        report.add(ValidationSeverity.ERROR, "recipe_reload_error", str(exc))
        log.exception("Recipe reload failed while applying candidate")
        return ReloadResult(False, RECIPE_REGISTRY_REVISION, catalogue.count, report, "Recipe reload failed; previous definitions remain active.")


def load_traveller_templates_from_disk(path: Path | None = None):
    import society

    candidate_path = Path(path or society._travellers_csv_path())
    report = validate_traveller_catalogue(candidate_path)
    if not report.ok:
        return [], report
    try:
        return society.load_traveller_templates(str(candidate_path)), report
    except Exception as exc:
        report.add(ValidationSeverity.ERROR, "traveller_parse_error", str(exc), file=str(candidate_path))
        return [], report


def reload_traveller_templates(path: Path | None = None) -> ReloadResult:
    global TRAVELLER_REGISTRY_REVISION
    import society

    templates, report = load_traveller_templates_from_disk(path)
    if not report.ok:
        log.warning("Traveller reload rejected: %s validation errors", len(report.errors))
        return ReloadResult(False, TRAVELLER_REGISTRY_REVISION, len(templates), report, "Traveller reload failed; previous templates remain active.")
    society._TRAVELLER_TEMPLATES = list(templates)
    TRAVELLER_REGISTRY_REVISION += 1
    log.info("Traveller reload succeeded: %s templates, revision %s", len(templates), TRAVELLER_REGISTRY_REVISION)
    return ReloadResult(True, TRAVELLER_REGISTRY_REVISION, len(templates), report, "Traveller templates reloaded. Existing villagers are unchanged.")


def refresh_icons() -> ReloadResult:
    global ICON_REGISTRY_REVISION
    import icons

    try:
        icons.clear_cache()
        names = icons.list_icon_names()
        report = validate_icons()
        if report.ok:
            ICON_REGISTRY_REVISION += 1
            log.info("Icon refresh succeeded: %s icons, revision %s", len(names), ICON_REGISTRY_REVISION)
            return ReloadResult(True, ICON_REGISTRY_REVISION, len(names), report, "Icon discovery and render caches refreshed.")
        return ReloadResult(False, ICON_REGISTRY_REVISION, len(names), report, "Icon refresh found validation errors.")
    except Exception as exc:
        report = ValidationReport()
        report.add(ValidationSeverity.ERROR, "icon_refresh_error", str(exc))
        log.exception("Icon refresh failed")
        return ReloadResult(False, ICON_REGISTRY_REVISION, 0, report, "Icon refresh failed.")
