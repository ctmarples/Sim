# Map Object Parameter Audit

Status: proposal only. No revised schema in this document has been applied to runtime data or editor persistence.

## Current editor scope

The Map Object editor currently exposes 45 records: 14 farm crops, 24 wild-species records, four tree species, and three fixed features (rock, fallen wood, mushroom). It does not yet catalogue buildings, construction sites/pads, loose deposits, community markers, wildlife, nests, or fish as map-object records.

Every dataclass field on crop, tree, and wild-species records is currently included in the form, but most complex values are presented as raw JSON/text. `icon_key` and `slots` are editor-owned overrides outside those dataclasses. Fixed features have no structured parameter model, so only their icon and footprint can currently be edited.

## Current parameters by family

### Farm crops (`CropDef`)

- Identity/resources: `key`, `label`, `short`, `produce_key`, `seed_key`.
- Presentation: `stem_colour`, `flower_colour`, `icon_base`, `dense_icon_base`.
- Calendar/growth: `plant_season`, `harvest_seasons`, `growth_days`, `year_phases`, `perennial`.
- Yield/ecology: `wild_seed_chance`, `farm_seed_amounts`, `fertility_effect`.
- Editor-only: `icon_key` override and `slots` footprint override.

Gaps: sparse and dense icons are implicit rather than named stages; colours cannot vary by stage/season; the 3×3 farm footprint is not part of `CropDef`; seed/produce references are free text; phases are raw enum arrays.

### Wild plants and wild crops (`WildSpeciesDef`)

- Identity/type: `key`, `label`, `feature`, `crop_key`.
- Habitat: `terrains`, `edge_terrains`, five niche ranges (`temperature`, `rainfall`, `moisture`, `fertility`, `disturbance`) and `ecology_tags`.
- Harvest: `resource_key`, `yield_amount`.
- Presentation: `icon_base`, `icon_recolour`, `fruit_class`, `fruit_colour`, `empty_fruit_colour`.
- Initial seeding: `initial_count`, `initial_fraction`, `seed_near_feature`, `seed_near_chance`.
- Recurring spawn: `spawn_peak`, `spawn_rise`, `spawn_fall`, `spawn_activity`, `near_feature`, `spread_chance`, `patch_extras`, `spawn_group`.
- Despawn: `despawn_fade`, `despawn_fade_end`, `despawn_fade_chance`, `despawn_leftover_from`, `despawn_leftover_chance`, `clear_from_day`, `clear_ramp_days`.
- Caps/fruiting: `counts_toward_cap`, `fruiting`, `fruit_rise`, `fruit_fall`.
- Editor-only: `icon_key` and `slots` overrides.

Gaps: visibility is encoded indirectly through day ranges; wild crop art falls back through `CropDef`; recolour tuples and niche objects are raw text; collision/density are global rules rather than species parameters.

### Trees (`TreeDef`)

- Identity/resources: `key`, `label`, `short`, `yield_key`, `yield_amount`.
- Growth: `growth_years`.
- Presentation: `shape`, `canopy`, `sapling_colour`, `cone_scale`.
- Editor-only: resolved sapling/mature icon names, `icon_key`, and `slots`.

Gaps: sapling and mature icons are inferred from shape; old-growth threshold and 2×2→3×3 footprint transition are global; trunk colour, seasonal canopy colours, stump state, spawn weighting and habitat weighting live elsewhere.

### Fixed natural features

- Rock: small/large icons and the `ROCK_LARGE_MIN` threshold are resolved outside the editor; deposit/yield and colour are also external.
- Mushroom and fallen wood: most yield, spawning, clearing and presentation values come from a matching `WildSpeciesDef` or legacy balance/settings constants, while the fixed editor rows themselves have no parameters.
- Loose meat/fish/hide/fur/feather markers use separate deposits, icons, colours and one-subcell placement rules and are absent from the editor.

### Structures and other map-visible objects

Buildings use `BuildingKind`, `Building` instance fields, settings constants, construction definitions and renderer-specific mappings. Plot width/height, extensions, capacity, recipes, worker limits, storage, colour sets and icon variants are not represented by the current object editor.

Wildlife uses `WildlifeSpeciesDef` (`key`, `label`, `group`, directional/sex/nest icons, body colours, fish spawn weight/yield/resource) plus substantial habitat, movement, breeding, hunting and pack/colony behaviour elsewhere. Wildlife is not currently in the object editor.

## Proposed unified parameter model

Use one `MapObjectDef` envelope with typed family components. Fields irrelevant to a family should be absent, not shown disabled.

### Common identity and classification

- `key`, `label`, `category`, `feature_type`, `tags`.
- `source_family` and `schema_version` for migration/debugging.
- Typed references: `resource_key`, `seed_key`, `produce_key`, `crop_key`, `building_kind` as applicable.

### Presentation

- `visual_states[]`, each containing:
  - `state_key`, `label`, `icon_base`, optional `variant_policy`.
  - `active_seasons` and/or explicit day window.
  - Optional conditions such as growth range, deposit range, age range, fruiting, sex or direction.
  - Named SVG-class colour map with optional per-season overrides.
  - `footprint` (`width`, `height`, occupied cells, anchor cell), `draw_layer`, `draw_scale`, and optional overhang.
- A separate `icon_override` should not silently replace all states.

This directly represents sparse/growing/harvest crop icons, wild-only icons, sapling/mature/old-growth trees, fruiting/empty bushes, and small/large rocks.

### Placement and collision

- `placement.terrains`, `edge_terrains`, `near_features`, exclusion tags.
- `placement.capacity_family`, `max_per_cell`, `overlap_policy`.
- `collision.hard_cells`, `walkable`, `blocks_building`, `blocks_spawning`.
- `footprint_by_state` where visual/collision size changes over time.

### Calendar, lifecycle and ecology

- `lifecycle.states[]` with explicit transitions and durations.
- `calendar.visible_seasons`, spawn/fruit/clear day windows and ramp curves.
- Typed environmental niche controls with min/optimum-low/optimum-high/max sliders.
- Initial population, recurring spawn, spread, grouping, cap contribution and mortality/despawn controls.

### Harvest, drops and regeneration

- `harvest.outputs[]` (`resource`, min/max or weighted amounts).
- Required tool/action, work amount, deposit capacity and depletion behaviour.
- Regrowth/refresh window, seed drops, fertility effect and missed-harvest outcome.

### Structures

- Plot/anchor footprint and extension rules.
- Construction costs/time/stages and construction-state icons.
- Worker capacity, storage rules, accepted resources, recipes and production modifiers.
- Upgrade/replacement links and interaction/inspection UI metadata.

### Wildlife

- Visual states for sex, direction, age and nest/den.
- Habitat, movement, diet, breeding, group limits, aggression/fleeing and seasonal activity.
- Hunting/fishing yield tables and population regeneration controls.

## Recommended editor sections

1. Identity & references.
2. Visual states, icons, colours and seasonal previews.
3. Footprint, anchor, layer and collision.
4. Habitat, placement and density.
5. Lifecycle and seasonal visibility.
6. Spawn, spread, despawn and population caps.
7. Harvest, yields, tools and regeneration.
8. Family-specific behaviour (crop, tree, structure or wildlife).

Complex parameters should use typed controls: reference pickers, season toggles, day-range sliders, colour popovers, footprint grids, weighted-output rows and niche-range graphs. Raw JSON should remain only as an optional advanced/debug view.

## Migration recommendation

Do not migrate all families at once. First introduce read-only adapters that produce `MapObjectDef` views from current registries and verify renderer/placement parity. Then persist presentation and footprint states, followed by ecology/harvest data. Structures and wildlife should remain later migrations because their behaviour is not currently data-only.
