"""Field quest progress from concrete inspections; no UI acknowledgement shortcuts."""
from resource_balance import POLLINATOR_BASE_RADIUS, POLLINATOR_RADIUS_PER_LEVEL

FIELD_ASSESSMENT_RADIUS = 16

# (id, label) — gated objectives appear only after OBJECTIVE_REQUIRES is checked.
FIELD_OBJECTIVES = (
    (('species', 'Inspect 4 different wild plant or wildlife species near the field'),
     ('species_layer', 'Enable Species diversity from the Layers panel'),
     ('hive', 'Check whether any beehives reach the field'),
     ('pollination_layer', 'Enable Pollination from the Layers panel')),
    (('health', 'Inspect the crop’s health'), ('weeds', 'Inspect weed cover')),
    (('traffic', 'Check 4 squares for footprints in the field'),
     ('disturbance_layer', 'Enable Disturbance from the Layers panel'),
     ('settlement', 'Inspect a nearby village building')),
    (('fertility_high', 'Inspect the most fertile ground'),
     ('fertility_low', 'Inspect the least fertile ground'),
     ('fertility_layer', 'Enable Soil fertility from the Layers panel'),
     ('moisture', 'Inspect soil moisture on another square'),
     ('moisture_layer', 'Enable Soil moisture from the Layers panel'),
     ('slope', 'Inspect the slope of the field'),
     ('erosion_layer', 'Enable Soil erosion from the Layers panel'),
     ('hill', 'Inspect a nearby hill')),
    (('read', 'View all four seasonal crop examples in the handbook'),
     ('rotation', 'Open the Rotation tab'), ('wheat', 'Add Wheat to the Rotation planner')),
)

# Layer enable objectives appear only after their prerequisite check.
OBJECTIVE_REQUIRES = {
    'species_layer': 'species',
    'pollination_layer': 'hive',
    'disturbance_layer': 'traffic',
    'fertility_layer': 'fertility_low',
    'moisture_layer': 'moisture',
    'erosion_layer': 'slope',
}

# Parent main objective → nested enable-layer child.
OBJECTIVE_CHILDREN = {parent: child for child, parent in OBJECTIVE_REQUIRES.items()}

# Overlay unlock alerts keyed by the prerequisite quest check id.
LAYER_UNLOCK_ALERTS = {
    'species': ('BIODIVERSITY', 'Species diversity layer unlocked', 'layer:BIODIVERSITY'),
    'hive': ('POLLINATION', 'Pollination layer unlocked', 'layer:POLLINATION'),
    'traffic': ('DISTURBANCE', 'Disturbance layer unlocked', 'layer:DISTURBANCE'),
    'fertility_low': ('FERTILITY', 'Soil fertility layer unlocked', 'layer:FERTILITY'),
    'moisture': ('SOIL_MOISTURE', 'Soil moisture layer unlocked', 'layer:SOIL_MOISTURE'),
    'slope': ('EROSION', 'Soil erosion layer unlocked', 'layer:EROSION'),
}

# Overlay mode name → (handbook stage index, prerequisite check id).
LAYER_UNLOCKS = {
    'BIODIVERSITY': (0, 'species'),
    'POLLINATION': (0, 'hive'),
    'DISTURBANCE': (2, 'traffic'),
    'FERTILITY': (3, 'fertility_low'),
    'SOIL_MOISTURE': (3, 'moisture'),
    'EROSION': (3, 'slope'),
    'FIELD_YIELD': (5, None),
}

# Enabling a layer marks this quest check when on the matching handbook stage.
LAYER_QUEST_MARKS = {
    'BIODIVERSITY': (0, 'species_layer'),
    'POLLINATION': (0, 'pollination_layer'),
    'DISTURBANCE': (2, 'disturbance_layer'),
    'FERTILITY': (3, 'fertility_layer'),
    'SOIL_MOISTURE': (3, 'moisture_layer'),
    'EROSION': (3, 'erosion_layer'),
}


FORAGE_SPECIES_GOAL = 6
FORAGE_FOOD_GOAL = 15
FORAGE_HERB_GOAL = 10
HERB_FORAGE_KEYS = frozenset({'sage', 'mint', 'hemp', 'flax'})
MEADOW_CELL = (45, 8)


def forage_ready(state):
    return (len(state.foraged_species) >= FORAGE_SPECIES_GOAL
            and state.forage_food >= FORAGE_FOOD_GOAL
            and state.forage_herbs >= FORAGE_HERB_GOAL)


def _known_forage_plants(state):
    known = {key for key in state.forage_known if key.startswith('plant:')}
    if known:
        return known
    known = {key for key in state.inspected_species if key.startswith('plant:')}
    known.update('plant:' + key.split(':', 1)[1] for key in state.discovered_flora
                 if key.startswith(('wild:', 'plant:')))
    return known


def begin_forage(state):
    if state.forage_known:
        return
    state.forage_known = sorted(_known_forage_plants(state))


def note_forage_species(game, species):
    state = game.scenario.state
    if getattr(state, 'key', None) != 'tutorial_slice' or state.step != 'forage_meadow':
        return
    if not species.startswith('plant:') or species in state.foraged_species:
        return
    if species in _known_forage_plants(state):
        return
    state.foraged_species.append(species)


def note_forage_collect(game, inventory, key, amount):
    state = game.scenario.state
    if getattr(state, 'key', None) != 'tutorial_slice' or state.step != 'forage_meadow':
        return
    player = getattr(game, 'player', None)
    if player is None or inventory is not player.inventory or int(amount) <= 0:
        return
    from resource_balance import VILLAGER_FOOD_KEYS
    if key in VILLAGER_FOOD_KEYS:
        state.forage_food += int(amount)
    elif key in HERB_FORAGE_KEYS:
        state.forage_herbs += int(amount)


def check_key(stage, key):
    return f'handbook_{stage + 1}:{key}'


def mark(state, key):
    value = check_key(state.handbook_completed, key)
    if value not in state.quest_checks:
        state.quest_checks.append(value)
        return True
    return False


def announce_layer_unlock(game, prerequisite_key):
    """Queue the flora-style unlock popup and start Layers pulse cues."""
    alert = LAYER_UNLOCK_ALERTS.get(prerequisite_key)
    if alert is None:
        return
    mode_name, label, target = alert
    announce_key = f'layer:{mode_name}'
    announced = game.scenario.state.announced_unlocks
    if announce_key in announced:
        return
    announced.append(announce_key)
    from quest_feedback import queue_alert
    queue_alert(game, label, 'field', target)
    game._layer_pulse_mode = mode_name
    game._layer_pulse_button = True


def active_objectives(state, stage=None):
    """Objectives currently visible for a handbook stage."""
    stage = state.handbook_completed if stage is None else stage
    if stage < 0 or stage >= len(FIELD_OBJECTIVES):
        return ()
    rows = []
    for key, label in FIELD_OBJECTIVES[stage]:
        required = OBJECTIVE_REQUIRES.get(key)
        if required and check_key(stage, required) not in state.quest_checks:
            continue
        rows.append((key, label))
    return tuple(rows)


def ready(state):
    stage = state.handbook_completed
    return stage < 5 and all(check_key(stage, key) in state.quest_checks
                             for key, _ in active_objectives(state, stage))


def overlay_unlocked(state, mode_name: str) -> bool:
    """Whether a Layers-panel overlay is available in the tutorial."""
    if getattr(state, 'key', None) != 'tutorial_slice':
        return True
    if state.completed or state.handbook_completed >= 5:
        return True
    rule = LAYER_UNLOCKS.get(mode_name)
    if rule is None:
        return True
    stage, prerequisite = rule
    if state.handbook_completed > stage:
        return True
    if state.handbook_completed < stage:
        return False
    if prerequisite is None:
        return state.handbook_completed >= stage
    return check_key(stage, prerequisite) in state.quest_checks


def mark_overlay_enabled(state, mode_name: str) -> None:
    """Complete the matching 'enable layer' objective when the player selects it."""
    if getattr(state, 'key', None) != 'tutorial_slice' or state.step != 'field_handbook':
        return
    rule = LAYER_QUEST_MARKS.get(mode_name)
    if rule is None:
        return
    stage, key = rule
    if state.handbook_completed != stage:
        return
    required = OBJECTIVE_REQUIRES.get(key)
    if required and check_key(stage, required) not in state.quest_checks:
        return
    mark(state, key)


def near_field(game, x, y):
    field = game.scenario._village_field(game)
    if field is None:
        return False
    radius = FIELD_ASSESSMENT_RADIUS
    return any(max(abs(x - fx), abs(y - fy)) <= radius for fx, fy in field.plot_cells())


def overlapping_hives(game):
    field = game.scenario._village_field(game)
    if field is None:
        return []
    return [colony for colony in game.wildlife.colonies
            if colony.kind.name == 'BEE' and colony.level >= 1
            and any(max(abs(x-colony.x), abs(y-colony.y)) <=
                    max(1, POLLINATOR_BASE_RADIUS + (colony.level-1)*POLLINATOR_RADIUS_PER_LEVEL)
                    for x, y in field.plot_cells())]


def inspect_species(game, x, y, species):
    state = game.scenario.state
    if state.key == 'tutorial_slice' and (x, y) in game.discovered_cells:
        flora_key = species.replace('plant:', 'wild:', 1) if species.startswith('plant:') else species if species.startswith('tree:') else None
        if flora_key and flora_key not in game.scenario.tutorial_management_flora():
            state.discovered_flora.append(flora_key)
            game.scenario._sync_management_unlocks(game)
    note_forage_species(game, species)
    if getattr(game.scenario, 'quest_feedback', None) and game.scenario.quest_feedback.holding:
        return
    if (state.step != 'field_handbook' or state.handbook_completed != 0
            or not near_field(game, x, y) or (x, y) not in game.discovered_cells):
        return
    if species not in state.inspected_species:
        state.inspected_species.append(species)
    if len(state.inspected_species) >= 4:
        if mark(state, 'species'):
            announce_layer_unlock(game, 'species')


def inspect_hive(game, colony):
    if game.scenario.quest_feedback.holding:
        return
    state = game.scenario.state
    if state.step == 'field_handbook' and state.handbook_completed == 0:
        inspect_species(game, colony.x, colony.y, 'animal:BEE')


def check_shroud(game):
    state = game.scenario.state
    if state.quest_shroud_checked:
        return
    field = game.scenario._village_field(game)
    if field is None:
        return
    cells = list(field.plot_cells())
    x0, x1 = min(x for x,y in cells), max(x for x,y in cells)
    y0, y1 = min(y for x,y in cells), max(y for x,y in cells)
    area = {(x,y) for y in range(max(0,y0-10), min(game.world.rows,y1+11))
            for x in range(max(0,x0-10), min(game.world.cols,x1+11))}
    if area.issubset(game.discovered_cells):
        state.quest_no_hives = not bool(overlapping_hives(game))
        state.quest_shroud_checked = True
        if mark(state, 'hive'):
            announce_layer_unlock(game, 'hive')


def local_slope(world, x, y):
    world.ensure_height_corners()
    heights = [world.height_corners[cy][cx] for cy in (y,y+1) for cx in (x,x+1)]
    return max(heights) - min(heights)


def record_square(state, key, x, y):
    cells = state.quest_cells.setdefault(key, [])
    if [x,y] not in cells:
        cells.append([x,y])
    return len(cells)


def inspect_field(game, x, y):
    state = game.scenario.state
    if game.scenario.quest_feedback.holding:
        return None
    if state.step != 'field_handbook' or (x,y) not in game.discovered_cells:
        return None
    stage = state.handbook_completed
    field = game.scenario._village_field(game)
    if field is None:
        return None
    cells = list(field.plot_cells())
    building = game._building_at(x,y)
    if stage == 2 and building is not None and building.kind.name != 'FIELD' and near_field(game,x,y):
        mark(state,'settlement')
        distance = min(max(abs(x-fx),abs(y-fy)) for fx,fy in cells)
        return ('Nearby settlement', ["Let’s see how far the field is from the village buildings.",
            f'Distance to field: {distance} squares',
            'The Farmhouse must be close by to store all the produce.'])
    if stage == 3 and building is None and not field.contains_plot(x,y) and near_field(game,x,y):
        slope = local_slope(game.world,x,y)
        field_height = min(game.world.height_at_cell(fx,fy) for fx,fy in cells)
        if slope > .001 and game.world.height_at_cell(x,y) > field_height + .001:
            mark(state,'hill')
            return ('Nearby hill', [f'Local slope: {slope:.2f}', 'The cast shadow makes the slope visible.'])
    if not field.contains_plot(x,y) or stage not in (1,2,3):
        return None
    cell = game.world.get_cell(x,y)
    status = game._field_env_status(field)
    if stage == 1:
        used = state.quest_cells.setdefault('crop', [])
        if [x,y] not in used:
            if 'handbook_2:health' not in state.quest_checks and getattr(cell,'crop_kind',None):
                mark(state,'health'); used.append([x,y])
            elif 'handbook_2:weeds' not in state.quest_checks:
                maximum = max(game.world.get_cell(fx,fy).weeds for fx,fy in cells)
                if cell.weeds >= maximum - .001:
                    mark(state,'weeds'); used.append([x,y])
        return ('Crop square', [f'Crop: {getattr(cell,"crop_kind",None) or "None"}',
            f'Crop health: {status["health"]:.0%}', f'Weeds here: {cell.weeds:.0%}',
            'Inspect crop and weed properties on different squares.'])
    if stage == 2:
        count = record_square(state,'traffic',x,y)
        if count >= 4 and mark(state,'traffic'):
            announce_layer_unlock(game, 'traffic')
        traffic = game._path_traffic.get((x,y),0)
        return ('Footprints', [f'Checked {min(4,count)} / 4 different field squares',
            f'Foot traffic here: {traffic:.1f}', 'Check for footprints in the field.'])
    from soil import overlay_fertility
    fertility = overlay_fertility(cell)
    values = [overlay_fertility(game.world.get_cell(fx,fy)) for fx,fy in cells]
    used = state.quest_cells.setdefault('soil', [])
    candidates = [('fertility_high', fertility >= max(values)-.001),
                  ('fertility_low', fertility <= min(values)+.001),
                  ('moisture', True), ('slope', True)]
    if [x,y] not in used:
        for key, matches in candidates:
            if matches and check_key(3,key) not in state.quest_checks:
                if mark(state,key):
                    announce_layer_unlock(game, key)
                used.append([x,y]); break
    slope = local_slope(game.world,x,y)
    return ('Soil square', ["Let’s check the soil. Darker colour means more fertile soil.",
        f'Fertility here: {fertility:.2f} (field {min(values):.2f}–{max(values):.2f})',
        f'Moisture here: {game.env_maps.soil_moisture[y][x]:.0%}',
        f'Local slope: {slope:.2f}', 'Seems flat to me.' if slope < .01 else 'This square has a slope.',
        'Use a different square for each observation, then inspect a nearby hill.'])
