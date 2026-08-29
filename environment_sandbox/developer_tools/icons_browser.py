"""Read-only icon discovery plus validated, source-path SVG/PNG import."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .content_io import ContentPathError, get_content_root, resolve_content_path
from .reload import ReloadResult, refresh_icons
from .validation import ValidationReport, ValidationSeverity, validate_icons

ICON_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class IconEntry:
    key: str
    formats: tuple[str, ...]
    paths: tuple[Path, ...]
    variant_count: int = 1


class IconBrowserService:
    def __init__(self, *, content_root: Path | None = None, icon_root: Path | None = None):
        import icons

        self.content_root = Path(content_root or get_content_root()).resolve()
        self.icon_root = Path(icon_root or icons.icons_dir()).resolve()

    @property
    def categories(self) -> list[str]:
        return ["."] + sorted(str(p.relative_to(self.icon_root)) for p in self.icon_root.iterdir() if p.is_dir() and not p.name.startswith("_"))

    def entries(self, search: str = "", file_type: str = "all") -> list[IconEntry]:
        needle = search.casefold().strip(); grouped: dict[str, list[Path]] = {}
        for path in sorted(self.icon_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".svg", ".png"): continue
            if any(part.startswith("_") for part in path.relative_to(self.icon_root).parts[:-1]): continue
            if file_type != "all" and path.suffix.lower() != f".{file_type.lower()}": continue
            if needle and needle not in path.stem.casefold(): continue
            grouped.setdefault(path.stem, []).append(path)
        result = []
        for key, paths in grouped.items():
            base, sep, suffix = key.rpartition("_")
            variants = len([name for name in grouped if name.startswith(base + "_") and name.rpartition("_")[2].isdigit()]) if sep and suffix.isdigit() else 1
            result.append(IconEntry(key, tuple(sorted({p.suffix.lower()[1:] for p in paths})), tuple(paths), max(1, variants)))
        return result

    def validate_import(self, source: Path, key: str, category: str = ".", *, overwrite: bool = False) -> tuple[Path | None, ValidationReport]:
        report = ValidationReport(); source = Path(source).expanduser().resolve()
        if not source.is_file():
            report.add(ValidationSeverity.ERROR, "icon_source_missing", "Source file does not exist", file=str(source)); return None, report
        suffix = source.suffix.lower()
        if suffix not in (".svg", ".png"):
            report.add(ValidationSeverity.ERROR, "unsupported_icon_format", "Only SVG and PNG icons are supported", file=str(source))
        if not ICON_KEY_RE.fullmatch(key):
            report.add(ValidationSeverity.ERROR, "invalid_icon_key", "Icon key must be snake_case", field="icon_key")
        if category not in self.categories:
            report.add(ValidationSeverity.ERROR, "invalid_icon_category", "Destination must be an existing icon category", field="category")
        try:
            destination = resolve_content_path(self.icon_root / category / f"{key}{suffix}", root=self.content_root)
        except ContentPathError as exc:
            report.add(ValidationSeverity.ERROR, "unsafe_icon_destination", str(exc)); return None, report
        duplicate = any(entry.key == key for entry in self.entries())
        if duplicate and not overwrite:
            report.add(ValidationSeverity.ERROR, "icon_overwrite_confirmation_required", f"Icon stem {key!r} already exists; explicit overwrite confirmation is required", file=str(destination))
        if suffix == ".svg":
            try:
                root = ET.parse(source).getroot()
                if not root.get("viewBox") and not (root.get("width") and root.get("height")):
                    report.add(ValidationSeverity.ERROR, "missing_svg_viewbox", "SVG needs viewBox or width/height", file=str(source))
                for element in root.iter():
                    if element.tag.rsplit("}", 1)[-1].lower() == "script":
                        report.add(ValidationSeverity.ERROR, "svg_script_forbidden", "SVG scripts are not allowed", file=str(source))
                    for attr, value in element.attrib.items():
                        if attr.rsplit("}", 1)[-1] in ("href", "src") and ("://" in value or value.startswith("//")):
                            report.add(ValidationSeverity.ERROR, "svg_external_reference", "External SVG references are not allowed", file=str(source))
            except (ET.ParseError, OSError) as exc:
                report.add(ValidationSeverity.ERROR, "invalid_svg", str(exc), file=str(source))
        else:
            try:
                import pygame
                pygame.image.load(str(source))
            except Exception as exc:
                report.add(ValidationSeverity.ERROR, "invalid_png", str(exc), file=str(source))
        return destination, report

    def import_file(self, source: Path, key: str, category: str = ".", *, overwrite: bool = False) -> ReloadResult:
        destination, report = self.validate_import(source, key, category, overwrite=overwrite)
        if destination is None or not report.ok:
            return ReloadResult(False, 0, len(self.entries()), report, "Icon import blocked by validation errors.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
            with os.fdopen(fd, "wb") as fh, Path(source).open("rb") as src:
                shutil.copyfileobj(src, fh); fh.flush(); os.fsync(fh.fileno())
            if destination.exists(): shutil.copy2(destination, destination.with_name(destination.name + ".bak"))
            os.replace(temp_name, destination); temp_name = None
            import icons
            if self.icon_root == icons.icons_dir().resolve():
                result = refresh_icons()
                if not result.success:
                    backup = destination.with_name(destination.name + ".bak")
                    if backup.exists(): shutil.copy2(backup, destination); refresh_icons()
                    else: destination.unlink(missing_ok=True); refresh_icons()
                    return ReloadResult(False, result.revision, result.count, result.report, "Imported icon failed canonical validation and was rolled back.")
                return result
            validation = validate_icons(self.icon_root, render=False)
            return ReloadResult(validation.ok, 1 if validation.ok else 0, len(self.entries()), validation, "Icon imported." if validation.ok else "Icon imported but validation failed.")
        finally:
            if temp_name: Path(temp_name).unlink(missing_ok=True)
