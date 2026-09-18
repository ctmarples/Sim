# Engine-independent simulation refactor

## Scope and evidence

This is an incremental refactor of the existing Python/Pygame game, not an
engine migration. Gameplay, content formats, balance, random-number calls,
save formats and update order remain the specification. This audit combines
an AST import inventory with inspection of the main loop, clock, state models,
save/load, content reload, worker systems and compost implementation.

The starting tree has 122 non-test Python modules (about 103,000 lines), 86 test
modules, and a 30,085-line `game.py`. File size alone is not a reason to move code.

## Findings

| Responsibility | Current ownership / coupling |
| --- | --- |
| Startup and scene flow | `main.py` configures display-dependent settings and loads authored overrides before importing `Game`; `Game` creates state, Pygame surfaces, dialogs, sound, launch menus and tutorials. Even `Game(headless=True)` constructs presentation objects. |
| Simulation scheduling | `_step_sim`, `_advance_sim_ticks`, `_advance_day` in `game.py`. Frame playback, cooldown skipping, ecology batching, wildlife cadence, weather/history, season hooks, overlay refresh and autosave are interleaved. |
| Worker AI and logistics | `Game` owns claims, reservations, task choice, path caches, supply/delivery, job-specific actions and work completion. These share transient per-tick caches and work-generation invalidation. |
| Farming | `Game` owns field plans, seasonal transitions, crop health/history, player work, worker work, nursery/barn/compost integration. `farm_pipeline.py`, `field_yield.py`, `soil.py` and crop definitions already provide useful narrower boundaries. |
| Ecology and wildlife | `world.py`, `environment.py`, `wildlife.py`, `weather.py`, `wild_species.py` contain substantial independent logic; `Game` coordinates their cadence and cross-system mutations. |
| Presentation and interaction | Drawing, projection, camera input, picking, selection, animation, overlays and minimap remain mixed into `Game`, alongside separate Pygame UI modules. |
| Persistence | `save_load.py` serializes/restores a `Game`-shaped object, including restoration hooks and visual state. Its `Game` import is type-only, but its structural dependence is real. It also imports Pygame-dependent `height_sample.py`. |
| Content | CSV/JSON remain authoritative. `recipes.py`, `resources.py`, species/crop modules and developer tools load and reload registries. Several consumers bind registry values at import time. |

### Already useful boundaries

`calendar_system.py` owns calendar policy; `food_spoilage.py` operates on storage;
`field_yield.py`, `soil.py`, `landscape_fields.py`, `random_map_generator.py`,
`market_economy.py`, `sociopolitical.py` and `resource_tracker.py` have reusable
data/calculation responsibilities. `entities.py` and `world.py` do not directly
import Pygame, but still mix state with behaviour and presentation bookkeeping.
An isolated import of `entities` and `extensions` does not load Pygame.
Do not relocate these modules just to populate a new directory tree.

### Cycles and reverse dependencies

Import cycles must be distinguished from import-time failures:

- `game -> scenario -> game`: scenario defers its runtime import of
  `FEATURE_FOR_BUILDING`; the content mapping belongs below scene orchestration.
- `game -> save_load/sociopolitical_hooks/bug_log -> game`: reverse `Game`
  references are type-only, but functions still consume the broad Game API.
- `entities -> recipes -> society`, with deferred/type-only paths back to
  entities; `society <-> happiness`, and `happiness <-> sociopolitical_hooks`.
- `world <-> soil/environment/soil_texture`, `seasons <-> wild_species`, and
  `balance_config <-> resource_balance` use deferred and/or type-only imports.
  Preserve initialization order before attempting to break these cycles.
- `society` imports `StatusMod` from `status_effects_ui` inside a function;
  `sociopolitical_hooks` imports it at module scope. Simulation-facing status
  data should eventually live outside the Pygame UI module.
- Terrain settings and terrain rendering modules also reference one another;
  that is primarily a presentation/content boundary.

### Global/shared state

- `balance_config._active` is a process-wide balance singleton, consulted deep
  inside simulation helpers.
- `seasons.set_ticks_per_day` mutates global calendar timing; `settings` mixes
  display dimensions with simulation constants and storage specifications.
- Recipe/resource/crop/species registries, revision counters, traveller templates
  and caches are shared, with reload operations updating several consumers.
- Randomness is split across world/wildlife generators, Game-owned food/drop
  generators, local seeded generators and module-level `random`. Preserve both
  call order and ownership; do not consolidate RNGs in this pass.
- `Game` owns stock/claim/path/forage caches and `_work_gen`. Accounting callbacks
  record history and invalidate stock/work caches, so their timing matters.

### State ownership problems

- `Game` and wildlife both mutate world cells; workers mutate inventories,
  buildings, terrain, claims, cooldowns, experience and resource history.
- `extensions.refresh_parent_extension_links` writes parent flags and direct
  storage references on buildings. Preserve IDs and current object identities
  when extracting operations; replacing state collections would stale references.
- `entity_draw_xy` writes `world_x/world_y` and interpolation fields while drawing.
  Movement/recovery logic reads these coordinates. Making rendering read-only
  immediately would change behaviour; characterize this separately first.
- `height_sample.py` combines height data with `pygame.Surface` operations.
- `_advance_day` performs simulation mutations, status messages, selection repair,
  overlay updates and autosave. Moving the method intact into a Game mixin would
  relocate coupling rather than remove it.

## Target boundaries (introduced only when used)

```text
environment_sandbox/
    simulation/
        compost.py          # first extraction: operations on existing state
        # later: farming, ecology, wildlife, villagers, jobs, logistics
    state/                  # later: models, clock state, persistence schema
    presentation/           # later: rendering, projection, visual interpolation
    content/                # later: existing loaders and registry management
    game.py                 # progressively narrower orchestration/adapters
    ... existing modules retained during transition ...
```

The existing `ui.py` prevents adding a same-named `ui/` package without an import
migration. Group UI under `presentation/ui/` when it is actually moved. Avoid
empty packages, blanket import rewrites and a generic ECS/event framework.

Simulation functions take specific state objects/collections and explicit
parameters, never `Game`, `Surface`, screen coordinates or Pygame events.
Mutations stay on the existing models. Small synchronous callbacks are suitable
for immediate accounting/invalidation; introduce structured events only where an
actual presentation consumer needs them. No change to save ownership yet.

## Staged plan and acceptance gates

1. **Establish one real boundary: compost operations (this pass).** Extract linked
   heap lookup, spoilage migration, recipe checks/application, surplus food
   transfer and seasonal conversion. Keep thin Game adapters for existing callers.
   Inject existing accounting and surplus-policy callbacks. Verify original tests,
   side effects, operation order, ID linkage and execution without Pygame.
2. **Adjacent barn processing.** Extract sheaf migration/deposit and threshing
   input/output operations with the same state-and-callback pattern. Retain work
   scheduling in Game. Gate on inventory conservation, partial batches, capacity,
   player/worker parity and resource-history tests.
3. **Characterize and isolate clock state/scheduling.** Record active versus skipped
   tick traces, boundary ordering, frozen tutorial calendar, pending ecology and
   wildlife counters, save/resume and pause behaviour. Separate calendar state
   from notifications, then scheduling from rendering. Preserve speed × playback
   ticks per displayed frame: do not introduce a delta-time accumulator or alter
   the existing 32-tick ecology / 4-tick wildlife batching and flush behaviour.
4. **Jobs and logistics.** Establish explicit claims/reservations and state ownership;
   extract one delivery route before the full dispatcher. Gate on ordering,
   simultaneous workers, interrupted work, stuck recovery and cache invalidation.
5. **Farming/ecology/wildlife coordination.** Move crop lifecycle and sampling
   operations, using the existing independent modules. Keep RNG streams, sampling
   cadence, per-cell effects and balance lookups unchanged until covered by tests.
6. **Presentation/input separation.** Extract height data from rendering; establish
   tested ownership for world positions versus visual interpolation; translate
   input to specific operations and presentation notifications. Move status data
   out of UI before isolating society. Gate on camera, movement, picking, screenshots
   or manual visual checks, plus unchanged simulation with/without drawing.
7. **Reduce Game to orchestration.** Move remaining UI/render coordination and
   state persistence behind concrete interfaces. Remove temporary delegates only
   once callers have moved. Keep existing CSV/JSON/save compatibility tests.

The clock follows two bounded extractions because its current fan-out and timing
semantics make it less safe than storage transformations as a first example.

## First-phase behaviour contract

- Keep insertion order for buildings, recipe inputs/outputs and enabled foods.
- Keep readiness checks' existing spoilage-migration side effect.
- Keep first matching completed heap selection by `parent_building_id`.
- Keep capacity/reserve/target handling, partial batches and food-quality resets.
- Keep spoilage-first seasonal consumption and immediate consumed/produced callbacks.
- Preserve existing permissive recipe application and output capacity behaviour;
  callers remain responsible for deciding when to craft.
- No RNG calls, timing changes, format changes or new persisted state.

## Validation record

Before implementation: 55 existing tests passed using `unittest` across compost,
food spoilage, recipe progress, farm treatments, field rotation, calendar and
wildlife rebalance. The local virtual environment has Pygame but not pytest;
function-style tests will need explicit execution in addition to unittest tests.
Implementation results are recorded below after verification.

### Implemented boundary

`simulation/compost.py` now owns the seven compost operations previously embedded
in Game. It receives existing buildings/home storage and synchronous accounting
and surplus-policy callbacks. It owns no copies of state, visual objects, clock
or random generator. Game keeps seven narrow adapters so player crafting,
seasonal processing, farm supply and inspectors retain their existing entry
points. The old implementation bodies have been removed from Game.

The small `simulation/__init__.py` documents the dependency direction. No other
target directories have been created. Existing content, models, registry loading,
save schemas, game-loop scheduling and UI remain in place.

Validation results:

- 67 focused unittest cases pass: the 55 baseline cases plus 12 new regression
  cases in `test_simulation_compost.py`.
- A clean subprocess blocks imports of Pygame, Game and selected UI modules,
  then executes seasonal compost conversion successfully without consuming RNG.
- A temporary comparison harness executes the original seven methods captured
  before editing against the extracted implementation: 1,000 operations across
  200 deterministic fixtures match return values, complete storage/building
  state, intermediate accounting callback snapshots and module RNG state.
  The old implementation is not retained in the repository.
- All five function-style tests in `test_time_feel.py` pass, including measured
  Pygame clock timing and Game playback-slot integration.
- A dummy-video/audio Pygame smoke test passes startup, compost conversion,
  real history/cache invalidation, JSON save/load and linked heap identity,
  simulation steps, pause, one rendered/event-loop frame and clean quit.
  Saves and balance preferences are redirected to a temporary directory.
- `git diff --check` passes; no existing tests, content, balance values or saves
  were edited.

### Broader suite limitations

A full isolated `unittest` discovery run executed 540 cases: 501 passed, 20
failed assertions and 19 raised errors. This is **not a green full-suite result**.
Saves/preferences were redirected to a temporary directory to protect user data.

All 39 affected cases were then rerun as the same smaller suite in two fresh
processes: once with the complete original `game.py` source captured before the
edit, and once with the refactored module. Both runs produced exactly the same
22 failing test IDs/outcome types (13 failures, 9 errors); the other 17 passed
in both smaller runs. The original full 540-case order was not replayed, so the
17 order-sensitive outcomes have not been fully diagnosed.

- Reproduced issues include incomplete `Game.__new__` fixtures (missing clock,
  scenario or height state), outdated mock signatures, content/recipe expectations,
  apiary/worker expectations, map editor behaviour and temperature expectations.
- Ten plant-editor errors, four kitchen-capacity assertions, two nursery timing
  assertions and one renderer-colour assertion occur only in the full run and
  disappear in both smaller runs. They warrant a separate shared-registry/test
  isolation investigation.
- One of the 22 reproduced failures is an artifact of the test harness:
  `test_named_catalog_matches_files` cannot find tutorial files in the redirected
  empty saves directory. Running that test with the normal save location passes.

No refactor regression was identified by the focused tests, direct operation
comparison, smoke test or paired failure reruns. These results support parity of
the extracted subsystem; they do not establish that every existing game feature
or the full test suite is correct. Unrelated implementation/test fixes are
deliberately outside this behaviour-preserving phase. The smoke test uses dummy
SDL drivers, so it does not replace a manual visual playthrough.

Re-run the focused regression set from `environment_sandbox`:

```sh
../.venv/bin/python -m unittest test_simulation_compost test_compost_spoilage test_food_spoilage test_recipe_progress test_farm_treatments test_field_rotation test_calendar_system test_wildlife_rebalance
```

Remaining coupling is explicit: models still live in `entities.py`; recipe and
resource registries remain global; Game still supplies the shared surplus policy,
history and cache invalidation callbacks; Game still decides when operations run.
This first boundary demonstrates the pattern without pretending to have isolated
the full simulation. The next recommended extraction is barn/sheaf/threshing
storage operations, before the higher-risk clock work.
