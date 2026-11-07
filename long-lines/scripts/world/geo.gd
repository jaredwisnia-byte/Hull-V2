class_name Geo
extends RefCounted
## Box-built geometry and the shared material palette.

const PAINT := preload("res://shaders/paint.gdshader")

## name: [albedo, albedo2, pattern, scale, grain]
const PALETTE := {
	"plaster_cream":   [Color(0.86, 0.80, 0.64), Color(0.80, 0.74, 0.58), 0, 1.0, 0.08],
	"wallpaper_green": [Color(0.55, 0.61, 0.46), Color(0.70, 0.66, 0.48), 5, 5.0, 0.06],
	"wall_blue":       [Color(0.40, 0.54, 0.68), Color(0.36, 0.50, 0.63), 0, 1.0, 0.08],
	"ceiling":         [Color(0.88, 0.86, 0.80), Color(0.85, 0.83, 0.77), 0, 1.0, 0.05],
	"boards":          [Color(0.46, 0.31, 0.19), Color(0.33, 0.21, 0.12), 3, 6.6, 0.07],
	"linoleum":        [Color(0.83, 0.81, 0.74), Color(0.20, 0.30, 0.28), 1, 3.3, 0.05],
	"brick":           [Color(0.52, 0.25, 0.18), Color(0.60, 0.57, 0.52), 4, 1.0, 0.10],
	"brick_dark":      [Color(0.36, 0.20, 0.16), Color(0.45, 0.42, 0.38), 4, 1.0, 0.10],
	"brownstone":      [Color(0.42, 0.30, 0.24), Color(0.38, 0.27, 0.21), 0, 1.0, 0.12],
	"trim":            [Color(0.90, 0.88, 0.82), Color(0.90, 0.88, 0.82), 0, 1.0, 0.04],
	"trim_dark":       [Color(0.30, 0.22, 0.16), Color(0.30, 0.22, 0.16), 0, 1.0, 0.04],
	"wood_dark":       [Color(0.31, 0.20, 0.12), Color(0.31, 0.20, 0.12), 0, 1.0, 0.08],
	"wood_mid":        [Color(0.52, 0.36, 0.22), Color(0.52, 0.36, 0.22), 0, 1.0, 0.08],
	"wood_light":      [Color(0.70, 0.55, 0.36), Color(0.70, 0.55, 0.36), 0, 1.0, 0.06],
	"slipcover":       [Color(0.68, 0.58, 0.40), Color(0.60, 0.49, 0.32), 2, 9.0, 0.05],
	"armchair":        [Color(0.45, 0.30, 0.22), Color(0.40, 0.26, 0.19), 0, 1.0, 0.08],
	"bedspread":       [Color(0.80, 0.62, 0.62), Color(0.95, 0.90, 0.72), 5, 6.0, 0.05],
	"pillow":          [Color(0.92, 0.91, 0.86), Color(0.92, 0.91, 0.86), 0, 1.0, 0.03],
	"rug":             [Color(0.50, 0.18, 0.15), Color(0.62, 0.48, 0.25), 5, 3.0, 0.08],
	"enamel":          [Color(0.92, 0.91, 0.86), Color(0.92, 0.91, 0.86), 0, 1.0, 0.03],
	"enamel_yellow":   [Color(0.86, 0.80, 0.52), Color(0.86, 0.80, 0.52), 0, 1.0, 0.03],
	"chrome":          [Color(0.72, 0.73, 0.75), Color(0.72, 0.73, 0.75), 0, 1.0, 0.02],
	"iron":            [Color(0.12, 0.12, 0.13), Color(0.12, 0.12, 0.13), 0, 1.0, 0.06],
	"grille":          [Color(0.13, 0.13, 0.14), Color(0.13, 0.13, 0.14), 6, 12.0, 0.04],
	"radiator":        [Color(0.68, 0.67, 0.62), Color(0.55, 0.54, 0.50), 2, 22.0, 0.05],
	"tv_screen":       [Color(0.16, 0.19, 0.18), Color(0.16, 0.19, 0.18), 0, 1.0, 0.02],
	"black":           [Color(0.06, 0.06, 0.06), Color(0.06, 0.06, 0.06), 0, 1.0, 0.02],
	"paper":           [Color(0.90, 0.88, 0.80), Color(0.90, 0.88, 0.80), 0, 1.0, 0.04],
	"newsprint":       [Color(0.80, 0.78, 0.70), Color(0.30, 0.30, 0.30), 2, 40.0, 0.04],
	"cooler_red":      [Color(0.70, 0.16, 0.12), Color(0.70, 0.16, 0.12), 0, 1.0, 0.04],
	"radio_case":      [Color(0.20, 0.32, 0.34), Color(0.20, 0.32, 0.34), 0, 1.0, 0.04],
	"pumpkin":         [Color(0.88, 0.44, 0.08), Color(0.70, 0.32, 0.05), 2, 14.0, 0.06],
	"pumpkin_soft":    [Color(0.66, 0.38, 0.12), Color(0.52, 0.30, 0.10), 2, 14.0, 0.10],
	"pumpkin_rot":     [Color(0.36, 0.30, 0.16), Color(0.25, 0.25, 0.18), 2, 14.0, 0.16],
	"stem":            [Color(0.30, 0.36, 0.16), Color(0.30, 0.36, 0.16), 0, 1.0, 0.06],
	"wax":             [Color(0.93, 0.90, 0.80), Color(0.93, 0.90, 0.80), 0, 1.0, 0.02],
	"coat":            [Color(0.20, 0.22, 0.30), Color(0.20, 0.22, 0.30), 0, 1.0, 0.08],
	"asphalt":         [Color(0.17, 0.17, 0.18), Color(0.17, 0.17, 0.18), 0, 1.0, 0.10],
	"sidewalk":        [Color(0.50, 0.49, 0.46), Color(0.40, 0.39, 0.37), 1, 0.7, 0.08],
	"window_dark":     [Color(0.07, 0.08, 0.10), Color(0.07, 0.08, 0.10), 0, 1.0, 0.04],
	"water_tower":     [Color(0.36, 0.26, 0.18), Color(0.30, 0.21, 0.14), 2, 8.0, 0.08],
	"car_cream":       [Color(0.86, 0.80, 0.62), Color(0.86, 0.80, 0.62), 0, 1.0, 0.03],
	"car_green":       [Color(0.22, 0.38, 0.30), Color(0.22, 0.38, 0.30), 0, 1.0, 0.03],
	"car_yellow":      [Color(0.92, 0.72, 0.12), Color(0.92, 0.72, 0.12), 0, 1.0, 0.03],
	"car_brown":       [Color(0.40, 0.26, 0.16), Color(0.40, 0.26, 0.16), 0, 1.0, 0.03],
	"tire":            [Color(0.08, 0.08, 0.08), Color(0.08, 0.08, 0.08), 0, 1.0, 0.03],
	"skeleton_paper":  [Color(0.95, 0.94, 0.88), Color(0.95, 0.94, 0.88), 0, 1.0, 0.02],
}

static var _cache := {}


static func mat(name: String) -> Material:
	if _cache.has(name):
		return _cache[name]
	var m := ShaderMaterial.new()
	m.shader = PAINT
	var p: Array = PALETTE.get(name, PALETTE["plaster_cream"])
	m.set_shader_parameter("albedo", p[0])
	m.set_shader_parameter("albedo2", p[1])
	m.set_shader_parameter("pattern", p[2])
	m.set_shader_parameter("scale", p[3])
	m.set_shader_parameter("grain", p[4])
	_cache[name] = m
	return m


static func emissive(color: Color, energy: float) -> Material:
	var key := "emit_%s_%.2f" % [color.to_html(), energy]
	if _cache.has(key):
		return _cache[key]
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color * energy
	_cache[key] = m
	return m


static func glass() -> Material:
	if _cache.has("glass"):
		return _cache["glass"]
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_color = Color(0.72, 0.80, 0.84, 0.16)
	m.roughness = 0.1
	m.metallic_specular = 0.8
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	_cache["glass"] = m
	return m


## Adds a box mesh to `parent` centred at `center` (local). If `collide`, a box
## collision shape is added to the nearest CollisionObject3D (parent itself, or
## a new StaticBody3D child of parent).
static func box(parent: Node3D, size: Vector3, center: Vector3, material: Variant, collide := true) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.position = center
	if material is String:
		mi.material_override = mat(material)
	elif material is Material:
		mi.material_override = material
		if material == _cache.get("glass") or (material is StandardMaterial3D and material.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED):
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(mi)
	if collide:
		add_box_shape(parent, size, center)
	return mi


static func add_box_shape(parent: Node3D, size: Vector3, center: Vector3) -> void:
	var body: Node3D = parent
	if not (parent is CollisionObject3D):
		body = StaticBody3D.new()
		parent.add_child(body)
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	cs.shape = shape
	cs.position = center
	body.add_child(cs)


static func cylinder(parent: Node3D, radius: float, height: float, center: Vector3, material: Variant, collide := false, sides := 14) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = radius
	cm.bottom_radius = radius
	cm.height = height
	cm.radial_segments = sides
	cm.rings = 1
	mi.mesh = cm
	mi.position = center
	mi.material_override = mat(material) if material is String else material
	parent.add_child(mi)
	if collide:
		add_box_shape(parent, Vector3(radius * 2, height, radius * 2), center)
	return mi


static func sphere(parent: Node3D, radius: float, center: Vector3, material: Variant, squash := 1.0) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = radius
	sm.height = radius * 2.0 * squash
	sm.radial_segments = 16
	sm.rings = 8
	mi.mesh = sm
	mi.position = center
	mi.material_override = mat(material) if material is String else material
	parent.add_child(mi)
	return mi


static func label3d(parent: Node3D, text: String, pos: Vector3, size := 0.02, color := Color(0.1, 0.1, 0.1)) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.position = pos
	l.pixel_size = size * 0.01
	l.font_size = 64
	l.modulate = color
	l.outline_size = 0
	l.shaded = true
	l.double_sided = false
	parent.add_child(l)
	return l
