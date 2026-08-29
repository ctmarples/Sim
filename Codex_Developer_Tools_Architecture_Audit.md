# Developer Tools / Content Editor Architecture Audit

## A. Executive summary

- The launcher is an overlay inside `Game`, not a separate application. A new top-level Developer Tools route fits naturally beside Continue/New/Load/Quit in `environment_sandbox/game.py`.
- The project runs from source with `python main.py`. No PyInstaller, package manifest, installer, or app-bundle configuration exists.
- Recipes and traveller templates are the strongest current editor candidates because their canonical authoring formats are CSV.
- Resources are hybrid. Base resources are Python `ResourceDef` entries, crop/tree resources are generated from Python catalogues, and recipe CSV rows can dynamically register additional resources and food/clothing effects.
- Crops, wild flora, trees, wildlife species, and buildings remain Python-defined. Externalizing crops/flora is feasible, but editing buildings or wildlife behavior requires broader architectural work.
- Recipe rows are loaded automatically on the next process launch. A correctly placed CSV row will appear at its mapped workstation, subject to duplicate-name suppression and extension requirements.
- A recipe output can register itself as a resource only when the row supplies `resource_group` or food metadata. Even then, arbitrary new keys are unsafe because `Inventory`, `HomeStorage`, and `Building` contain explicit item fields.
- Icons are dynamically discovered by filename, but discovery and rendered surfaces are cached. `icons.clear_cache()` makes runtime import/re-preview practical.
- Useful developer infrastructure already exists: headless `Game`, a launch-time map generator, a small production-backed subtile scenario, map/environment editing, balance controls, wildlife repopulation, diagnostics, and extensive tests.
- There is no unified content validator, hot-reload controller, generic form toolkit, or safe atomic project-data writer. These should precede a broad editor UI.

## B. Current content architecture

| Content type | Canonical source(s) | Format | Loader | Runtime registry/consumer | Editable without code? | Suitability |
|---|---|---|---|---|---|---|
| Resources/items | `resources.py`; derived from `CROPS` and `TREES`; optional recipe metadata | Python dataclasses/list + CSV side effects | Module import; `register_resource()` | `RESOURCES`, `RESOURCE_KEYS` | Partly | POOR |
| Recipes | `recipes_data/<building>/recipes.csv`; legacy JSON; built-in tuples in `recipes.py` | CSV, legacy JSON, Python defaults | `_load_directory_recipes()` | Workstation-specific `*_RECIPES` tuples | Yes for directory recipes | ACCEPTABLE |
| Food effects | `resource_balance.py` for raw food; kitchen CSV metadata for crafted food | Python + CSV | Import and `register_food()` | `FOODS`, `FOOD_BY_KEY`, `VILLAGER_FOOD_KEYS` | Partly | POOR as unified catalogue |
| Food requirement tags | `resource_balance.py` | Python dicts/sets | Import | `FOOD_REQUIREMENT_TAGS`, `FOOD_STAPLE_TAGS` | No | POOR |
| Crops | `crops.py` | Frozen dataclasses in Python | Import | `CROPS`, `CROP_BY_KEY`, `PRODUCE_KEYS`, `SEED_KEYS` | No | POOR |
| Wild flora | `wild_species.py` | Frozen dataclasses in Python | Import | `WILD_SPECIES`, `WILD_BY_KEY` | No | POOR |
| Trees | `trees.py` | Frozen dataclasses/dicts in Python | Import | `TREES`, `TREE_BY_KEY`, `TREE_SPAWN_WEIGHTS` | No | POOR |
| Wildlife species/art/fish yields | `wildlife_species.py` | Frozen dataclasses in Python | Import | `WILDLIFE_SPECIES`, `WILDLIFE_BY_KEY` | No | POOR |
| Wildlife behavior/ecology | `wildlife.py`, `resource_balance.py` | Enums, classes, hard-coded branching | Import | `WildlifeManager`, `FishManager`, `AnimalKind`, `FishKind` | No | POOR |
| Traveller templates | `society_data/travellers.csv` | CSV | `load_traveller_templates()` | Lazy `_TRAVELLER_TEMPLATES` cache | Yes before first load/restart | GOOD |
| Skills/traits | `society.py` | Enums and Python lists/maps | Import | `SkillType`, `SKILL_ORDER`, trait pools | No | ACCEPTABLE for logic; POOR for editor |
| Buildings | `entities.py`, `building_unlock.py`, `settings.py` | Enum + Python maps + behavior | Import | `BuildingKind`, labels, costs, storage, recipes | No | POOR |
| Production/workstations | `recipes.py`, `entities.py`, `game.py`, `extensions.py` | CSV catalogue + Python execution | Import | `Building.known_recipes()`, `craftable_recipe()` | Recipe rows only | ACCEPTABLE |
| Tools | `resources.py`, `entities.py`, recipe CSVs, icons | Python tuples/maps + CSV | Import | `TOOL_KEYS`, `WORKPLACE_TOOL` | Partly | POOR |
| Clothing | `entities.py` plus tailor/cobbler CSV metadata | Python + CSV | Import and `_register_clothing_effects()` | Slot and effect maps | Partly | ACCEPTABLE for known slots |
| Icons/assets | `assets/icons/**/*.svg` and `*.png` | Asset directory | Dynamic recursive index | Icon path/surface caches | Yes | GOOD with validation |
| Terrain/world generation | `random_map_generator.py`, `world.py`, `terrain_settings.py`, terrain assets | Python + JSON + PNG | Module/config loaders | `World`, `GeneratedMap`, caches | Partly | ACCEPTABLE |
| Balance/settings | `settings.py`, `balance_config.py`, `balance_prefs.json` | Python defaults + JSON preferences | `BalanceState` | Active balance state | Runtime tuning supported | ACCEPTABLE |
| Saves | `saves/*.json` | JSON | `save_load.py` | Live `Game` state | Yes, but not canonical content | Not content source |

Important duplication and coupling:

- Resource identity/display is split between `resources.py`, recipe CSV metadata, crop/tree-derived definitions, `resource_icon_style()`, food tags, and explicit storage fields.
- Raw-food effects live in `resource_balance.py`; crafted-food effects live in recipe CSV.
- Edibility is represented indirectly by membership in `VILLAGER_FOOD_KEYS`; `FoodDef` has no stored `edible` field.
- Food labels/categories/icons and dietary tags are distinct sources.
- Crop produce and seed resources derive from `CropDef`, while edibility is controlled by `_FOOD_CROP_KEYS` in `resources.py`.
- Wildlife art/fish metadata is in `wildlife_species.py`, while habitat, capacity, mating, migration, predation, and enums live in `wildlife.py`; copied balance aliases also exist in `resource_balance.py`.
- Building identity, labels, menu order, unlock tiers, costs, storage, tools, icons, feature mappings, placement, extensions, and behavior are spread across modules.
- Recipe names simultaneously act as IDs, saved UI-state keys, labels/fallback output IDs, and some behavior selectors.

## C. Resource lifecycle

```text
Python ResourceDef / crop-or-tree-derived ResourceDef / recipe metadata
→ resources.RESOURCES + RESOURCE_KEYS
→ optional FoodDef / food tags / clothing maps
→ explicit Inventory, HomeStorage, and Building attributes
→ workplace gather/craft functions
→ resource bar, stock panels, inventory dialogs, recipe UI
→ JSON save fields and dynamic resource maps
```

Key components:

- Valid display catalogue: `RESOURCES` and `RESOURCE_KEYS` in `resources.py`.
- Labels/groups/short labels: `ResourceDef`, `resource_label()`, `resources_by_group()`.
- Icons: `resource_icon()` → `resource_icon_style()`, including many key-specific branches and crop fallbacks.
- Edibility/effects: `FOODS`, `FOOD_BY_KEY`, `VILLAGER_FOOD_KEYS`, `register_food()`.
- Dietary classification: `FOOD_REQUIREMENT_TAGS`, `FOOD_STAPLE_TAGS`, `REQUIREMENT_OR_GROUPS`.
- Storage: explicit dataclass fields in `Inventory`, `HomeStorage`, and `Building`; generic operations then use `getattr/setattr`.
- Starting stock: `_give_starting_resources()` and `STARTING_*` constants.
- Production: wild gathering/hunting/fishing and `Recipe.outputs`.
- Saves: fixed save lists, dataclass fields, and resource dictionaries.

Examples:

- `bread`: base `ResourceDef`; kitchen recipe and food metadata; dietary tags; explicit storage fields; icons.
- `fish`: base resource/raw food; wildlife species yield into generic `fish`; fishing logic/storage; dietary tags.
- `mushroom_stew`: kitchen recipe metadata plus explicit inventory/storage fields and icon styling.
- `wheat_flour`: base resource, explicit storage fields, mill output, kitchen input.
- `reeds`: base resource, wild-flora output, explicit storage fields and harvesting branches.

### Can a new resource be created with one row/file?

No, not safely in the general case.

Current edits commonly include:

- Resource catalogue entry or recipe metadata registration.
- `Inventory`, `HomeStorage`, and `Building` item fields.
- Save/load fixed-key handling where applicable.
- Icon asset and sometimes a `resource_icon_style()` branch.
- Food definition, edibility list, and dietary tags for food.
- Starting inventory if desired.
- Tool/clothing maps if applicable.
- Producer/consumer rows or custom gathering logic.

Recipe metadata can create a display resource dynamically, and `ensure_storage_item_fields()` tries to add recipe-output class attributes after recipe loading, but this is an import-time compatibility mechanism rather than a robust arbitrary-resource schema.

A future canonical resource definition could own stable key, labels, category, icon/recolour, stack size, edibility/effects, dietary tags, and data-only equipment metadata. Inventory/storage should become dictionary-backed before arbitrary one-file resources are safe.

Keys should be immutable after release. Renaming `fish_stew` would affect saves, recipe state, favourites/requirements, UI branches, and Python references and therefore requires aliases/migrations.

## D. Recipe lifecycle

```text
recipes_data/<workstation>/recipes.csv
→ csv.DictReader
→ _recipe_from_row()
→ Recipe(name, inputs, outputs, icon_key, skill_reqs, category, steps)
→ _apply_row_metadata()
→ workstation-specific *_RECIPES tuple
→ Building.known_recipes()/addon_craft_recipes()
→ building inspection/production UI
→ Building.craftable_recipe()
→ society.recipe_skill_gate() + recipe_ready() + output-cap checks
→ Building.advance_recipe_progress()
→ Game._apply_recipe_tracked()
→ recipes.apply_recipe()
→ consume_recipe_item()/add_recipe_output()
→ storage/inventory and production history
```

- Folder-to-registry mapping is `_BUILDING_RECIPE_ATTR`.
- Inputs/outputs use `key:amount;key:amount`.
- Skill columns map to `SkillType`; values are clamped.
- `steps` falls back through `Recipe.work_steps()` to defaults.
- Kitchen categories drive UI grouping/default priority.
- Workstation linkage comes from the directory, not a column.
- Barn, compost-heap, and drying-rack recipes require linked extensions.
- Enablement, priority, production caps, and progress are saved by string key.

Adding a valid row to a recognized `recipes_data/<building>/recipes.csv` makes it appear on the next launch because `_load_directory_recipes()` runs during module import and updates the corresponding tuple before building recipe state initializes.

Caveats:

- Duplicate names are silently ignored after the first.
- Malformed rows are printed and skipped.
- Unknown skills reject the row.
- Unknown resource references are not comprehensively validated.
- Add-on recipes require their extension.
- New folders are ignored unless mapped in `_BUILDING_RECIPE_ATTR`.

A recipe can only partially create an unknown output resource. `resource_group` or food metadata invokes `register_resource()`, and output fields may be injected into storage classes, but save lists, instance fields, icons, food tags, UI, and behavior may remain incomplete.

Food effects currently live in both resources and recipes: raw foods in `resource_balance.py`, crafted foods in recipe CSV. Moving intrinsic effects to a resource catalogue would simplify multiple recipes producing the same item, but would affect recipe loading, food registration, villager meal selection, dietary tags, validation, and editing.

## E. Asset/icon architecture

- Canonical root: `environment_sandbox/assets/icons/`, recursively searched.
- Supported formats: SVG and PNG.
- IDs are file stems; category directories are not part of the ID.
- Spaces, additional dots, leading `_`, and assets below `_` directories are excluded.
- Duplicate stems across directories collide; sorted-path first match wins.
- Variants use contiguous `base_1`, `base_2`, … naming. Numbered variants cause the plain `base` file to be ignored.
- SVG is preferred by default (`ICON_USE_PNG=False`); PNG is fallback.
- SVG is rasterized internally using XML parsing and Pygame drawing.
- SVG classes support recolouring, omission, and scaling.
- Missing/load failures result in an empty draw rectangle, not a visible fallback glyph.
- Caches include path, surface, hit, variant, and PNG-manifest caches.
- `icons.clear_cache()` resets discovery and rendered state.

Therefore, copying `assets/icons/mushroom_pie.svg` and setting `icon_key=mushroom_pie` works after a fresh launch. During a running session, call `icons.clear_cache()` before previewing a newly imported file.

Reusable preview functions are `get_icon()`, `blit_icon()`, `preload()`, and `list_icon_names()`.

An editor should enforce unique snake-case stems, valid XML and `viewBox`, supported elements/paints/transforms, class-based recolour conventions, no scripts/external resources, contiguous variant numbering, and a successful render through `get_icon()`.

There is no OS file-picker dependency. Existing `FileDialog` only browses saves. Typed paths or drag/drop are safer initially than adding Tkinter or another GUI dependency.

## F. Launcher/UI architecture

```text
File: environment_sandbox/main.py
Function: main()
Role: argparse, pygame initialization, display configuration, Game construction/run
```

```text
File: environment_sandbox/game.py
Class: Game
Functions: _launch_buttons(), _handle_launch_event(), _draw_launch_overlay(), run()
Current menu:
  Continue
  New game
  Load game
  Quit
```

There is no launcher Settings button; balance/sound settings are accessed in-game.

- Continue loads the newest save through `load_from_path()`.
- New Game offers Default Valley, existing maps, and map generation.
- Load uses `FileDialog` and `load_from_path()`.
- Starting/loading a game sets `_launch_menu=None`.
- Quit sets `running=False`; `run()` calls `pygame.quit()`.

Developer Tools can be another `_launch_buttons()` action that sets `_launch_menu="developer_tools"`. It can reuse the launch overlay while retaining the tiny placeholder world already created behind the launcher.

Existing launch modes are `--time-demo`, `--original-resource-grid` and aliases, plus `Game(headless=True)`.

Reusable UI patterns include text entry in `FileDialog`, `NumberInputDialog`, scrollable lists, management tabs, modal dialogs, hand-built buttons/toggles/sliders, tooltips, and icon rendering. Missing generic controls include free text/float fields, dropdowns, checkboxes, editable tables, arbitrary file picker, icon/color picker, multiline validation summaries, and unified focus/navigation.

## G. Existing debug infrastructure

| Existing dev feature | Location | Reusable? | Notes |
|---|---|---:|---|
| Headless real game | `Game(headless=True)` | Yes | Used by diagnostics/speed runs |
| Small production test scenario | `_open_subtile_test()`, `subtile_test_map.py` | Strongly | Best current Content Lab base |
| Map generator/preview | Launcher, `random_map_generator.py` | Yes | Deterministic seed/options |
| Standalone map tool | `map_generator_tool.py` | Yes | Spawned subprocess |
| Map/height/terrain editor | `Game`, `UI._draw_map_edit_panel()` | Yes | Brushes and terrain tools |
| Environment overlays | Number keys, F10/F11 | Yes | Habitat, diversity, moisture, temperature, etc. |
| Time controls | Simulation speeds/ticks-per-day cycling | Yes | No arbitrary season/date form |
| Balance editor | `BalanceDialog`, `BalanceState` | Yes | Runtime tuning and persistence |
| Wildlife repopulation | `WildlifeRepopulateDialog`, `_repopulate_wildlife()` | Yes | Real clear/reseed path |
| F6 diagnostic | `Game` | Limited | Autotile diagnostic |
| F8 bug log | `Game`, `bug_log.py` | Yes | Writes JSONL |
| Footprint overlay | `O` key | Yes | Placement inspection |
| Time demo | `time_demo.py` | Limited | Separate demo process |
| Headless diagnostics | economy/stability/villager scripts | Yes | Real simulation paths |
| Niche audit | `wild_species.niche_audit()` | Yes | Validation/preview basis |
| Tests | `test_*.py` | Yes | Strong reuse evidence |
| General hot reload | None | No | Only icons/balance have partial support |
| Spawn/console/teleport | None | — | No command registry |

## H. Hot reload assessment

| Catalogue | Can reload now? | Main blocker | Difficulty |
|---|---:|---|---|
| Resources | Partly | Hybrid derivation, explicit storage fields, imported snapshots | Difficult |
| Recipes | No public reload | Merge-oriented loader, derived constants, building caches | Moderate |
| Crops | No | Immutable globals and many derived/imported lists | Moderate |
| Wild plants | No | Immutable globals, terrain maps, season and balance copies | Moderate–difficult |
| Villagers | Nearly | Reset lazy `_TRAVELLER_TEMPLATES` cache | Easy |
| Buildings | No | Enum and scattered maps/branches | Difficult |
| Icons | Yes with cache clear | Must call `icons.clear_cache()` | Easy |
| Wildlife species | No | Enum-backed runtime types and copied tables | Difficult |

Stale consumers include tuple imports in `entities.py`, `RESOURCE_KEYS`, derived produce/seed lists, `world.WILD_CROPS_BY_TERRAIN`, copied `resource_balance.py` values, building recipe state/policy caches, and UI row/tab caches.

Reloading definitions only affects future lookup. It does not mutate existing cells, crops, villagers, wildlife entities, recipe progress, or buildings. Definitions-only reload is a reasonable documented V1 boundary.

Crop externalization is **Moderate** risk. `CropDef` is data-oriented, but import-time resource generation, field plans, wild-crop links, season enums, and save fallbacks need coordinated loaders/invalidation.

Wild-flora edit/save/reload currently requires restart because registries and derived constants are fixed during import.

## I. Data writing / packaging constraints

Current writes include world saves, balance preferences, bug logs, generated maps/debug output, terrain settings, icon exports, and temporary stippled icon caches.

`save_to_path()` writes directly to the destination. There is no temporary sibling, atomic replace, backup, fsync, locking, or schema-preserving content writer.

Source editing is practical locally because content paths derive from `__file__`. It is unsuitable for read-only installations, signed bundles, protected application directories, or PyInstaller extraction/bundled resources.

No packaging configuration exists. The correct initial boundary is:

> Developer Tools is a source-development feature that writes only under a verified repository content root.

A packaged mod editor should later use a writable user-content override directory, not mutate bundled assets.

Git-friendly writing requires preserving each CSV's existing header, UTF-8, row order, newlines, and quoting; recipe folders currently have different headers. Python catalogue rewriting should be avoided because it is fragile and noisy. SVG additions naturally produce clean diffs; overwrites require confirmation.

## J. Validation and safe editing

Existing checks include required recipe names, input/output amount parsing, known skill names, clamped skill values, skipped malformed recipe rows, duplicate recipe suppression, bounded traveller values, niche behavior tests, save-version checks/migrations, and icon discovery/render helpers.

Missing checks include:

- Duplicate resource/crop/flora/wildlife/template keys.
- Duplicate icon stems across folders.
- Unknown recipe input/output resources.
- Missing outputs where inappropriate.
- Missing workstation/folder mappings.
- Missing or unrenderable icons.
- Crop seed/produce consistency.
- Wild-crop references to unknown crops.
- Invalid wild terrain/feature names.
- Unknown traveller foods, traits, workplaces, or IDs.
- Completeness of parallel building registries.
- Unknown food-tag resources.
- Recipe dependency cycles/unreachable chains.
- Save compatibility effects of renames/deletions.

Recommended safe-write path:

```text
clone catalogue in memory
→ validate complete candidate and cross-references
→ serialize deterministically to temporary sibling
→ flush/fsync where practical
→ optionally create one backup
→ os.replace(temp, canonical)
→ reload definitions and clear dependent caches
→ rerun the same validator
```

Also refuse paths outside the repository content root, show exact changed files, detect disk changes since opening, confirm asset replacement/key rename, avoid Python rewrites in V1, and label restart requirements.

A dependency scanner can combine parsed recipes, crops, wild yields, traveller requirements/favourites, building tools/storage, starting stock, food tags, and targeted Python/AST searches. Saves should be scanned separately as instances rather than catalogue definitions.

## K. Content Lab feasibility

Feasibility is **Moderate**, with a strong existing base.

`Game(headless=True)` proves the full simulation can run without a display. Normal launcher construction uses a tiny `World(cols=8, rows=8)`. `Game` still initializes most managers: world, player/storage, buildings/villagers, wildlife/fish, environment, soil/weather, UI/dialogs, balance, and resource history.

The best foundation is `Game._open_subtile_test()` with `subtile_test_map.build_test_map()`, because it uses real systems rather than a fake simulator.

Reusable paths:

- Resources: `Inventory.add_item()` and building/storage APIs.
- Villagers: `Villager`, traveller-template helpers, `SkillState`.
- Buildings: `Building`, `apply_building_storage()`, placement/init paths.
- Time/season: `calendar_day`, `day_tick`, tick controls, environment sampling.
- Environment: `EnvironmentMaps`, map-edit tools, soil/environment fields.
- Wildlife: manager seeding and `_repopulate_wildlife()`.
- Recipes: `Building.craftable_recipe()`, `advance_recipe_progress()`, `Game._apply_recipe_tracked()`.

`Save + Test Recipe` should save and validate, rebuild the relevant registry, invalidate building caches, start a deterministic small map, create the matching workstation/extension, create a sufficiently skilled/tool-equipped villager, deposit inputs through normal APIs, and allow the real crafting/task path to execute. Orchestration is the main difficulty; production execution already exists.

## L. V1 recommendation

```text
Developer Tools
├── Content
│   ├── Recipes
│   ├── Traveller Templates
│   └── Icons
├── Testing
│   └── Content Lab
└── Validation
    ├── Validate Recipes
    ├── Validate Travellers
    ├── Validate Icons
    └── Validate All
```

Resources should initially be viewable/reference-selectable, not advertised as fully arbitrary. Recipe metadata may edit existing resources and carefully create simple recipe-owned outputs, with warnings for missing storage compatibility.

Before UI work:

- Extract pure loaders returning candidate catalogues without mutating globals.
- Add structured file/row/field/severity validation results.
- Add deterministic atomic CSV writers.
- Add explicit recipe/traveller reload and icon refresh.
- Define one content-root/path policy.
- Add registry revision/invalidation hooks for building recipe state.
- Centralize resource lookup enough to validate recipe outputs.
- Build reusable text, float, dropdown, table, and validation-summary controls.

This removes routine CSV syntax, ID lookup, icon wiring, and manual testing work while preserving custom behavior as code.

## M. V2/V3 opportunities

### V2

- External canonical resource catalogue.
- Dictionary-backed inventory/storage or another dynamic item store.
- Resource editor for labels, groups, icons, stacks, food effects, and dietary tags.
- Crop externalization/editor.
- Wild-flora externalization, niche editor, scenario preview, and definitions-only reload.
- Dependency lookup and safe-delete/rename analysis.
- Full recipe test orchestration.

### V3

- Traveller scenario/generation testing.
- Tree editor.
- Wildlife metadata editor for existing enum-backed species.
- Building metadata editor for labels, costs, storage, icons, and unlock tiers.
- User-writable mod/override directories.
- Explicit migrations/aliases for renamed keys.

Keep code-defined for now: new wildlife behavior, prey/migration/mating/habitat algorithms, new building behaviors/placement/extensions/tasks, new tool mechanics, and simulation/save-migration logic.

Wildlife is **partially data-driven**. Buildings range from data + behavior (housing, processors) to mostly custom Python behavior (fields/farms, forestry, hunting, fishing, market, extensions). No current building is strictly data-only because all participate in enum, UI, placement, and save registries.

## N. Risks / architectural blockers

- Explicit item fields block arbitrary resources.
- Import-time registries and copied constants make reload nonlocal.
- Duplicate recipe IDs are silently ignored rather than errors.
- Recipe metadata conflates recipe, resource, food, and clothing authoring.
- Stable string IDs are serialized extensively; naive renames break saves.
- Building definitions are fragmented and enum-backed.
- Wildlife keys must match runtime enums; rows alone cannot add behavior.
- Icon stems can collide across directories.
- Missing icons render invisibly rather than using a clear placeholder.
- Current writes are not atomic.
- Existing dialogs are bespoke rather than a generic toolkit.
- Source writing must be disabled/redirected in packaged installations.
- Definition reload does not update existing world instances.
- Python catalogues cannot be safely rewritten while preserving formatting.
- Traveller templates cache after first use; generated villagers become independent save objects.

| Current task | Why manual/code knowledge is needed | Editor? | Difficulty |
|---|---|---:|---|
| Add recipe with existing resources | Folder/header, compound syntax, skill IDs | Yes | Low |
| Add crafted food | Recipe plus resource/food/icon/tags | Yes after validation | Low–medium |
| Add clothing item | Recipe columns, slot/effects/storage/icon | Existing slots | Medium |
| Add icon | Naming/render restrictions/cache | Yes | Low |
| Add traveller template | CSV schema and reference IDs | Yes | Low |
| Tune crop | Python dataclass/season syntax | V2 | Medium |
| Add crop | Resource, flora, field, recipe cross-links | V2 | Medium–high |
| Tune flora niche | Large Python dataclass | V2 | Medium |
| Add wild plant | Feature/resource/spawn/render links | V2 | Medium–high |
| Tune wildlife art/fish yield | Python catalogue | Eventually | Medium |
| Add animal behavior | Enums/custom simulation logic | No generic editor | High |
| Tune building cost/storage | Several Python maps | Eventually | Medium |
| Add building type | Enum, UI, placement, tasks, save, behavior | No V1 | High |
| Rename/delete stable key | References and migrations | Scanner-assisted | High |

## O. Files likely involved in implementation

- `environment_sandbox/main.py` — startup boundary.
- `environment_sandbox/game.py` — launcher route, Content Lab, invalidation.
- `environment_sandbox/recipes.py` — pure loading, registry rebuild, validation.
- `environment_sandbox/recipes_data/` — canonical recipes.
- `environment_sandbox/resources.py` — resource registry/icon metadata.
- `environment_sandbox/resource_balance.py` — food effects/tags.
- `environment_sandbox/entities.py` — storage and production state/execution.
- `environment_sandbox/society.py` — traveller loading/cache/skills.
- `environment_sandbox/society_data/travellers.csv` — canonical templates.
- `environment_sandbox/icons.py` — discovery, rendering, cache refresh.
- `environment_sandbox/assets/icons/` — canonical assets.
- `environment_sandbox/dialogs.py` — file-dialog patterns.
- `environment_sandbox/number_input_dialog.py` — numeric input.
- `environment_sandbox/management_window.py` — tabs/tables/scrolling.
- `environment_sandbox/building_inspect_dialog.py` — recipe UI patterns.
- `environment_sandbox/subtile_test_map.py` — Content Lab seed scenario.
- `environment_sandbox/save_load.py` — stable-ID/migration implications.
- `environment_sandbox/crops.py` — future crop schema.
- `environment_sandbox/wild_species.py` — future flora/niche schema.
- `environment_sandbox/wildlife_species.py` — wildlife metadata.
- `environment_sandbox/wildlife.py` — behavioral boundary.
- `environment_sandbox/trees.py` — future tree editor.
- `environment_sandbox/building_unlock.py` — build order/tiers/costs.
- `environment_sandbox/settings.py` — storage/global defaults.
- `environment_sandbox/toolbar.py` — building icon/menu duplication.
- Likely new `content_validation.py` — shared pure validation.
- Likely new `content_io.py` — path policy and atomic writes.
- Likely new `developer_tools.py` or `developer_tools/` package — UI/controllers.

## P. Questions that still require a design decision

1. Should V1 permit recipe-owned resource creation, or restrict outputs to existing keys until storage is dynamic?
2. Is Developer Tools intentionally source-only, visibly refusing writes in packaged/read-only builds?
3. Should recipe CSVs retain per-folder headers or later migrate to a common superset schema?
4. Should food effects move to resources before the resource editor, or remain editable in recipe rows initially?
5. Is definitions-only hot reload sufficient for V1, with Content Lab restart after structural changes?
6. Should destructive key renaming initially be forbidden or supported through explicit aliases/migrations?
7. Should Content Lab reuse the current `Game` or create a disposable session?
8. Should icon import use typed paths/drag-and-drop initially, or add an OS-native picker dependency?
9. Should writes preserve manual row order exactly or enforce deterministic sorting?
10. Should validation errors block canonical saves entirely, or may invalid drafts be stored outside canonical content?
