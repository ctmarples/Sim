"""Pygame UI for the sociopolitical sandbox test."""

from __future__ import annotations

import pygame

from settings import (
    COLOUR_MENU_BG,
    COLOUR_TEXT,
    COLOUR_TEXT_DIM,
    COLOUR_TOOLBAR_BORDER,
    COLOUR_TOOLBAR_BTN,
    COLOUR_TOOLBAR_BTN_HOVER,
    MAP_OFFSET_Y,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from sociopolitical import (
    CATEGORY_LABELS,
    DECISION_EVENTS,
    EVENT_ORDER,
    INSTITUTIONS,
    PRINCIPLES,
    PrincipleCategory,
    RecruitmentPolicy,
    SettlementPoliticalState,
    event_by_id,
    format_value_tendency,
    generate_settlement_description,
    institution_by_id,
    principle_by_id,
)


def _wrap(font: pygame.font.Font, text: str, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _btn(
    surface: pygame.Surface,
    rect: pygame.Rect,
    label: str,
    font: pygame.font.Font,
    mouse: tuple[int, int],
) -> None:
    colour = COLOUR_TOOLBAR_BTN_HOVER if rect.collidepoint(mouse) else COLOUR_TOOLBAR_BTN
    pygame.draw.rect(surface, colour, rect, border_radius=4)
    pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
    text = font.render(label, True, COLOUR_TEXT)
    surface.blit(text, text.get_rect(center=rect.center))


class SociopoliticalPanel:
    """Settlement principles panel + developer controls."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 15, bold=True)
        self._open = False
        self._panel_x = 24
        self._panel_y = MAP_OFFSET_Y + 28
        self._panel_w = 420
        self._panel_h = 620
        self._scroll = 0
        self._buttons: list[tuple[str, pygame.Rect]] = []
        self.pending_action: str | None = None
        self._tab = "settlement"  # settlement | recruit | effects | developer

    @property
    def open(self) -> bool:
        return self._open

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open_panel()

    def open_panel(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False
        self.pending_action = None

    def panel_rect(self) -> pygame.Rect:
        return pygame.Rect(self._panel_x, self._panel_y, self._panel_w, self._panel_h)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.open and self.panel_rect().collidepoint(pos)

    def handle_mousedown(self, pos: tuple[int, int]) -> bool:
        if not self.open:
            return False
        for action, rect in self._buttons:
            if rect.collidepoint(pos):
                if action.startswith("tab:"):
                    self._tab = action.split(":", 1)[1]
                elif action == "close":
                    self.close()
                else:
                    self.pending_action = action
                return True
        return self.contains(pos)

    def handle_mousewheel(self, dy: int) -> bool:
        if not self.open:
            return False
        self._scroll = max(0, self._scroll - dy * 24)
        return True

    def draw(self, surface: pygame.Surface, state: SettlementPoliticalState, mouse_pos) -> None:
        if not self.open:
            return
        mouse = mouse_pos or (0, 0)
        panel = self.panel_rect()
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=8)
        self._buttons = []

        title = self.font_title.render("Settlement principles", True, COLOUR_TEXT)
        surface.blit(title, (panel.x + 14, panel.y + 10))
        close = pygame.Rect(panel.right - 34, panel.y + 8, 24, 22)
        self._buttons.append(("close", close))
        _btn(surface, close, "×", self.font, mouse)

        tabs = (
            ("settlement", "Values"),
            ("recruit", "Recruit"),
            ("effects", "Effects"),
            ("developer", "Dev"),
        )
        tx = panel.x + 12
        for key, label in tabs:
            rect = pygame.Rect(tx, panel.y + 36, 92, 24)
            self._buttons.append((f"tab:{key}", rect))
            colour = (
                COLOUR_TOOLBAR_BTN_HOVER if key == self._tab or rect.collidepoint(mouse) else COLOUR_TOOLBAR_BTN
            )
            pygame.draw.rect(surface, colour, rect, border_radius=4)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=4)
            surface.blit(self.font_small.render(label, True, COLOUR_TEXT), (rect.x + 8, rect.y + 5))
            tx += 98

        body = pygame.Rect(panel.x + 12, panel.y + 68, panel.w - 24, panel.h - 80)
        clip = surface.subsurface(body.clip(surface.get_rect()))
        # Draw into a temporary surface for scrolling.
        canvas = pygame.Surface((body.w, 900), pygame.SRCALPHA)
        y = 4 - self._scroll
        if self._tab == "settlement":
            y = self._draw_settlement_tab(canvas, state, y)
        elif self._tab == "recruit":
            y = self._draw_recruit_tab(canvas, state, y, mouse)
        elif self._tab == "effects":
            y = self._draw_effects_tab(canvas, state, y)
        else:
            y = self._draw_developer_tab(canvas, state, y, mouse)
        clip.blit(canvas, (0, 0))
        # Hit-test developer buttons against panel coordinates.
        if self._tab == "developer":
            self._layout_developer_buttons(body, mouse, surface)
        elif self._tab == "recruit":
            self._layout_recruit_buttons(body, state, mouse, surface)
        elif self._tab == "effects":
            self._layout_effects_buttons(body, state, mouse, surface)

    def _draw_settlement_tab(
        self, canvas: pygame.Surface, state: SettlementPoliticalState, y: int
    ) -> int:
        canvas.blit(self.font.render("Settlement values (50 = neutral)", True, COLOUR_TEXT), (0, y))
        y += 22
        for label, value, blurb in (
            (
                "Authority",
                state.authority,
                "High Authority centralises work. Unsuitable assignments under Settlement Office "
                "cut happiness → extra breaks and wandering.",
            ),
            (
                "Solidarity",
                state.solidarity,
                "High Solidarity shares provision and open admission. Shared rations and care "
                "protect happiness; low Solidarity leaves morale brittle.",
            ),
            (
                "Stewardship",
                state.stewardship,
                "High Stewardship slows extractive work for ecology. Ignoring it trades short-term "
                "output for later disturbance — not a direct happiness hit.",
            ),
        ):
            canvas.blit(
                self.font.render(f"{label}: {value}", True, COLOUR_TEXT),
                (8, y),
            )
            bar = pygame.Rect(150, y + 4, 200, 10)
            pygame.draw.rect(canvas, (30, 36, 40), bar, border_radius=3)
            fill_w = int(bar.w * max(0, min(100, value)) / 100)
            pygame.draw.rect(
                canvas, (120, 150, 110), pygame.Rect(bar.x, bar.y, fill_w, bar.h), border_radius=3
            )
            pygame.draw.line(
                canvas, COLOUR_TEXT_DIM, (bar.x + bar.w // 2, bar.y), (bar.x + bar.w // 2, bar.bottom)
            )
            y += 20
            for line in _wrap(self.font_small, blurb, canvas.get_width() - 16):
                canvas.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (8, y))
                y += self.font_small.get_linesize()
            y += 8
        tendency = format_value_tendency(state.authority, state.solidarity, state.stewardship)
        canvas.blit(self.font_small.render(tendency, True, COLOUR_TEXT_DIM), (8, y))
        y += 18
        chain = (
            "Chain: decisions → principles/institutions → happiness & work modifiers → "
            "morale bands (Engaged/Content/Disengaged/Unhappy) → breaks & wandering."
        )
        for line in _wrap(self.font_small, chain, canvas.get_width() - 16):
            canvas.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (8, y))
            y += self.font_small.get_linesize()
        y += 14

        canvas.blit(self.font.render("Institution progress", True, COLOUR_TEXT), (0, y))
        y += 20
        for cat in PrincipleCategory:
            count, need = state.category_progress()[cat]
            formed = state.has_category_institution(cat)
            mark = " ✓" if formed else ""
            canvas.blit(
                self.font_small.render(
                    f"{CATEGORY_LABELS[cat]}: {count}/{need}{mark}",
                    True,
                    COLOUR_TEXT,
                ),
                (8, y),
            )
            y += 16
        y += 10

        canvas.blit(self.font.render("Enacted principles", True, COLOUR_TEXT), (0, y))
        y += 20
        by_cat: dict[PrincipleCategory, list[str]] = {c: [] for c in PrincipleCategory}
        for pid in state.enacted_principle_ids:
            p = PRINCIPLES.get(pid)
            if p:
                by_cat[p.category].append(p.name)
        for cat in PrincipleCategory:
            names = by_cat[cat]
            if not names:
                continue
            canvas.blit(
                self.font_small.render(f"{CATEGORY_LABELS[cat]}:", True, COLOUR_TEXT_DIM),
                (8, y),
            )
            y += 15
            for name in names:
                canvas.blit(self.font_small.render(f"• {name}", True, COLOUR_TEXT), (18, y))
                y += 14
        if not state.enacted_principle_ids:
            canvas.blit(
                self.font_small.render("None yet — resolve decisions to enact principles.", True, COLOUR_TEXT_DIM),
                (8, y),
            )
            y += 18
        y += 12
        canvas.blit(self.font.render("Institutions", True, COLOUR_TEXT), (0, y))
        y += 20
        if not state.institution_ids:
            canvas.blit(
                self.font_small.render("None formed (need 3 principles in one category).", True, COLOUR_TEXT_DIM),
                (8, y),
            )
            y += 18
        for iid in state.institution_ids:
            inst = INSTITUTIONS.get(iid)
            if not inst:
                continue
            canvas.blit(self.font_small.render(inst.name, True, COLOUR_TEXT), (8, y))
            y += 15
            for line in _wrap(self.font_small, inst.description, 360):
                canvas.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (18, y))
                y += 13
            y += 6
        return y

    def _draw_recruit_tab(
        self, canvas: pygame.Surface, state: SettlementPoliticalState, y: int, mouse
    ) -> int:
        policy = state.recruitment_policy
        canvas.blit(self.font.render("Recruitment policy", True, COLOUR_TEXT), (0, y))
        y += 22
        for pol, title, blurb in (
            (
                RecruitmentPolicy.CONTRACT,
                "Contract recruitment",
                "Control over skills; unmet requirements may cost gold each season.",
            ),
            (
                RecruitmentPolicy.OPEN_ADMISSION,
                "Open admission",
                "With empty housing, one applicant may arrive each season. "
                "Accept or refuse; no recurring compensation.",
            ),
        ):
            mark = "●" if policy == pol else "○"
            canvas.blit(self.font.render(f"{mark} {title}", True, COLOUR_TEXT), (8, y))
            y += 18
            for line in _wrap(self.font_small, blurb, 360):
                canvas.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (18, y))
                y += 13
            y += 8
        y += 6
        note = (
            "Contract offers control over skills but may require gold. "
            "Open admission brings villagers without payment but offers less control."
        )
        for line in _wrap(self.font_small, note, 360):
            canvas.blit(self.font_small.render(line, True, COLOUR_TEXT), (0, y))
            y += 13
        y += 16
        if state.open_applicant is not None:
            app = state.open_applicant
            skills = ", ".join(f"{k}:{v}" for k, v in sorted(app.skills.items())[:4]) or "varied"
            canvas.blit(self.font.render(f"Applicant: {app.name}", True, COLOUR_TEXT), (0, y))
            y += 18
            canvas.blit(self.font_small.render(f"Skills {skills}", True, COLOUR_TEXT_DIM), (8, y))
            y += 24
        return y

    def _layout_recruit_buttons(
        self, body: pygame.Rect, state: SettlementPoliticalState, mouse, surface
    ) -> None:
        y = body.y + 210
        for action, label in (
            ("policy_contract", "Use Contract"),
            ("policy_open", "Use Open Admission"),
        ):
            rect = pygame.Rect(body.x, y, 180, 26)
            self._buttons.append((action, rect))
            _btn(surface, rect, label, self.font_small, mouse)
            y += 32
        if state.open_applicant is not None:
            y += 8
            accept = pygame.Rect(body.x, y, 120, 28)
            refuse = pygame.Rect(body.x + 130, y, 120, 28)
            self._buttons.append(("accept_applicant", accept))
            self._buttons.append(("refuse_applicant", refuse))
            _btn(surface, accept, "Accept", self.font_small, mouse)
            _btn(surface, refuse, "Refuse", self.font_small, mouse)

    def _draw_effects_tab(
        self, canvas: pygame.Surface, state: SettlementPoliticalState, y: int
    ) -> int:
        canvas.blit(self.font.render("Active effects", True, COLOUR_TEXT), (0, y))
        y += 20
        effects = state.active_effects()
        if not effects:
            canvas.blit(
                self.font_small.render("No institutional effects active.", True, COLOUR_TEXT_DIM),
                (8, y),
            )
            y += 18
        for line in effects:
            for wrapped in _wrap(self.font_small, line, 360):
                canvas.blit(self.font_small.render(wrapped, True, COLOUR_TEXT), (8, y))
                y += 14
            y += 4
        if state.has_institution("common_provision"):
            y += 8
            canvas.blit(
                self.font_small.render(
                    f"Shared ration mode: {state.settlement_ration_mode}",
                    True,
                    COLOUR_TEXT,
                ),
                (8, y),
            )
            y += 18
        y += 12
        canvas.blit(self.font.render("Recent diary", True, COLOUR_TEXT), (0, y))
        y += 18
        for entry in state.diary[-12:][::-1]:
            canvas.blit(
                self.font_small.render(f"[d{entry.day}] {entry.text}", True, COLOUR_TEXT),
                (4, y),
            )
            y += 14
            if entry.detail:
                for line in _wrap(self.font_small, entry.detail, 350)[:2]:
                    canvas.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (14, y))
                    y += 12
        return y

    def _layout_effects_buttons(
        self, body: pygame.Rect, state: SettlementPoliticalState, mouse, surface
    ) -> None:
        if not state.has_institution("common_provision"):
            return
        y = body.y + 40 + 16 * max(1, len(state.active_effects()))
        for mode in ("HALF", "NORMAL", "DOUBLE"):
            rect = pygame.Rect(body.x, y, 110, 22)
            self._buttons.append((f"ration_all:{mode}", rect))
            _btn(surface, rect, f"Ration {mode.title()}", self.font_small, mouse)
            y += 26

    def _draw_developer_tab(
        self, canvas: pygame.Surface, state: SettlementPoliticalState, y: int, mouse
    ) -> int:
        canvas.blit(self.font.render("Developer controls", True, COLOUR_TEXT), (0, y))
        y += 22
        canvas.blit(
            self.font_small.render(
                f"Seasons {state.seasons_elapsed} · Decisions {state.decisions_resolved} · "
                f"Policy {state.recruitment_policy.value}",
                True,
                COLOUR_TEXT_DIM,
            ),
            (0, y),
        )
        y += 20
        for event_id in EVENT_ORDER:
            ev = DECISION_EVENTS[event_id]
            done = "✓" if event_id in state.fired_event_ids else " "
            canvas.blit(
                self.font_small.render(f"[{done}] {ev.id}", True, COLOUR_TEXT_DIM),
                (8, y),
            )
            y += 14
        return y + 8

    def _layout_developer_buttons(self, body: pygame.Rect, mouse, surface) -> None:
        actions = [
            ("advance_season", "Advance one season"),
            ("next_decision", "Trigger next decision"),
            ("add_food", "Add food"),
            ("add_gold", "Add gold (+20)"),
            ("add_housing", "Create empty housing"),
            ("reset_politics", "Reset sociopolitical state"),
            ("show_summary", "Show end-of-test summary"),
        ]
        y = body.y + 24 + 18 + 14 * len(EVENT_ORDER) + 12
        for action, label in actions:
            rect = pygame.Rect(body.x, y, body.w - 8, 24)
            self._buttons.append((action, rect))
            _btn(surface, rect, label, self.font_small, mouse)
            y += 28
        y += 6
        for event_id in EVENT_ORDER:
            rect = pygame.Rect(body.x, y, body.w - 8, 20)
            self._buttons.append((f"event:{event_id}", rect))
            _btn(surface, rect, f"Fire: {event_id}", self.font_small, mouse)
            y += 22


class DecisionModal:
    """Decision incident with options and visible consequences."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 16, bold=True)
        self.event_id: str | None = None
        self.choice_id: str | None = None
        self._option_rects: list[tuple[str, pygame.Rect]] = []
        self.reveal_principle_after = True

    @property
    def open(self) -> bool:
        return self.event_id is not None

    def show(self, event_id: str) -> None:
        self.event_id = event_id
        self.choice_id = None

    def close(self) -> None:
        self.event_id = None
        self.choice_id = None
        self._option_rects = []

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        ev = event_by_id(self.event_id or "")
        if ev is None:
            self.close()
            return True
        if event.type == pygame.KEYDOWN:
            keys = (
                (pygame.K_1, pygame.K_KP1),
                (pygame.K_2, pygame.K_KP2),
                (pygame.K_3, pygame.K_KP3),
            )
            for index, pair in enumerate(keys):
                if index < len(ev.options) and event.key in pair:
                    self.choice_id = ev.options[index].id
                    return True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for opt_id, rect in self._option_rects:
                if rect.collidepoint(event.pos):
                    self.choice_id = opt_id
                    return True
            return True
        return True

    def draw(self, surface: pygame.Surface, mouse_pos) -> None:
        if not self.open:
            return
        ev = event_by_id(self.event_id or "")
        if ev is None:
            return
        mouse = mouse_pos or (0, 0)
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        surface.blit(shade, (0, 0))

        lines = _wrap(self.font, ev.description, 560)
        option_block = 0
        for opt in ev.options:
            option_block += 72 + 14 * len(opt.immediate_effects)
        panel_h = min(WINDOW_HEIGHT - 40, 140 + 22 * len(lines) + option_block)
        panel = pygame.Rect((WINDOW_WIDTH - 620) // 2, (WINDOW_HEIGHT - panel_h) // 2, 620, panel_h)
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=8)

        surface.blit(self.font_title.render(ev.title, True, COLOUR_TEXT), (panel.x + 20, panel.y + 16))
        y = panel.y + 48
        for line in lines:
            surface.blit(self.font.render(line, True, COLOUR_TEXT), (panel.x + 20, y))
            y += 20
        y += 10
        self._option_rects = []
        for i, opt in enumerate(ev.options):
            h = 58 + 14 * len(opt.immediate_effects)
            rect = pygame.Rect(panel.x + 18, y, panel.w - 36, h)
            self._option_rects.append((opt.id, rect))
            colour = COLOUR_TOOLBAR_BTN_HOVER if rect.collidepoint(mouse) else COLOUR_TOOLBAR_BTN
            pygame.draw.rect(surface, colour, rect, border_radius=5)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=5)
            surface.blit(
                self.font.render(f"{i + 1}. {opt.label}", True, COLOUR_TEXT),
                (rect.x + 10, rect.y + 8),
            )
            oy = rect.y + 28
            value_bits = []
            for k, v in opt.value_changes.items():
                value_bits.append(f"{k.title()} {v:+d}")
            if value_bits:
                surface.blit(
                    self.font_small.render("Tendency: " + ", ".join(value_bits), True, COLOUR_TEXT_DIM),
                    (rect.x + 10, oy),
                )
                oy += 14
            for effect in opt.immediate_effects:
                surface.blit(
                    self.font_small.render(f"Immediate: {effect.label}", True, COLOUR_TEXT_DIM),
                    (rect.x + 10, oy),
                )
                oy += 14
            if not self.reveal_principle_after:
                p = principle_by_id(opt.principle_id)
                if p:
                    surface.blit(
                        self.font_small.render(
                            f"Principle: {p.name} — {CATEGORY_LABELS[p.category]}",
                            True,
                            COLOUR_TEXT_DIM,
                        ),
                        (rect.x + 10, oy),
                    )
            y += h + 10
        hint = self.font_small.render("Choose with click / 1–3", True, COLOUR_TEXT_DIM)
        surface.blit(hint, hint.get_rect(midbottom=(panel.centerx, panel.bottom - 8)))


class InstitutionRevealModal:
    """Pause presentation when an institution forms."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 14)
        self.font_small = pygame.font.SysFont("menlo", 12)
        self.font_title = pygame.font.SysFont("menlo", 18, bold=True)
        self.institution_id: str | None = None
        self.summary_lines: tuple[str, ...] = ()
        self.dismissed = False
        self._continue_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self.institution_id is not None

    def show(self, institution_id: str, summary_lines: tuple[str, ...]) -> None:
        self.institution_id = institution_id
        self.summary_lines = summary_lines
        self.dismissed = False

    def close(self) -> None:
        self.institution_id = None
        self.summary_lines = ()
        self.dismissed = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
            pygame.K_SPACE,
            pygame.K_ESCAPE,
        ):
            self.dismissed = True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._continue_rect.collidepoint(event.pos) or True:
                self.dismissed = True
            return True
        return True

    def draw(self, surface: pygame.Surface, mouse_pos) -> None:
        if not self.open:
            return
        inst = institution_by_id(self.institution_id or "")
        if inst is None:
            return
        mouse = mouse_pos or (0, 0)
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        surface.blit(shade, (0, 0))
        panel = pygame.Rect((WINDOW_WIDTH - 560) // 2, (WINDOW_HEIGHT - 360) // 2, 560, 360)
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=8)
        surface.blit(
            self.font_title.render("A tradition has become an institution", True, COLOUR_TEXT),
            (panel.x + 24, panel.y + 22),
        )
        y = panel.y + 64
        for line in self.summary_lines:
            for wrapped in _wrap(self.font, line, 500):
                surface.blit(self.font.render(wrapped, True, COLOUR_TEXT), (panel.x + 28, y))
                y += 20
            y += 4
        y += 10
        for wrapped in _wrap(self.font, inst.description, 500):
            surface.blit(self.font.render(wrapped, True, COLOUR_TEXT), (panel.x + 28, y))
            y += 20
        y += 12
        surface.blit(self.font_small.render(f"Benefit: {inst.benefit}", True, COLOUR_TEXT), (panel.x + 28, y))
        y += 18
        surface.blit(self.font_small.render(f"Constraint: {inst.cost}", True, COLOUR_TEXT), (panel.x + 28, y))
        self._continue_rect = pygame.Rect(panel.centerx - 70, panel.bottom - 48, 140, 30)
        _btn(surface, self._continue_rect, "Continue", self.font, mouse)


class EndOfTestSummaryModal:
    def __init__(self) -> None:
        self.font = pygame.font.SysFont("menlo", 13)
        self.font_small = pygame.font.SysFont("menlo", 11)
        self.font_title = pygame.font.SysFont("menlo", 17, bold=True)
        self.lines: list[str] = []
        self.description = ""
        self.dismissed = False
        self._open = False
        self._continue_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:
        return self._open

    def show(self, lines: list[str], description: str) -> None:
        self.lines = list(lines)
        self.description = description
        self.dismissed = False
        self._open = True

    def close(self) -> None:
        self._open = False
        self.dismissed = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.open:
            return False
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
            pygame.K_SPACE,
            pygame.K_ESCAPE,
        ):
            self.dismissed = True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.dismissed = True
            return True
        return True

    def draw(self, surface: pygame.Surface, mouse_pos) -> None:
        if not self.open:
            return
        mouse = mouse_pos or (0, 0)
        shade = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 130))
        surface.blit(shade, (0, 0))
        panel_h = min(WINDOW_HEIGHT - 30, 120 + 16 * len(self.lines) + 80)
        panel = pygame.Rect((WINDOW_WIDTH - 580) // 2, (WINDOW_HEIGHT - panel_h) // 2, 580, panel_h)
        pygame.draw.rect(surface, COLOUR_MENU_BG, panel, border_radius=8)
        pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, panel, 2, border_radius=8)
        surface.blit(
            self.font_title.render("Sociopolitical test summary", True, COLOUR_TEXT),
            (panel.x + 20, panel.y + 16),
        )
        y = panel.y + 50
        for wrapped in _wrap(self.font, self.description, 530):
            surface.blit(self.font.render(wrapped, True, COLOUR_TEXT), (panel.x + 20, y))
            y += 18
        y += 10
        for line in self.lines:
            surface.blit(self.font_small.render(line, True, COLOUR_TEXT_DIM), (panel.x + 24, y))
            y += 15
        self._continue_rect = pygame.Rect(panel.centerx - 70, panel.bottom - 44, 140, 28)
        _btn(surface, self._continue_rect, "Continue", self.font, mouse)
