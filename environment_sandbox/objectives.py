"""Objective text and chronological milestones for the authored tutorial.

The scenario's persisted step is the source of truth, including older saves.
Dialogue-only milestones complete the preceding task without unlocking the next.
"""
from field_handbook import HANDBOOK_STEPS

HANDBOOK_EXPLANATIONS = (
    "Walk around the field’s assessment area and count the different plant and animal species. "
    "Look for nearby beehives and estimate their distance from the field. "
    "Record your observations in Old Field Handbook to reveal Surroundings, Biodiversity and Pollination.",
    "Inspect the crop’s health and weed cover. Use your species count to understand natural pest control "
    "and the crop-health cap. Remember how clearing the weeds reduced competition with the crop. "
    "Record your observations in Old Field Handbook to reveal Crop Condition.",
    "Walk across the field and look for footprints or compacted ground. Look back towards the village "
    "and assess how close the buildings are. Record your observations in Old Field Handbook to reveal "
    "Disturbance in Field Condition and unlock its overlay.",
    "Explore the field to compare its most fertile and poorest areas. Observe soil moisture and inspect "
    "the slope: flatter ground has less erosion risk. Record your observations in Old Field Handbook "
    "to reveal Soil and unlock the Soil Fertility, Soil Moisture and Erosion Risk overlays.",
    "Read ‘Think past this harvest’ in Old Field Handbook, then select ‘Record current crop: Wheat’ "
    "to reveal Rotation. Consider a crop that could restore the soil for the next harvest.",
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
    return rows
