# Scenario, Tutorial, and Narrative System Assessment

## Recommendation

Add a data-driven `ScenarioDirector` that runs beside the simulation and temporarily owns only the actors named by an active script. Do not embed tutorial sequences directly into `Game._update_villagers()` or `WildlifeManager.tick()`; those systems already contain substantial autonomous behaviour and would overwrite scripted targets.

The first useful version should support:

- ordered and conditional objectives;
- modal or non-modal dialogue popups;
- scripted villager and animal movement;
- actors that follow or remain within a configurable number of cells of the player;
- waits for player actions, locations, dates, inventory, buildings, and elapsed time;
- save/load of the scenario id, active step, variables, controlled actors, and completed objectives.

## Existing foundations

- `game.py::_update_simulation()` is the central deterministic update point. The director should tick immediately before normal villager and wildlife updates so it can establish actor-control claims for that tick.
- Villagers already have targets, movement cooldowns, and pathfinding through `Game._step_villager_toward()` and `World.find_path()`.
- Wildlife already has path movement helpers, but they are internal to `WildlifeManager`. A small public scripted-movement API is needed rather than manipulating private path caches from scenario code.
- The existing dialog classes establish input blocking, drawing, dragging, and keyboard conventions. Narrative dialogue should be its own lightweight dialog because current inspection dialogs are tied to live entities.
- `save_load.py` already serializes the entire world and actor identity. A new top-level `scenario` payload can preserve director state without changing individual actor save schemas initially.
- `Game._open_subtile_test()` demonstrates launching a prepared scenario-like map through production systems, but it has no timeline, conditions, or persistence.

## Proposed modules

### `scenario.py`

Own the runtime state:

- `ScenarioDirector`
- `ScenarioState`
- `ScenarioStep`
- trigger evaluation
- action dispatch
- actor-control claims
- serialization and restoration

The director should expose `tick(game)`, `handle_game_event(event)`, `to_dict()`, and `load_dict(data)`.

### `scenario_dialog.py`

A dedicated popup with speaker, portrait/icon, body text, and Continue/choice buttons. Each page should declare whether simulation and player input continue. Dialogue completion returns a stable choice key to the director.

### `objects_data/scenarios/*.json`

Store authored scripts outside Python. Reference actors by stable scenario aliases which resolve to saved numeric ids when the scenario starts.

Example shape:

```json
{
  "key": "tutorial_slice",
  "start": "welcome",
  "steps": {
    "welcome": {
      "on_enter": [{"action": "dialogue", "speaker": "Mara", "text": "Follow me."}],
      "then": "walk_to_storehouse"
    },
    "walk_to_storehouse": {
      "on_enter": [{"action": "move_actor", "actor": "guide", "target": [24, 18]}],
      "complete_when": {"actor_within": {"actor": "guide", "target": [24, 18], "distance": 1}},
      "then": "stay_close"
    },
    "stay_close": {
      "on_enter": [{"action": "follow_player", "actor": "guide", "max_distance": 4}],
      "complete_when": {"player_has": {"resource": "berries", "amount": 1}}
    }
  }
}
```

## Scripted actor control

Use an explicit ownership table such as `controlled_actors[("villager", id)] = command`. Normal AI must skip decision-making for a controlled actor, while wellbeing, animation, interpolation, collision, and cooldown processing continue.

Movement commands should include:

- `move_to`: path to a fixed cell and report arrived/blocked;
- `follow_player`: move only when distance exceeds `max_distance`, aiming for a reachable cell inside the radius rather than the player's occupied cell;
- `keep_near_player`: teleport only as an optional recovery policy after a configurable blocked timeout;
- `release_actor`: return the actor cleanly to autonomous AI and clear stale targets/path caches.

For animals, add public methods on `WildlifeManager` such as `script_step_toward(animal_id, target, world)` and `clear_script_path(animal_id)`. Packs and colonies need an explicit policy: control one member, the leader, or the whole group. The first version should support only individual animals and declare pack control unsupported.

## Trigger and action vocabulary

Start with a deliberately small vocabulary.

Triggers:

- player enters/leaves an area;
- player is within a distance of an actor or cell;
- actor arrives or becomes blocked;
- inventory reaches an amount;
- building exists/completes;
- resource is harvested;
- date/season reached;
- dialogue dismissed or choice selected;
- elapsed simulation ticks or real-time seconds.

Actions:

- show dialogue or objective text;
- move/follow/release an actor;
- focus camera or highlight a cell/entity;
- set/clear a map marker;
- give/take a resource;
- change a scenario variable;
- branch, advance, complete, or fail the scenario.

Prefer semantic game events (`resource_harvested`, `building_completed`) over repeatedly scanning all state. Initially, condition polling is acceptable for simple inventory/location checks; add a small event bus as authored scenarios expand.

## Integration changes

1. Construct `ScenarioDirector` and `ScenarioDialog` in `Game.__init__()`.
2. Tick the director in both `_update_simulation()` and `_advance_sim_ticks()` so fast-forward cannot bypass scripts.
3. Skip autonomous decision branches for director-controlled villagers and animals, while still applying survival and animation updates.
4. Route modal input before ordinary world input, following the existing file/dialog pattern.
5. Draw dialogue after the world and regular panels so it remains visible.
6. Add the director payload in `save_load.py`; missing data means no active scenario for backward compatibility.
7. Add a scenario selector/start command to Developer Tools after the runtime is stable.

## Important edge cases

- Saving during dialogue must restore the same page without replaying `on_enter` rewards.
- Actor ids can disappear through death or editor deletion; every step needs an `on_missing_actor` policy.
- Player-controlled god/villager mode must not seize a scenario-owned villager without an explicit override.
- Pausing should pause simulation-time waits. Modal dialogue may pause automatically; non-modal dialogue should not.
- Fast-forward must either execute each significant scenario transition or cap skipping at the next scheduled trigger.
- Dynamic following must avoid oscillating at the radius boundary; use separate start/stop thresholds, for example move at distance 6 and stop at 4.
- Scripts should never call private AI helpers directly from JSON actions.

## Suggested delivery order

1. Director state machine, JSON loading, dialogue, location/inventory conditions, save/load.
2. Scripted villager `move_to`, `follow_player`, control release, and blocked recovery.
3. Semantic gameplay events and objective/marker UI.
4. Individual animal movement, followed later by explicit pack/colony choreography.
5. Developer Tools scenario authoring and validation.

The smallest production-worthy vertical slice is: load `tutorial_slice.json`, show one dialogue page, guide one villager to a fixed location, keep that villager within four cells of the player, wait for one berry harvest, show completion dialogue, then release the villager. This exercises the difficult ownership, persistence, movement, and trigger boundaries without prematurely building a full quest editor.
