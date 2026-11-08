// Stylized painted surfaces in the spirit of the GDD's art direction (and the
// Long Dark references): toon-ramped light, painted grain, worn edges that
// catch the light, grime that gathers low on walls and in blotches.
shader_type spatial;
render_mode diffuse_toon, specular_schlick_ggx;

uniform vec3 albedo : source_color = vec3(0.8);
uniform vec3 albedo2 : source_color = vec3(0.6);
// 0 plain, 1 checker, 2 stripes, 3 floorboards, 4 brick, 5 floral, 6 grille,
// 7 octagon linoleum, 8 ornamental tile, 10 flame-stitch zigzag,
// 11 wood grain, 12 formica speckle
uniform int pattern = 0;
uniform float scale = 1.0;
uniform float grain = 0.07;
uniform float wear = 0.0;         // lighten and chip bevelled edges
uniform float grime = 0.0;        // low-frequency dirty blotches
uniform float floor_grime = 0.0;  // darkening near the floor (walls)
uniform float cracks = 0.0;       // hairline plaster cracks
uniform float peel = 0.0;         // patches where paint has flaked to the coat below
uniform float stains = 0.0;       // brown water stains (ceilings, upper walls)
uniform float roughness_v = 0.85;
uniform vec3 emission_color : source_color = vec3(0.0);
uniform float emission_energy = 0.0;

varying vec3 wpos;
varying vec3 wnorm;
varying float edge;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnorm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	edge = 1.0 - COLOR.r;
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

float fbm(vec3 p) {
	return vnoise(p) * 0.55 + vnoise(p * 2.1) * 0.3 + vnoise(p * 4.3) * 0.15;
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
	float line = 0.0;
	if (pattern == 1) {
		c = mix(albedo, albedo2, mod(floor(uv.x) + floor(uv.y), 2.0));
	} else if (pattern == 2) {
		c = mix(albedo, albedo2, step(0.5, fract(uv.x)));
	} else if (pattern == 3) {
		float row = floor(uv.y);
		float seg = floor(uv.x * 0.25 + hash(vec3(row, 1.0, 0.0)) * 7.0);
		c = mix(albedo, albedo2, hash(vec3(row, seg, 3.0)) * 0.8);
		c *= 1.0 - (vnoise(vec3(uv.x * 0.6, uv.y * 9.0, 2.0)) - 0.5) * 0.25;
		c *= 1.0 - step(0.94, fract(uv.y)) * 0.5;
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
		c = mix(albedo2, albedo, max(step(0.82, f.x), step(0.82, f.y)));
	} else if (pattern == 7) {
		// Octagons with small squares between them, like 1970s sheet vinyl.
		vec2 f = fract(uv) - 0.5;
		vec2 a = abs(f);
		float oct = max(max(a.x, a.y), (a.x + a.y) * 0.7071);
		float inside = step(oct, 0.43);
		c = mix(albedo2, albedo, inside);
		c = mix(c, albedo * 0.9 + vec3(0.03), step(0.30, oct) * inside * 0.5);
		line = smoothstep(0.415, 0.43, oct) * (1.0 - smoothstep(0.44, 0.455, oct));
	} else if (pattern == 8) {
		// Ornamental glazed tile with grout.
		vec2 f = fract(uv) - 0.5;
		vec2 a = abs(f);
		float diamond = step(a.x + a.y, 0.32);
		float ring = step(abs(length(f) - 0.2), 0.035);
		float corner = step(0.36, min(a.x, a.y));
		c = mix(albedo, albedo2, clamp(diamond * 0.6 + ring + corner, 0.0, 1.0));
		c = mix(c, albedo * 0.7, step(a.x + a.y, 0.1));
		line = step(0.47, max(a.x, a.y));
		c *= 1.0 + 0.15 * (1.0 - smoothstep(0.0, 0.45, length(f + vec2(0.15, -0.15))));
	} else if (pattern == 10) {
		// Flame-stitch zigzag upholstery / curtains.
		float z = abs(fract(uv.x * 2.0) - 0.5) * 0.6;
		float band = fract(uv.y * 3.0 + z);
		c = mix(albedo, albedo2, step(0.55, band));
		c = mix(c, albedo2 * 0.6, step(0.85, band));
	} else if (pattern == 11) {
		// Wood grain.
		float g = vnoise(vec3(uv.x * 0.15, uv.y * 4.0, 0.0)) + vnoise(vec3(uv.x * 0.5, uv.y * 14.0, 3.0)) * 0.5;
		c = mix(albedo, albedo2, smoothstep(0.4, 1.2, g));
	} else if (pattern == 12) {
		// Formica speckle.
		float s1 = step(0.93, hash(vec3(floor(uv * 1.0), 1.0)));
		c = mix(albedo, albedo2, s1 * 0.8);
	}
	// Fade fine patterns to their average colour at a distance (no moire).
	float period = pattern == 4 ? 0.075 : 1.0;
	float fw = max(length(dFdx(uv)), length(dFdy(uv)));
	float far = smoothstep(0.2 * period, 0.55 * period, fw);
	c = mix(c, mix(albedo, albedo2, pattern == 4 ? 0.25 : 0.4), far);
	c *= 1.0 - line * 0.35 * (1.0 - far);

	// Painted grain.
	float g = vnoise(wpos * 3.1) * 0.6 + vnoise(wpos * 13.0) * 0.4;
	c *= 1.0 + (g - 0.5) * grain * 2.0;

	// Grime: blotches, and a dirty band low on walls.
	if (grime > 0.0) {
		float bl = fbm(wpos * 1.7 + vec3(3.0));
		c *= 1.0 - grime * 0.35 * smoothstep(0.45, 0.85, bl);
		float drip = fbm(vec3(wpos.x * 6.0, wpos.y * 0.6, wpos.z * 6.0));
		c *= 1.0 - grime * 0.12 * smoothstep(0.5, 0.9, drip);
	}
	if (floor_grime > 0.0 && n.y < 0.5) {
		float h = fract(wpos.y / 3.0 + 1000.0) * 3.0; // height above this storey's floor
		float low = 1.0 - smoothstep(0.0, 0.7, h + (vnoise(wpos * 4.0) - 0.5) * 0.25);
		c *= 1.0 - floor_grime * 0.35 * low;
	}

	// Old plaster: flaking paint, hairline cracks, water stains from the flat above.
	if (peel > 0.0) {
		float pn = fbm(wpos * 2.3 + vec3(11.0));
		float patch = smoothstep(0.66, 0.7, pn) * step(0.0, 1.0 - n.y);
		vec3 under = mix(vec3(0.78, 0.74, 0.64), c, 0.25);
		c = mix(c, under, patch * peel);
		c *= 1.0 - (smoothstep(0.64, 0.66, pn) - smoothstep(0.66, 0.68, pn)) * peel * 0.5;
	}
	if (cracks > 0.0) {
		float cn = abs(fbm(wpos * 1.4 + vec3(5.0)) - 0.5);
		float cn2 = abs(vnoise(wpos * 6.0) - 0.5);
		float crack = (1.0 - smoothstep(0.0, 0.006, cn)) * smoothstep(0.55, 0.75, fbm(wpos * 0.7));
		crack += (1.0 - smoothstep(0.0, 0.01, cn2)) * smoothstep(0.7, 0.85, fbm(wpos * 0.5 + vec3(3.0))) * 0.6;
		c *= 1.0 - clamp(crack, 0.0, 1.0) * cracks * 0.6;
	}
	if (stains > 0.0) {
		float h2 = fract(wpos.y / 3.0 + 1000.0) * 3.0;
		float sn = fbm(wpos * 0.9 + vec3(21.0));
		float near_top = smoothstep(1.6, 2.7, h2) + step(0.6, n.y) * 0.0 + step(n.y, -0.6);
		float blot = smoothstep(0.58, 0.62, sn) * clamp(near_top, 0.0, 1.0);
		float ring = (smoothstep(0.58, 0.6, sn) - smoothstep(0.6, 0.63, sn)) * clamp(near_top, 0.0, 1.0);
		c = mix(c, c * vec3(0.82, 0.7, 0.5), blot * stains * 0.6);
		c = mix(c, c * vec3(0.55, 0.42, 0.28), ring * stains);
	}
	if (floor_grime > 0.0 && n.y < 0.5) {
		// Scuffs where furniture and feet hit the wall.
		float h3 = fract(wpos.y / 3.0 + 1000.0) * 3.0;
		float sc = step(0.82, vnoise(vec3(wpos.x * 8.0, h3 * 30.0, wpos.z * 8.0))) * (1.0 - smoothstep(0.1, 0.9, h3));
		c *= 1.0 - sc * floor_grime * 0.25;
	}

	// Worn, light-catching edges on bevels.
	float rough = roughness_v;
	if (wear > 0.0 && edge > 0.01) {
		float chip = vnoise(wpos * 38.0);
		float w = edge * wear;
		c = mix(c, c * 1.25 + vec3(0.06), w * 0.55);
		c = mix(c, c * 0.55, w * step(0.78, chip) * 0.6);
		rough -= w * 0.3;
	}
	ALBEDO = clamp(c, 0.0, 1.0);
	ROUGHNESS = rough;
	SPECULAR = 0.25;
	EMISSION = emission_color * emission_energy;
}
