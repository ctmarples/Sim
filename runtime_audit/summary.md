# Runtime usage observation

This measures executed Python code, not the minimum code required to ship the game.
Unobserved code is not established as dead or safe to delete. Imports and startup
are included separately from gameplay. Executable lines are bytecode line-table
locations, not a count of all physical source lines. Test files are excluded.

```json
{
  "save": "/Users/christophermarples/PycharmProjects/Sim/saves/SP_new_1.json",
  "grid": {
    "cols": 96,
    "rows": 72,
    "seed": 77
  },
  "buildings": 43,
  "villagers": 27,
  "interactive": false,
  "requested_frames": 180,
  "speed": 32,
  "frames": 180,
  "simulation_ticks": 5760,
  "status": "completed",
  "calendar_start": 56.0,
  "calendar_end": 56.0,
  "elapsed_seconds": 39.8
}
```

Observed 30,236 / 81,192 executable lines (37.2%).
Entered 1,530 / 3,831 declared functions/methods.
Observed 94 / 124 non-test modules.

| Module | Source lines | Executable | Startup/load | Gameplay | Observed % |
| --- | ---: | ---: | ---: | ---: | ---: |
| game.py | 29973 | 24224 | 1769 | 6189 | 32.6 |
| wildlife.py | 5083 | 4025 | 917 | 1158 | 45.5 |
| entities.py | 4893 | 3781 | 1405 | 1249 | 66.0 |
| world.py | 4284 | 3384 | 1751 | 1024 | 68.0 |
| building_inspect_dialog.py | 2562 | 1983 | 165 | 1 | 8.4 |
| ui.py | 2490 | 1933 | 127 | 811 | 48.5 |
| save_load.py | 2431 | 1977 | 1096 | 0 | 55.4 |
| scenario.py | 2088 | 1780 | 274 | 12 | 16.1 |
| management_window.py | 2081 | 1666 | 213 | 0 | 12.8 |
| icons.py | 2033 | 1588 | 1045 | 744 | 74.6 |
| field_plan_dialog.py | 1833 | 1520 | 141 | 1 | 9.3 |
| villager_inspect_dialog.py | 1773 | 1460 | 150 | 1 | 10.3 |
| balance_config.py | 1688 | 1262 | 1232 | 5 | 97.6 |
| society.py | 1459 | 1074 | 411 | 113 | 48.0 |
| developer_tools/authoring_ui.py | 1258 | 1164 | 0 | 0 | 0.0 |
| sociopolitical.py | 1052 | 813 | 547 | 11 | 68.6 |
| villager_roster.py | 1028 | 824 | 176 | 48 | 27.2 |
| sociopolitical_hooks.py | 1027 | 803 | 0 | 91 | 11.3 |
| terrain_tiles_png.py | 980 | 751 | 0 | 0 | 0.0 |
| wild_species.py | 891 | 666 | 506 | 135 | 81.5 |
| preview_terrain_fills.py | 888 | 680 | 0 | 0 | 0.0 |
| recipes.py | 840 | 596 | 305 | 104 | 66.1 |
| happiness.py | 756 | 549 | 141 | 221 | 63.0 |
| landscape_fields.py | 743 | 536 | 0 | 0 | 0.0 |
| sociopolitical_ui.py | 733 | 589 | 87 | 12 | 16.8 |
| inventory_ui.py | 726 | 567 | 58 | 0 | 10.2 |
| settings.py | 721 | 508 | 498 | 6 | 98.0 |
| resource_balance.py | 720 | 437 | 278 | 94 | 85.1 |
| environment.py | 715 | 517 | 222 | 7 | 44.3 |
| developer_tools/landscape_fields_lab.py | 699 | 573 | 0 | 0 | 0.0 |
| terrain_flecks.py | 692 | 544 | 103 | 20 | 22.6 |
| field_yield.py | 688 | 540 | 92 | 0 | 17.0 |
| terrain_tiles_procedural.py | 663 | 482 | 88 | 163 | 52.1 |
| indicators.py | 624 | 483 | 147 | 20 | 30.4 |
| resources.py | 593 | 415 | 179 | 77 | 59.5 |
| status_effects_ui.py | 592 | 452 | 88 | 0 | 19.5 |
| resource_bar.py | 580 | 458 | 62 | 132 | 42.4 |
| crops.py | 574 | 447 | 389 | 20 | 91.3 |
| terrain_mottle.py | 573 | 393 | 87 | 146 | 59.3 |
| bug_log.py | 559 | 445 | 63 | 0 | 14.2 |
| terrain_fills.py | 527 | 393 | 94 | 27 | 30.8 |
| seasons.py | 509 | 285 | 131 | 90 | 71.2 |
| height_sample.py | 506 | 380 | 81 | 140 | 53.7 |
| random_map_generator.py | 506 | 409 | 0 | 0 | 0.0 |
| resource_tracker_dialog.py | 506 | 397 | 61 | 3 | 16.1 |
| assess_town_stability.py | 504 | 375 | 0 | 0 | 0.0 |
| player_inventory_dialog.py | 485 | 388 | 63 | 1 | 16.5 |
| quest_progress.py | 482 | 368 | 0 | 82 | 22.3 |
| assign_picker_dialog.py | 472 | 376 | 98 | 1 | 26.3 |
| balance_dialog.py | 457 | 359 | 61 | 3 | 17.8 |
| toolbar.py | 455 | 363 | 143 | 150 | 62.3 |
| developer_tools/content_lab.py | 410 | 355 | 0 | 0 | 0.0 |
| time_demo.py | 406 | 330 | 0 | 0 | 0.0 |
| terrain_settings.py | 384 | 260 | 122 | 16 | 53.1 |
| developer_tools/editors.py | 383 | 322 | 0 | 0 | 0.0 |
| developer_tools/widgets.py | 382 | 326 | 0 | 0 | 0.0 |
| soil.py | 358 | 217 | 84 | 33 | 51.6 |
| crop_status_ui.py | 346 | 276 | 25 | 0 | 9.1 |
| subtile_layout.py | 338 | 254 | 205 | 157 | 89.0 |
| diagnose_villagers.py | 337 | 252 | 0 | 0 | 0.0 |
| terrain_overlays.py | 322 | 246 | 41 | 141 | 74.0 |
| villager_priority_ui.py | 321 | 255 | 45 | 0 | 17.6 |
| habitat_inspect_dialog.py | 315 | 243 | 65 | 1 | 27.2 |
| dialogs.py | 310 | 250 | 43 | 3 | 18.4 |
| perf_hud.py | 309 | 256 | 57 | 13 | 27.3 |
| scenario_dialog.py | 302 | 262 | 45 | 11 | 21.4 |
| objectives.py | 298 | 214 | 0 | 46 | 21.5 |
| track_villagers_year.py | 285 | 204 | 0 | 0 | 0.0 |
| developer_tools/terrain_editor.py | 280 | 195 | 94 | 0 | 48.2 |
| developer_tools/validation.py | 264 | 233 | 44 | 0 | 18.9 |
| wildlife_species.py | 258 | 183 | 141 | 16 | 85.8 |
| tutorial_progress.py | 246 | 152 | 0 | 0 | 0.0 |
| resource_inspect_dialog.py | 241 | 191 | 50 | 3 | 27.7 |
| sound_system.py | 234 | 209 | 92 | 98 | 87.6 |
| traits.py | 234 | 174 | 116 | 45 | 92.5 |
| soil_texture.py | 228 | 163 | 128 | 4 | 78.5 |
| developer_tools/controller.py | 218 | 202 | 0 | 0 | 0.0 |
| developer_tools/plant_editor.py | 208 | 177 | 133 | 0 | 75.1 |
| number_input_dialog.py | 197 | 164 | 33 | 2 | 21.3 |
| simulation/compost.py | 192 | 146 | 12 | 5 | 11.6 |
| developer_tools/reload.py | 187 | 139 | 30 | 0 | 21.6 |
| market_economy.py | 187 | 107 | 87 | 33 | 89.7 |
| developer_tools/wild_species_editor.py | 186 | 159 | 110 | 0 | 69.2 |
| building_unlock.py | 180 | 137 | 106 | 20 | 84.7 |
| speed_run_economy.py | 178 | 127 | 0 | 0 | 0.0 |
| extensions.py | 172 | 127 | 85 | 5 | 70.1 |
| camera.py | 169 | 118 | 45 | 18 | 50.8 |
| resource_tracker.py | 169 | 118 | 56 | 6 | 52.5 |
| trees.py | 163 | 114 | 91 | 12 | 88.6 |
| action_choice_dialog.py | 156 | 123 | 33 | 3 | 29.3 |
| developer_tools/objects_editor.py | 155 | 127 | 56 | 0 | 44.1 |
| shade_icons_png.py | 154 | 120 | 0 | 0 | 0.0 |
| food_spoilage.py | 151 | 106 | 28 | 48 | 67.9 |
| developer_tools/crop_editor.py | 149 | 120 | 86 | 0 | 71.7 |
| calendar_system.py | 143 | 107 | 50 | 15 | 60.7 |
| weather.py | 128 | 105 | 29 | 0 | 27.6 |
| quest_navigation.py | 124 | 101 | 30 | 16 | 45.5 |
| wildlife_repopulate_dialog.py | 123 | 97 | 27 | 2 | 29.9 |
| developer_tools/sounds_editor.py | 121 | 117 | 0 | 0 | 0.0 |
| map_generator_tool.py | 121 | 100 | 0 | 0 | 0.0 |
| developer_tools/icons_browser.py | 117 | 102 | 0 | 0 | 0.0 |
| developer_tools/content_io.py | 114 | 90 | 31 | 0 | 34.4 |
| bug_log_report.py | 112 | 86 | 0 | 0 | 0.0 |
| export_icons_png.py | 111 | 71 | 0 | 0 | 0.0 |
| farm_pipeline.py | 104 | 70 | 38 | 12 | 71.4 |
| developer_tools/resources_browser.py | 101 | 91 | 0 | 0 | 0.0 |
| berry_bushes.py | 88 | 57 | 19 | 15 | 59.6 |
| main.py | 84 | 58 | 46 | 1 | 81.0 |
| rain_effect.py | 84 | 66 | 22 | 2 | 36.4 |
| developer_tools/editor_state.py | 80 | 65 | 0 | 0 | 0.0 |
| quest_ui.py | 77 | 67 | 0 | 0 | 0.0 |
| quest_feedback.py | 73 | 61 | 18 | 13 | 50.8 |
| subtile_test_map.py | 69 | 57 | 0 | 0 | 0.0 |
| sound_settings_dialog.py | 63 | 51 | 17 | 2 | 37.3 |
| generate_terrain_fills.py | 62 | 37 | 0 | 0 | 0.0 |
| tutorial_checkpoints.py | 55 | 13 | 0 | 13 | 100.0 |
| developer_tools/references.py | 48 | 39 | 0 | 0 | 0.0 |
| field_handbook.py | 45 | 2 | 2 | 0 | 100.0 |
| field_fertility_tint.py | 31 | 27 | 0 | 27 | 100.0 |
| foods.py | 28 | 4 | 0 | 0 | 0.0 |
| terrain_tiles.py | 22 | 8 | 6 | 1 | 87.5 |
| developer_tools/__init__.py | 12 | 7 | 5 | 0 | 71.4 |
| simulation/__init__.py | 5 | 1 | 1 | 0 | 100.0 |
| __init__.py | 1 | 0 | 0 | 0 | 0.0 |
