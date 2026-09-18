# Runtime usage and redundancy assessment

## What was tested

The current working-tree source, including the existing compost extraction, was
run through the actual `main.py` entry point with its normal authored-content
bootstrap. The selected save was `saves/SP_new_1.json`, the newest world save by
modification time (the newer `balance_prefs.json` is preferences, not a world).
It contains a 96×72 map, 43 buildings and 27 villagers.

The save was paused. The bounded measurement resumed it at speed 32 for 180
rendered frames / 5,760 simulation ticks, using dummy SDL video/audio drivers.
The measured run completed in 39.8 seconds; instrumentation and dummy drivers
make this unsuitable as a normal FPS benchmark. No player actions were scripted.
The integer calendar coordinate stayed at 56; no day or season boundary was
crossed. This is a running saved-town sample, not a complete playthrough.

Saves and balance preferences were copied to temporary storage. The original
save and preferences retained their original modification times and sizes.
The audit made no edits to gameplay code, assets, content definitions or saves;
the previous refactor's uncommitted changes remain in place.

## Measurements

The inventory excludes tests and `_debug` scripts. It includes offline tools and
alternate implementations alongside runtime modules. Blank/comment lines are
included in physical source counts, but excluded from executable-line counts.
Executable lines are derived from compiled Python bytecode line tables, including
definitions/annotations; this is not branch coverage or a minimum-build estimate.

| Measure | Result |
| --- | ---: |
| Non-test Python source | 103,303 physical lines in 124 modules |
| Executable source locations | 81,192 |
| Observed during startup/load | 18,273 |
| Observed during gameplay | 13,970 |
| Observed in either phase (deduplicated) | **30,236 / 81,192 = 37.2%** |
| Declared functions/methods entered | 1,530 / 3,831 |
| Modules with any observed execution | 94 / 124 |
| Entirely unobserved modules | 30 modules, 9,625 physical lines |

Startup and gameplay overlap, so their line counts must not be added directly.
An earlier equivalent bounded sample observed 37.4%; coverage can vary with
runtime conditions. No RNG changes were made to force repeatable coverage.

| Module | Executable lines | Observed in either phase | Observed % |
| --- | ---: | ---: | ---: |
| `game.py` | 24,224 | 7,909 | 32.6% |
| `world.py` | 3,384 | 2,302 | 68.0% |
| `entities.py` | 3,781 | 2,496 | 66.0% |
| `wildlife.py` | 4,025 | 1,831 | 45.5% |
| `save_load.py` | 1,977 | 1,096 | 55.4% |
| `balance_config.py` | 1,262 | 1,232 | 97.6% |
| `simulation/compost.py` | 146 | 17 | 11.6% |

The low compost number is a useful counterexample: the save exercises heap
lookup but not seasonal compost conversion. It would be incorrect to delete
the remaining compost operations based on this run.

Full module tables: [CSV](runtime_audit/modules.csv) and
[generated summary](runtime_audit/summary.md). The detailed line-hit and
unentered-function JSON is retained at `/tmp/sim-runtime-usage/coverage.json`.

## What the unobserved code represents

- **Developer tools not opened:** 3,817 physical lines across 11 unobserved
  developer-tool modules. These support authoring and diagnostics. Other modules
  in the same package *were* executed by the main content bootstrap, so deleting
  the whole developer-tools package would break normal startup/content loading.
- **Offline tools and optional auxiliary windows:** 3,158 lines across 11
  unobserved modules. Examples include icon exporters, economic diagnostics,
  terrain previews, the map generator window and the time demo. These are useful
  tooling or optional entry points, not automatically obsolete game code.
- **Features outside this saved-town workload:** map generation, landscape
  generation, tutorial progression, quest detail UI and subtile test maps total
  1,641 lines in five entirely unobserved modules. Existing callers reference them.
- **Alternative terrain implementation:** `terrain_tiles_png.py` has 980 lines.
  `terrain_tiles.py` still explicitly selects it for `TERRAIN_FILL_MODE="png"`;
  this run used the procedural implementation. Removing it would retire a
  supported configuration and requires a deliberate decision.
- **Compatibility shim:** `foods.py` has 28 lines and re-exports symbols from
  `resource_balance`. No importers were found in the repository's Python files.
  This is the clearest small obsolete-module candidate, subject to checking any
  external scripts relying on that compatibility import.
- The remaining one line is the package initializer.

A conservative AST import walk from `main` reaches 112 modules, including imports
inside functions and inactive branches. That walk undercounts subprocess and
dynamic entry points: `Game` explicitly launches `map_generator_tool.py` and
`preview_terrain_fills.py` by filename. Absence of an import is therefore not a
reliable deletion test either.

## Actual duplication candidates

An AST comparison found seven pairs of identical function bodies among functions
at least 15 physical lines long (ignoring docstrings and source positions):

| Functions | Locations |
| --- | --- |
| `_fg_field`, `resolve_corner_type`, `mask_for_corners`, `_unit_polygons` | `terrain_tiles_png.py` and `terrain_tiles_procedural.py` |
| `_wrap_axis` | `terrain_tiles_png.py` and `terrain_fills.py` |
| `_advance_scroll`, `_draw_button` | `building_inspect_dialog.py` and `villager_inspect_dialog.py` |

The additional copies represent roughly 140 physical lines, before accounting
for shared-helper imports or wrappers. This is a conservative exact-body scan;
it does not detect all near-duplicates, inline repetition or obsolete branches.
Matching bodies may depend on different module globals/helpers, so tests must
establish interchangeability before consolidation. `resolve_corner_type` already
describes itself as retained for diagnostics/experiments.

## What can be concluded

About 37% of executable source was *observed* in this workload. That does not
establish that the other 63% can be removed, or that a build containing only the
observed lines would run. Untaken branches, class definitions, content-driven
dispatch, alternate inputs, future events and error handling still matter.
The roughly 9,600 lines in entirely untouched modules mostly have identifiable
tooling, alternate-mode or unvisited-feature roles. This first pass does not
demonstrate a large safely removable block of code.

The strongest immediate candidates are the small compatibility shim and the
duplicated helpers. Larger reductions require choosing features/tooling to keep
in a shipping build, and separating content loading from authoring UI first.
No deletion was performed and no reduced build has been proven equivalent.

## Record a real play session

From the repository root:

```sh
.venv/bin/python tools/audit_runtime_usage.py --save saves/SP_new_1.json --interactive --speed 1 --output /tmp/sim-play-coverage
```

This opens the game with the selected save and records until you quit. It uses
Python 3.14's standard-library monitoring, with no extra dependency. Saves and
preferences are disposable copies and are discarded on exit; content-editor
writes are not isolated, so use this for gameplay observation. Coverage reports
remain in the specified output directory, including if the game raises an error.

For a more representative sample, exercise movement, pan/zoom, overlays,
building/villager inspectors, inventory, assignment and delivery, farming and
crafting, wildlife interaction, pause/speed controls and save/load. Include day
and seasonal transitions. Tutorial and fresh-map behaviour need separate runs
if those remain supported features.

After that, combine observed sets across workloads, check unobserved candidates
against static/dynamic callers and tests, then remove one small candidate at a
time on an isolated branch. Re-run the same workloads and regression tests after
each removal. Runtime coverage is the evidence-gathering stage, not the deletion
criterion.

## Validation of the audit tool

Two focused tests verify that branch hits are recorded separately across startup
and gameplay and that external files are excluded. Both pass:

```sh
.venv/bin/python -m unittest discover -s tools -p test_audit_runtime_usage.py -v
```

The bounded game runs complete without errors. The launcher preserves normal
content-bootstrap order by intercepting Game construction only after its module
has loaded. It changes only the test run's selected save, initial simulation speed,
save destinations and automatic stopping point. The recorded gameplay phase
includes rendering and UI callbacks, not just simulation functions.
