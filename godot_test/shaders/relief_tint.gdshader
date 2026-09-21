shader_type canvas_item;
render_mode unshaded;

uniform sampler2D relief_corner_map : filter_linear, repeat_disable;
uniform vec2 terrain_origin = vec2(0.0);
uniform vec2 terrain_grid_size = vec2(1.0);
uniform float terrain_cell_size = 40.0;
uniform vec2 projection_offset = vec2(0.0);
varying vec2 relief_canvas_position;

void vertex() {
	relief_canvas_position = (MODEL_MATRIX * vec4(VERTEX, 0.0, 1.0)).xy;
}

void fragment() {
	vec4 source = texture(TEXTURE, UV) * COLOR;
	vec3 colour = source.rgb;
	vec2 logical_position = relief_canvas_position - terrain_origin;
	logical_position -= projection_offset;
	vec2 corner_coordinate = logical_position / terrain_cell_size;
	vec2 relief_uv = (corner_coordinate + vec2(0.5)) / (terrain_grid_size + vec2(1.0));
	float relief_shade = texture(relief_corner_map, clamp(relief_uv, vec2(0.0), vec2(1.0))).r;
	if (relief_shade >= 1.0) {
		float highlight = clamp((relief_shade - 1.0) / 0.10, 0.0, 1.0) * 0.10;
		colour = mix(colour, vec3(248.0, 228.0, 175.0) / 255.0, highlight);
	} else {
		float shadow = clamp((1.0 - relief_shade) / 0.28, 0.0, 1.0) * 0.25;
		colour = mix(colour, vec3(72.0, 46.0, 28.0) / 255.0, shadow);
	}
	COLOR = vec4(colour, source.a);
}
