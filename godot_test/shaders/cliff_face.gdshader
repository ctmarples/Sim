shader_type canvas_item;
render_mode unshaded;

float cliff_hash(vec2 point) {
	return fract(sin(dot(floor(point), vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
	// UV is supplied in terrain-pixel units by TerrainRenderer. Unlike
	// FRAGCOORD, it remains attached to the cliff while the camera moves.
	vec2 cliff_pixel = floor(UV);
	float grain = cliff_hash(cliff_pixel) - 0.5;
	float vertical_amount = 1.0 - exp(-max(UV.y, 0.0) / 24.0);
	float vertical = mix(1.08, 0.72, vertical_amount);
	vec3 rock = vec3(112.0, 94.0, 76.0) / 255.0;
	rock *= vertical + grain * 0.12;
	COLOR = vec4(rock, 1.0);
}
