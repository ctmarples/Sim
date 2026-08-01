# Environmental Farming Sandbox

A small interactive prototype of an environmental farming sandbox built with **Python** and **Pygame**.

Explore a grid landscape, collect wood and rock, plant saplings, deposit resources at home, and inspect translucent environmental indicator overlays (habitat diversity, tree density, disturbance).

The codebase is intentionally small and modular so farming actions, environmental processes, and new indicators can be added later without rewriting the core loop.

## Requirements

- Python 3.10+
- [pygame-ce](https://pyga.me/) 2.x (compatible Pygame fork; recommended, especially on Python 3.14+)

`pip install pygame` also works on Python 3.10–3.13. On Python 3.14, use `pygame-ce`.

## Installation

Create a virtual environment, install dependencies, and run the game from the `environment_sandbox` folder.

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd environment_sandbox
python main.py
```

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd environment_sandbox
python main.py
```

Equivalent one-liner install:

```bash
pip install pygame-ce
```

## Controls

| Key / input | Action |
|-------------|--------|
| `W` `A` `S` `D` or arrows | Move |
| `E` or `Enter` | Interact with the cell you stand on (hire, deposit, chop, plant, or place building) |
| Toolbar build buttons | Choose Forester / Mason / Hunter / Forager / Fisher / Off (`B` still cycles) |
| Toolbar task buttons | Set draw task for the selected building (`T` still cycles) |
| Toolbar speed | Simulation speed x1 / x2 / x4 / x8 / x16 |
| File / Save / Load | In-game dialogs: type a save name, or pick a file from `saves/` |
| Click | Select villager or building; with villager selected, click building/home to assign |
| Drag (building selected) | Draw a task area for that building |
| `C` or toolbar Clear | Clear task areas on the selected building |
| `Esc` | Close File menu / clear selection; press again to quit |
| `1`–`4` | Environmental overlays |
| `R` | Reset world |

## Current mechanics

- **Hire**: Stand on the work station and press `Enter`/`E`.
- **Build**: Toolbar (or `B`) selects Forester / Mason / Hunter / Forager / Fisher (2 wood + 2 rock each).
- **Speed**: Toolbar speed buttons run the simulation at x1–x16.
- **Save / load**: File dialogs — Save asks for a filename; Load lists JSON files in `saves/`.
- **Resources**: Shown in groups (Food, Construction, Agriculture). Fish is a food resource.
- **Rock**: Small deposits on soil/grass; large deposits (20+) only on grey rock terrain patches. Water appears as larger lake patches.
- **Fisher**: Draw fish areas over water; workers catch fish within 1 tile (shore), leave fish on shore, then collect and deliver.
- **Forager**: Collects mushrooms, berries, berry seeds, herbs, herb seeds; can plant berry/herb seeds. Task buttons / `T` cycle forage/plant modes.
- **Mushrooms**: Appear on soil beside trees and spread to neighbouring soil.
- **Berry bushes**: On grass, yield 5 berries then regenerate slowly; rare berry-seed drops; very slow natural spread.
- **Herbs**: Spawn on grass; harvesting can drop herb seeds.
- **Forester**: Local wood storage (max 20). Select it, use `T` for chop / plant / full-manage areas, drag to paint zones. Assigned villagers work those zones and deliver wood to the Forester.
- **Mason**: Local rock storage (max 20). Select it and draw collect-rock areas. Workers deliver rock to the Mason.
- **Hunter**: Local meat storage (max 20). Draw hunt areas; assigned villagers approach animals within the area (must be within 1 square to kill), leave **5 meat** on that tile, then collect it and deliver to the Hunter.
- **Assign villagers**: Click a villager, then click a building or home.
- **Home haulers**: Villagers assigned to home pull stock from workplaces and deposit it in home storage.
- **Trees / rocks / saplings**: Trees hold **2 wood**; rocks hold **10 rock**. Each chop has a **25%** chance to also yield a **sapling item**. Planting requires a sapling item.
- **Growth**: Saplings mature slowly. Tree patches of **4+** have a **1/8** chance each sprout interval to grow a new sapling on an adjacent empty cell.
- **Map**: Window scales to fill the display; grid is +4 cells larger on each axis beside the sidebar.
- **Wildlife**: Brown animals roam cells within 1 of trees. Population grows slowly toward **1 animal per 4 trees** in each connected tree patch.
- **UI**: Side panel scrolls with the mouse wheel.
- **Areas** are only shown while their building is selected (`Esc` hides them).

## Project structure

```text
environment_sandbox/
    main.py          # Entry point
    game.py          # Loop, input, interactions, rendering
    world.py         # Grid, generation, neighbourhood queries
    entities.py      # Player, inventory, home storage
    indicators.py    # Diversity, tree density, disturbance overlays
    ui.py            # Side panel, legends, feature drawing
    settings.py      # Dimensions, colours, capacities, seed
    README.md        # This file
```

## Architecture notes

- **Simulation state** lives in `world.py` / `entities.py`.
- **Indicators** are derived from current cells in `indicators.py` (not hard-coded at startup).
- **Interaction logic** is dispatched from `game.py`.
- **Rendering / UI** is split between `game.py` (map) and `ui.py` (panel).

## Suggested extension points

Comments in the source mark where these could plug in later:

- Crop planting and harvesting
- Soil fertility and water availability
- Biodiversity species / habitat connectivity
- Seasonal changes and tree growth stages
- Erosion risk, pollination, farm income, subsidies
- Action costs, multiple farms, landscape objectives
- Scenario comparison, save/load, agent-based wildlife
- Real GIS-derived maps

## License

Prototype / educational use.
