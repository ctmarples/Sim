"""Lightweight canonical-data dependency lookups for destructive warnings."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .content_io import get_content_root


@dataclass(frozen=True)
class ContentReference:
    kind: str
    owner: str
    field: str
    file: str
    row: int


def _amount_keys(raw: str) -> set[str]:
    return {part.split(":", 1)[0].strip() for part in str(raw or "").split(";") if part.strip()}


def find_content_references(key: str, *, content_root: Path | None = None) -> list[ContentReference]:
    root = Path(content_root or get_content_root())
    refs: list[ContentReference] = []
    for path in sorted((root / "recipes_data").glob("*/recipes.csv")):
        with path.open(encoding="utf-8", newline="") as fh:
            for number, row in enumerate(csv.DictReader(fh), 2):
                owner = str(row.get("name") or "")
                for field in ("inputs", "outputs"):
                    if key in _amount_keys(row.get(field, "")):
                        refs.append(ContentReference("recipe", owner, field, str(path), number))
                if str(row.get("icon_key") or "").strip() == key:
                    refs.append(ContentReference("recipe", owner, "icon_key", str(path), number))
    path = root / "society_data" / "travellers.csv"
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as fh:
            for number, row in enumerate(csv.DictReader(fh), 2):
                owner = str(row.get("template_id") or row.get("name") or "")
                for field in ("required_foods", "favourite_foods"):
                    values = {v.strip() for clause in str(row.get(field) or "").split(";") for v in clause.split("/") if v.strip()}
                    if key in values:
                        refs.append(ContentReference("traveller", owner, field, str(path), number))
                if str(row.get("required_workplace") or "").strip() == key:
                    refs.append(ContentReference("traveller", owner, "required_workplace", str(path), number))
    return refs
