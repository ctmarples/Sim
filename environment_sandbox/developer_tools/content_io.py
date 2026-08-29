"""Verified content paths, file snapshots, and atomic CSV writes."""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

log = logging.getLogger(__name__)


class ContentPathError(ValueError):
    pass


class DiskConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileSnapshot:
    digest: str
    size: int


def get_content_root() -> Path:
    """Return the trusted environment_sandbox source directory."""
    return Path(__file__).resolve().parents[1]


def is_writable_source_tree(root: Path | None = None) -> bool:
    root = (root or get_content_root()).resolve()
    markers = (root / "game.py", root / "recipes.py", root / "society.py")
    return not getattr(sys, "frozen", False) and root.is_dir() and all(p.is_file() for p in markers) and os.access(root, os.W_OK)


def resolve_content_path(path: str | Path, *, root: Path | None = None) -> Path:
    """Resolve a path and reject traversal, symlink escape, and outside paths."""
    approved = (root or get_content_root()).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = approved / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(approved)
    except ValueError as exc:
        log.warning("Developer Tools refused unsafe content path: %s", path)
        raise ContentPathError(f"Path escapes approved content root: {path}") from exc
    return resolved


def snapshot_file(path: str | Path, *, root: Path | None = None) -> FileSnapshot:
    target = resolve_content_path(path, root=root)
    data = target.read_bytes()
    return FileSnapshot(hashlib.sha256(data).hexdigest(), len(data))


def atomic_write_csv(
    path: str | Path,
    header: list[str] | tuple[str, ...],
    rows: Iterable[Mapping[str, object]],
    *,
    root: Path | None = None,
    expected_snapshot: FileSnapshot | None = None,
    create_backup: bool = True,
    validation_report=None,
) -> FileSnapshot:
    """Write ordered CSV rows through a flushed temporary sibling and os.replace."""
    approved = (root or get_content_root()).resolve()
    if validation_report is not None and not validation_report.ok:
        raise ValueError("Validation errors block canonical save")
    target = resolve_content_path(path, root=approved)
    if not is_writable_source_tree(approved):
        raise ContentPathError("Approved content root is not a writable source tree")
    if expected_snapshot is not None:
        try:
            current = snapshot_file(target, root=approved)
        except FileNotFoundError:
            current = None
        if current != expected_snapshot:
            log.warning("Developer Tools disk conflict: %s", target)
            raise DiskConflictError(f"{target.name} changed on disk since it was opened")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(header), extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in header})
            fh.flush()
            os.fsync(fh.fileno())
        if create_backup and target.is_file():
            shutil.copy2(target, target.with_name(target.name + ".bak"))
        os.replace(temp_name, target)
        temp_name = None
        return snapshot_file(target, root=approved)
    except Exception:
        log.exception("Developer Tools atomic CSV write failed: %s", target)
        raise
    finally:
        if temp_name is not None:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass
