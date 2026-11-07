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
	_floors_and_ceiling()
	_outer_walls()
	_partitions()
	_trim()
	_fire_escape()
	_exterior()
	_street()
	return root


func _room_at(z: float) -> Dictionary:
	for r in d.rooms:
		if z >= float(r.z0) - 0.06 and z <= float(r.z1) + 0.06:
			return r
	return d.rooms[0]


# ------------------------------------------------------------ shell

func _floors_and_ceiling() -> void:
	var body := StaticBody3D.new()
	body.name = "Shell"
	root.add_child(body)
	for r in d.rooms:
		var z0 := float(r.z0) - 0.05
		var z1 := float(r.z1) + 0.05
		Geo.box(body, Vector3(W, 0.2, z1 - z0), Vector3(W * 0.5, -0.1, (z0 + z1) * 0.5), String(r.floor))
	Geo.box(body, Vector3(W + 0.5, 0.25, D + 0.5), Vector3(W * 0.5, H + 0.125, D * 0.5), "ceiling")


## A straight wall with rectangular openings. axis "x": runs along x at
## z = fixed, thickness extends in out_dir. axis "z": runs along z at x = fixed.
func wall_run(body: Node3D, axis: String, fixed: float, out_dir: float, thickness: float,
		a0: float, a1: float, openings: Array, material: String, offset := 0.0) -> void:
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
			pieces.append([cursor, oa, 0.0, H])
		if float(op.y0) > 0.0:
			pieces.append([oa, ob, 0.0, float(op.y0)])
		if float(op.y1) < H:
			pieces.append([oa, ob, float(op.y1), H])
		cursor = ob
	if cursor < a1:
		pieces.append([cursor, a1, 0.0, H])
	for p in pieces:
		var len: float = p[1] - p[0]
		var hgt: float = p[3] - p[2]
		var c := (float(p[0]) + float(p[1])) * 0.5
		var cy := (float(p[2]) + float(p[3])) * 0.5
		if axis == "x":
			Geo.box(body, Vector3(len, hgt, thickness), Vector3(c, cy, mid), material)
		else:
			Geo.box(body, Vector3(thickness, hgt, len), Vector3(mid, cy, c), material)


func _outer_walls() -> void:
	var body := StaticBody3D.new()
	body.name = "Walls"
	root.add_child(body)
	var ops: Dictionary = d.openings
	var paint := 0.03
	var brick := 0.25
	# Front (street) wall: wallpaper inside, brick outside.
	wall_run(body, "x", 0.0, -1.0, paint, 0.0, W, ops.front, String(_room_at(0.0).wall))
	wall_run(body, "x", 0.0, -1.0, brick, -0.25, W + 0.25, ops.front, "brick", paint)
	# Back wall to the stair hall.
	wall_run(body, "x", D, 1.0, paint, 0.0, W, ops.back, String(_room_at(D).wall))
	wall_run(body, "x", D, 1.0, brick, -0.25, W + 0.25, ops.back, "plaster_cream", paint)
	# Side walls, painted per room.
	for r in d.rooms:
		var z0 := float(r.z0) - 0.05
		var z1 := float(r.z1) + 0.05
		if r == d.rooms[0]:
			z0 = 0.0
		if r == d.rooms[d.rooms.size() - 1]:
			z1 = D
		wall_run(body, "z", 0.0, -1.0, paint, z0, z1, ops.left, String(r.wall))
		wall_run(body, "z", W, 1.0, paint, z0, z1, ops.right, String(r.wall))
	wall_run(body, "z", 0.0, -1.0, brick, -0.25, D + 0.25, ops.left, "brick", paint)
	wall_run(body, "z", W, 1.0, brick, -0.25, D + 0.25, ops.right, "brick", paint)

	for side in ["front", "right", "back", "left"]:
		for op in ops[side]:
			if op.kind == "window":
				_window(side, op)
			elif op.kind == "door":
				_hall_door(side, op)


func _partitions() -> void:
	var body := StaticBody3D.new()
	body.name = "Partitions"
	root.add_child(body)
	for p in d.partitions:
		var z := float(p.z)
		var dw: Array = p.doorway
		var op := {"a": dw[0], "b": dw[1], "y0": 0.0, "y1": dw[2]}
		var front_room: Dictionary = _room_by_id(String(p.front_room))
		var back_room: Dictionary = _room_by_id(String(p.back_room))
		wall_run(body, "x", z, -1.0, 0.05, 0.0, W, [op], String(front_room.wall))
		wall_run(body, "x", z, 1.0, 0.05, 0.0, W, [op], String(back_room.wall))
		# Door frame trim.
		var a := float(dw[0])
		var b := float(dw[1])
		var top := float(dw[2])
		Geo.box(body, Vector3(0.06, top, 0.14), Vector3(a - 0.03, top * 0.5, z), "trim", false)
		Geo.box(body, Vector3(0.06, top, 0.14), Vector3(b + 0.03, top * 0.5, z), "trim", false)
		Geo.box(body, Vector3(b - a + 0.12, 0.07, 0.14), Vector3((a + b) * 0.5, top + 0.035, z), "trim", false)


func _room_by_id(id: String) -> Dictionary:
	for r in d.rooms:
		if r.id == id:
			return r
	return d.rooms[0]


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
	win.climb_in_point = Vector3(center.x, 0.05, center.z) + into * 0.75
	win.climb_out_point = Vector3(center.x, 0.05, center.z) - into * 0.55


func _sash_geometry(parent: Node3D, w: float, h: float) -> void:
	Geo.box(parent, Vector3(w, h, 0.012), Vector3(0, h * 0.5, 0), Geo.glass(), parent is CollisionObject3D)
	Geo.box(parent, Vector3(w, 0.045, 0.045), Vector3(0, 0.0225, 0), "trim", false)
	Geo.box(parent, Vector3(w, 0.035, 0.045), Vector3(0, h - 0.0175, 0), "trim", false)
	Geo.box(parent, Vector3(0.035, h, 0.045), Vector3(-w * 0.5 + 0.0175, h * 0.5, 0), "trim", false)
	Geo.box(parent, Vector3(0.035, h, 0.045), Vector3(w * 0.5 - 0.0175, h * 0.5, 0), "trim", false)


func _hall_door(_side: String, op: Dictionary) -> void:
	var a := float(op.a)
	var b := float(op.b)
	var h := float(op.y1)
	var door := HallDoor.new()
	door.name = "hall_door"
	door.persist_id = "hall_door"
	door.display_name = "door"
	root.add_child(door)
	door.position = Vector3((a + b) * 0.5, 0, D + 0.12)
	var w := b - a
	Geo.box(door, Vector3(w, h, 0.05), Vector3(0, h * 0.5, 0), "wood_mid")
	for i in 2:
		Geo.box(door, Vector3(w * 0.7, h * 0.32, 0.01), Vector3(0, h * (0.3 + i * 0.4), -0.03), "wood_light", false)
	Geo.sphere(door, 0.03, Vector3(w * 0.38, 0.95, -0.06), "chrome")
	Geo.box(door, Vector3(0.1, 0.02, 0.02), Vector3(w * 0.3, 1.45, -0.04), "chrome", false)
	Geo.box(door, Vector3(0.012, 0.012, 0.18), Vector3(w * 0.33, 1.4, -0.06), "chrome", false).rotation.x = 0.4
	Geo.box(door, Vector3(0.06, 0.1, 0.03), Vector3(w * 0.38, 1.25, -0.05), "chrome", false)
	Geo.box(door, Vector3(0.14, 0.06, 0.005), Vector3(0, 1.65, -0.028), "chrome", false)
	Geo.label3d(door, "4A", Vector3(0, 1.65, -0.032), 0.05).rotation.y = PI
	# Frame
	Geo.box(door, Vector3(0.07, h, 0.14), Vector3(-w * 0.5 - 0.035, h * 0.5, -0.05), "trim", false)
	Geo.box(door, Vector3(0.07, h, 0.14), Vector3(w * 0.5 + 0.035, h * 0.5, -0.05), "trim", false)
	Geo.box(door, Vector3(w + 0.14, 0.08, 0.14), Vector3(0, h + 0.04, -0.05), "trim", false)


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
	# Our building's face around the apartment, five storeys of brick.
	Geo.box(n, Vector3(8.0, top - street_y, 0.3), Vector3(-4.25, (top + street_y) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(8.0, top - street_y, 0.3), Vector3(W + 4.25, (top + street_y) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(W + 0.5, -0.2 - street_y, 0.3), Vector3(W * 0.5, (street_y - 0.2) * 0.5, front_z + 0.15), "brick")
	Geo.box(n, Vector3(W + 0.5, top - H - 0.25, 0.3), Vector3(W * 0.5, (top + H + 0.25) * 0.5, front_z + 0.15), "brick")
	# Cornice.
	Geo.box(n, Vector3(W + 16.5, 0.4, 0.6), Vector3(W * 0.5, top, front_z), "brownstone", false)
	# Neighbour windows on our own facade (dark: nobody has light).
	for floor_i in range(-3, 2):
		var y := floor_i * 3.0 + 0.75
		for x in [-6.2, -4.8, -2.0, -0.6, 4.0, 5.4, 8.2, 9.6]:
			if floor_i == 0 and x > -0.5 and x < W + 0.5:
				continue
			Geo.box(n, Vector3(0.9, 1.5, 0.02), Vector3(x, y + 0.75, front_z - 0.01), "window_dark", false)
			Geo.box(n, Vector3(1.0, 0.06, 0.12), Vector3(x, y, front_z - 0.05), "brownstone", false)
	# Airshaft: a brick wall 1.2 m away from the side windows.
	Geo.box(n, Vector3(0.3, top - street_y, D + 1.0), Vector3(W + 0.25 + 1.2 + 0.15, (top + street_y) * 0.5, D * 0.5), "brick_dark")
	for floor_i in range(-3, 2):
		Geo.box(n, Vector3(0.02, 1.2, 0.7), Vector3(W + 0.25 + 1.19, floor_i * 3.0 + 1.6, 6.0), "window_dark", false)
	# Neighbouring roofs and a water tower, seen across the street.
	Geo.box(n, Vector3(0.6, 0.2, 2.0), Vector3(W + 1.0, top - 0.1, D * 0.5), "brownstone", false)


func _street() -> void:
	var n := StaticBody3D.new()
	n.name = "Street"
	root.add_child(n)
	var sy := street_y
	Geo.box(n, Vector3(80, 0.2, 2.6), Vector3(W * 0.5, sy + 0.05, -1.65), "sidewalk")
	Geo.box(n, Vector3(80, 0.1, 10.0), Vector3(W * 0.5, sy - 0.05, -7.95), "asphalt")
	Geo.box(n, Vector3(80, 0.2, 2.6), Vector3(W * 0.5, sy + 0.05, -14.25), "sidewalk")
	Geo.box(n, Vector3(80, 0.02, 0.12), Vector3(W * 0.5, sy + 0.01, -7.95), "car_yellow", false)
	# Across the street: tenements and a loft building, all dark.
	var fronts := [
		{"x": -14.0, "w": 7.6, "h": 16.0, "m": "brick"},
		{"x": -6.2, "w": 7.6, "h": 14.5, "m": "brick_dark"},
		{"x": 1.6, "w": 7.6, "h": 16.0, "m": "brick"},
		{"x": 9.4, "w": 7.6, "h": 17.5, "m": "brownstone"},
		{"x": 17.2, "w": 7.6, "h": 15.0, "m": "brick_dark"},
	]
	var far_z := -15.55
	for f in fronts:
		var fx := float(f.x)
		var fw := float(f.w)
		var fh := float(f.h)
		Geo.box(n, Vector3(fw, fh, 1.0), Vector3(fx, sy + fh * 0.5, far_z - 0.5), String(f.m))
		Geo.box(n, Vector3(fw + 0.2, 0.35, 0.4), Vector3(fx, sy + fh, far_z + 0.1), "brownstone", false)
		var floors := int((fh - 3.0) / 3.0)
		for fi in floors:
			for wi in 4:
				var wx := fx - fw * 0.5 + 1.0 + wi * (fw - 2.0) / 3.0
				var wy := sy + 3.6 + fi * 3.0
				Geo.box(n, Vector3(0.9, 1.5, 0.05), Vector3(wx, wy + 0.75, far_z + 0.01), "window_dark", false)
				Geo.box(n, Vector3(1.0, 0.07, 0.15), Vector3(wx, wy, far_z + 0.05), "brownstone", false)
				# Halloween paper in a few windows.
				if (fi * 7 + wi * 3 + int(fx)) % 9 == 0:
					var sk := PropFactory.make("skeleton", "sk")
					sk.position = Vector3(wx, wy + 0.4, far_z + 0.06)
					sk.scale = Vector3(1.6, 1.6, 1.6)
					sk.rotation.y = PI
					n.add_child(sk)
		# Fire escape across the street.
		for fi in floors:
			var ey := sy + 3.5 + fi * 3.0
			Geo.box(n, Vector3(fw * 0.6, 0.04, 0.8), Vector3(fx, ey, far_z + 0.4), "grille", false)
			Geo.box(n, Vector3(fw * 0.6, 0.04, 0.04), Vector3(fx, ey + 0.9, far_z + 0.8), "iron", false)
		# Storefront at street level.
		Geo.box(n, Vector3(fw - 1.0, 2.6, 0.05), Vector3(fx, sy + 1.4, far_z + 0.02), "window_dark", false)
		Geo.box(n, Vector3(fw - 0.6, 0.5, 0.12), Vector3(fx, sy + 3.0, far_z + 0.08), "car_green" if int(fx) % 2 == 0 else "cooler_red", false)
	# Water tower on the roof across the street.
	var wt := Node3D.new()
	n.add_child(wt)
	wt.position = Vector3(3.0, sy + 16.0, far_z - 3.0)
	for lx in [-1.0, 1.0]:
		for lz in [-1.0, 1.0]:
			Geo.box(wt, Vector3(0.12, 2.0, 0.12), Vector3(lx, 1.0, lz), "iron", false)
	Geo.cylinder(wt, 1.5, 2.8, Vector3(0, 3.4, 0), "water_tower", false, 18)
	var cone := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 0.05
	cm.bottom_radius = 1.6
	cm.height = 0.9
	cone.mesh = cm
	cone.position = Vector3(0, 5.25, 0)
	cone.material_override = Geo.mat("wood_dark")
	wt.add_child(cone)
	# Cars, left where they stopped, some still idling with their lights on.
	var car_specs := [
		{"x": -7.0, "z": -4.0, "m": "car_cream", "dir": 1.0, "lights": true},
		{"x": -1.0, "z": -4.0, "m": "car_green", "dir": 1.0, "lights": false},
		{"x": 5.5, "z": -5.5, "m": "car_yellow", "dir": 1.0, "lights": true},
		{"x": 12.0, "z": -4.2, "m": "car_brown", "dir": 1.0, "lights": true},
		{"x": 0.5, "z": -11.6, "m": "car_brown", "dir": -1.0, "lights": false},
		{"x": 9.0, "z": -11.6, "m": "car_cream", "dir": -1.0, "lights": true},
	]
	for c in car_specs:
		_car(n, Vector3(float(c.x), sy, float(c.z)), String(c.m), float(c.dir), bool(c.lights))


func _car(parent: Node3D, pos: Vector3, material: String, dir: float, lights: bool) -> void:
	var car := Node3D.new()
	parent.add_child(car)
	car.position = pos
	car.rotation.y = 0.0 if dir > 0.0 else PI
	car.rotation.y += randf_range(-0.06, 0.06)
	# Big American sedan: about 5.4 m long.
	Geo.box(car, Vector3(5.4, 0.7, 1.95), Vector3(0, 0.6, 0), material, false)
	Geo.box(car, Vector3(2.6, 0.55, 1.75), Vector3(-0.3, 1.22, 0), material, false)
	Geo.box(car, Vector3(2.4, 0.42, 1.78), Vector3(-0.3, 1.2, 0), "window_dark", false)
	for wx in [-1.7, 1.6]:
		for wz in [-0.9, 0.9]:
			var t := Geo.cylinder(car, 0.36, 0.25, Vector3(wx, 0.36, wz), "tire", false)
			t.rotation.x = PI * 0.5
	Geo.box(car, Vector3(0.06, 0.18, 1.9), Vector3(2.72, 0.5, 0), "chrome", false)
	var lamps: Array = []
	if lights:
		for lz in [-0.68, 0.68]:
			var l := Geo.box(car, Vector3(0.04, 0.16, 0.22), Vector3(2.73, 0.72, lz), Geo.emissive(Color(1.0, 0.92, 0.7), 2.0), false)
			lamps.append(l)
		var spot := SpotLight3D.new()
		spot.position = Vector3(2.9, 0.75, 0)
		spot.rotation = Vector3(-0.15, -PI * 0.5, 0)
		spot.spot_range = 14.0
		spot.spot_angle = 28.0
		spot.light_energy = 1.5
		spot.light_color = Color(1.0, 0.9, 0.7)
		car.add_child(spot)
		cars.append({"lamps": lamps, "spot": spot, "seed": randf()})
