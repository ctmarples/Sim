"""Structured validation for the first editable catalogues and icon assets."""

from __future__ import annotations

import csv
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

log = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    file: str | None = None
    row: int | None = None
    field: str | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    sections: dict[str, "ValidationReport"] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is ValidationSeverity.WARNING]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is ValidationSeverity.INFO]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, severity: ValidationSeverity, code: str, message: str, **location) -> None:
        self.issues.append(ValidationIssue(severity, code, message, **location))

    def extend(self, other: "ValidationReport", *, section: str | None = None) -> None:
        self.issues.extend(other.issues)
        if section:
            self.sections[section] = other


def _parse_amounts(raw: str, report: ValidationReport, *, path: Path, row: int, field_name: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for part in (p.strip() for p in str(raw or "").split(";") if p.strip()):
        if ":" not in part:
            report.add(ValidationSeverity.ERROR, "malformed_amount_map", f"Expected key:amount, got {part!r}", file=str(path), row=row, field=field_name)
            continue
        key, qty = (v.strip() for v in part.split(":", 1))
        try:
            amount = int(qty)
        except ValueError:
            report.add(ValidationSeverity.ERROR, "malformed_numeric_field", f"Invalid amount {qty!r}", file=str(path), row=row, field=field_name)
            continue
        if not key or amount <= 0:
            report.add(ValidationSeverity.ERROR, "invalid_recipe_amount", "Resource key must be non-empty and amount positive", file=str(path), row=row, field=field_name)
            continue
        result[key] = amount
    return result


def validate_recipe_catalogue(data_dir: Path | None = None) -> ValidationReport:
    from icons import has_icon
    from recipes import _BUILDING_RECIPE_ATTR, _SKILL_CSV_COLS
    from resources import RESOURCE_KEYS, resource_icon

    base = Path(data_dir or Path(__file__).resolve().parents[1] / "recipes_data")
    report = ValidationReport()
    known_resources = set(RESOURCE_KEYS)
    declared_outputs: set[str] = set()
    # Outputs are valid resource declarations regardless of workstation folder
    # order. Discover all of them before checking any recipe input.
    for folder in _BUILDING_RECIPE_ATTR:
        path = base / folder / "recipes.csv"
        if not path.is_file(): continue
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    for token in str(row.get("outputs") or "").split(";"):
                        key = token.split(":", 1)[0].strip()
                        if key: declared_outputs.add(key)
        except (OSError, csv.Error, UnicodeError):
            pass
    seen: dict[tuple[str, str], tuple[Path, int]] = {}
    for folder, _attr in _BUILDING_RECIPE_ATTR.items():
        directory = base / folder
        if not directory.is_dir():
            report.add(ValidationSeverity.ERROR, "missing_workstation_folder", f"Missing mapped recipe folder {folder}", file=str(directory))
            continue
        path = directory / "recipes.csv"
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, csv.Error, UnicodeError) as exc:
            report.add(ValidationSeverity.ERROR, "recipe_file_error", str(exc), file=str(path))
            continue
        for number, row in enumerate(rows, 2):
            name = str(row.get("name") or "").strip()
            if not name:
                report.add(ValidationSeverity.ERROR, "missing_recipe_key", "Recipe name is required", file=str(path), row=number, field="name")
                continue
            key = (folder, name)
            if key in seen:
                first_path, first_row = seen[key]
                report.add(ValidationSeverity.ERROR, "duplicate_recipe_key", f"Duplicate recipe {name!r} in {folder}; first at {first_path}:{first_row}", file=str(path), row=number, field="name")
            else:
                seen[key] = (path, number)
            inputs = _parse_amounts(row.get("inputs", ""), report, path=path, row=number, field_name="inputs")
            outputs = _parse_amounts(row.get("outputs", ""), report, path=path, row=number, field_name="outputs")
            declared_outputs.update(outputs)
            for field_name in ("steps", *_SKILL_CSV_COLS, "min_skill", "food_satiation", "food_walk_speed", "food_work_efficiency", "food_hunger_rate", "walk_speed", "capacity_bonus", "heat_protection", "cold_protection"):
                raw = str(row.get(field_name) or "").strip()
                if raw:
                    try:
                        float(raw)
                    except ValueError:
                        report.add(ValidationSeverity.ERROR, "malformed_numeric_field", f"Invalid numeric value {raw!r}", file=str(path), row=number, field=field_name)
            compact = str(row.get("skills") or "").strip()
            for token in (p for p in compact.split(";") if p.strip()):
                skill = token.split(":", 1)[0].strip().lower()
                if skill not in _SKILL_CSV_COLS:
                    report.add(ValidationSeverity.ERROR, "unknown_skill", f"Unknown skill {skill!r}", file=str(path), row=number, field="skills")
            icon_key = str(row.get("icon_key") or "").strip()
            fallback_key = resource_icon(next(iter(outputs))) if outputs else name
            resolved_icon = icon_key or fallback_key
            if not has_icon(resolved_icon):
                code = "unknown_icon_key" if icon_key else "missing_recipe_icon_fallback"
                report.add(ValidationSeverity.WARNING, code, f"No usable icon found for {resolved_icon!r}", file=str(path), row=number, field="icon_key")
            is_declared_resource = bool(str(row.get("resource_group") or "").strip() or str(row.get("food_satiation") or "").strip())
            for key in inputs:
                if key not in known_resources and key not in declared_outputs:
                    report.add(ValidationSeverity.ERROR, "unknown_input_resource", f"Unknown input resource {key!r}", file=str(path), row=number, field="inputs")
            for key in outputs:
                if key not in known_resources and not is_declared_resource:
                    report.add(ValidationSeverity.ERROR, "unknown_output_resource", f"Unknown output resource {key!r}", file=str(path), row=number, field="outputs")
    return report


def validate_traveller_catalogue(path: Path | None = None) -> ValidationReport:
    from entities import BuildingKind
    from resource_balance import REQUIREMENT_LABELS, REQUIREMENT_OR_GROUPS
    from resources import RESOURCE_KEYS
    from society import SKILL_ORDER, VICE_POOL, VIRTUE_POOL

    csv_path = Path(path or Path(__file__).resolve().parents[1] / "society_data" / "travellers.csv")
    report = ValidationReport()
    try:
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error, UnicodeError) as exc:
        report.add(ValidationSeverity.ERROR, "traveller_file_error", str(exc), file=str(csv_path))
        return report
    seen: set[str] = set()
    foods = set(RESOURCE_KEYS) | set(REQUIREMENT_OR_GROUPS) | set(REQUIREMENT_LABELS)
    workplaces = {kind.name.lower() for kind in BuildingKind}
    for number, row in enumerate(rows, 2):
        key = str(row.get("template_id") or "").strip()
        if not key:
            report.add(ValidationSeverity.ERROR, "missing_template_id", "template_id is required", file=str(csv_path), row=number, field="template_id")
        elif key in seen:
            report.add(ValidationSeverity.ERROR, "duplicate_template_id", f"Duplicate template_id {key!r}", file=str(csv_path), row=number, field="template_id")
        seen.add(key)
        def integer(field_name: str, low: int, high: int) -> int | None:
            raw = str(row.get(field_name) or "").strip()
            try:
                value = int(raw)
            except ValueError:
                report.add(ValidationSeverity.ERROR, "invalid_traveller_numeric", f"Invalid integer {raw!r}", file=str(csv_path), row=number, field=field_name)
                return None
            if not low <= value <= high:
                report.add(ValidationSeverity.ERROR, f"invalid_{field_name}", f"{field_name} must be {low}–{high}", file=str(csv_path), row=number, field=field_name)
            return value
        integer("tier", 1, 3)
        integer("housing_need", 1, 3)
        integer("signing_fee", 0, 10**9)
        for field_name in ("required_foods", "favourite_foods"):
            for food in (v.strip() for v in str(row.get(field_name) or "").split(";") if v.strip()):
                if food not in foods:
                    report.add(ValidationSeverity.ERROR, f"unknown_{field_name}", f"Unknown food expression {food!r}", file=str(csv_path), row=number, field=field_name)
        for field_name, pool in (("virtues", set(VIRTUE_POOL)), ("vices", set(VICE_POOL))):
            for trait in (v.strip() for v in str(row.get(field_name) or "").split(";") if v.strip()):
                if trait not in pool:
                    report.add(ValidationSeverity.ERROR, f"unknown_{field_name}", f"Unknown trait {trait!r}", file=str(csv_path), row=number, field=field_name)
        workplace = str(row.get("required_workplace") or "").strip().lower()
        if workplace and workplace not in workplaces:
            report.add(ValidationSeverity.ERROR, "unknown_required_workplace", f"Unknown workplace {workplace!r}", file=str(csv_path), row=number, field="required_workplace")
        for skill in SKILL_ORDER:
            field_name = skill.name.lower()
            level = integer(field_name, 1, 10)
            cap = integer(f"{field_name}_cap", 1, 10)
            if level is not None and cap is not None and level > cap:
                report.add(ValidationSeverity.ERROR, "skill_exceeds_cap", f"{field_name} level exceeds cap", file=str(csv_path), row=number, field=field_name)
    return report


def validate_icons(icon_root: Path | None = None, *, render: bool = True) -> ValidationReport:
    import icons

    root = Path(icon_root or icons.icons_dir())
    report = ValidationReport()
    stems: dict[str, Path] = {}
    variants: dict[str, set[int]] = {}
    for path in sorted(root.rglob("*")) if root.is_dir() else ():
        if not path.is_file() or path.suffix.lower() not in (".svg", ".png"):
            continue
        relative_parts = path.relative_to(root).parts[:-1]
        if any(part.startswith("_") for part in relative_parts):
            continue
        stem = path.stem
        if not stem or stem.startswith("_") or " " in stem or "." in stem:
            report.add(ValidationSeverity.ERROR, "invalid_icon_filename", f"Invalid icon filename {path.name!r}", file=str(path))
        if stem in stems and stems[stem].parent != path.parent:
            report.add(ValidationSeverity.ERROR, "duplicate_icon_stem", f"Duplicate icon stem {stem!r}", file=str(path))
        stems.setdefault(stem, path)
        base, sep, suffix = stem.rpartition("_")
        if sep and suffix.isdigit():
            variants.setdefault(base, set()).add(int(suffix))
        if path.suffix.lower() == ".svg":
            try:
                svg = ET.parse(path).getroot()
                if not svg.get("viewBox") and not (svg.get("width") and svg.get("height")):
                    report.add(ValidationSeverity.ERROR, "missing_svg_viewbox", "SVG requires viewBox or width/height", file=str(path))
            except (ET.ParseError, OSError) as exc:
                report.add(ValidationSeverity.ERROR, "invalid_svg", str(exc), file=str(path))
                continue
        if render and root.resolve() == icons.icons_dir().resolve() and not (sep and suffix.isdigit()):
            try:
                icons.get_icon(stem, 40, prefer_png=path.suffix.lower() == ".png")
            except Exception as exc:
                report.add(ValidationSeverity.ERROR, "icon_render_failed", str(exc), file=str(path))
    for base, indexes in variants.items():
        if indexes and indexes != set(range(1, max(indexes) + 1)):
            report.add(ValidationSeverity.WARNING, "broken_icon_variant_sequence", f"Variant sequence for {base!r} is not contiguous", file=str(root))
    return report


def validate_all() -> ValidationReport:
    log.info("Developer Tools content validation started")
    report = ValidationReport()
    report.extend(validate_recipe_catalogue(), section="Recipes")
    report.extend(validate_traveller_catalogue(), section="Travellers")
    report.extend(validate_icons(), section="Icons")
    log.info("Developer Tools validation finished: %s errors, %s warnings", len(report.errors), len(report.warnings))
    return report
