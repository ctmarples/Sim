shader_type canvas_item;
render_mode unshaded;

// Direct GPU translation of terrain_mottle.sample_mottle for grass.
// Parameters are from assets/terrain/sets/default.json.
const vec3 BASE = vec3(90.0, 150.0, 70.0) / 255.0;
const float COARSE_SCALE = 0.035;
const float MID_SCALE = 0.11;
const float FINE_SCALE = 0.38;
const float COARSE_AMP = 0.0864;
const float MID_AMP = 0.096;
const float FINE_AMP = 0.07;
const float PALETTE_MIX = 0.4;
const float SPECKLE = 0.15;
const float SALT = 1954.0; // 1000 + GRASS(3)*97 + seed(51)*13

// terrain_mottle.palette_for deliberately takes the first 48 entries from
// grass_palette.json. Keep this list in precisely the same order.
const vec3 PALETTE[48] = {
	vec3(105.0,183.0,80.0)/255.0, vec3(97.0,158.0,111.0)/255.0,
	vec3(114.0,188.0,91.0)/255.0, vec3(92.0,148.0,95.0)/255.0,
	vec3(96.0,124.0,70.0)/255.0, vec3(35.0,151.0,82.0)/255.0,
	vec3(79.0,142.0,65.0)/255.0, vec3(68.0,146.0,1.0)/255.0,
	vec3(96.0,113.0,57.0)/255.0, vec3(91.0,146.0,98.0)/255.0,
	vec3(99.0,145.0,73.0)/255.0, vec3(119.0,136.0,103.0)/255.0,
	vec3(102.0,158.0,83.0)/255.0, vec3(87.0,102.0,49.0)/255.0,
	vec3(100.0,156.0,62.0)/255.0, vec3(81.0,143.0,79.0)/255.0,
	vec3(68.0,112.0,50.0)/255.0, vec3(79.0,152.0,65.0)/255.0,
	vec3(74.0,152.0,69.0)/255.0, vec3(95.0,166.0,89.0)/255.0,
	vec3(93.0,176.0,75.0)/255.0, vec3(105.0,151.0,91.0)/255.0,
	vec3(96.0,151.0,40.0)/255.0, vec3(93.0,128.0,72.0)/255.0,
	vec3(94.0,161.0,67.0)/255.0, vec3(107.0,160.0,85.0)/255.0,
	vec3(89.0,151.0,84.0)/255.0, vec3(79.0,131.0,81.0)/255.0,
	vec3(61.0,122.0,60.0)/255.0, vec3(65.0,117.0,72.0)/255.0,
	vec3(92.0,128.0,58.0)/255.0, vec3(99.0,188.0,102.0)/255.0,
	vec3(108.0,172.0,82.0)/255.0, vec3(104.0,161.0,87.0)/255.0,
	vec3(111.0,181.0,106.0)/255.0, vec3(96.0,187.0,78.0)/255.0,
	vec3(90.0,151.0,82.0)/255.0, vec3(63.0,111.0,12.0)/255.0,
	vec3(43.0,101.0,51.0)/255.0, vec3(80.0,161.0,64.0)/255.0,
	vec3(92.0,126.0,63.0)/255.0, vec3(83.0,136.0,78.0)/255.0,
	vec3(106.0,144.0,92.0)/255.0, vec3(90.0,165.0,60.0)/255.0,
	vec3(119.0,182.0,106.0)/255.0, vec3(82.0,146.0,88.0)/255.0,
	vec3(66.0,137.0,63.0)/255.0, vec3(44.0,173.0,52.0)/255.0
};

const vec3 SOIL_BASE = vec3(139.0,105.0,70.0)/255.0;
const vec3 SOIL_PALETTE[48] = {
	vec3(103.0,78.0,55.0)/255.0, vec3(128.0,104.0,81.0)/255.0,
	vec3(142.0,113.0,84.0)/255.0, vec3(137.0,105.0,75.0)/255.0,
	vec3(143.0,114.0,85.0)/255.0, vec3(128.0,97.0,68.0)/255.0,
	vec3(136.0,105.0,75.0)/255.0, vec3(133.0,101.0,70.0)/255.0,
	vec3(105.0,80.0,56.0)/255.0, vec3(121.0,94.0,69.0)/255.0,
	vec3(145.0,116.0,89.0)/255.0, vec3(142.0,112.0,84.0)/255.0,
	vec3(147.0,119.0,93.0)/255.0, vec3(140.0,112.0,83.0)/255.0,
	vec3(131.0,100.0,69.0)/255.0, vec3(124.0,94.0,66.0)/255.0,
	vec3(119.0,92.0,67.0)/255.0, vec3(144.0,116.0,88.0)/255.0,
	vec3(148.0,121.0,95.0)/255.0, vec3(146.0,117.0,90.0)/255.0,
	vec3(134.0,102.0,71.0)/255.0, vec3(137.0,106.0,76.0)/255.0,
	vec3(137.0,109.0,83.0)/255.0, vec3(134.0,103.0,72.0)/255.0,
	vec3(126.0,96.0,67.0)/255.0, vec3(122.0,93.0,65.0)/255.0,
	vec3(140.0,110.0,81.0)/255.0, vec3(141.0,112.0,84.0)/255.0,
	vec3(129.0,98.0,68.0)/255.0, vec3(125.0,95.0,66.0)/255.0,
	vec3(112.0,85.0,59.0)/255.0, vec3(142.0,113.0,85.0)/255.0,
	vec3(139.0,109.0,80.0)/255.0, vec3(135.0,103.0,73.0)/255.0,
	vec3(128.0,98.0,68.0)/255.0, vec3(132.0,101.0,70.0)/255.0,
	vec3(138.0,107.0,77.0)/255.0, vec3(144.0,114.0,87.0)/255.0,
	vec3(141.0,112.0,83.0)/255.0, vec3(123.0,93.0,65.0)/255.0,
	vec3(132.0,100.0,70.0)/255.0, vec3(110.0,84.0,59.0)/255.0,
	vec3(125.0,99.0,75.0)/255.0, vec3(119.0,93.0,67.0)/255.0,
	vec3(137.0,107.0,77.0)/255.0, vec3(130.0,99.0,69.0)/255.0,
	vec3(107.0,81.0,57.0)/255.0, vec3(136.0,104.0,74.0)/255.0
};

varying vec2 terrain_world_position;
varying float terrain_relief_shade;
uniform sampler2D soil_corner_map : filter_nearest, repeat_disable;
uniform sampler2D height_corner_map : filter_nearest, repeat_disable;
uniform sampler2D relief_corner_map : filter_linear, repeat_disable;
uniform ivec2 terrain_grid_size = ivec2(12, 8);
uniform float terrain_cell_size = 100.0;
uniform float height_lift_pixels = 1.0;
uniform float terrain_max_height = 32.0;

void vertex() {
	// Preserve flat logical coordinates before the mesh is height-projected so
	// terrain texture scale and terrain boundaries do not stretch with relief.
	terrain_world_position = VERTEX;
	ivec2 corner = clamp(ivec2(round(VERTEX / terrain_cell_size)), ivec2(0), terrain_grid_size);
	float h = texelFetch(height_corner_map, corner, 0).r;
	float he = texelFetch(height_corner_map, min(corner + ivec2(1, 0), terrain_grid_size), 0).r;
	float hw = texelFetch(height_corner_map, max(corner - ivec2(1, 0), ivec2(0)), 0).r;
	float hs = texelFetch(height_corner_map, min(corner + ivec2(0, 1), terrain_grid_size), 0).r;
	float hn = texelFetch(height_corner_map, max(corner - ivec2(0, 1), ivec2(0)), 0).r;
	float gx = (he - hw) * 0.5;
	float gy = (hs - hn) * 0.5;
	float lit = (gx - gy * 0.35) / 1.35 / max(8.0, terrain_max_height * 0.15);
	float response = lit * 0.28 * 4.0;
	if (response < 0.0) {
		response *= 1.5;
	}
	terrain_relief_shade = clamp(1.0 + response, 0.55, 1.10);
	VERTEX.y -= h * height_lift_pixels;
}

float hash_2d(ivec2 cell, int salt) {
	// Bit-for-bit equivalent to terrain_mottle._hash01 for 32-bit coordinates.
	uint n = uint(cell.x) * 374761393u;
	n = n ^ (uint(cell.y) * 668265263u);
	n = n ^ (uint(salt) * 1274126177u);
	n = (n ^ (n >> 13u)) * 1274126177u;
	n = n ^ (n >> 16u);
	return float(n & 0x7fffffffu) / 2147483647.0;
}

float value_noise(vec2 point, int salt) {
	ivec2 cell = ivec2(floor(point));
	vec2 fraction = fract(point);
	vec2 blend = fraction * fraction * (3.0 - 2.0 * fraction);
	float top = mix(hash_2d(cell, salt), hash_2d(cell + ivec2(1, 0), salt), blend.x);
	float bottom = mix(hash_2d(cell + ivec2(0, 1), salt), hash_2d(cell + ivec2(1), salt), blend.x);
	return mix(top, bottom, blend.y);
}

vec3 palette_colour(float selection) {
	return PALETTE[int(floor(selection * 48.0)) % 48];
}

vec3 soil_palette_colour(float selection) {
	return SOIL_PALETTE[int(floor(selection * 48.0)) % 48];
}

vec3 shift_colour(vec3 base, float amount) {
	return amount >= 0.0 ? mix(base, vec3(1.0), amount) : base * (1.0 + amount);
}

vec3 sample_grass(vec2 world) {
	float coarse = value_noise(world * COARSE_SCALE, int(SALT));
	const mat2 MID_ROTATION = mat2(vec2(0.7986355, 0.6018150), vec2(-0.6018150, 0.7986355));
	const mat2 FINE_ROTATION = mat2(vec2(0.3255682, 0.9455186), vec2(-0.9455186, 0.3255682));
	float middle = value_noise((MID_ROTATION * world) * MID_SCALE, int(SALT) + 3);
	float fine = value_noise((FINE_ROTATION * world) * FINE_SCALE, int(SALT) + 7);

	float shade = (coarse - 0.5) * 2.0 * COARSE_AMP;
	shade += (middle - 0.5) * 2.0 * MID_AMP;
	shade += (fine - 0.5) * 2.0 * FINE_AMP;
	vec3 colour = shift_colour(BASE, shade);

	float mix_field = smoothstep(0.0, 1.0, 0.35 + 0.55 * coarse + 0.15 * (middle - 0.5));
	vec3 palette = palette_colour(hash_2d(ivec2(floor(world / 2.0)), int(SALT) + 21));
	colour = mix(colour, palette, clamp(PALETTE_MIX * mix_field, 0.0, 1.0));

	if (hash_2d(ivec2(floor(world)), int(SALT) + 40) > 1.0 - SPECKLE) {
		vec3 speck = palette_colour(hash_2d(ivec2(floor(world)), int(SALT) + 41));
		colour = mix(colour, speck, 0.55);
	}
	return colour;
}

vec3 sample_soil(vec2 world) {
	const int salt = 1318; // 1000 + SOIL(1)*97 + seed(17)*13
	const mat2 MID_ROTATION = mat2(vec2(0.7986355, 0.6018150), vec2(-0.6018150, 0.7986355));
	const mat2 FINE_ROTATION = mat2(vec2(0.3255682, 0.9455186), vec2(-0.9455186, 0.3255682));
	float coarse = value_noise(world * 0.035, salt);
	float middle = value_noise((MID_ROTATION * world) * 0.11, salt + 3);
	float fine = value_noise((FINE_ROTATION * world) * 0.38, salt + 7);
	float shade = (coarse - 0.5) * 2.0 * 0.22;
	shade += (middle - 0.5) * 2.0 * 0.12;
	shade += (fine - 0.5) * 2.0 * 0.07;
	vec3 colour = shift_colour(SOIL_BASE, shade);
	float mix_field = smoothstep(0.0, 1.0, 0.35 + 0.55 * coarse + 0.15 * (middle - 0.5));
	vec3 palette = soil_palette_colour(hash_2d(ivec2(floor(world / 2.0)), salt + 21));
	colour = mix(colour, palette, clamp(0.65 * mix_field, 0.0, 1.0));
	if (hash_2d(ivec2(world), salt + 40) > 0.86) {
		colour = mix(colour, soil_palette_colour(hash_2d(ivec2(world), salt + 41)), 0.55);
	}
	return colour;
}

float soil_at_corner(ivec2 vertex) {
	ivec2 safe_vertex = clamp(vertex, ivec2(0), terrain_grid_size);
	return texelFetch(soil_corner_map, safe_vertex, 0).r;
}

void fragment() {
	vec2 world = floor(terrain_world_position);
	ivec2 cell = ivec2(floor(world / terrain_cell_size));
	vec2 local_uv = fract(world / terrain_cell_size);
	float top = mix(soil_at_corner(cell), soil_at_corner(cell + ivec2(1, 0)), local_uv.x);
	float bottom = mix(soil_at_corner(cell + ivec2(0, 1)), soil_at_corner(cell + ivec2(1, 1)), local_uv.x);
	float field = mix(top, bottom, local_uv.y);
	// Exact soft land-to-land band used by compose_cell_fills.
	float soil_blend = clamp((field - 0.08) / 0.84, 0.0, 1.0);
	soil_blend = soil_blend * soil_blend * (3.0 - 2.0 * soil_blend);
	vec3 colour = mix(sample_grass(world), sample_soil(world), soil_blend);
	vec2 relief_coordinate = terrain_world_position / terrain_cell_size;
	vec2 relief_uv = (relief_coordinate + vec2(0.5)) / (vec2(terrain_grid_size) + vec2(1.0));
	float visible_relief_shade = texture(relief_corner_map, clamp(relief_uv, vec2(0.0), vec2(1.0))).r;
	if (visible_relief_shade >= 1.0) {
		float highlight = clamp((visible_relief_shade - 1.0) / 0.10, 0.0, 1.0) * 0.10;
		colour = mix(colour, vec3(248.0, 228.0, 175.0) / 255.0, highlight);
	} else {
		float shadow = clamp((1.0 - visible_relief_shade) / 0.28, 0.0, 1.0) * 0.25;
		colour = mix(colour, vec3(72.0, 46.0, 28.0) / 255.0, shadow);
	}
	COLOR = vec4(colour, 1.0);
}
