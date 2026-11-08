class_name ApartmentBuilder
extends RefCounted
## Builds the apartment shell, its windows and door, the fire escape, the
## airshaft, and a dressed slice of Sullivan Street outside, all from
## data/apartment.json.


var d: Dictionary
var W: float
var D: float
var H: float
var street_y: float
var root: Node3D
var cars: Array = []      # [{lights: Array[Node3D], spot: SpotLight3D}]
var window_lights: Array = []  # cool fill light spilling in from each window


func _init(data: Dictionary) -> void:
	d = data
	W = float(d.width)
	D = float(d.depth)
	H = float(d.height)
	street_y = -float(d.floor_y_above_street)


func build(parent: Node3D) -> Node3D:
	root = Node3D.new()
	root.name = "Apartment"
	parent.add_child(root)
	Geo.bevel = false
	_floors_and_ceiling()
	_outer_walls()
	_partitions()
	_wainscots()
	_trim()
	_reflection_probes()
	Geo.bevel = true
	_fire_escape()
	Geo.bevel = false
	_exterior()
	_street()
	Geo.bevel = true
	return root


## One reflection probe per room, so chrome and glass reflect the room.
func _reflection_probes() -> void:
	for r in d.rooms:
		var rx := _rx(r)
		var z0 := float(r.z0)
		var z1 := float(r.z1)
		var p := ReflectionProbe.new()
		p.name = "Probe_" + String(r.id)
		p.size = Vector3(rx[1] - rx[0], H, z1 - z0)
		p.position = Vector3((rx[0] + rx[1]) * 0.5, H * 0.5, (z0 + z1) * 0.5)
		p.box_projection = true
		p.interior = true
		p.ambient_mode = ReflectionProbe.AMBIENT_DISABLED
		p.update_mode = ReflectionProbe.UPDATE_ONCE
		p.intensity = 0.6
		root.add_child(p)


## Rooms carry an optional x range (x0, x1); sub-rooms such as a closet or a
## bathroom sit inside a main room's footprint and take precedence there.
func _rx(r: Dictionary) -> Array:
	return [float(r.get("x0", 0.0)), float(r.get("x1", W))]


func _is_sub(r: Dictionary) -> bool:
	return r.has("x0") or r.has("x1")


func _room_at(z: float, x := -1.0) -> Dictionary:
	if x >= 0.0:
		for r in d.rooms:
			var rx := _rx(r)
			if _is_sub(r) and z >= float(r.z0) - 0.06 and z <= float(r.z1) + 0.06 and x >= rx[0] - 0.06 and x <= rx[1] + 0.06:
				return r
	for r in d.rooms:
		if not _is_sub(r) and z >= float(r.z0) - 0.06 and z <= float(r.z1) + 0.06:
			return r
	return d.rooms[0]


func _room_by_id(id: String) -> Dictionary:
	for r in d.rooms:
		if r.id == id:
			return r
	return d.rooms[0]


func _floors_and_ceiling() -> void:
	var body := StaticBody3D.new()
	body.name = "Shell"
	root.add_child(body)
	for r in d.rooms:
		var rx := _rx(r)
		var z0 := float(r.z0) - 0.05
		var z1 := float(r.z1) + 0.05
		var lift := 0.003 if _is_sub(r) else 0.0
		Geo.box(body, Vector3(rx[1] - rx[0] + (0.0 if _is_sub(r) else 0.0), 0.2, z1 - z0),
			Vector3((rx[0] + rx[1]) * 0.5, -0.1 + lift, (z0 + z1) * 0.5), String(r.floor), not _is_sub(r))
	Geo.box(body, Vector3(W + 0.5, 0.25, D + 0.5), Vector3(W * 0.5, H + 0.125, D * 0.5), "ceiling")


## A straight wall with rectangular openings. axis "x": runs along x at
## z = fixed, thickness extends in out_dir. axis "z": runs along z at x = fixed.
func wall_run(body: Node3D, axis: String, fixed: float, out_dir: float, thickness: float,
		a0: float, a1: float, openings: Array, material: String, offset := 0.0, top := -1.0) -> void:
	var hmax := H if top < 0.0 else top
	var ops := openings.duplicate()
	ops.sort_custom(func(p, q): return float(p.a) < float(q.a))
	var cursor := a0
	var mid := fixed + out_dir * (offset + thickness * 0.5)
	var pieces: Array = []  # [a, b, y0, y1]
	for op in ops:
		var oa := maxf(float(op.a), a0)
		var ob := minf(float(op.b), a1)
		if ob <= a0 or oa >= a1:
			continue
		if oa > cursor:
			pieces.append([cursor, oa, 0.0, hmax])
		if float(op.y0) > 0.0:
			pieces.append([oa, ob, 0.0, minf(float(op.y0), hmax)])
		if float(op.y1) < hmax:
			pieces.append([oa, ob, float(op.y1), hmax])
		cursor = ob
	if cursor < a1:
		pieces.append([cursor, a1, 0.0, hmax])
	for p in pieces:
		var len: float = p[1] - p[0]
		var hgt: float = p[3] - p[2]
		var c := (float(p[0]) + float(p[1])) * 0.5
		var cy := (float(p[2]) + float(p[3])) * 0.5
		if axis == "x":
			Geo.box(body, Vector3(len, hgt, thickness), Vector3(c, cy, mid), material)
		else:
			Geo.box(body, Vector3(thickness, hgt, len), Vector3(mid, cy, c), material)

## Splits one outer wall into stretches by the room behind each stretch.
## side: front/back run along x; left/right run along z.
func _wall_stretches(side: String) -> Array:
	var along_x := side == "front" or side == "back"
	var fixed := 0.0
	match side:
		"back":
			fixed = D
		"right":
			fixed = W
	var length := W if along_x else D
	var cuts := [0.0, length]
	for r in d.rooms:
		var rx := _rx(r)
		if along_x:
			cuts.append(rx[0])
			cuts.append(rx[1])
		else:
			cuts.append(float(r.z0) - 0.05)
			cuts.append(float(r.z1) + 0.05)
	var pts: Array = []
	for c in cuts:
		var v := clampf(float(c), 0.0, length)
		if not pts.any(func(q): return absf(q - v) < 0.02):
			pts.append(v)
	pts.sort()
	var out: Array = []
	for i in pts.size() - 1:
		var a: float = pts[i]
		var b: float = pts[i + 1]
		var mid := (a + b) * 0.5
		var r: Dictionary
		if along_x:
			r = _room_at(clampf(fixed, 0.01, D - 0.01), mid)
		else:
			r = _room_at(mid, clampf(fixed, 0.01, W - 0.01))
		out.append([a, b, r])
	return out


func _outer_walls() -> void:
	var body := StaticBody3D.new()
	body.name = "Walls"
	root.add_child(body)
	var ops: Dictionary = d.openings
	var paint := 0.03
	var brick := 0.25
	for st in _wall_stretches("front"):
		wall_run(body, "x", 0.0, -1.0, paint, st[0], st[1], ops.front, String(st[2].wall))
	for st in _wall_stretches("back"):
		wall_run(body, "x", D, 1.0, paint, st[0], st[1], ops.back, String(st[2].wall))
	for st in _wall_stretches("left"):
		wall_run(body, "z", 0.0, -1.0, paint, st[0], st[1], ops.left, String(st[2].wall))
	for st in _wall_stretches("right"):
		wall_run(body, "z", W, 1.0, paint, st[0], st[1], ops.right, String(st[2].wall))
	wall_run(body, "x", 0.0, -1.0, brick, -0.25, W + 0.25, ops.front, "brick", paint)
	wall_run(body, "x", D, 1.0, brick, -0.25, W + 0.25, ops.back, "plaster_hall", paint)
	wall_run(body, "z", 0.0, -1.0, brick, -0.25, D + 0.25, ops.left, "brick", paint)
	wall_run(body, "z", W, 1.0, brick, -0.25, D + 0.25, ops.right, "brick", paint)

	for side in ["front", "right", "back", "left"]:
		for op in ops[side]:
			Geo.bevel = true
			if op.kind == "window":
				_window(side, op)
			elif op.kind == "door":
				_hall_door(side, op)
			Geo.bevel = false


## Interior walls: {"axis": "x" (runs along x at z = at) or "z" (along z at x = at),
## "at", "from", "to", "doorways": [[a, b, top], ...], "a": room on the low side,
## "b": room on the high side, "door": optional library door for each doorway}.
func _partitions() -> void:
	var body := StaticBody3D.new()
	body.name = "Partitions"
	root.add_child(body)
	for p in d.get("walls", []):
		var axis := String(p.axis)
		var at := float(p.at)
		var a0 := float(p.get("from", 0.0))
		var a1 := float(p.get("to", W if axis == "x" else D))
		var ops: Array = []
		for dw in p.get("doorways", []):
			ops.append({"a": dw[0], "b": dw[1], "y0": 0.0, "y1": dw[2]})
		var ra := _room_by_id(String(p.a))
		var rb := _room_by_id(String(p.b))
		wall_run(body, axis, at, -1.0, 0.05, a0, a1, ops, String(ra.wall))
		wall_run(body, axis, at, 1.0, 0.05, a0, a1, ops, String(rb.wall))
		for dw in p.get("doorways", []):
			var mid := (float(dw[0]) + float(dw[1])) * 0.5
			var pos := Vector3(mid, 0, at) if axis == "x" else Vector3(at, 0, mid)
			var rot := 0.0 if axis == "x" else PI * 0.5
			var casing := PropFactory.baked_prop("door_casing")
			if casing:
				casing.position = pos
				casing.rotation.y = rot
				root.add_child(casing)
			if dw.size() > 3 and String(dw[3]) != "":
				var door := PropFactory.baked_prop(String(dw[3]))
				if door:
					# Hung open against the wall on the low side.
					var hinge := float(dw[0]) + 0.02
					door.position = (Vector3(hinge, 0, at - 0.03) if axis == "x" else Vector3(at - 0.03, 0, hinge))
					door.rotation.y = rot + PI * 0.5 + 0.25
					door.position += (Vector3(0, 0, -0.38) if axis == "x" else Vector3(-0.38, 0, 0))
					root.add_child(door)


## Glazed tile up the lower part of a room's walls (kitchen, bathroom), with a cap.
func _wainscots() -> void:
	var body := StaticBody3D.new()
	body.name = "Wainscot"
	root.add_child(body)
	var ops: Dictionary = d.openings
	var t := 0.012
	for r in d.rooms:
		if not r.has("wainscot"):
			continue
		var ws: Dictionary = r.wainscot
		var top := float(ws.height)
		var m := String(ws.material)
		var rx := _rx(r)
		var z0 := float(r.z0)
		var z1 := float(r.z1)
		if rx[0] <= 0.01:
			wall_run(body, "z", 0.0, 1.0, t, z0, z1, ops.left, m, 0.0, top)
		if rx[1] >= W - 0.01:
			wall_run(body, "z", W, -1.0, t, z0, z1, ops.right, m, 0.0, top)
		if z1 >= D - 0.01:
			wall_run(body, "x", D, -1.0, t, rx[0], rx[1], ops.back, m, 0.0, top)
		if z0 <= 0.01:
			wall_run(body, "x", 0.0, 1.0, t, rx[0], rx[1], ops.front, m, 0.0, top)
		for p in d.get("walls", []):
			var ops2: Array = []
			for dw in p.get("doorways", []):
				ops2.append({"a": dw[0], "b": dw[1], "y0": 0.0, "y1": dw[2]})
			var axis := String(p.axis)
			var at := float(p.at)
			var a0 := maxf(float(p.get("from", 0.0)), rx[0] if axis == "x" else z0)
			var a1 := minf(float(p.get("to", W if axis == "x" else D)), rx[1] if axis == "x" else z1)
			if a1 <= a0:
				continue
			if String(p.b) == String(r.id):
				wall_run(body, axis, at + 0.05, 1.0, t, a0, a1, ops2, m, 0.0, top)
			if String(p.a) == String(r.id):
				wall_run(body, axis, at - 0.05, -1.0, t, a0, a1, ops2, m, 0.0, top)



func _trim() -> void:
	var n := Node3D.new()
	n.name = "Trim"
	root.add_child(n)
	# Baseboards on the long side walls.
	for x in [0.012, W - 0.012]:
		Geo.box(n, Vector3(0.025, 0.12, D), Vector3(x, 0.06, D * 0.5), "trim_dark", false)


# ------------------------------------------------------------ windows and door

func _window(side: String, op: Dictionary) -> void:
	var a := float(op.a)
	var b := float(op.b)
	var y0 := float(op.y0)
	var y1 := float(op.y1)
	var w := b - a
	var h := y1 - y0
	var half := h * 0.5
	var frame := Node3D.new()
	frame.name = String(op.id) + "_frame"
	root.add_child(frame)
	# Place a local frame where +x runs along the wall and -z faces outside.
	var basis := Basis.IDENTITY
	var origin := Vector3.ZERO
	match side:
		"front":
			origin = Vector3((a + b) * 0.5, y0, -0.14)
		"right":
			basis = Basis(Vector3.UP, -PI * 0.5)
			origin = Vector3(W + 0.14, y0, (a + b) * 0.5)
		"left":
			basis = Basis(Vector3.UP, PI * 0.5)
			origin = Vector3(-0.14, y0, (a + b) * 0.5)
	frame.transform = Transform3D(basis, origin)

	# Frame and sill (sill sticks into the room). Its collider belongs to the
	# window body below, so aiming at the sill offers the window's actions.
	Geo.box(frame, Vector3(w + 0.12, 0.05, 0.36), Vector3(0, 0.005, 0.1), "trim", false)
	Geo.box(frame, Vector3(0.06, h, 0.3), Vector3(-w * 0.5 - 0.03, half, 0.0), "trim", false)
	Geo.box(frame, Vector3(0.06, h, 0.3), Vector3(w * 0.5 + 0.03, half, 0.0), "trim", false)
	Geo.box(frame, Vector3(w + 0.12, 0.06, 0.3), Vector3(0, h + 0.03, 0.0), "trim", false)

	# Upper sash, fixed.
	var upper := StaticBody3D.new()
	frame.add_child(upper)
	upper.position = Vector3(0, half, -0.04)
	_sash_geometry(upper, w, half)

	# Lower sash, the interactable one.
	var win := WindowSash.new()
	win.name = String(op.id)
	win.persist_id = String(op.id)
	win.opening_id = String(op.id)
	win.outside = String(op.get("outside", "airshaft"))
	win.display_name = "window"
	win.lift = half - 0.04
	frame.add_child(win)
	win.position = Vector3(0, 0, 0.03)
	var sash := Node3D.new()
	win.add_child(sash)
	_sash_geometry(sash, w, half)
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(w, half, 0.05)
	cs.shape = shape
	cs.position = Vector3(0, half * 0.5, 0)
	win.add_child(cs)
	win.sash = sash
	win.shape = cs
	Geo.add_box_shape(win, Vector3(w + 0.12, 0.05, 0.36), Vector3(0, 0.005, 0.07))
	var into := frame.transform.basis * Vector3(0, 0, 1)
	var center := frame.transform.origin
	# Soft daylight spilling in through the window: cool, broad, no shadows.
	var fill := SpotLight3D.new()
	fill.light_color = Color(0.62, 0.72, 0.9)
	fill.spot_range = 5.0
	fill.spot_angle = 85.0
	fill.spot_angle_attenuation = 0.35
	fill.spot_attenuation = 1.2
	fill.light_energy = 0.0
	fill.shadow_enabled = false
	fill.light_specular = 0.1
	root.add_child(fill)
	var fp := center + into * 0.25 + Vector3(0, h * 0.75, 0)
	fill.look_at_from_position(fp, fp + into + Vector3(0, -0.6, 0), Vector3.UP)
	window_lights.append({"light": fill, "outside": String(op.get("outside", "")), "area": w * h})
	win.climb_in_point = Vector3(center.x, 0.05, center.z) + into * 0.75
	win.climb_out_point = Vector3(center.x, 0.05, center.z) - into * 0.55


func _sash_geometry(parent: Node3D, w: float, h: float) -> void:
	Geo.box(parent, Vector3(w, h, 0.012), Vector3(0, h * 0.5, 0), Geo.glass(), parent is CollisionObject3D)
	Geo.box(parent, Vector3(w, 0.045, 0.045), Vector3(0, 0.0225, 0), "trim", false)
	Geo.box(parent, Vector3(w, 0.035, 0.045), Vector3(0, h - 0.0175, 0), "trim", false)
	Geo.box(parent, Vector3(0.035, h, 0.045), Vector3(-w * 0.5 + 0.0175, h * 0.5, 0), "trim", false)
	Geo.box(parent, Vector3(0.035, h, 0.045), Vector3(w * 0.5 - 0.0175, h * 0.5, 0), "trim", false)

## The apartment door (a library model) and, behind it, the stair landing.
func _hall_door(_side: String, op: Dictionary) -> void:
	var a := float(op.a)
	var b := float(op.b)
	var door := HallDoor.new()
	door.name = "hall_door"
	door.persist_id = "hall_door"
	door.display_name = "door"
	root.add_child(door)
	door.position = Vector3(a + 0.02, 0, D + 0.03)
	door.hinge_open = -1.2
	var leaf := Node3D.new()
	leaf.position = Vector3(0, 0, 0)
	door.add_child(leaf)
	var model := PropFactory.baked_prop("door_entry_4a")
	if model:
		model.rotation.y = PI  # its inside face (police lock) toward the apartment
		model.position = Vector3((b - a) * 0.5 - 0.02, 0, 0)
		leaf.add_child(model)
	else:
		Geo.box(leaf, Vector3(b - a, float(op.y1), 0.05), Vector3((b - a) * 0.5, float(op.y1) * 0.5, 0), "wood_mid", false)
	door.leaf = leaf
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(b - a, float(op.y1), 0.06)
	cs.shape = bs
	cs.position = Vector3((b - a) * 0.5, float(op.y1) * 0.5, 0)
	door.add_child(cs)
	var casing := PropFactory.baked_prop("door_casing")
	if casing:
		casing.position = Vector3((a + b) * 0.5, 0, D + 0.12)
		root.add_child(casing)
	_landing(a, b)


## The fourth-floor landing outside 4A: hall tile, a neighbour's door, the stair down.
func _landing(a: float, b: float) -> void:
	var n := StaticBody3D.new()
	n.name = "Landing"
	root.add_child(n)
	var z0 := D + 0.28
	var z1 := z0 + 2.4
	Geo.bevel = false
	Geo.box(n, Vector3(W + 1.0, 0.2, z1 - z0), Vector3(W * 0.5, -0.1, (z0 + z1) * 0.5), "tile_hex")
	Geo.box(n, Vector3(W + 1.0, 0.2, z1 - z0), Vector3(W * 0.5, H + 0.1, (z0 + z1) * 0.5), "ceiling")
	Geo.box(n, Vector3(W + 1.0, H, 0.2), Vector3(W * 0.5, H * 0.5, z1 + 0.1), "plaster_hall")
	Geo.box(n, Vector3(0.2, H, z1 - z0), Vector3(-0.6, H * 0.5, (z0 + z1) * 0.5), "plaster_hall")
	Geo.box(n, Vector3(0.2, H, z1 - z0), Vector3(W + 0.6, H * 0.5, (z0 + z1) * 0.5), "plaster_hall")
	Geo.bevel = true
	var other := PropFactory.baked_prop("door_entry_4b")
	if other:
		other.position = Vector3(0.6, 0, z1 - 0.03)
		other.rotation.y = PI
		root.add_child(other)
	var stair := PropFactory.baked_prop("stair_flight")
	if stair:
		stair.position = Vector3(W - 0.35, 0, z0 + 0.6)
		stair.rotation.y = PI * 0.5
		root.add_child(stair)
	var lamp := OmniLight3D.new()
	lamp.position = Vector3(W * 0.5, H - 0.3, (z0 + z1) * 0.5)
	lamp.light_color = Color(0.7, 0.75, 0.85)
	lamp.light_energy = 0.15
	lamp.omni_range = 4.0
	root.add_child(lamp)


# ------------------------------------------------------------ fire escape and outside

func _fire_escape() -> void:
	var fe: Dictionary = d.fire_escape
	var x0 := float(fe.x0)
	var x1 := float(fe.x1)
	var z0 := float(fe.z0)
	var z1 := float(fe.z1) - 0.25
	var body := StaticBody3D.new()
	body.name = "FireEscape"
	root.add_child(body)
	var cx := (x0 + x1) * 0.5
	var cz := (z0 + z1) * 0.5
	Geo.box(body, Vector3(x1 - x0, 0.03, z1 - z0), Vector3(cx, -0.015, cz), "grille")
	# Railing: top rail and posts.
	var rail_h := 1.0
	Geo.box(body, Vector3(x1 - x0, 0.04, 0.04), Vector3(cx, rail_h, z0), "iron")
	Geo.box(body, Vector3(0.04, 0.04, z1 - z0), Vector3(x0, rail_h, cz), "iron")
	Geo.box(body, Vector3(0.04, 0.04, z1 - z0), Vector3(x1, rail_h, cz), "iron")
	Geo.box(body, Vector3(x1 - x0, 0.03, 0.03), Vector3(cx, 0.5, z0), "iron", false)
	for i in 9:
		var x := lerpf(x0, x1, i / 8.0)
		Geo.box(body, Vector3(0.025, rail_h, 0.025), Vector3(x, rail_h * 0.5, z0), "iron", false)
	for side_x in [x0, x1]:
		Geo.box(body, Vector3(0.025, rail_h, 0.025), Vector3(side_x, rail_h * 0.5, cz), "iron", false)
	# Invisible guard so nobody falls off the edge.
	Geo.add_box_shape(body, Vector3(x1 - x0, 1.6, 0.05), Vector3(cx, 0.8, z0 - 0.03))
	Geo.add_box_shape(body, Vector3(0.05, 1.6, z1 - z0), Vector3(x0 - 0.03, 0.8, cz))
	Geo.add_box_shape(body, Vector3(0.05, 1.6, z1 - z0), Vector3(x1 + 0.03, 0.8, cz))
	# Drop ladder hatch and a ladder to the platform below.
	Geo.box(body, Vector3(0.5, 0.035, 0.45), Vector3(x1 - 0.4, 0.0, cz), "iron", false)
	for k in 2:
		Geo.box(body, Vector3(0.03, 3.0, 0.03), Vector3(x1 - 0.6 + k * 0.4, -1.5, cz), "iron", false)
	for level in [-3.0, -6.0]:
		Geo.box(body, Vector3(x1 - x0, 0.03, z1 - z0), Vector3(cx, level, cz), "grille", false)
		Geo.box(body, Vector3(x1 - x0, 0.04, 0.04), Vector3(cx, level + rail_h, z0), "iron", false)
	Geo.box(body, Vector3(x1 - x0, 0.03, z1 - z0), Vector3(cx, 3.0, cz), "grille", false)

func _exterior() -> void:
	var n := StaticBody3D.new()
	n.name = "Facade"
	root.add_child(n)
	var top := H + 3.6
	var front_z := -0.28 - 0.06
	# Our building's face around the apartment.
	Geo.box(n, Vector3(8.0, top - street_y, 0.3), Vector3(-4.25, (top + street_y) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(8.0, top - street_y, 0.3), Vector3(W + 4.25, (top + street_y) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(W + 0.5, -0.2 - street_y, 0.3), Vector3(W * 0.5, (street_y - 0.2) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(W + 0.5, top - H - 0.25, 0.3), Vector3(W * 0.5, (top + H + 0.25) * 0.5, front_z + 0.15), "brick")
	# Airshaft: a brick wall 1.2 m from the side windows, with the neighbours' windows.
	Geo.box(n, Vector3(0.3, top - street_y, D + 1.0), Vector3(W + 0.25 + 1.2 + 0.15, (top + street_y) * 0.5, D * 0.5), "brick_dark")
	for floor_i in range(-3, 2):
		for zz in [5.2, 8.0, 10.8]:
			Geo.box(n, Vector3(0.02, 1.2, 0.7), Vector3(W + 0.25 + 1.19, floor_i * 3.0 + 1.6, zz), "window_dark", false)


## Sullivan Street below, assembled from library parts: facade bays, cornices,
## shopfronts, street furniture and cars. Interchangeable pieces, placed by data.
func _street() -> void:
	var n := StaticBody3D.new()
	n.name = "Street"
	root.add_child(n)
	var sy := street_y
	Geo.bevel = false
	Geo.box(n, Vector3(80, 0.2, 2.6), Vector3(W * 0.5, sy + 0.05, -1.65), "sidewalk")
	Geo.box(n, Vector3(80, 0.1, 10.0), Vector3(W * 0.5, sy - 0.05, -7.95), "asphalt")
	Geo.box(n, Vector3(80, 0.2, 2.6), Vector3(W * 0.5, sy + 0.05, -14.25), "sidewalk")
	Geo.box(n, Vector3(80, 0.02, 0.12), Vector3(W * 0.5, sy + 0.01, -7.95), "car_yellow", false)
	Geo.box(n, Vector3(80, 0.25, 0.2), Vector3(W * 0.5, sy + 0.05, -2.95), "sidewalk")
	Geo.box(n, Vector3(80, 0.25, 0.2), Vector3(W * 0.5, sy + 0.05, -12.95), "sidewalk")
	Geo.bevel = true
	var street: Dictionary = d.get("street", {})
	var far_z := -15.55
	var x := float(street.get("start_x", -18.0))
	for bld in street.get("buildings", []):
		var bays := int(bld.get("bays", 4))
		var storeys := int(bld.get("storeys", 5))
		var width := bays * 1.8
		for k in range(int(width / 3.6)):
			_lib(String(bld.get("shop", "storefront")), Vector3(x + 1.8 + k * 3.6, sy + 0.1, far_z), 0.0)
		for s_i in range(storeys - 1):
			for b_i in bays:
				_lib("facade_bay", Vector3(x + 0.9 + b_i * 1.8, sy + 0.1 + 3.6 + s_i * 3.0, far_z), 0.0)
		for b_i in bays:
			_lib("facade_cornice", Vector3(x + 0.9 + b_i * 1.8, sy + 0.1 + 3.6 + (storeys - 1) * 3.0, far_z), 0.0)
		# Fire escapes on the upper floors.
		for s_i in range(storeys - 1):
			var ey := sy + 0.1 + 3.6 + s_i * 3.0
			Geo.box(n, Vector3(width * 0.55, 0.04, 0.8), Vector3(x + width * 0.5, ey, far_z + 0.4), "grille", false)
			Geo.box(n, Vector3(width * 0.55, 0.04, 0.04), Vector3(x + width * 0.5, ey + 0.95, far_z + 0.8), "iron", false)
		x += width + float(bld.get("gap", 0.1))
	for item in street.get("furniture", []):
		var pos: Array = item.pos
		_lib(String(item.prop), Vector3(pos[0], sy + 0.15 + float(pos[1]), pos[2]), deg_to_rad(float(item.get("rot", 0.0))))
	for c in street.get("cars", []):
		var pos: Array = c.pos
		var car := _lib(String(c.prop), Vector3(pos[0], sy, pos[1]), deg_to_rad(float(c.get("rot", 90.0))))
		if car and c.get("lights", false):
			_car_lights(car, float(c.get("length", 5.5)))


func _lib(prop: String, pos: Vector3, rot_y: float) -> Node3D:
	var m := PropFactory.baked_prop(prop)
	if m == null:
		return null
	m.position = pos
	m.rotation.y = rot_y
	root.add_child(m)
	return m


## An idling car's headlights: they fade as the battery dies over days 1 to 3.
func _car_lights(car: Node3D, length: float) -> void:
	var lamps: Array = []
	for lx in [-0.75, 0.75]:
		var l := Geo.sphere(car, 0.07, Vector3(lx, 0.7, length * 0.5 + 0.02), Geo.emissive(Color(1.0, 0.92, 0.7), 2.5))
		l.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		lamps.append(l)
	var spot := SpotLight3D.new()
	spot.position = Vector3(0, 0.75, length * 0.5 + 0.2)
	spot.spot_range = 14.0
	spot.spot_angle = 28.0
	spot.light_energy = 1.5
	spot.light_color = Color(1.0, 0.9, 0.7)
	spot.rotation = Vector3(-0.12, 0, 0)
	spot.rotation.y = PI
	car.add_child(spot)
	cars.append({"lamps": lamps, "spot": spot, "seed": randf()})



