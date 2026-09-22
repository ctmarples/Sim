class_name MapGenerator
extends RefCounted


static func generate(settings: TerrainGenerationSettings) -> TerrainMapData:
	var result := TerrainMapData.new()
	result.configure(settings.columns, settings.rows, settings.cell_size)

	var noise := FastNoiseLite.new()
	noise.seed = settings.seed
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = settings.frequency
	noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	noise.fractal_octaves = settings.fractal_octaves
	noise.fractal_gain = 0.5
	noise.fractal_lacunarity = 2.0
	var biome_noise := _make_noise(settings.seed + 101, settings.biome_frequency, settings.fractal_octaves)

	for y in settings.rows:
		for x in settings.columns:
			var border_distance := mini(x, settings.columns - 1 - x)
			border_distance = mini(border_distance, mini(y, settings.rows - 1 - y))
			if border_distance < settings.grass_border_cells:
				continue
			var value := noise.get_noise_2d(float(x), float(y))
			var biome := biome_noise.get_noise_2d(float(x), float(y))
			var river_centre := settings.rows * 0.52 + sin(float(x) * 0.075 + settings.seed * 0.01) * settings.rows * 0.08
			var river_distance := absf(float(y) - river_centre)
			if river_distance <= settings.river_half_width_cells:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.RIVER)
			elif biome <= settings.water_threshold:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.WATER)
			elif biome >= settings.rock_threshold:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.ROCK)
			elif value >= settings.soil_threshold:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.SOIL)
			elif biome >= settings.meadow_threshold:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.MEADOW)

	_add_riparian_edges(result, settings.riparian_width_cells)
	_generate_mixed_forest(result, settings)

	if settings.height_enabled:
		var height_noise := FastNoiseLite.new()
		height_noise.seed = settings.seed + 7919
		height_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		height_noise.frequency = settings.height_frequency
		height_noise.fractal_type = FastNoiseLite.FRACTAL_FBM
		height_noise.fractal_octaves = 3
		for vertex_y in settings.rows + 1:
			for vertex_x in settings.columns + 1:
				var noise_value := height_noise.get_noise_2d(float(vertex_x), float(vertex_y))
				var height := settings.height_amplitude * smoothstep(-0.65, 0.75, noise_value)
				result.set_corner_height(Vector2i(vertex_x, vertex_y), height)
	return result


static func _make_noise(seed: int, frequency: float, octaves: int) -> FastNoiseLite:
	var generated := FastNoiseLite.new()
	generated.seed = seed
	generated.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	generated.frequency = frequency
	generated.fractal_type = FastNoiseLite.FRACTAL_FBM
	generated.fractal_octaves = octaves
	generated.fractal_gain = 0.5
	generated.fractal_lacunarity = 2.0
	return generated


static func _add_riparian_edges(data: TerrainMapData, width: float) -> void:
	var radius := ceili(width)
	var shoreline: Array[Vector2i] = []
	for y in data.rows:
		for x in data.columns:
			var cell := Vector2i(x, y)
			if data.terrain_at(cell) == TerrainMapData.Terrain.WATER or data.terrain_at(cell) == TerrainMapData.Terrain.RIVER:
				continue
			var near_water := false
			for oy in range(-radius, radius + 1):
				for ox in range(-radius, radius + 1):
					if Vector2(ox, oy).length() > width:
						continue
					var nearby := data.terrain_at(cell + Vector2i(ox, oy))
					if nearby == TerrainMapData.Terrain.WATER or nearby == TerrainMapData.Terrain.RIVER:
						near_water = true
			if near_water:
				shoreline.append(cell)
	for cell in shoreline:
		data.set_terrain(cell, TerrainMapData.Terrain.RIPARIAN)


static func _generate_mixed_forest(data: TerrainMapData, settings: TerrainGenerationSettings) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = settings.seed + 211
	var occupied := {}
	var cluster_count := settings.forest_cluster_count if settings.forest_cluster_count > 0 else maxi(3, data.columns / 10)
	for _cluster in cluster_count:
		var centre := Vector2i(rng.randi_range(3, data.columns - 4), rng.randi_range(3, data.rows - 4))
		for oy in range(-3, 4):
			for ox in range(-3, 4):
				var cell := centre + Vector2i(ox, oy)
				if _forest_cell_excluded(cell, settings) or occupied.has(cell):
					continue
				var terrain := data.terrain_at(cell)
				if terrain in [TerrainMapData.Terrain.WATER, TerrainMapData.Terrain.RIVER, TerrainMapData.Terrain.RIPARIAN, TerrainMapData.Terrain.ROCK]:
					continue
				# Original generator establishes a coherent soil clearing below canopy.
				if rng.randf() < 0.85:
					data.set_terrain(cell, TerrainMapData.Terrain.SOIL)
				var distance := maxi(absi(ox), absi(oy))
				var chance := 0.90 if distance <= 1 else (0.70 if distance <= 2 else 0.45)
				if rng.randf() < chance:
					occupied[cell] = true
	# Match the original's three small mixed clumps outside the large forests.
	for _clump in 3:
		var centre := Vector2i(rng.randi_range(2, data.columns - 3), rng.randi_range(2, data.rows - 3))
		for oy in range(-1, 2):
			for ox in range(-1, 2):
				var cell := centre + Vector2i(ox, oy)
				if not _forest_cell_excluded(cell, settings) and not occupied.has(cell) and rng.randf() < 0.5:
					var terrain := data.terrain_at(cell)
					if terrain in [TerrainMapData.Terrain.GRASS, TerrainMapData.Terrain.MEADOW, TerrainMapData.Terrain.SOIL]:
						occupied[cell] = true
	var cells: Array[Vector2i] = []
	for cell: Vector2i in occupied:
		cells.append(cell)
	cells.sort_custom(func(a: Vector2i, b: Vector2i) -> bool: return a.y < b.y or (a.y == b.y and a.x < b.x))
	for cell in cells.slice(0, settings.maximum_trees):
		data.tree_cells.append(cell)
		# Per-tree family selection produces mixed deciduous/conifer clusters.
		var family_offset := 0 if rng.randf() < 0.55 else 3
		data.tree_variants.append(family_offset + rng.randi_range(0, 2))
	_apply_forest_floor_components(data, settings.minimum_forest_floor_trees)


static func _forest_cell_excluded(cell: Vector2i, settings: TerrainGenerationSettings) -> bool:
	for area in settings.forest_exclusion_rects:
		if area.has_point(cell):
			return true
	return false


static func _apply_forest_floor_components(data: TerrainMapData, minimum_size: int) -> void:
	var occupied := {}
	for cell in data.tree_cells:
		occupied[cell] = true
	var visited := {}
	for start in data.tree_cells:
		if visited.has(start):
			continue
		var component: Array[Vector2i] = []
		var pending: Array[Vector2i] = [start]
		visited[start] = true
		while not pending.is_empty():
			var cell: Vector2i = pending.pop_back()
			component.append(cell)
			for offset: Vector2i in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
				var neighbour: Vector2i = cell + offset
				if occupied.has(neighbour) and not visited.has(neighbour):
					visited[neighbour] = true
					pending.append(neighbour)
		if component.size() >= minimum_size:
			for cell in component:
				data.set_terrain(cell, TerrainMapData.Terrain.FOREST_FLOOR)
