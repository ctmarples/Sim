"""Small reusable Pygame controls for Developer Tools forms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

import pygame

from settings import COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER, COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_ACTIVE
from .validation import ValidationIssue, ValidationReport, ValidationSeverity

T = TypeVar("T")


class TextField:
    def __init__(self, rect: pygame.Rect, text: str = "", *, placeholder: str = "", max_length: int | None = None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.placeholder = placeholder
        self.max_length = max_length
        self.focused = False
        self.cursor = len(text)
        self.disabled = False
        self.error: str | None = None
        self.on_enter: Callable[[str], None] | None = None
        self.on_tab: Callable[[], None] | None = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.disabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focused = self.rect.collidepoint(event.pos)
            if self.focused:
                self.cursor = len(self.text)
            return self.focused
        if event.type != pygame.KEYDOWN or not self.focused:
            return False
        if event.key == pygame.K_ESCAPE:
            self.focused = False
        elif event.key == pygame.K_a and getattr(event, "mod", 0) & (pygame.KMOD_CTRL | pygame.KMOD_META):
            # Compact fields do not render selection ranges; clearing here gives
            # the expected Cmd/Ctrl+A then type-to-replace workflow.
            self.text = ""
            self.cursor = 0
        elif event.key == pygame.K_BACKSPACE:
            if self.cursor > 0:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif event.key == pygame.K_DELETE:
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.cursor = min(len(self.text), self.cursor + 1)
        elif event.key == pygame.K_HOME:
            self.cursor = 0
        elif event.key == pygame.K_END:
            self.cursor = len(self.text)
        elif event.key == pygame.K_TAB:
            if self.on_tab:
                self.on_tab()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.on_enter:
                self.on_enter(self.text)
        elif event.unicode and event.unicode.isprintable():
            if self.max_length is None or len(self.text) < self.max_length:
                self.text = self.text[:self.cursor] + event.unicode + self.text[self.cursor:]
                self.cursor += len(event.unicode)
        return True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, (25, 31, 34), self.rect, border_radius=3)
        border = (185, 75, 75) if self.error else (115, 145, 125) if self.focused else COLOUR_TOOLBAR_BORDER
        pygame.draw.rect(surface, border, self.rect, 1, border_radius=3)
        shown = self.text or self.placeholder
        colour = COLOUR_TEXT if self.text else COLOUR_TEXT_DIM
        surface.blit(font.render(shown, True, colour), (self.rect.x + 7, self.rect.centery - font.get_height() // 2))
        if self.focused:
            cursor_x = self.rect.x + 7 + font.size(self.text[:self.cursor])[0]
            pygame.draw.line(surface, COLOUR_TEXT, (cursor_x, self.rect.y + 5), (cursor_x, self.rect.bottom - 5), 1)


class NumericField(TextField):
    number_type = float
    kind = "number"

    def __init__(self, rect: pygame.Rect, text: str = "", *, minimum=None, maximum=None, nullable: bool = False, **kwargs):
        super().__init__(rect, text, **kwargs)
        self.minimum = minimum
        self.maximum = maximum
        self.nullable = nullable

    def parse(self):
        raw = self.text.strip()
        if not raw and self.nullable:
            self.error = None
            return None
        try:
            value = self.number_type(raw)
        except ValueError:
            self.error = f"Invalid {self.kind}"
            return None
        if self.minimum is not None and value < self.minimum:
            self.error = f"Must be at least {self.minimum}"
            return None
        if self.maximum is not None and value > self.maximum:
            self.error = f"Must be at most {self.maximum}"
            return None
        self.error = None
        return value


class IntegerField(NumericField):
    number_type = int
    kind = "integer"


class FloatField(NumericField):
    number_type = float
    kind = "number"


class ColourField(TextField):
    """Compact RGB swatch which expands to three directly-manipulable sliders."""

    def __init__(self, rect: pygame.Rect, value=(255, 255, 255)):
        if isinstance(value, str):
            import re
            parts = [int(v) for v in re.findall(r"\d+", value)[:3]]
            value = tuple(parts) if len(parts) == 3 else (255, 255, 255)
        self.value = tuple(max(0, min(255, int(v))) for v in value)
        super().__init__(rect, str(list(self.value)))
        self.open = False
        self._slider_rects = [pygame.Rect(0, 0, 1, 1) for _ in range(3)]

    def _set_channel(self, channel: int, mouse_x: int) -> None:
        slider = self._slider_rects[channel]
        values = list(self.value)
        values[channel] = max(0, min(255, round((mouse_x - slider.x) * 255 / max(1, slider.w))))
        self.value = tuple(values)
        self.text = str(list(self.value))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and self.open and event.key == pygame.K_ESCAPE:
            self.open = False
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            if self.open:
                for channel, slider in enumerate(self._slider_rects):
                    if slider.inflate(0, 12).collidepoint(event.pos):
                        self._set_channel(channel, event.pos[0]); return True
                self.open = False
        if event.type == pygame.MOUSEMOTION and self.open and event.buttons[0]:
            for channel, slider in enumerate(self._slider_rects):
                if slider.inflate(0, 12).collidepoint(event.pos):
                    self._set_channel(channel, event.pos[0]); return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, (25, 31, 34), self.rect, border_radius=3)
        swatch = pygame.Rect(self.rect.x + 5, self.rect.y + 4, 28, self.rect.h - 8)
        pygame.draw.rect(surface, self.value, swatch, border_radius=2)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, swatch, 1, border_radius=2)
        surface.blit(font.render("RGB colour", True, COLOUR_TEXT), (swatch.right + 7, self.rect.centery-font.get_height()//2))
        if not self.open:
            return
        popup = pygame.Rect(self.rect.x, self.rect.bottom + 3, max(250, self.rect.w), 116)
        pygame.draw.rect(surface, (30, 37, 40), popup, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, popup, 1, border_radius=4)
        for channel, label in enumerate("RGB"):
            y = popup.y + 13 + channel * 31
            slider = pygame.Rect(popup.x + 38, y + 5, popup.w - 86, 8); self._slider_rects[channel] = slider
            pygame.draw.rect(surface, (65, 70, 72), slider, border_radius=4)
            knob_x = slider.x + round(slider.w * self.value[channel] / 255)
            pygame.draw.circle(surface, (220, 225, 220), (knob_x, slider.centery), 7)
            surface.blit(font.render(label, True, COLOUR_TEXT_DIM), (popup.x + 12, y))
            surface.blit(font.render(str(self.value[channel]), True, COLOUR_TEXT), (slider.right + 9, y))
        pygame.draw.rect(surface, self.value, pygame.Rect(popup.right-29, popup.bottom-24, 17, 17), border_radius=2)


class Dropdown(Generic[T]):
    def __init__(self, rect: pygame.Rect, options: list[tuple[T, str]], value: T | None = None):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        if value is not None and not any(k == value for k, _ in self.options):
            # Never silently substitute the first option for persisted content.
            # Keep the value visible so validation can explain a stale reference.
            self.options.insert(0, (value, f"{value} (unavailable)"))
        self.value = value if value is not None else (self.options[0][0] if self.options else None)
        self.open = False
        self.disabled = False
        self.scroll = 0
        self.max_visible = 8

    def select(self, value: T) -> bool:
        if any(key == value for key, _ in self.options):
            self.value = value
            self.open = False
            return True
        return False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.disabled:
            return False
        if event.type == pygame.KEYDOWN and self.open and event.key == pygame.K_ESCAPE:
            self.open = False
            return True
        if event.type == pygame.MOUSEWHEEL and self.open:
            self.scroll = max(0, min(max(0, len(self.options) - self.max_visible), self.scroll - event.y))
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return True
            if self.open:
                for i, (key, _label) in enumerate(self.options[self.scroll:self.scroll + self.max_visible]):
                    row = pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.h, self.rect.w, self.rect.h)
                    if row.collidepoint(event.pos):
                        return self.select(key)
                self.open = False
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        label = next((label for key, label in self.options if key == self.value), "—")
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN, self.rect, border_radius=3)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self.rect, 1, border_radius=3)
        surface.blit(font.render(label, True, COLOUR_TEXT), (self.rect.x + 7, self.rect.centery - font.get_height() // 2))
        if self.open:
            for i, (key, option) in enumerate(self.options[self.scroll:self.scroll + self.max_visible]):
                row = pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.h, self.rect.w, self.rect.h)
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN_ACTIVE if key == self.value else COLOUR_TOOLBAR_BTN, row)
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, row, 1)
                surface.blit(font.render(option, True, COLOUR_TEXT), (row.x + 7, row.centery - font.get_height() // 2))


class Checkbox:
    def __init__(self, rect: pygame.Rect, checked: bool = False, *, disabled: bool = False):
        self.rect = pygame.Rect(rect)
        self.checked = checked
        self.disabled = disabled

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.disabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.checked = not self.checked
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN, self.rect)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self.rect, 1)
        if self.checked:
            pygame.draw.line(surface, COLOUR_TEXT, self.rect.topleft, self.rect.bottomright, 2)
            pygame.draw.line(surface, COLOUR_TEXT, self.rect.topright, self.rect.bottomleft, 2)


class ScrollableList(Generic[T]):
    def __init__(self, rect: pygame.Rect, items: list[T] | None = None, *, row_height: int = 24):
        self.rect = pygame.Rect(rect)
        self.items = list(items or [])
        self.row_height = row_height
        self.scroll = 0
        self.selected_index: int | None = None
        self.category: Callable[[T], str] | None = None
        self.collapsed: set[str] = set()

    def _rows(self):
        """Return (item-index, item) rows, with category headers as (None, str)."""
        if self.category is None:
            return list(enumerate(self.items))
        rows=[]; last=object()
        for index,item in enumerate(self.items):
            group=str(self.category(item) or "Other")
            if group != last:
                rows.append((None,group));last=group
            if group not in self.collapsed:rows.append((index,item))
        return rows

    @property
    def selected(self) -> T | None:
        if self.selected_index is None or not 0 <= self.selected_index < len(self.items):
            return None
        return self.items[self.selected_index]

    def set_items(self, items: list[T]) -> None:
        self.items = list(items)
        self.scroll = 0
        self.selected_index = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        visible = max(1, self.rect.h // self.row_height)
        rows=self._rows()
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self.scroll = max(0, min(max(0, len(rows) - visible), self.scroll - event.y * 2))
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            row_index = self.scroll + (event.pos[1] - self.rect.y) // self.row_height
            if 0 <= row_index < len(rows):
                index,item=rows[row_index]
                if index is None:
                    if item in self.collapsed:self.collapsed.remove(item)
                    else:self.collapsed.add(item)
                    self.scroll=min(self.scroll,max(0,len(self._rows())-visible))
                else:self.selected_index=index
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, label: Callable[[T], str] = str) -> None:
        pygame.draw.rect(surface, (25, 31, 34), self.rect)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self.rect, 1)
        old_clip = surface.get_clip()
        surface.set_clip(self.rect)
        visible = max(1, self.rect.h // self.row_height + 1)
        for offset, (index,item) in enumerate(self._rows()[self.scroll:self.scroll + visible]):
            row = pygame.Rect(self.rect.x + 1, self.rect.y + offset * self.row_height, self.rect.w - 2, self.row_height)
            if index is None:
                pygame.draw.rect(surface,(36,46,43),row)
                marker="▸" if item in self.collapsed else "▾"
                surface.blit(font.render(f"{marker}  {str(item).replace('_',' ').title()}",True,(150,190,165)),(row.x+6,row.centery-font.get_height()//2))
                continue
            if index == self.selected_index:
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BTN_ACTIVE, row)
            surface.blit(font.render(label(item), True, COLOUR_TEXT), (row.x + 18, row.centery - font.get_height() // 2))
        surface.set_clip(old_clip)


class ValidationSummary:
    COLOURS = {ValidationSeverity.ERROR: (230, 95, 95), ValidationSeverity.WARNING: (226, 183, 80), ValidationSeverity.INFO: (115, 170, 210)}

    def __init__(self, rect: pygame.Rect, report: ValidationReport | None = None):
        self.list = ScrollableList[ValidationIssue](rect, (report or ValidationReport()).issues, row_height=36)

    def set_report(self, report: ValidationReport) -> None:
        self.list.set_items(report.issues)

    def severity_counts(self) -> dict[ValidationSeverity, int]:
        return {severity: sum(i.severity is severity for i in self.list.items) for severity in ValidationSeverity}

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.list.handle_event(event)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, (25, 31, 34), self.list.rect)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, self.list.rect, 1)
        old_clip = surface.get_clip(); surface.set_clip(self.list.rect)
        visible = max(1, self.list.rect.h // self.list.row_height + 1)
        for offset, issue in enumerate(self.list.items[self.list.scroll:self.list.scroll + visible]):
            row = pygame.Rect(self.list.rect.x + 1, self.list.rect.y + offset * self.list.row_height, self.list.rect.w - 2, self.list.row_height)
            colour = self.COLOURS[issue.severity]
            surface.blit(small_font.render(f"{issue.severity.name}: {issue.message}", True, colour), (row.x + 6, row.y + 3))
            location = PathLabel(issue.file, issue.row, issue.field)
            if location:
                surface.blit(small_font.render(location.strip(), True, COLOUR_TEXT_DIM), (row.x + 18, row.y + 19))
        surface.set_clip(old_clip)


def PathLabel(file: str | None, row: int | None, field: str | None) -> str:
    bits = []
    if file:
        bits.append(file.rsplit("/", 1)[-1])
    if row is not None:
        bits.append(f"row {row}")
    if field:
        bits.append(field)
    return f"  ({', '.join(bits)})" if bits else ""


@dataclass
class FormRow:
    label: str
    control: object

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, x: int, y: int) -> None:
        surface.blit(font.render(self.label, True, COLOUR_TEXT_DIM), (x, y + 5))
        draw = getattr(self.control, "draw", None)
        if draw:
            draw(surface, font)
