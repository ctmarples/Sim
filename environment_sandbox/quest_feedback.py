"""Real-time quest pacing and queued management discovery notifications."""
from copy import deepcopy
import time

COMPLETION_PAUSE = 2.0
ALERT_DURATION = 4.0


def emit(game, trigger):
    sounds = getattr(game, 'sounds', None)
    if sounds is not None:
        sounds.emit(trigger)


def queue_alert(game, label, icon, target):
    queue = getattr(game, '_tutorial_alert_queue', None)
    if queue is None:
        queue = game._tutorial_alert_queue = []
    queue.append((label, icon, target))
    update_alerts(game)


def update_alerts(game):
    now = time.monotonic()
    if getattr(game, '_tutorial_unlock_popup', None) is not None:
        if now < getattr(game, '_tutorial_alert_until', float('inf')):
            return
        game._tutorial_unlock_popup = None
    queue = getattr(game, '_tutorial_alert_queue', [])
    if queue:
        game._tutorial_unlock_popup = queue.pop(0)
        game._tutorial_alert_until = now + ALERT_DURATION
        emit(game, 'management.item_added')


class QuestFeedback:
    def __init__(self):
        self.previous = None
        self.hold_rows = None
        self.until = 0.0
        self.announced = None

    @property
    def holding(self):
        return self.hold_rows is not None and time.monotonic() < self.until

    def rows(self, actual):
        return deepcopy(self.hold_rows) if self.holding else actual

    def sync(self, game, actual):
        if self.holding:
            return
        self.hold_rows = None
        current = next((q for q in actual if not q['completed']), None)
        old = next((q for q in (self.previous or []) if not q['completed']), None)
        if old is not None:
            updated = next((q for q in actual if q['id'] == old['id']), None)
            if updated is not None:
                before = {i['id']: i['completed'] for i in old['objectives']}
                newly_done = [i for i in updated['objectives'] if i['completed'] and not before.get(i['id'], False)]
                if newly_done:
                    for _ in newly_done:
                        emit(game, 'quest.objective_complete')
                    held = deepcopy(updated)
                    held['completed'] = False
                    self.hold_rows = [deepcopy(q) for q in actual if q['completed'] and q['id'] != old['id']] + [held]
                    self.until = time.monotonic() + COMPLETION_PAUSE
                    self.previous = deepcopy(actual)
                    return
        self.previous = deepcopy(actual)
        if current is not None and current['id'] != self.announced:
            emit(game, 'quest.new')
            self.announced = current['id']
