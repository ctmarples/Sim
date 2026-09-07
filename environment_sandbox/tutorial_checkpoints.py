"""Named tutorial_intro checkpoint catalog for the sidebar quick loader."""
from pathlib import Path

from save_load import saves_dir

# (file number, quest group, display name)
CHECKPOINTS = (
    (1, 'shelter', 'Hunger dialog'),
    (2, 'shelter', 'Find food'),
    (3, 'shelter', 'Follow deer'),
    (4, 'shelter', 'Find tent'),
    (5, 'shelter', 'Fix tent'),
    (6, 'shelter', 'Go to sleep'),
    (7, 'land', 'Talk to Rhea'),
    (8, 'land', 'Equip hoe'),
    (9, 'land', 'Clear weeds'),
    (10, 'land', 'Weeds complete dialog'),
    (11, 'land', 'Ask villagers'),
    (12, 'land', 'Ask Joss'),
    (13, 'land', 'Enter farmhouse'),
    (14, 'land', 'Open book'),
    (15, 'land', 'Beyond the fence'),
    (16, 'land', 'Watch the crop'),
    (17, 'land', 'Mind the traffic'),
    (18, 'land', 'Know the ground'),
    (19, 'land', 'Thinking past this harvest'),
    (20, 'land', 'Add Wheat to Rotation'),
    (21, 'land', 'Help Gwen forage'),
    (22, 'land', 'Wear the leather satchel'),
    (23, 'land', 'Forage for dinner'),
    (24, 'land', 'Identify the diversity hotspot'),
    (25, 'land', 'Inspect hotspot flora'),
    (26, 'land', 'Look for wildlife'),
    (27, 'knowledge', 'Return to Rhea'),
    (28, 'knowledge', 'Return for berry bushes'),
    (29, 'knowledge', 'Trade for berry seeds'),
    (30, 'knowledge', 'Create orchard field'),
    (31, 'knowledge', 'Plan orchard planting'),
    (32, 'knowledge', 'Plant orchard bushes'),
    (33, 'knowledge', 'New knowledge complete'),
)

GROUP_LABELS = {'shelter': 'Shelter', 'land': 'Land', 'knowledge': 'Knowledge'}


def checkpoint_path(number: int) -> Path:
    return saves_dir() / f'tutorial_intro_{number}.json'


def available(group: str | None = None) -> list[tuple[int, str, str]]:
    rows = [(number, quest_group, label) for number, quest_group, label in CHECKPOINTS
            if checkpoint_path(number).is_file()]
    if group is None:
        return rows
    return [row for row in rows if row[1] == group]
