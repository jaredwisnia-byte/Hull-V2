// Screen-space grade: teal shadows, warm highlights, a soft vignette and film
// grain, after the Long Dark references.
shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform vec3 shadow_tint = vec3(0.9, 1.0, 1.06);
uniform vec3 highlight_tint = vec3(1.08, 1.0, 0.86);
uniform float contrast = 1.1;
uniform float saturation = 1.0;
uniform float vignette = 0.55;
uniform float grain = 0.035;

void fragment() {
	vec3 c = texture(screen_tex, SCREEN_UV).rgb;
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(vec3(l), c, saturation);
	c = (c - 0.5) * contrast + 0.5;
	c *= mix(shadow_tint, highlight_tint, smoothstep(0.08, 0.65, l));
	vec2 d = (SCREEN_UV - 0.5) * vec2(1.0, 0.8);
	c *= 1.0 - vignette * smoothstep(0.25, 0.75, length(d));
	float n = fract(sin(dot(SCREEN_UV * 1000.0 + fract(TIME) * 37.0, vec2(12.9898, 78.233))) * 43758.5453);
	c += (n - 0.5) * grain;
	COLOR = vec4(clamp(c, 0.0, 1.0), 1.0);
}
