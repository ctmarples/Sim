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
	return result
