class_name Geo
extends RefCounted
## Box-built geometry and the shared material palette.

const PAINT := preload("res://shaders/paint.gdshader")

## name: [albedo, albedo2, pattern, scale, grain]
const PALETTE := {
	"plaster_cream":   [Color(0.86, 0.80, 0.64), Color(0.80, 0.74, 0.58), 0, 1.0, 0.08],
	"wallpaper_green": [Color(0.55, 0.61, 0.46), Color(0.70, 0.66, 0.48), 5, 5.0, 0.06, {"grime": 0.5, "floor_grime": 0.4, "cracks": 0.4, "peel": 0.6, "stains": 0.5}],
	"wall_blue":       [Color(0.40, 0.54, 0.68), Color(0.36, 0.50, 0.63), 0, 1.0, 0.08, {"grime": 0.55, "floor_grime": 0.45, "cracks": 0.6, "peel": 0.5, "stains": 0.5}],
	"ceiling":         [Color(0.84, 0.82, 0.76), Color(0.85, 0.83, 0.77), 0, 1.0, 0.05, {"grime": 0.6, "cracks": 0.7, "stains": 0.9}],
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
	# Kitchen test pass: 1970s New York, Long Dark-style rendering.
	"linoleum_oct":    [Color(0.80, 0.64, 0.30), Color(0.93, 0.85, 0.62), 7, 5.5, 0.07, {"wear": 0.0, "grime": 0.35}],
	"tile_gold":       [Color(0.84, 0.66, 0.22), Color(0.95, 0.86, 0.55), 8, 6.6, 0.05, {"grime": 0.3, "floor_grime": 0.5}],
	# Painted tiles from assets/source_textures/<name>/tile.png (pattern 13); scale = 1 / repeat in metres.
	"wallpaper_teardrop": [Color(0.92, 0.9, 0.86), Color(0.8, 0.78, 0.74), 13, 1.25, 0.03, {"tex": "res://assets/source_textures/wallpaper_teardrop/tile.png", "grime": 0.45, "floor_grime": 0.4, "cracks": 0.35, "peel": 0.45, "stains": 0.45}],
	"plaster_kitchen": [Color(0.86, 0.82, 0.70), Color(0.80, 0.75, 0.62), 0, 1.0, 0.10, {"grime": 0.7, "floor_grime": 0.5, "cracks": 0.7, "peel": 0.5, "stains": 0.6}],
	"plaster_hall":    [Color(0.62, 0.58, 0.48), Color(0.45, 0.42, 0.35), 0, 1.0, 0.12, {"grime": 0.9, "floor_grime": 0.7, "cracks": 0.9, "peel": 0.8, "stains": 0.8}],
	"plaster_office":  [Color(0.72, 0.70, 0.60), Color(0.66, 0.64, 0.55), 0, 1.0, 0.10, {"grime": 0.6, "floor_grime": 0.45, "cracks": 0.6, "peel": 0.4, "stains": 0.5}],
	"wall_rose":       [Color(0.74, 0.58, 0.54), Color(0.66, 0.5, 0.46), 0, 1.0, 0.10, {"grime": 0.6, "floor_grime": 0.45, "cracks": 0.5, "peel": 0.5, "stains": 0.4}],
	"tile_hex":        [Color(0.88, 0.87, 0.82), Color(0.22, 0.22, 0.22), 7, 22.0, 0.05, {"grime": 0.6}],
	"tile_bath":       [Color(0.86, 0.88, 0.84), Color(0.72, 0.76, 0.74), 1, 6.6, 0.05, {"grime": 0.5, "floor_grime": 0.5}],
	"cabinet_paint":   [Color(0.90, 0.88, 0.80), Color(0.90, 0.88, 0.80), 0, 1.0, 0.05, {"wear": 0.9, "grime": 0.35}],
	"cabinet_wood":    [Color(0.40, 0.24, 0.13), Color(0.33, 0.19, 0.10), 11, 9.0, 0.06, {"wear": 0.7, "grime": 0.2}],
	"enamel_old":      [Color(0.92, 0.90, 0.83), Color(0.92, 0.90, 0.83), 0, 1.0, 0.04, {"wear": 0.6, "grime": 0.3}],
	"enamel_cream":    [Color(0.90, 0.86, 0.72), Color(0.90, 0.86, 0.72), 0, 1.0, 0.04, {"wear": 0.6, "grime": 0.3}],
	"formica_yellow":  [Color(0.90, 0.80, 0.45), Color(0.82, 0.70, 0.38), 12, 70.0, 0.04, {"wear": 0.5}],
	"chrome_worn":     [Color(0.70, 0.71, 0.72), Color(0.55, 0.56, 0.58), 0, 1.0, 0.05, {"wear": 0.9}],
	"vinyl_red":       [Color(0.62, 0.13, 0.10), Color(0.62, 0.13, 0.10), 0, 1.0, 0.05, {"wear": 0.9}],
	"paper_bag":       [Color(0.66, 0.50, 0.32), Color(0.58, 0.43, 0.26), 0, 1.0, 0.14, {"wear": 0.4}],
	"towel":           [Color(0.92, 0.90, 0.84), Color(0.75, 0.30, 0.20), 2, 12.0, 0.06, {}],
	"curtain_kitchen": [Color(0.94, 0.92, 0.84), Color(0.84, 0.66, 0.28), 5, 9.0, 0.05, {}],
	"curtain_doorway": [Color(0.82, 0.78, 0.68), Color(0.45, 0.32, 0.22), 10, 5.0, 0.07, {}],
	"jar_label_red":   [Color(0.75, 0.22, 0.14), Color(0.95, 0.85, 0.60), 2, 40.0, 0.05, {}],
	"jar_label_green": [Color(0.30, 0.50, 0.30), Color(0.95, 0.90, 0.70), 2, 40.0, 0.05, {}],
	"jar_lid":         [Color(0.85, 0.70, 0.30), Color(0.85, 0.70, 0.30), 0, 1.0, 0.04, {"wear": 0.8}],
	"can_tin":         [Color(0.70, 0.70, 0.68), Color(0.60, 0.60, 0.58), 2, 60.0, 0.05, {"wear": 0.6}],
	"soup_label":      [Color(0.78, 0.18, 0.12), Color(0.95, 0.92, 0.82), 0, 1.0, 0.04, {}],
	"clock_face":      [Color(0.95, 0.93, 0.86), Color(0.95, 0.93, 0.86), 0, 1.0, 0.03, {}],
	"phone_yellow":    [Color(0.88, 0.76, 0.36), Color(0.88, 0.76, 0.36), 0, 1.0, 0.04, {"wear": 0.6}],
	"cooler_red2":     [Color(0.66, 0.14, 0.10), Color(0.66, 0.14, 0.10), 0, 1.0, 0.05, {"wear": 0.9, "grime": 0.2}],
}

static var _cache := {}
static var _mesh_cache := {}
## When true, Geo.box makes bevelled boxes. The apartment builder turns it off
## for walls, floors and ceilings, which meet each other at sharp corners.
static var bevel := true


static func mat(name: String) -> Material:
	if _cache.has(name):
		return _cache[name]
	var m := ShaderMaterial.new()
	m.shader = PAINT
	var surf: Dictionary = surfaces().get(name, {})
	if not surf.is_empty() and not PALETTE.has(name):
		# A painted surface from data/surfaces.json (made by tools/make_tiles.py).
		m.set_shader_parameter("pattern", 13)
		m.set_shader_parameter("albedo", Color(1, 1, 1))
		m.set_shader_parameter("albedo2", Color(1, 1, 1))
		m.set_shader_parameter("scale", 1.0 / float(surf.get("repeat_m", 1.0)))
		m.set_shader_parameter("grain", 0.03)
		m.set_shader_parameter("tex_img", load(String(surf.file)))
		var wear: Dictionary = surf.get("wear", {})
		for k in wear:
			m.set_shader_parameter(k, wear[k])
		_cache[name] = m
		return m
	var p: Array = PALETTE.get(name, PALETTE["plaster_cream"])
	m.set_shader_parameter("albedo", p[0])
	m.set_shader_parameter("albedo2", p[1])
	m.set_shader_parameter("pattern", p[2])
	m.set_shader_parameter("scale", p[3])
	m.set_shader_parameter("grain", p[4])
	var extra: Dictionary = p[5] if p.size() > 5 else {}
	for k in extra:
		if k == "tex":
			m.set_shader_parameter("tex_img", load(String(extra[k])))
		else:
			m.set_shader_parameter(k, extra[k])
	_cache[name] = m
	return m


static var _surfaces := {}


## The painted surface catalogue (data/surfaces.json): floors, walls, carpets.
static func surfaces() -> Dictionary:
	if _surfaces.is_empty() and FileAccess.file_exists("res://data/surfaces.json"):
		var f := FileAccess.open("res://data/surfaces.json", FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if typeof(parsed) == TYPE_DICTIONARY:
			_surfaces = parsed
	return _surfaces


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
static func box(parent: Node3D, size: Vector3, center: Vector3, material: Variant, collide := true, radius := -1.0) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	if radius > 0.0:
		mi.mesh = rounded_box_mesh(size, radius, 3)
	elif bevel:
		var r := clampf(minf(size.x, minf(size.y, size.z)) * 0.22, 0.002, 0.03)
		mi.mesh = rounded_box_mesh(size, r)
	else:
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


## A box with rounded edges and corners. Vertices on the rounded bands carry
## vertex colour red = 0 so the shader can wear and highlight the edges, the
## way painted props in The Long Dark catch light along their bevels.
static func rounded_box_mesh(size: Vector3, radius: float, seg := 2) -> Mesh:
	var key := "%.4f_%.4f_%.4f_%.4f_%d" % [size.x, size.y, size.z, radius, seg]
	if _mesh_cache.has(key):
		return _mesh_cache[key]
	var h := size * 0.5
	var r := minf(radius, minf(h.x, minf(h.y, h.z)) * 0.98)
	var inner := h - Vector3(r, r, r)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	# Each face: normal axis, sign, and the two in-plane axes.
	var faces := [[0, 1, 1, 2], [0, -1, 2, 1], [1, 1, 2, 0], [1, -1, 0, 2], [2, 1, 0, 1], [2, -1, 1, 0]]
	for f in faces:
		var n_ax: int = f[0]
		var sgn: float = f[1]
		var u_ax: int = f[2]
		var v_ax: int = f[3]
		var cu := _band_coords(h[u_ax], r, seg)
		var cv := _band_coords(h[v_ax], r, seg)
		var face_n := Vector3.ZERO
		face_n[n_ax] = sgn
		for i in cu.size() - 1:
			for j in cv.size() - 1:
				var q := [
					_rb_point(n_ax, sgn * h[n_ax], u_ax, cu[i], v_ax, cv[j]),
					_rb_point(n_ax, sgn * h[n_ax], u_ax, cu[i + 1], v_ax, cv[j]),
					_rb_point(n_ax, sgn * h[n_ax], u_ax, cu[i + 1], v_ax, cv[j + 1]),
					_rb_point(n_ax, sgn * h[n_ax], u_ax, cu[i], v_ax, cv[j + 1]),
				]
				var verts: Array = []
				for p in q:
					verts.append(_rb_vertex(p, inner, r, face_n))
				# Godot treats clockwise triangles (seen from outside) as front faces.
				var a: Vector3 = verts[0][0]
				var b: Vector3 = verts[1][0]
				var c: Vector3 = verts[2][0]
				var flip := (b - a).cross(c - a).dot(face_n) > 0.0
				var order := [0, 2, 1, 0, 3, 2] if flip else [0, 1, 2, 0, 2, 3]
				for k in order:
					var vtx: Array = verts[k]
					st.set_color(vtx[2])
					st.set_normal(vtx[1])
					st.add_vertex(vtx[0])
	var mesh := st.commit()
	_mesh_cache[key] = mesh
	return mesh


static func _band_coords(hh: float, r: float, seg: int) -> Array:
	var out: Array = []
	for k in seg + 1:
		out.append(-hh + r * k / seg)
	for k in seg + 1:
		out.append(hh - r + r * k / seg)
	return out


static func _rb_point(n_ax: int, n_val: float, u_ax: int, u_val: float, v_ax: int, v_val: float) -> Vector3:
	var p := Vector3.ZERO
	p[n_ax] = n_val
	p[u_ax] = u_val
	p[v_ax] = v_val
	return p


## Returns [position, normal, colour] for a point on the unrounded box surface.
static func _rb_vertex(p: Vector3, inner: Vector3, r: float, face_n: Vector3) -> Array:
	var c := p.clamp(-inner, inner)
	var d := p - c
	var on_band := false
	for ax in 3:
		if absf(face_n[ax]) < 0.5 and absf(p[ax]) > inner[ax] + 1e-6:
			on_band = true
	if d.length() < 1e-7:
		return [p, face_n, Color(1, 1, 1)]
	var n := d.normalized()
	return [c + n * r, n, Color(0, 1, 1) if on_band else Color(1, 1, 1)]
