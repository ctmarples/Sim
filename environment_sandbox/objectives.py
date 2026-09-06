"""Objective text and chronological milestones for the authored tutorial.

The scenario's persisted step is the source of truth, including older saves.
Dialogue-only milestones complete the preceding task without unlocking the next.
"""
from field_handbook import HANDBOOK_STEPS
from quest_progress import (
    FIELD_OBJECTIVES, OBJECTIVE_CHILDREN, OBJECTIVE_REQUIRES, active_objectives, check_key,
)

HANDBOOK_EXPLANATIONS = (
    "Inspect four distinct species near the field and uncover every square within 10 squares of its edge to check which beehives reach it.",
    "Find a growing crop square to inspect crop health, then inspect a different square with the highest weed cover. Each observation is recorded separately.",
    "Check for footprints in the field. Let’s see how far the field is from the village buildings. The Farmhouse must be close by to store all the produce.",
    "Let’s check the soil. Darker colour means more fertile soil. Compare the darkest and lightest squares, then inspect moisture on another square. Inspect the field’s slope — seems flat to me — and compare it with a nearby hill.",
    "In Old Field Handbook, look below the table at the example crop progression through Spring, Summer, Autumn and Winter. Ah ok, so I’ll add the crop into the Rotation planner. Open Rotation and add Wheat, the current crop.",
)

# (scenario steps, optional objective headline, explanation)
MILESTONES = (
    ('hunger_dialog', None, ''),
    ('open_inventory', 'Open your inventory', 'Press I to open your inventory and see what you have in your bag.'),
    ('eat_berries', 'Eat your berries', 'Right-click the berries in your inventory to eat them.'),
    ('last_berry_dialog', None, ''),
    ('find_food', 'Find more food', 'Explore the nearby clearing and look for a berry bush.'),
    ('found_berries_dialog', None, ''),
    ('pick_berries', 'Pick some berries', 'Stand beside a berry bush and press Enter to pick berries.'),
    ('traveller_approaches traveller_accuses traveller_reply join_berry_traveller', None, ''),
    ('find_village', 'Find the village', 'Look for the village to the north west. Explore the path ahead.'),
    ('deer_dialog', None, ''),
    ('follow_deer', 'Follow the deer', 'Follow the deer through the landscape until you discover the village farmhouse.'),
    ('deer_flee find_tent', 'Find a tent', 'Explore the village and look for a tent where you might find shelter.'),
    ('rhea_approaches shelter_greeting shelter_request shelter_offer join_rhea', None, ''),
    ('fix_tent', 'Repair the tent', 'Find wood in the forest to the north, then bring it to the collapsed tent and repair its support.'),
    ('rhea_congrats_approaches tent_repaired_dialog', None, ''),
    ('go_to_sleep sleeping', 'Get some sleep', 'Press Enter at your repaired tent to go inside and sleep until morning.'),
    ('talk_to_rhea', 'Talk to Rhea', 'Approach Rhea in the morning and press Enter to speak with her.'),
    ('morning_greeting morning_thanks morning_invitation morning_accept farm_history weed_request', None, ''),
    ('walk_to_field', 'Follow Rhea to the field', 'Walk with Rhea to the village field and inspect the weeds.'),
    ('field_reaction hoe_gift give_hoe', None, ''),
    ('equip_hoe', 'Equip your hoe', 'Open your inventory and equip the hoe Rhea gave you.'),
    ('clear_weeds', 'Clear the field', 'Use your hoe to clear all weeds from the village field.'),
    ('rhea_weeds_approaches weeds_complete_dialog farm_question rhea_abundance ask_villagers_intro', None, ''),
    ('ask_villagers gwen_intro gwen_player gwen_history joss_intro joss_help joss_doubt joss_learn joss_books finish_interview', 'Ask about the old farm', 'Speak with both Gwen and Joss about the old farm. Approach each villager and press Enter to hear what they remember.'),
    ('enter_farmhouse', 'Find the old book', 'Enter the Farmhouse and look for the old field handbook mentioned by Joss.'),
    ('open_book', 'Open the old handbook', 'Right-click the old book in your inventory. Its pages become the Field Planner under the Farmhouse in Management.'),
)


def scenario_objectives(state):
    """Return only completed or unlocked tasks, in story chronology."""
    if state.key != 'tutorial_slice':
        return []
    stage = next((i for i, (steps, _, _) in enumerate(MILESTONES)
                  if state.step in steps.split()), None)
    if state.step == 'field_handbook' or (state.completed and state.field_planner_unlocked):
        stage = len(MILESTONES)
    if stage is None and (state.step == 'release_rhea' or state.completed):
        stage = next(i for i, (steps, _, _) in enumerate(MILESTONES) if 'rhea_weeds_approaches' in steps.split())
    if stage is None:
        return []
    rows = []
    for index, (steps, headline, explanation) in enumerate(MILESTONES):
        if index > stage:
            break
        if headline:
            rows.append(dict(id=steps.split()[0], headline=headline,
                             explanation=explanation, completed=index < stage))
    if stage == len(MILESTONES):
        completed = max(0, min(5, state.handbook_completed))
        for index, (title, narrative, objective) in enumerate(HANDBOOK_STEPS):
            if index > completed or (index == completed and state.completed):
                break
            explanation = HANDBOOK_EXPLANATIONS[index]
            rows.append(dict(id=f'handbook_{index + 1}', headline=title.split('. ', 1)[-1],
                             explanation=explanation, completed=index < completed))
    from quest_navigation import GROUP_TITLES
    land_ids = {steps.split()[0] for steps, headline, _ in MILESTONES[
        next(i for i, (steps, _, _) in enumerate(MILESTONES) if steps == 'talk_to_rhea'):]
        if headline}
    for quest in rows:
        quest['group'] = 'land' if quest['id'] in land_ids or quest['id'].startswith('handbook_') else 'shelter'
        quest['group_title'] = GROUP_TITLES[quest['group']]
        quest["objectives"] = quest_items(state, quest)
        if quest["id"] == "handbook_1" and state.quest_no_hives:
            quest["note"] = "Hmm, doesn’t look like there are any bees nearby."
    return rows


OBJECTIVE_TIPS = {
    'species': 'Tip: inspect species with a cursor click.',
    'species_layer': 'Tip: open Layers (top right) and choose Species diversity.',
    'hive': 'Tip: uncover all shroud within 10 squares of the field.',
    'pollination_layer': 'Tip: open Layers and choose Pollination.',
    'health': 'Tip: click a crop square.',
    'weeds': 'Tip: click a different square with the highest weed cover.',
    'traffic': 'Tip: check four different field squares for footprints.',
    'disturbance_layer': 'Tip: open Layers and choose Disturbance.',
    'settlement': 'Tip: click a nearby village building.',
    'fertility_high': 'Tip: darker soil is more fertile — inspect the darkest square.',
    'fertility_low': 'Tip: inspect the lightest square.',
    'fertility_layer': 'Tip: open Layers and choose Soil fertility.',
    'moisture': 'Tip: inspect moisture on another square.',
    'moisture_layer': 'Tip: open Layers and choose Soil moisture.',
    'slope': 'Tip: inspect the field’s slope.',
    'erosion_layer': 'Tip: open Layers and choose Soil erosion.',
    'hill': 'Tip: a hill’s cast shadow shows its slope.',
    'read': 'Tip: scroll below the handbook table to see all four seasons.',
    'rotation': 'Tip: open the Rotation tab.',
    'wheat': 'Tip: add Wheat to the Rotation planner.',
}


def quest_items(state, quest):
    """Backfill checked items for every historical quest, including old saves."""
    key = quest["id"]
    if key.startswith("handbook_"):
        stage = int(key.split("_")[1]) - 1
        source = FIELD_OBJECTIVES[stage] if quest["completed"] else active_objectives(state, stage)
        visible = {item_id for item_id, _ in source}
        items = []
        by_id = {}
        for item_id, label in source:
            if item_id in OBJECTIVE_REQUIRES:
                continue
            done = quest["completed"] or check_key(stage, item_id) in state.quest_checks
            if item_id == "species":
                count = 4 if quest["completed"] else min(4, len(state.inspected_species))
                label += f" ({count}/4)"
            if item_id == 'traffic':
                count = 4 if quest['completed'] else min(4, len(state.quest_cells.get('traffic', [])))
                label += f' ({count}/4)'
            if item_id == "hive" and state.quest_no_hives:
                label = "Check whether any beehives reach the field"
            row = dict(id=item_id, label=label, completed=done,
                       tip=OBJECTIVE_TIPS.get(item_id, ''), children=[])
            by_id[item_id] = row
            items.append(row)
        for parent_id, child_id in OBJECTIVE_CHILDREN.items():
            if child_id not in visible or parent_id not in by_id:
                continue
            child_label = dict(FIELD_OBJECTIVES[stage]).get(child_id, child_id)
            done = quest["completed"] or check_key(stage, child_id) in state.quest_checks
            by_id[parent_id]['children'].append(dict(
                id=child_id, label=child_label, completed=done,
                tip=OBJECTIVE_TIPS.get(child_id, ''),
            ))
        return items
    if key == "ask_villagers":
        return [dict(id="gwen", label="Speak with Gwen", completed=quest["completed"] or state.gwen_asked),
                dict(id="joss", label="Speak with Joss", completed=quest["completed"] or state.joss_asked)]
    return [dict(id=key, label=quest["headline"], completed=quest["completed"])]
