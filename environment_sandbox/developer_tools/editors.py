"""Canonical recipe and traveller document models and CRUD services."""

from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .content_io import atomic_write_csv, get_content_root, snapshot_file
from .editor_state import EditorState
from .references import find_content_references
from .reload import ReloadResult, reload_recipes, reload_traveller_templates
from .validation import ValidationReport, ValidationSeverity, validate_recipe_catalogue, validate_traveller_catalogue

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_amount_rows(raw: str) -> list[tuple[str, int]]:
    result = []
    for part in (p.strip() for p in str(raw or "").split(";") if p.strip()):
        key, qty = part.split(":", 1)
        result.append((key.strip(), int(qty.strip())))
    return result


def serialize_amount_rows(rows: list[tuple[str, int]]) -> str:
    return ";".join(f"{key}:{int(qty)}" for key, qty in rows)


def parse_food_requirements(raw: str) -> list[list[str]]:
    return [[v.strip() for v in clause.split("/") if v.strip()] for clause in str(raw or "").split(";") if clause.strip()]


def serialize_food_requirements(clauses: list[list[str]]) -> str:
    return ";".join("/".join(v for v in clause if v) for clause in clauses if clause)


@dataclass
class CsvDocument:
    path: Path
    header: list[str]
    rows: list[dict[str, str]]
    snapshot: object


@dataclass
class RecipeRecord:
    workstation: str
    row: dict[str, str]
    source_file: Path
    row_index: int

    @property
    def key(self) -> str:
        return str(self.row.get("name") or "")

    @property
    def label(self) -> str:
        return str(self.row.get("label") or self.key.replace("_", " ").title())

    @property
    def inputs(self) -> list[tuple[str, int]]:
        return parse_amount_rows(self.row.get("inputs", ""))

    @inputs.setter
    def inputs(self, value: list[tuple[str, int]]) -> None:
        self.row["inputs"] = serialize_amount_rows(value)

    @property
    def outputs(self) -> list[tuple[str, int]]:
        return parse_amount_rows(self.row.get("outputs", ""))

    @outputs.setter
    def outputs(self, value: list[tuple[str, int]]) -> None:
        self.row["outputs"] = serialize_amount_rows(value)


@dataclass
class TravellerRecord:
    row: dict[str, str]
    source_file: Path
    row_index: int

    @property
    def key(self) -> str:
        return str(self.row.get("template_id") or "")

    @property
    def label(self) -> str:
        return str(self.row.get("name") or self.key)

    @property
    def required_food_clauses(self) -> list[list[str]]:
        return parse_food_requirements(self.row.get("required_foods", ""))

    @required_food_clauses.setter
    def required_food_clauses(self, value: list[list[str]]) -> None:
        self.row["required_foods"] = serialize_food_requirements(value)


def _read_csv(path: Path, *, root: Path | None = None) -> CsvDocument:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = [{key: str(row.get(key) or "") for key in header} for row in reader]
    return CsvDocument(path, header, rows, snapshot_file(path, root=root))


def _write_temp_recipe_tree(documents: dict[str, CsvDocument]) -> tuple[tempfile.TemporaryDirectory, Path]:
    temp = tempfile.TemporaryDirectory()
    base = Path(temp.name)
    for workstation, doc in documents.items():
        folder = base / workstation; folder.mkdir(parents=True, exist_ok=True)
        with (folder / "recipes.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=doc.header, lineterminator="\n")
            writer.writeheader(); writer.writerows(doc.rows)
    return temp, base


class RecipeEditorService:
    def __init__(self, *, content_root: Path | None = None):
        import recipes

        self.content_root = Path(content_root or get_content_root()).resolve()
        self.data_dir = self.content_root / "recipes_data"
        self.mapping = dict(recipes._BUILDING_RECIPE_ATTR)
        self.documents: dict[str, CsvDocument] = {}
        self.records: list[RecipeRecord] = []
        self.state: EditorState[RecipeRecord] = EditorState()
        self.load()

    def load(self) -> None:
        self.documents.clear(); self.records.clear()
        for workstation in self.mapping:
            path = self.data_dir / workstation / "recipes.csv"
            if not path.is_file():
                continue
            doc = _read_csv(path, root=self.content_root); self.documents[workstation] = doc
            self.records.extend(RecipeRecord(workstation, deepcopy(row), path, i) for i, row in enumerate(doc.rows))

    def filtered(self, workstation: str | None = None, search: str = "") -> list[RecipeRecord]:
        needle = search.casefold().strip()
        return [r for r in self.records if (not workstation or r.workstation == workstation) and (not needle or needle in f"{r.key} {r.label}".casefold())]

    def select(self, record: RecipeRecord) -> None:
        doc = self.documents[record.workstation]
        self.state.select(record, source_file=doc.path, row_index=record.row_index, snapshot=doc.snapshot)
        self.state.validation = self.validate_candidate()

    def new(self, workstation: str) -> RecipeRecord:
        doc = self.documents[workstation]
        row = {key: "" for key in doc.header}
        row.update(name="", label="", inputs="", outputs="")
        record = RecipeRecord(workstation, row, doc.path, len(doc.rows))
        self.state.begin_new(record, source_file=doc.path, snapshot=doc.snapshot)
        self.state.validation = self.validate_candidate()
        return record

    def duplicate(self) -> RecipeRecord:
        if self.state.candidate is None:
            raise ValueError("Select a recipe first")
        source = deepcopy(self.state.candidate)
        source.row["name"] = ""; source.row["label"] = f"{source.label} Copy"
        doc = self.documents[source.workstation]
        source.row_index = len(doc.rows)
        self.state.begin_new(source, source_file=doc.path, snapshot=doc.snapshot, duplicate=True)
        self.state.validation = self.validate_candidate()
        return source

    def validate_candidate(self) -> ValidationReport:
        report = ValidationReport(); candidate = self.state.candidate
        if candidate is None:
            return report
        from resources import RESOURCE_KEYS
        key = candidate.key.strip()
        if not key or not ID_RE.fullmatch(key):
            report.add(ValidationSeverity.ERROR, "invalid_recipe_key", "Recipe ID must be snake_case", field="name")
        if not self.state.is_new and self.state.original and key != self.state.original.key:
            report.add(ValidationSeverity.ERROR, "immutable_recipe_key", "Existing recipe IDs cannot be renamed", field="name")
        if any(r.key == key and not (r.source_file == candidate.source_file and r.row_index == candidate.row_index) for r in self.records):
            report.add(ValidationSeverity.ERROR, "duplicate_recipe_key", f"Recipe {key!r} already exists", field="name")
        known = set(RESOURCE_KEYS)
        for field_name, rows in (("inputs", candidate.inputs), ("outputs", candidate.outputs)):
            seen = set()
            for resource, qty in rows:
                if resource not in known:
                    report.add(ValidationSeverity.ERROR, f"unknown_{field_name[:-1]}_resource", f"Resource {resource!r} does not exist. Arbitrary resource creation is not supported.", field=field_name)
                if resource in seen:
                    report.add(ValidationSeverity.ERROR, "duplicate_resource_row", f"Duplicate resource {resource!r}", field=field_name)
                if int(qty) < 1:
                    report.add(ValidationSeverity.ERROR, "invalid_recipe_amount", "Quantities must be at least 1", field=field_name)
                seen.add(resource)
        return report

    def _candidate_documents(self, *, delete: bool = False) -> dict[str, CsvDocument]:
        docs = deepcopy(self.documents); candidate = self.state.candidate
        if candidate is None:
            raise ValueError("No active recipe")
        doc = docs[candidate.workstation]
        if delete:
            del doc.rows[candidate.row_index]
        elif self.state.is_new:
            doc.rows.append({key: candidate.row.get(key, "") for key in doc.header})
        else:
            doc.rows[candidate.row_index] = {key: candidate.row.get(key, "") for key in doc.header}
        return docs

    def validate_full_candidate(self, *, delete: bool = False) -> ValidationReport:
        light = self.validate_candidate() if not delete else ValidationReport()
        if not light.ok:
            return light
        docs = self._candidate_documents(delete=delete)
        temp, base = _write_temp_recipe_tree(docs)
        try:
            for workstation in self.mapping:
                (base / workstation).mkdir(parents=True, exist_ok=True)
            full = validate_recipe_catalogue(base)
        finally:
            temp.cleanup()
        return full

    def save(self) -> ReloadResult:
        candidate = self.state.candidate
        if candidate is None:
            raise ValueError("No active recipe")
        report = self.validate_full_candidate(); self.state.validation = report
        if not report.ok:
            return ReloadResult(False, 0, len(self.records), report, "Recipe save blocked by validation errors.")
        docs = self._candidate_documents(); doc = docs[candidate.workstation]
        live = self.documents[candidate.workstation]
        atomic_write_csv(live.path, live.header, doc.rows, root=self.content_root, expected_snapshot=self.state.snapshot, validation_report=report)
        result = reload_recipes(self.data_dir)
        if not result.success:
            backup = live.path.with_name(live.path.name + ".bak")
            if backup.is_file():
                shutil.copy2(backup, live.path); reload_recipes(self.data_dir)
            return ReloadResult(False, result.revision, len(self.records), result.report, "Runtime reload failed; canonical file was rolled back from backup.")
        selected_key = candidate.key; self.load()
        selected = next(r for r in self.records if r.key == selected_key)
        self.select(selected); self.state.mark_saved()
        return result

    def delete(self) -> tuple[ReloadResult, list]:
        candidate = self.state.candidate
        if candidate is None or self.state.is_new:
            raise ValueError("Select a saved recipe")
        references = [r for r in find_content_references(candidate.key, content_root=self.content_root) if not (r.kind == "recipe" and r.owner == candidate.key)]
        report = self.validate_full_candidate(delete=True)
        if not report.ok:
            return ReloadResult(False, 0, len(self.records), report, "Delete blocked by validation errors."), references
        docs = self._candidate_documents(delete=True); live = self.documents[candidate.workstation]; doc = docs[candidate.workstation]
        atomic_write_csv(live.path, live.header, doc.rows, root=self.content_root, expected_snapshot=self.state.snapshot, validation_report=report)
        result = reload_recipes(self.data_dir); self.load(); self.state = EditorState()
        return result, references


class TravellerEditorService:
    def __init__(self, *, content_root: Path | None = None):
        self.content_root = Path(content_root or get_content_root()).resolve()
        self.path = self.content_root / "society_data" / "travellers.csv"
        self.document: CsvDocument | None = None
        self.records: list[TravellerRecord] = []
        self.state: EditorState[TravellerRecord] = EditorState()
        self.load()

    def load(self) -> None:
        self.document = _read_csv(self.path, root=self.content_root)
        self.records = [TravellerRecord(deepcopy(row), self.path, i) for i, row in enumerate(self.document.rows)]

    def filtered(self, tier: int | None = None, search: str = "") -> list[TravellerRecord]:
        needle = search.casefold().strip()
        return [r for r in self.records if (tier is None or int(r.row.get("tier") or 0) == tier) and (not needle or needle in f"{r.key} {r.label}".casefold())]

    def select(self, record: TravellerRecord) -> None:
        assert self.document
        self.state.select(record, source_file=self.path, row_index=record.row_index, snapshot=self.document.snapshot)
        self.state.validation = self.validate_candidate()

    def new(self) -> TravellerRecord:
        assert self.document
        row = {key: "" for key in self.document.header}
        row.update(template_id="", name="", tier="1", housing_need="1", required_foods="meat", favourite_is_junk="0", signing_fee="0")
        from society import SKILL_ORDER
        for skill in SKILL_ORDER:
            key = skill.name.lower(); row[key] = "1"; row[f"{key}_cap"] = "5"
        record = TravellerRecord(row, self.path, len(self.document.rows))
        self.state.begin_new(record, source_file=self.path, snapshot=self.document.snapshot)
        self.state.validation = self.validate_candidate(); return record

    def duplicate(self) -> TravellerRecord:
        if self.state.candidate is None: raise ValueError("Select a traveller first")
        assert self.document
        record = deepcopy(self.state.candidate); record.row["template_id"] = ""; record.row["name"] += " Copy"; record.row_index = len(self.document.rows)
        self.state.begin_new(record, source_file=self.path, snapshot=self.document.snapshot, duplicate=True)
        self.state.validation = self.validate_candidate(); return record

    def validate_candidate(self) -> ValidationReport:
        report = ValidationReport(); candidate = self.state.candidate
        if candidate is None: return report
        key = candidate.key.strip()
        if not key or not ID_RE.fullmatch(key): report.add(ValidationSeverity.ERROR, "invalid_template_id", "Template ID must be snake_case", field="template_id")
        if not self.state.is_new and self.state.original and key != self.state.original.key: report.add(ValidationSeverity.ERROR, "immutable_template_id", "Existing template IDs cannot be renamed", field="template_id")
        if any(r.key == key and r.row_index != candidate.row_index for r in self.records): report.add(ValidationSeverity.ERROR, "duplicate_template_id", f"Template {key!r} already exists", field="template_id")
        from society import SKILL_ORDER
        for skill in SKILL_ORDER:
            name = skill.name.lower()
            try: level, cap = int(candidate.row[name]), int(candidate.row[f"{name}_cap"])
            except ValueError:
                report.add(ValidationSeverity.ERROR, "invalid_skill", f"Invalid {name} skill/cap", field=name); continue
            if not 1 <= level <= 10 or not 1 <= cap <= 10: report.add(ValidationSeverity.ERROR, "invalid_skill", f"{name} must be 1–10", field=name)
            if level > cap: report.add(ValidationSeverity.ERROR, "skill_exceeds_cap", f"{name} starting skill exceeds cap", field=name)
        return report

    def _candidate_rows(self, *, delete=False) -> list[dict[str, str]]:
        assert self.document and self.state.candidate
        rows = deepcopy(self.document.rows)
        if delete: del rows[self.state.candidate.row_index]
        elif self.state.is_new: rows.append({k: self.state.candidate.row.get(k, "") for k in self.document.header})
        else: rows[self.state.candidate.row_index] = {k: self.state.candidate.row.get(k, "") for k in self.document.header}
        return rows

    def validate_full_candidate(self, *, delete=False) -> ValidationReport:
        light = self.validate_candidate() if not delete else ValidationReport()
        if not light.ok: return light
        assert self.document
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "travellers.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=self.document.header, lineterminator="\n"); writer.writeheader(); writer.writerows(self._candidate_rows(delete=delete))
            return validate_traveller_catalogue(path)

    def save(self) -> ReloadResult:
        assert self.document and self.state.candidate
        report = self.validate_full_candidate(); self.state.validation = report
        if not report.ok: return ReloadResult(False, 0, len(self.records), report, "Traveller save blocked by validation errors.")
        atomic_write_csv(self.path, self.document.header, self._candidate_rows(), root=self.content_root, expected_snapshot=self.state.snapshot, validation_report=report)
        result = reload_traveller_templates(self.path)
        if not result.success:
            backup = self.path.with_name(self.path.name + ".bak")
            if backup.is_file(): shutil.copy2(backup, self.path); reload_traveller_templates(self.path)
            return ReloadResult(False, result.revision, len(self.records), result.report, "Runtime reload failed; canonical file was rolled back.")
        key = self.state.candidate.key; self.load(); self.select(next(r for r in self.records if r.key == key)); self.state.mark_saved(); return result

    def delete(self) -> ReloadResult:
        assert self.document and self.state.candidate
        report = self.validate_full_candidate(delete=True)
        if not report.ok: return ReloadResult(False, 0, len(self.records), report, "Delete blocked by validation errors.")
        atomic_write_csv(self.path, self.document.header, self._candidate_rows(delete=True), root=self.content_root, expected_snapshot=self.state.snapshot, validation_report=report)
        result = reload_traveller_templates(self.path); self.load(); self.state = EditorState(); return result
