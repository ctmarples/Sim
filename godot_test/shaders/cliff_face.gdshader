shader_type canvas_item;
render_mode unshaded;

float cliff_hash(vec2 point) {
	return fract(sin(dot(floor(point), vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
	float grain = cliff_hash(FRAGCOORD.xy * 0.32) - 0.5;
	float vertical = mix(1.08, 0.72, UV.y);
	vec3 rock = vec3(112.0, 94.0, 76.0) / 255.0;
	rock *= vertical + grain * 0.12;
	COLOR = vec4(rock, 1.0);
}
