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

	for y in settings.rows:
		for x in settings.columns:
			var border_distance := mini(x, settings.columns - 1 - x)
			border_distance = mini(border_distance, mini(y, settings.rows - 1 - y))
			if border_distance < settings.grass_border_cells:
				continue
			var value := noise.get_noise_2d(float(x), float(y))
			if value >= settings.soil_threshold:
				result.set_terrain(Vector2i(x, y), TerrainMapData.Terrain.SOIL)

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
