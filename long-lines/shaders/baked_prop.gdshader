// Hero props modelled and baked in Blender (tools/build_props.py, tools/factory.py).
// The baked albedo carries crevice grime, edge wear and dust; this keeps the same
// toon-ramped light as the apartment.
//
// Condition variants without new geometry: the same model can be shown new, aged,
// wrecked or snowed under by setting `condition` and `snow` (per placement in the
// layout JSON: "condition": 0.6, "snow": 1.0).
shader_type spatial;
render_mode diffuse_toon, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap_anisotropic;
uniform float normal_strength = 1.0;
uniform float specular_amount = 0.4;
uniform float metal_amount = 0.55;
uniform float condition : hint_range(0.0, 1.0) = 0.0;  // 0 as baked, 1 derelict
uniform float snow : hint_range(0.0, 1.0) = 0.0;       // snow on upward faces
uniform float frost : hint_range(0.0, 1.0) = 0.0;      // pale rime everywhere

varying vec3 wpos;
varying vec3 wnorm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnorm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float hash(vec3 p) {
	return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453);
}

float vnoise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = mix(hash(i), hash(i + vec3(1, 0, 0)), f.x);
	float b = mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x);
	float c = mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x);
	float d = mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x);
	return mix(mix(a, b, f.y), mix(c, d, f.y), f.z);
}

void fragment() {
	vec3 c = texture(albedo_tex, UV).rgb;
	vec3 orm = texture(orm_tex, UV).rgb;
	float rough = orm.g;
	float metal = orm.b * metal_amount;
	c = mix(c, c * 1.15 + vec3(0.04), orm.b * (1.0 - metal_amount));
	if (condition > 0.0) {
		float n = vnoise(wpos * 6.0) * 0.6 + vnoise(wpos * 23.0) * 0.4;
		float l = dot(c, vec3(0.299, 0.587, 0.114));
		c = mix(c, vec3(l) * vec3(1.02, 0.98, 0.9), condition * 0.6);          // sun-faded
		c *= 1.0 - condition * 0.45 * smoothstep(0.45, 0.8, n);                // grime blotches
		vec3 rust = vec3(0.35, 0.17, 0.08);
		c = mix(c, rust * (0.7 + n * 0.5), orm.b * condition * smoothstep(0.4, 0.7, n)); // rust on metal
		rough = mix(rough, 0.95, condition * 0.7);
		metal *= 1.0 - condition * 0.8;
	}
	float up = smoothstep(0.55, 0.85, wnorm.y);
	float s = snow * up * smoothstep(0.25, 0.55, vnoise(wpos * 9.0) + snow * 0.5);
	c = mix(c, vec3(0.88, 0.9, 0.94), clamp(s + frost * 0.35, 0.0, 1.0));
	rough = mix(rough, 0.8, s);
	ALBEDO = c;
	ROUGHNESS = rough;
	METALLIC = metal * (1.0 - s);
	SPECULAR = specular_amount;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_strength * (1.0 - s * 0.7);
}
