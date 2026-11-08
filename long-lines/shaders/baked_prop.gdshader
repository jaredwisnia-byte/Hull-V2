// Hero props modelled and baked in Blender (tools/build_*.py). The baked
// albedo already carries crevice grime, edge wear and dust; this keeps the
// same toon-ramped light as the rest of the apartment.
shader_type spatial;
render_mode diffuse_toon, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D orm_tex : hint_default_white, filter_linear_mipmap_anisotropic;
uniform float normal_strength = 1.0;
uniform float specular_amount = 0.4;
uniform float metal_amount = 0.55;

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb;
	vec3 orm = texture(orm_tex, UV).rgb;
	// Painted-metal look: keep chrome bright even where there is little to reflect.
	ROUGHNESS = orm.g;
	METALLIC = orm.b * metal_amount;
	ALBEDO = mix(ALBEDO, ALBEDO * 1.15 + vec3(0.04), orm.b * (1.0 - metal_amount));
	SPECULAR = specular_amount;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_strength;
}
