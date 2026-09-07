"""Modal narrative dialogue plus a non-modal tutorial prompt."""

from __future__ import annotations

import pygame

from settings import (
    COLOUR_MENU_BG, COLOUR_TEXT, COLOUR_TEXT_DIM, COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN, COLOUR_TOOLBAR_BTN_HOVER, MAP_OFFSET_Y, WINDOW_HEIGHT,
    WINDOW_WIDTH, map_view_width,
)

# Tall browse window while scrolling; settled window fits one quest.
SCROLL_QUEST_HEIGHT = 400
MAX_QUEST_HEIGHT = 480
HEADER_HEIGHT = 34
GAP_LINES = 1
HOVER_FILL = (48, 56, 62)


class ScenarioDialog:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 15)
        self.small = pygame.font.SysFont("menlo", 12)
        self.text: str | None = None
        self.choices: tuple[str, ...] = ()
        self.choice: int | None = None
        self._choice_rects: list[pygame.Rect] = []
        self.dismissed = False
        self.objective_rect = pygame.Rect(0, 0, 0, 0)
        self.quest_rect = pygame.Rect(0, 0, 0, 0)
        self.quest_steps = []
        self.section_hits: list[tuple[pygame.Rect, str]] = []
        self._section_tops: list[int] = []
        self._section_ids: list[str] = []
        self._section_heights: list[int] = []
        self._content_height = 0
        self._view_height = SCROLL_QUEST_HEIGHT

    @property
    def open(self) -> bool:
        return self.text is not None

    def show(self, text: str, choices: tuple[str, ...] = ()) -> None:
        self.text = text
        self.choices = tuple(choices)
        self.choice = None
        self.dismissed = False

    def close(self) -> None:
        self.text = None
        self.choices = ()
        self._choice_rects = []

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN and self.choices:
            keys = (
                (pygame.K_1, pygame.K_KP1),
                (pygame.K_2, pygame.K_KP2),
                (pygame.K_3, pygame.K_KP3),
                (pygame.K_4, pygame.K_KP4),
            )
            for index, pair in enumerate(keys):
                if index < len(self.choices) and event.key in pair:
                    self._dismiss(index)
                    return True
        elif event.type == pygame.KEYDOWN and event.key in (
            pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE
        ):
            if self.choices:
                return True
            self._dismiss(None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            selected = next(
                (i for i, r in enumerate(self._choice_rects) if r.collidepoint(event.pos)),
                None,
            )
            if self.choices and selected is None:
                return True
            self._dismiss(selected)
        return True

    def _dismiss(self, choice: int | None) -> None:
        self.choice = choice
        self.dismissed = True
        self.close()

    def quest_at(self, pos: tuple[int, int]) -> str | None:
        """Return the quest id under ``pos`` in the scrolled body, if any."""
        for rect, quest_id in self.section_hits:
            if rect.collidepoint(pos):
                return quest_id
        return None

    @staticmethod
    def _wrap(font, text, width):
        lines = []
        line = ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if line and font.size(trial)[0] > width:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    def draw(
        self,
        surface: pygame.Surface,
        prompt: str | None = None,
        *,
        quest: dict | None = None,
        group_rows: list[dict] | None = None,
        navigation=None,
    ) -> None:
        self.objective_rect = pygame.Rect(0, 0, 0, 0)
        self.quest_rect = pygame.Rect(0, 0, 0, 0)
        self.quest_steps = []
        self.section_hits = []
        self._section_tops = []
        self._section_ids = []
        self._section_heights = []
        if prompt or group_rows:
            self._draw_quest_viewport(
                surface,
                prompt=prompt,
                quest=quest,
                group_rows=group_rows or [],
                navigation=navigation,
            )
        if not self.open:
            return
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 105))
        surface.blit(shade, (0, 0))
        text_lines = self._wrap(self.font, self.text or "", 590 - 48)
        choice_n = len(self.choices)
        panel_h = 120 + 24 * len(text_lines) + (56 * choice_n + 28 if choice_n else 56)
        panel_h = min(WINDOW_HEIGHT - 40, max(190, panel_h))
        panel = pygame.Rect((WINDOW_WIDTH - 590) // 2, (WINDOW_HEIGHT - panel_h) // 2, 590, panel_h)
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=7)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=7)
        y = panel.y + 28
        for line in text_lines:
            surface.blit(self.font.render(line, True, COLOUR_TEXT), (panel.x + 24, y))
            y += 24
        self._choice_rects = []
        if self.choices:
            cy = y + 14
            for i, choice in enumerate(self.choices):
                button = pygame.Rect(panel.x + 24, cy, panel.w - 48, 34)
                self._choice_rects.append(button)
                colour = (
                    COLOUR_TOOLBAR_BTN_HOVER
                    if button.collidepoint(pygame.mouse.get_pos())
                    else COLOUR_TOOLBAR_BTN
                )
                pygame.draw.rect(surface, colour, button, border_radius=4)
                pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, button, 1, border_radius=4)
                label = self.small.render(f"{i + 1}. {choice}", True, COLOUR_TEXT)
                surface.blit(label, (button.x + 10, button.y + 9))
                cy += 42
            keys = "/".join(str(i + 1) for i in range(len(self.choices)))
            hint = self.small.render(f"Choose with click / {keys}", True, COLOUR_TEXT_DIM)
            surface.blit(hint, hint.get_rect(midbottom=(panel.centerx, panel.bottom - 10)))
            return
        button = pygame.Rect(panel.centerx - 65, panel.bottom - 48, 130, 28)
        colour = (
            COLOUR_TOOLBAR_BTN_HOVER
            if button.collidepoint(pygame.mouse.get_pos())
            else COLOUR_TOOLBAR_BTN
        )
        pygame.draw.rect(surface, colour, button, border_radius=4)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, button, 1, border_radius=4)
        label = self.small.render("Continue", True, COLOUR_TEXT)
        surface.blit(label, label.get_rect(center=button.center))
        hint = self.small.render("Enter / click", True, COLOUR_TEXT_DIM)
        surface.blit(hint, hint.get_rect(midtop=(panel.centerx, button.bottom + 5)))

    def _draw_quest_viewport(
        self,
        surface: pygame.Surface,
        *,
        prompt: str | None = None,
        quest: dict | None,
        group_rows: list[dict],
        navigation,
    ) -> None:
        from quest_ui import detail_lines, draw_line

        rows = group_rows or ([quest] if quest else [])
        if not rows and prompt:
            rows = [dict(id='prompt', headline=prompt, group_title='Quests',
                         objectives=[], completed=False)]
        if not rows:
            return
        width = min(390, max(160, map_view_width() - 36))
        line_h = self.small.get_linesize()
        gap = line_h * GAP_LINES
        sections = []
        offset = 0
        for row in rows:
            lines = detail_lines(self.small, row, width - 24)
            visual = sum(1 if kind != 'gap' else GAP_LINES for _, kind in lines)
            body_h = visual * line_h
            headline_h = self.small.get_linesize() + 8
            height = headline_h + body_h + 14
            sections.append((row, offset, height, lines, headline_h))
            self._section_tops.append(offset)
            self._section_ids.append(row['id'])
            self._section_heights.append(height)
            offset += height
        self._content_height = max(offset, 1)
        focused = quest or rows[0]
        if prompt and not quest:
            focused = dict(focused)
            focused['headline'] = prompt
        focus_index = next(
            (i for i, row in enumerate(rows) if row['id'] == focused.get('id')),
            0,
        )
        focus_body = self._section_heights[focus_index]
        mouse = pygame.mouse.get_pos()
        if navigation is not None:
            if navigation.settled:
                navigation.snap_to_focus(self._section_tops, self._section_ids)
                target_h = min(MAX_QUEST_HEIGHT, HEADER_HEIGHT + focus_body)
            else:
                target_h = SCROLL_QUEST_HEIGHT
            body_h = max(1, target_h - HEADER_HEIGHT)
            max_scroll = max(0, self._content_height - body_h)
            navigation._clamp(max_scroll)
            scroll = navigation.scroll
        else:
            target_h = min(MAX_QUEST_HEIGHT, HEADER_HEIGHT + focus_body)
            scroll = float(self._section_tops[focus_index])
        self._view_height = int(target_h)
        rect = pygame.Rect(
            map_view_width() - width - 18,
            MAP_OFFSET_Y + 18,
            width,
            self._view_height,
        )
        self.quest_rect = rect.copy()
        self.objective_rect = pygame.Rect(rect.x, rect.y, rect.w - 64, HEADER_HEIGHT)
        pygame.draw.rect(surface, (32, 37, 40), rect, border_radius=5)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=5)
        # Sticky chrome: quest-group title only (quest names live in the list).
        title = focused.get('group_title', 'Quests')
        surface.blit(self.small.render(title, True, COLOUR_TEXT_DIM), (rect.x + 12, rect.y + 10))
        for button_offset, label, delta in ((60, '‹', -1), (30, '›', 1)):
            button = pygame.Rect(rect.right - button_offset, rect.y + 4, 26, 24)
            surface.blit(self.font.render(label, True, COLOUR_TEXT), button.topleft)
            self.quest_steps.append((button, delta))
        clip = pygame.Rect(rect.x, rect.y + HEADER_HEIGHT, rect.w, rect.h - HEADER_HEIGHT)
        browsing = navigation is not None and not navigation.settled
        hover_id = None
        if browsing and clip.collidepoint(mouse):
            for row, section_offset, height, _lines, _hh in sections:
                top = clip.y + section_offset - scroll
                hit = pygame.Rect(clip.x, int(top), clip.w, height)
                if hit.collidepoint(mouse):
                    hover_id = row['id']
                    break
        if navigation is not None:
            navigation.hover = hover_id
        old = surface.get_clip()
        surface.set_clip(clip.clip(old))
        for row, section_offset, height, lines, headline_h in sections:
            top = clip.y + section_offset - scroll
            hit = pygame.Rect(clip.x, int(top), clip.w, height)
            visible = hit.clip(clip)
            if visible.h > 0:
                self.section_hits.append((visible.copy(), row['id']))
            if top > clip.bottom or top + height < clip.y:
                continue
            if browsing and row['id'] == hover_id:
                pygame.draw.rect(surface, HOVER_FILL, visible)
            colour = COLOUR_TEXT if row['id'] == focused.get('id') else COLOUR_TEXT_DIM
            surface.blit(
                self.small.render(row['headline'], True, colour),
                (rect.x + 12, top + 4),
            )
            y = top + headline_h
            for text, checked in lines:
                if checked == 'gap':
                    y += gap
                    continue
                draw_line(surface, self.small, text, checked, rect.x + 10, int(y), colour)
                y += line_h
        surface.set_clip(old)
        if self._content_height > clip.h:
            track = pygame.Rect(rect.right - 5, clip.y + 2, 3, clip.h - 4)
            thumb_h = max(16, int(clip.h * clip.h / max(1, self._content_height)))
            max_scroll = max(1, self._content_height - clip.h)
            thumb_y = clip.y + int((clip.h - thumb_h) * scroll / max_scroll)
            pygame.draw.rect(surface, COLOUR_TEXT_DIM, (track.x, thumb_y, 3, thumb_h))
