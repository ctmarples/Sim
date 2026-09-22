extends SceneTree


func _init() -> void:
	var settings := TerrainGenerationSettings.new()
	settings.columns = 100
	settings.rows = 100
	settings.seed = 3889
	var data := MapGenerator.generate(settings)
	var counts := {}
	for terrain in data.cells:
		counts[terrain] = counts.get(terrain, 0) + 1
	var round_trees := 0
	var conifers := 0
	var occupied := {}
	for index in data.tree_cells.size():
		occupied[data.tree_cells[index]] = true
		if data.tree_variants[index] < 3:
			round_trees += 1
		else:
			conifers += 1
	var forest_floor_count: int = counts.get(TerrainMapData.Terrain.FOREST_FLOOR, 0)
	for y in data.rows:
		for x in data.columns:
			var cell := Vector2i(x, y)
			if data.terrain_at(cell) == TerrainMapData.Terrain.FOREST_FLOOR:
				assert(occupied.has(cell), "Forest floor without an occupying tree")
	assert(forest_floor_count > 0, "No qualifying forest-floor group generated")
	assert(round_trees > 0 and conifers > 0, "Forest is not mixed")
	print("terrain counts=", counts, " trees=", data.tree_cells.size(), " round=", round_trees, " conifer=", conifers)
	quit()
