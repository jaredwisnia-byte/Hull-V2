class_name PropFactory
extends RefCounted
## Builds each prop from boxes. Every prop's origin is its bottom centre and
## its front faces local +z. Sizes are real 1970s furniture sizes in metres.



static func make(type: String, id: String) -> Node3D:
	var n: Node3D
	match type:
		"sofa": n = _sofa()
		"armchair": n = _armchair()
		"coffee_table": n = _coffee_table()
		"side_table": n = _side_table()
		"tv": n = _tv()
		"radiator": n = _radiator()
		"rug": n = _rug()
		"skeleton": n = _skeleton()
		"ceiling_lamp": n = _ceiling_lamp()
		"bed": n = _bed()
		"dresser": n = _dresser()
		"fridge": n = _fridge()
		"stove": n = _stove()
		"sink": n = _sink()
		"wall_cabinet": n = _wall_cabinet()
		"tub": n = _tub()
		"kitchen_table": n = _kitchen_table()
		"chair": n = _chair()
		"candy_bowl": n = _candy_bowl()
		"breadbox": n = _breadbox()
		"phone": n = _phone()
		"notepad": n = _wall_readable("notepad", "notepad", Vector3(0.14, 0.2, 0.01), "paper")
		"calendar": n = _wall_readable("calendar", "calendar", Vector3(0.3, 0.45, 0.01), "paper")
		"fridge_note": n = _wall_readable("wall_note", "note on the fridge", Vector3(0.12, 0.14, 0.005), "paper")
		"coat_hook": n = _coat_hook()
		"light_switch": n = _light_switch()
		"radio": n = _radio()
		"cooler": n = _cooler()
		"candle": n = _candle()
		"jack_o_lantern": n = _jack()
		"photo": n = _photo()
		"newspaper": n = _newspaper()
		_:
			push_warning("Unknown prop type: %s" % type)
			n = StaticBody3D.new()
	n.name = id
	if n is Interactable:
		n.persist_id = id
	if n is Carriable:
		n.prop_type = type
	return n


# ------------------------------------------------------------ front room

static func _sofa() -> Node3D:
	var b := StaticBody3D.new()
	Geo.box(b, Vector3(1.9, 0.42, 0.85), Vector3(0, 0.21, 0), "slipcover")
	Geo.box(b, Vector3(1.9, 0.5, 0.2), Vector3(0, 0.62, -0.33), "slipcover")
	Geo.box(b, Vector3(0.18, 0.2, 0.85), Vector3(-0.86, 0.52, 0), "slipcover")
	Geo.box(b, Vector3(0.18, 0.2, 0.85), Vector3(0.86, 0.52, 0), "slipcover")
	Geo.box(b, Vector3(0.75, 0.1, 0.6), Vector3(-0.38, 0.47, 0.08), "slipcover", false)
	Geo.box(b, Vector3(0.75, 0.1, 0.6), Vector3(0.38, 0.47, 0.08), "slipcover", false)
	return b


static func _armchair() -> Node3D:
	var b := StaticBody3D.new()
	Geo.box(b, Vector3(0.8, 0.42, 0.8), Vector3(0, 0.21, 0), "armchair")
	Geo.box(b, Vector3(0.8, 0.55, 0.18), Vector3(0, 0.68, -0.31), "armchair")
	Geo.box(b, Vector3(0.14, 0.22, 0.8), Vector3(-0.33, 0.53, 0), "armchair")
	Geo.box(b, Vector3(0.14, 0.22, 0.8), Vector3(0.33, 0.53, 0), "armchair")
	Geo.box(b, Vector3(0.5, 0.12, 0.25), Vector3(0, 0.98, -0.3), "pillow", false)
	return b


static func _coffee_table() -> Node3D:
	var b := StaticBody3D.new()
	Geo.box(b, Vector3(1.1, 0.04, 0.55), Vector3(0, 0.40, 0), "wood_mid")
	for x in [-0.5, 0.5]:
		for z in [-0.23, 0.23]:
			Geo.box(b, Vector3(0.04, 0.38, 0.04), Vector3(x, 0.19, z), "wood_dark", false)
	return b


static func _side_table() -> Node3D:
	var b := StaticBody3D.new()
	Geo.box(b, Vector3(0.4, 0.04, 0.4), Vector3(0, 0.58, 0), "wood_mid")
	Geo.box(b, Vector3(0.36, 0.03, 0.36), Vector3(0, 0.18, 0), "wood_mid", false)
	for x in [-0.17, 0.17]:
		for z in [-0.17, 0.17]:
			Geo.box(b, Vector3(0.035, 0.56, 0.035), Vector3(x, 0.28, z), "wood_dark", false)
	return b


static func _tv() -> Node3D:
	var f := Fixture.new()
	f.display_name = "television"
	f.verb = "Turn on the television"
	f.lines = [
		"You turn the knob. Nothing. Of course nothing.",
		"You catch your reflection in the dead grey screen. You look like your father.",
		"Last thing on it was the Thursday late movie, before the shaking.",
	]
	Geo.box(f, Vector3(0.75, 0.32, 0.5), Vector3(0, 0.16, 0), "wood_dark")
	Geo.box(f, Vector3(0.7, 0.5, 0.48), Vector3(0, 0.57, 0), "wood_mid")
	Geo.box(f, Vector3(0.5, 0.38, 0.02), Vector3(-0.06, 0.58, 0.245), "tv_screen", false)
	Geo.box(f, Vector3(0.1, 0.38, 0.02), Vector3(0.28, 0.58, 0.245), "grille", false)
	Geo.box(f, Vector3(0.01, 0.25, 0.01), Vector3(-0.1, 0.95, 0), "chrome", false).rotation.z = 0.45
	Geo.box(f, Vector3(0.01, 0.25, 0.01), Vector3(0.1, 0.95, 0), "chrome", false).rotation.z = -0.45
	return f


static func _radiator() -> Node3D:
	var f := Fixture.new()
	f.display_name = "radiator"
	f.verb = "Touch the radiator"
	f.lines = [
		"Cold iron. The oil burner in the basement needs electric to run.",
		"Still cold. Walter will be down there swearing at the boiler.",
	]
	Geo.box(f, Vector3(0.9, 0.62, 0.16), Vector3(0, 0.36, 0), "radiator")
	Geo.box(f, Vector3(0.06, 0.06, 0.06), Vector3(0.48, 0.12, 0), "iron", false)
	return f


static func _rug() -> Node3D:
	var n := Node3D.new()
	Geo.box(n, Vector3(1.9, 0.01, 1.5), Vector3(0, 0.005, 0), "rug", false)
	return n


static func _skeleton() -> Node3D:
	# A paper Halloween skeleton taped inside the window glass.
	var n := Node3D.new()
	var m := "skeleton_paper"
	Geo.box(n, Vector3(0.1, 0.12, 0.003), Vector3(0, 0.5, 0), m, false)
	Geo.box(n, Vector3(0.04, 0.3, 0.003), Vector3(0, 0.28, 0), m, false)
	Geo.box(n, Vector3(0.2, 0.025, 0.003), Vector3(0, 0.37, 0), m, false)
	Geo.box(n, Vector3(0.16, 0.025, 0.003), Vector3(0, 0.30, 0), m, false)
	Geo.box(n, Vector3(0.025, 0.24, 0.003), Vector3(-0.12, 0.30, 0), m, false).rotation.z = 0.3
	Geo.box(n, Vector3(0.025, 0.24, 0.003), Vector3(0.12, 0.30, 0), m, false).rotation.z = -0.3
	Geo.box(n, Vector3(0.025, 0.28, 0.003), Vector3(-0.05, 0.0, 0), m, false).rotation.z = 0.12
	Geo.box(n, Vector3(0.025, 0.28, 0.003), Vector3(0.05, 0.0, 0), m, false).rotation.z = -0.12
	return n


static func _ceiling_lamp() -> Node3D:
	var f := Fixture.new()
	f.display_name = "ceiling light"
	f.verb = ""
	Geo.box(f, Vector3(0.3, 0.06, 0.3), Vector3(0, -0.03, 0), "trim", false)
	Geo.sphere(f, 0.13, Vector3(0, -0.13, 0), "enamel", 0.7)
	return f


# ------------------------------------------------------------ bedroom

static func _bed() -> Node3D:
	var bed := Bed.new()
	bed.display_name = "bed"
	# Length runs along local z; headboard at -z.
	Geo.box(bed, Vector3(1.4, 0.3, 2.0), Vector3(0, 0.25, 0), "wood_dark")
	Geo.box(bed, Vector3(1.36, 0.18, 1.96), Vector3(0, 0.49, 0), "pillow", false)
	Geo.box(bed, Vector3(1.44, 0.06, 1.55), Vector3(0, 0.6, 0.22), "bedspread", false)
	Geo.box(bed, Vector3(1.44, 0.4, 0.02), Vector3(0, 0.38, 1.0), "bedspread", false)
	Geo.box(bed, Vector3(1.4, 1.0, 0.05), Vector3(0, 0.5, -1.0), "wood_dark")
	Geo.box(bed, Vector3(0.55, 0.12, 0.35), Vector3(-0.33, 0.64, -0.75), "pillow", false)
	Geo.box(bed, Vector3(0.55, 0.12, 0.35), Vector3(0.33, 0.64, -0.75), "pillow", false)
	return bed


static func _dresser() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "dresser"
	c.cid = "dresser"
	c.title = "Dresser drawers"
	c.verb = "Go through the dresser"
	Geo.box(c, Vector3(1.1, 0.9, 0.4), Vector3(0, 0.45, 0), "wood_mid")
	for i in 3:
		Geo.box(c, Vector3(1.0, 0.24, 0.02), Vector3(0, 0.18 + i * 0.28, 0.205), "wood_light", false)
		Geo.box(c, Vector3(0.12, 0.025, 0.03), Vector3(0, 0.22 + i * 0.28, 0.22), "chrome", false)
	Geo.box(c, Vector3(1.14, 0.03, 0.44), Vector3(0, 0.915, 0), "wood_dark", false)
	return c


static func _photo() -> Node3D:
	var c := Carriable.new()
	c.display_name = "photo of you and Terry"
	c.doc_id = "photo"
	Geo.box(c, Vector3(0.16, 0.21, 0.02), Vector3(0, 0.105, 0), "wood_dark")
	Geo.box(c, Vector3(0.13, 0.17, 0.005), Vector3(0, 0.105, 0.011), "sidewalk", false)
	Geo.box(c, Vector3(0.02, 0.15, 0.02), Vector3(0, 0.075, -0.05), "wood_dark", false).rotation.x = 0.35
	return c


# ------------------------------------------------------------ kitchen

static func _fridge() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "refrigerator"
	c.cid = "fridge"
	c.title = "Refrigerator (dead since 1 a.m.)"
	c.verb = "Open the fridge"
	c.cid2 = "freezer"
	c.title2 = "Freezer compartment"
	c.verb2 = "Open the freezer"
	Geo.box(c, Vector3(0.7, 1.55, 0.66), Vector3(0, 0.78, 0), "enamel")
	Geo.box(c, Vector3(0.66, 0.02, 0.02), Vector3(0, 1.18, 0.335), "chrome", false)
	Geo.box(c, Vector3(0.04, 0.3, 0.04), Vector3(0.28, 0.85, 0.35), "chrome", false)
	Geo.box(c, Vector3(0.04, 0.16, 0.04), Vector3(0.28, 1.35, 0.35), "chrome", false)
	Geo.box(c, Vector3(0.7, 0.06, 0.66), Vector3(0, 1.58, 0), "enamel", false)
	Geo.box(c, Vector3(0.55, 0.06, 0.04), Vector3(0, 0.06, 0.33), "grille", false)
	return c


static func _stove() -> Node3D:
	var s := GasRange.new()
	s.display_name = "gas range"
	Geo.box(s, Vector3(0.75, 0.88, 0.62), Vector3(0, 0.44, 0), "enamel")
	Geo.box(s, Vector3(0.75, 0.02, 0.62), Vector3(0, 0.89, 0), "iron", false)
	Geo.box(s, Vector3(0.75, 0.5, 0.06), Vector3(0, 1.15, -0.28), "enamel")
	Geo.box(s, Vector3(0.5, 0.36, 0.02), Vector3(0, 0.42, 0.31), "black", false)
	for i in 4:
		Geo.box(s, Vector3(0.04, 0.04, 0.04), Vector3(-0.27 + i * 0.18, 0.78, 0.32), "black", false)
	var positions := [Vector3(-0.18, 0.91, -0.14), Vector3(0.18, 0.91, -0.14), Vector3(-0.18, 0.91, 0.14), Vector3(0.18, 0.91, 0.14)]
	for p in positions:
		Geo.cylinder(s, 0.07, 0.015, p, "iron", false)
		var flame := Geo.cylinder(s, 0.06, 0.02, p + Vector3(0, 0.015, 0), Geo.emissive(Color(0.3, 0.5, 1.0), 2.5), false)
		flame.visible = false
		s.flames.append(flame)
	var glow := OmniLight3D.new()
	glow.light_color = Color(0.5, 0.6, 1.0)
	glow.omni_range = 2.5
	glow.light_energy = 0.0
	glow.position = Vector3(0, 1.1, 0)
	glow.visible = false
	s.add_child(glow)
	s.glow = glow
	return s


static func _sink() -> Node3D:
	var s := Sink.new()
	s.display_name = "sink"
	Geo.box(s, Vector3(0.6, 0.06, 0.5), Vector3(0, 0.86, 0), "enamel")
	Geo.box(s, Vector3(0.48, 0.02, 0.36), Vector3(0, 0.89, 0.02), "chrome", false)
	Geo.box(s, Vector3(0.6, 0.3, 0.08), Vector3(0, 1.04, -0.21), "enamel")
	Geo.box(s, Vector3(0.04, 0.2, 0.04), Vector3(0, 1.02, -0.12), "chrome", false)
	Geo.box(s, Vector3(0.04, 0.04, 0.12), Vector3(0, 1.1, -0.07), "chrome", false)
	Geo.box(s, Vector3(0.06, 0.8, 0.06), Vector3(-0.22, 0.42, -0.15), "chrome")
	Geo.box(s, Vector3(0.06, 0.8, 0.06), Vector3(0.22, 0.42, -0.15), "chrome")
	return s


static func _wall_cabinet() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "cupboard"
	c.cid = "wall_cabinet"
	c.title = "Kitchen cupboard"
	c.verb = "Open the cupboard"
	Geo.box(c, Vector3(1.4, 0.7, 0.33), Vector3(0, 0.35, 0), "trim")
	Geo.box(c, Vector3(0.01, 0.66, 0.01), Vector3(0, 0.35, 0.17), "trim_dark", false)
	Geo.box(c, Vector3(0.03, 0.08, 0.03), Vector3(-0.06, 0.2, 0.18), "chrome", false)
	Geo.box(c, Vector3(0.03, 0.08, 0.03), Vector3(0.06, 0.2, 0.18), "chrome", false)
	return c


static func _tub() -> Node3D:
	var t := KitchenTub.new()
	t.display_name = "tub"
	Geo.box(t, Vector3(1.6, 0.56, 0.75), Vector3(0, 0.3, 0), "enamel")
	for x in [-0.7, 0.7]:
		for z in [-0.28, 0.28]:
			Geo.box(t, Vector3(0.07, 0.05, 0.07), Vector3(x, 0.025, z), "iron", false)
	# The board lid used as a counter.
	Geo.box(t, Vector3(1.64, 0.04, 0.79), Vector3(0, 0.6, 0), "wood_light")
	var w := Geo.box(t, Vector3(1.5, 0.01, 0.65), Vector3(0, 0.5, 0), Geo.emissive(Color(0.25, 0.32, 0.36), 1.0), false)
	w.visible = false
	t.water = w
	return t


static func _kitchen_table() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "kitchen table"
	c.cid = "kitchen_drawer"
	c.title = "Kitchen table drawer"
	c.verb = "Open the table drawer"
	Geo.box(c, Vector3(1.0, 0.04, 0.7), Vector3(0, 0.74, 0), "enamel_yellow")
	Geo.box(c, Vector3(0.96, 0.1, 0.66), Vector3(0, 0.67, 0), "chrome", false)
	Geo.box(c, Vector3(0.4, 0.08, 0.02), Vector3(0, 0.67, 0.34), "chrome", false)
	for x in [-0.46, 0.46]:
		for z in [-0.31, 0.31]:
			Geo.box(c, Vector3(0.03, 0.72, 0.03), Vector3(x, 0.36, z), "chrome", false)
	Geo.add_box_shape(c, Vector3(0.96, 0.72, 0.66), Vector3(0, 0.36, 0))
	return c


static func _chair() -> Node3D:
	var b := StaticBody3D.new()
	Geo.box(b, Vector3(0.42, 0.05, 0.42), Vector3(0, 0.46, 0), "cooler_red")
	Geo.box(b, Vector3(0.42, 0.3, 0.04), Vector3(0, 0.78, -0.2), "cooler_red", false)
	for x in [-0.18, 0.18]:
		for z in [-0.18, 0.18]:
			Geo.box(b, Vector3(0.025, 0.45, 0.025), Vector3(x, 0.225, z), "chrome", false)
	Geo.box(b, Vector3(0.025, 0.4, 0.025), Vector3(-0.18, 0.66, -0.2), "chrome", false)
	Geo.box(b, Vector3(0.025, 0.4, 0.025), Vector3(0.18, 0.66, -0.2), "chrome", false)
	Geo.add_box_shape(b, Vector3(0.42, 0.45, 0.42), Vector3(0, 0.225, 0))
	return b


static func _candy_bowl() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "candy bowl"
	c.cid = "candy_bowl"
	c.title = "Bowl of Halloween candy"
	c.verb = "Take from the candy bowl"
	Geo.cylinder(c, 0.11, 0.07, Vector3(0, 0.035, 0), "pumpkin", true)
	Geo.box(c, Vector3(0.05, 0.02, 0.03), Vector3(0.02, 0.075, 0.01), "cooler_red", false)
	Geo.box(c, Vector3(0.04, 0.02, 0.03), Vector3(-0.03, 0.075, -0.02), "car_yellow", false)
	return c


static func _breadbox() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "breadbox"
	c.cid = "breadbox"
	c.title = "Breadbox"
	c.verb = "Open the breadbox"
	Geo.box(c, Vector3(0.36, 0.18, 0.24), Vector3(0, 0.09, 0), "chrome")
	Geo.box(c, Vector3(0.3, 0.03, 0.01), Vector3(0, 0.12, 0.125), "cooler_red", false)
	return c


static func _phone() -> Node3D:
	var p := WallPhone.new()
	p.display_name = "wall phone"
	Geo.box(p, Vector3(0.16, 0.22, 0.08), Vector3(0, 0.11, 0.04), "enamel_yellow")
	Geo.box(p, Vector3(0.05, 0.22, 0.05), Vector3(-0.1, 0.12, 0.09), "enamel_yellow", false)
	Geo.cylinder(p, 0.045, 0.01, Vector3(0.02, 0.09, 0.085), "chrome", false).rotation.x = PI * 0.5
	return p


static func _wall_readable(doc: String, name: String, size: Vector3, material: String) -> Node3D:
	var r := Readable.new()
	r.display_name = name
	r.doc_id = doc
	Geo.box(r, size, Vector3(0, size.y * 0.5, size.z * 0.5), material)
	if doc == "calendar":
		Geo.box(r, Vector3(size.x * 0.9, size.y * 0.45, 0.003), Vector3(0, size.y * 0.75, size.z + 0.002), "wall_blue", false)
		Geo.box(r, Vector3(size.x * 0.85, size.y * 0.4, 0.003), Vector3(0, size.y * 0.25, size.z + 0.002), "newsprint", false)
	return r


static func _coat_hook() -> Node3D:
	var h := CoatHook.new()
	h.display_name = "coat"
	Geo.box(h, Vector3(0.3, 0.05, 0.03), Vector3(0, 0.0, 0.015), "wood_dark")
	Geo.box(h, Vector3(0.02, 0.02, 0.08), Vector3(0, 0.0, 0.06), "chrome", false)
	var coat := Node3D.new()
	h.add_child(coat)
	Geo.box(coat, Vector3(0.48, 0.85, 0.16), Vector3(0, -0.45, 0.12), "coat", false)
	Geo.box(coat, Vector3(0.2, 0.12, 0.17), Vector3(0, 0.0, 0.12), "coat", false)
	Geo.add_box_shape(h, Vector3(0.48, 0.9, 0.2), Vector3(0, -0.4, 0.12))
	h.coat = coat
	return h


static func _light_switch() -> Node3D:
	var f := Fixture.new()
	f.display_name = "light switch"
	f.verb = "Flip the light switch"
	f.lines = ["Click. Nothing.", "Click, click. Habit.", "You leave it in the on position, so you'll know if it ever comes back."]
	Geo.box(f, Vector3(0.08, 0.12, 0.015), Vector3(0, 0, 0.007), "trim")
	Geo.box(f, Vector3(0.015, 0.03, 0.015), Vector3(0, 0, 0.02), "trim_dark", false)
	return f


# ------------------------------------------------------------ carriables

static func _radio() -> Node3D:
	var r := RadioProp.new()
	r.display_name = "transistor radio"
	Geo.box(r, Vector3(0.24, 0.15, 0.07), Vector3(0, 0.075, 0), "radio_case")
	Geo.box(r, Vector3(0.11, 0.11, 0.005), Vector3(-0.05, 0.075, 0.036), "grille", false)
	Geo.box(r, Vector3(0.08, 0.04, 0.005), Vector3(0.065, 0.1, 0.036), "paper", false)
	Geo.cylinder(r, 0.018, 0.02, Vector3(0.065, 0.04, 0.04), "chrome", false).rotation.x = PI * 0.5
	Geo.box(r, Vector3(0.2, 0.015, 0.01), Vector3(0, 0.16, 0), "chrome", false)
	r.dial_label = Geo.label3d(r, "1010", Vector3(0.065, 0.1, 0.04), 0.035)
	return r


static func _cooler() -> Node3D:
	var c := CoolerProp.new()
	c.display_name = "medicine cooler"
	Geo.box(c, Vector3(0.42, 0.28, 0.3), Vector3(0, 0.14, 0), "cooler_red")
	Geo.box(c, Vector3(0.44, 0.05, 0.32), Vector3(0, 0.3, 0), "enamel")
	Geo.box(c, Vector3(0.3, 0.03, 0.04), Vector3(0, 0.36, 0), "enamel", false)
	Geo.box(c, Vector3(0.03, 0.06, 0.03), Vector3(-0.15, 0.33, 0), "enamel", false)
	Geo.box(c, Vector3(0.03, 0.06, 0.03), Vector3(0.15, 0.33, 0), "enamel", false)
	# Dial thermometer clipped to the front.
	Geo.cylinder(c, 0.045, 0.012, Vector3(0.1, 0.16, 0.156), "paper", false).rotation.x = PI * 0.5
	var pivot := Node3D.new()
	pivot.position = Vector3(0.1, 0.16, 0.165)
	c.add_child(pivot)
	Geo.box(pivot, Vector3(0.004, 0.035, 0.003), Vector3(0, 0.0175, 0), "cooler_red", false)
	c.needle = pivot
	Geo.box(c, Vector3(0.06, 0.006, 0.002), Vector3(0.1, 0.205, 0.163), Geo.emissive(Color(0.2, 0.6, 0.2), 1.0), false)
	return c


static func _candle() -> Node3D:
	var c := CandleProp.new()
	c.display_name = "candle"
	Geo.cylinder(c, 0.05, 0.015, Vector3(0, 0.0075, 0), "chrome", true)
	var stick := Node3D.new()
	c.add_child(stick)
	Geo.cylinder(stick, 0.012, 0.16, Vector3(0, 0.08, 0), "wax", false)
	c.stick = stick
	# The flame rides on top of the shrinking stick, so it lives outside it.
	c.flame = Geo.sphere(c, 0.012, Vector3(0, 0.175, 0), Geo.emissive(Color(1.0, 0.7, 0.3), 2.0), 1.8)
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.68, 0.36)
	light.omni_range = 2.5
	light.omni_attenuation = 2.2
	light.light_energy = 0.55
	light.position = Vector3(0, 0.25, 0)
	c.add_child(light)
	c.light = light
	Geo.add_box_shape(c, Vector3(0.06, 0.18, 0.06), Vector3(0, 0.09, 0))
	return c


static func _jack() -> Node3D:
	var j := JackOLantern.new()
	j.display_name = "jack-o'-lantern"
	var body := Geo.sphere(j, 0.16, Vector3(0, 0.13, 0), "pumpkin", 0.82)
	j.body = body
	Geo.cylinder(j, 0.015, 0.06, Vector3(0, 0.29, 0), "stem", false)
	var dark := "black"
	Geo.box(j, Vector3(0.04, 0.035, 0.02), Vector3(-0.055, 0.17, 0.145), dark, false).rotation.z = 0.5
	Geo.box(j, Vector3(0.04, 0.035, 0.02), Vector3(0.055, 0.17, 0.145), dark, false).rotation.z = -0.5
	Geo.box(j, Vector3(0.12, 0.025, 0.02), Vector3(0, 0.09, 0.15), dark, false)
	Geo.add_box_shape(j, Vector3(0.32, 0.27, 0.32), Vector3(0, 0.135, 0))
	return j


static func _newspaper() -> Node3D:
	var c := Carriable.new()
	c.display_name = "newspaper"
	c.doc_id = "newspaper"
	Geo.box(c, Vector3(0.3, 0.012, 0.4), Vector3(0, 0.006, 0), "newsprint")
	Geo.box(c, Vector3(0.26, 0.002, 0.08), Vector3(0, 0.013, -0.13), "black", false)
	return c
