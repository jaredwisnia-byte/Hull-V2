// Flat, toon-ramped surfaces with a painted grain, in the spirit of the GDD's
// art direction: flat-shaded forms, readable silhouettes, texture overlays.
shader_type spatial;
render_mode diffuse_toon, specular_disabled;

uniform vec3 albedo : source_color = vec3(0.8);
uniform vec3 albedo2 : source_color = vec3(0.6);
// 0 plain, 1 checker, 2 stripes, 3 floorboards, 4 brick, 5 floral, 6 grille
uniform int pattern = 0;
uniform float scale = 1.0;
uniform float grain = 0.07;
uniform vec3 emission_color : source_color = vec3(0.0);
uniform float emission_energy = 0.0;

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
	vec3 n = abs(wnorm);
	vec2 uv;
	if (n.y > 0.6) {
		uv = wpos.xz;
	} else if (n.x > n.z) {
		uv = wpos.zy;
	} else {
		uv = wpos.xy;
	}
	uv *= scale;
	vec3 c = albedo;
	if (pattern == 1) {
		float k = mod(floor(uv.x) + floor(uv.y), 2.0);
		c = mix(albedo, albedo2, k);
	} else if (pattern == 2) {
		c = mix(albedo, albedo2, step(0.5, fract(uv.x)));
	} else if (pattern == 3) {
		float row = floor(uv.y);
		float seg = floor(uv.x * 0.25 + hash(vec3(row, 1.0, 0.0)) * 7.0);
		c = mix(albedo, albedo2, hash(vec3(row, seg, 3.0)) * 0.8);
		c *= 1.0 - step(0.94, fract(uv.y)) * 0.45;
	} else if (pattern == 4) {
		vec2 b = vec2(uv.x / 0.215, uv.y / 0.075);
		b.x += mod(floor(b.y), 2.0) * 0.5;
		vec2 f = fract(b);
		float mortar = step(f.x, 0.05) + step(f.y, 0.13);
		vec3 brick = albedo * (0.82 + 0.3 * hash(vec3(floor(b), 5.0)));
		c = mix(brick, albedo2, clamp(mortar, 0.0, 1.0));
	} else if (pattern == 5) {
		vec2 cell = fract(uv) - 0.5;
		vec2 cell2 = fract(uv + 0.5) - 0.5;
		float flower = smoothstep(0.17, 0.12, length(cell)) + smoothstep(0.08, 0.05, length(cell2));
		c = mix(albedo, albedo2, clamp(flower, 0.0, 1.0));
	} else if (pattern == 6) {
		vec2 f = fract(uv);
		float bar = max(step(0.82, f.x), step(0.82, f.y));
		c = mix(albedo2, albedo, bar);
	}
	// Fade fine patterns to their average colour at a distance (no moire).
	float period = pattern == 4 ? 0.075 : 1.0;
	float fw = max(length(dFdx(uv)), length(dFdy(uv)));
	c = mix(c, mix(albedo, albedo2, pattern == 4 ? 0.25 : 0.4), smoothstep(0.2 * period, 0.55 * period, fw));
	float g = vnoise(wpos * 3.1) * 0.6 + vnoise(wpos * 13.0) * 0.4;
	c *= 1.0 + (g - 0.5) * grain * 2.0;
	ALBEDO = c;
	EMISSION = emission_color * emission_energy;
}
