"""Shared state and dirty-navigation guard for catalogue editors."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from .content_io import FileSnapshot
from .validation import ValidationReport

T = TypeVar("T")


@dataclass
class EditorState(Generic[T]):
    selected_item: T | None = None
    candidate: T | None = None
    original: T | None = None
    dirty: bool = False
    source_file: Path | None = None
    source_row_index: int | None = None
    snapshot: FileSnapshot | None = None
    validation: ValidationReport = field(default_factory=ValidationReport)
    is_new: bool = False
    is_duplicate: bool = False

    def select(self, item: T, *, source_file: Path, row_index: int, snapshot: FileSnapshot) -> None:
        self.selected_item = item
        self.original = deepcopy(item)
        self.candidate = deepcopy(item)
        self.source_file = source_file
        self.source_row_index = row_index
        self.snapshot = snapshot
        self.validation = ValidationReport()
        self.dirty = self.is_new = self.is_duplicate = False

    def begin_new(self, item: T, *, source_file: Path, snapshot: FileSnapshot, duplicate: bool = False) -> None:
        self.selected_item = None
        self.original = None
        self.candidate = deepcopy(item)
        self.source_file = source_file
        self.source_row_index = None
        self.snapshot = snapshot
        self.validation = ValidationReport()
        self.dirty = True
        self.is_new = True
        self.is_duplicate = duplicate

    def mark_changed(self) -> None:
        self.dirty = self.candidate != self.original or self.is_new

    def mark_saved(self) -> None:
        self.original = deepcopy(self.candidate)
        self.selected_item = deepcopy(self.candidate)
        self.dirty = self.is_new = self.is_duplicate = False


@dataclass
class DirtyNavigationGuard:
    pending_action: str | None = None
    open: bool = False

    def request(self, action: str, *, dirty: bool) -> bool:
        if not dirty:
            return True
        self.pending_action = action
        self.open = True
        return False

    def discard(self) -> str | None:
        action = self.pending_action
        self.pending_action = None
        self.open = False
        return action

    def cancel(self) -> None:
        self.pending_action = None
        self.open = False
