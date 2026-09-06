"""Continuous scroll focus within the quest group."""
import time

GROUP_TITLES = {'shelter': 'Shelter from the Storm', 'land': 'Lay of the Land'}

SCROLL_FRICTION = 0.88
SCROLL_STOP = 0.35
WHEEL_IMPULSE = 42.0
LEAVE_COLLAPSE = 1.0


class QuestNavigation:
    def __init__(self):
        self.focus = None
        self.active = None
        self.scroll = 0.0
        self.velocity = 0.0
        self.settled = True
        self.hover = None
        self._left_at = None

    def select(self, key):
        """Focus a quest and collapse the viewport to that section."""
        self.focus = key
        self.settled = True
        self.velocity = 0.0
        self.hover = None
        self._left_at = None

    def begin_browse(self):
        """Expand to the tall browse window while scrolling."""
        self.settled = False
        self._left_at = None

    def group_rows(self, rows):
        current = self.focused(rows)
        if current is None:
            return []
        return [row for row in rows if row['group'] == current['group']]

    def focused(self, rows):
        active = next((r['id'] for r in rows if not r['completed']), None)
        if active and active != self.active:
            self.focus = active
            self.settled = True
            self.velocity = 0.0
            self._left_at = None
        self.active = active
        return next((r for r in rows if r['id'] == self.focus), rows[-1] if rows else None)

    def step(self, rows, delta):
        current = self.focused(rows)
        if current is None:
            return
        group = self.group_rows(rows)
        index = next(i for i, r in enumerate(group) if r['id'] == current['id'])
        self.select(group[max(0, min(len(group) - 1, index + delta))]['id'])

    def scroll_by(self, wheel_y, max_scroll):
        """Apply wheel impulse; positive wheel_y scrolls content up (show earlier)."""
        self.begin_browse()
        self.velocity -= float(wheel_y) * WHEEL_IMPULSE
        self._clamp(max_scroll)

    def tick(self, max_scroll, dt=1 / 60):
        """Advance momentum and return True while still moving."""
        if abs(self.velocity) < SCROLL_STOP and self.settled:
            self.velocity = 0.0
            return False
        if abs(self.velocity) >= SCROLL_STOP:
            self.begin_browse()
            self.scroll += self.velocity * max(0.008, min(0.05, dt)) * 60
            self.velocity *= SCROLL_FRICTION
            self._clamp(max_scroll)
            if abs(self.velocity) < SCROLL_STOP:
                self.velocity = 0.0
            return True
        return False

    def note_pointer(self, inside):
        """Track pointer enter/leave for delayed collapse."""
        if inside:
            self._left_at = None
            return
        if self.settled:
            self._left_at = None
            return
        if self._left_at is None:
            self._left_at = time.monotonic()

    def tick_collapse(self, timeout=LEAVE_COLLAPSE):
        """After leaving the viewport, collapse back to the focused quest."""
        if self.settled or self._left_at is None:
            return False
        if time.monotonic() - self._left_at < timeout:
            return False
        self.settled = True
        self.velocity = 0.0
        self.hover = None
        self._left_at = None
        return True

    def _clamp(self, max_scroll):
        limit = max(0.0, float(max_scroll))
        if self.scroll < 0:
            self.scroll = 0.0
            self.velocity = 0.0
        elif self.scroll > limit:
            self.scroll = limit
            self.velocity = 0.0

    def snap_to_focus(self, section_tops, section_ids):
        """Align scroll so the focused quest sits at the top of the body."""
        if not section_tops or self.focus is None:
            return
        try:
            index = section_ids.index(self.focus)
        except ValueError:
            return
        self.scroll = float(section_tops[index])
