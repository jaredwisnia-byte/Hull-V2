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
		"ceiling_globe": n = _ceiling_globe()
		"cafe_curtain": n = _cafe_curtain()
		"doorway_curtain": n = _doorway_curtain()
		"paper_bags": n = _paper_bags()
		"jars": n = _jars()
		"wall_clock": n = _wall_clock()
		"plant": n = _plant()
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
# Modelled on 1950s-70s New York kitchens: rounded enamel appliances, painted
# wooden cabinets with chrome pulls, formica and chrome dinette, milk glass.

static func _fridge() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "refrigerator"
	c.cid = "fridge"
	c.title = "Refrigerator (dead since 1 a.m.)"
	c.verb = "Open the fridge"
	c.cid2 = "freezer"
	c.title2 = "Freezer compartment"
	c.verb2 = "Open the freezer"
	# A round-shouldered '50s fridge, cream enamel gone slightly yellow.
	Geo.box(c, Vector3(0.72, 1.5, 0.66), Vector3(0, 0.82, 0), "enamel_cream", true, 0.09)
	Geo.box(c, Vector3(0.66, 0.012, 0.02), Vector3(0, 1.17, 0.33), "trim_dark", false, 0.004)
	Geo.box(c, Vector3(0.05, 0.3, 0.05), Vector3(0.27, 0.95, 0.35), "chrome_worn", false, 0.02)
	Geo.box(c, Vector3(0.08, 0.05, 0.06), Vector3(0.27, 1.11, 0.36), "chrome_worn", false, 0.02)
	Geo.box(c, Vector3(0.16, 0.035, 0.01), Vector3(0, 1.45, 0.33), "chrome_worn", false, 0.008)
	Geo.box(c, Vector3(0.62, 0.07, 0.04), Vector3(0, 0.06, 0.31), "grille", false, 0.01)
	for x in [-0.28, 0.28]:
		Geo.box(c, Vector3(0.05, 0.06, 0.05), Vector3(x, 0.03, -0.25), "iron", false, 0.01)
	return c


static func _stove() -> Node3D:
	var s := GasRange.new()
	s.display_name = "gas range"
	# Body, cooktop, back panel with a clock: a 1950s apartment range.
	Geo.box(s, Vector3(0.76, 0.86, 0.62), Vector3(0, 0.45, 0), "enamel_old", true, 0.025)
	Geo.box(s, Vector3(0.74, 0.03, 0.6), Vector3(0, 0.885, 0), "enamel_old", false, 0.008)
	Geo.box(s, Vector3(0.76, 0.32, 0.07), Vector3(0, 1.08, -0.275), "enamel_old", true, 0.025)
	Geo.box(s, Vector3(0.7, 0.025, 0.02), Vector3(0, 1.22, -0.235), "chrome_worn", false, 0.008)
	var clock := Geo.cylinder(s, 0.055, 0.02, Vector3(0, 1.08, -0.235), "clock_face", false, 20)
	clock.rotation.x = PI * 0.5
	Geo.box(s, Vector3(0.004, 0.04, 0.004), Vector3(0, 1.095, -0.223), "black", false)
	Geo.box(s, Vector3(0.03, 0.004, 0.004), Vector3(0.012, 1.08, -0.223), "black", false)
	# Apron with knobs.
	Geo.box(s, Vector3(0.74, 0.1, 0.02), Vector3(0, 0.79, 0.31), "chrome_worn", false, 0.006)
	for i in 5:
		var k := Geo.cylinder(s, 0.022, 0.03, Vector3(-0.28 + i * 0.14, 0.79, 0.33), "black", false, 12)
		k.rotation.x = PI * 0.5
	# Oven door with window and a bar handle; broiler drawer under it.
	Geo.box(s, Vector3(0.62, 0.42, 0.02), Vector3(0, 0.5, 0.315), "enamel_old", false, 0.015)
	Geo.box(s, Vector3(0.34, 0.16, 0.01), Vector3(0, 0.52, 0.327), "window_dark", false, 0.01)
	Geo.box(s, Vector3(0.5, 0.025, 0.035), Vector3(0, 0.69, 0.345), "chrome_worn", false, 0.01)
	Geo.box(s, Vector3(0.62, 0.14, 0.02), Vector3(0, 0.17, 0.315), "enamel_old", false, 0.012)
	Geo.box(s, Vector3(0.2, 0.025, 0.03), Vector3(0, 0.2, 0.335), "chrome_worn", false, 0.01)
	Geo.box(s, Vector3(0.76, 0.04, 0.6), Vector3(0, 0.02, -0.01), "black", false, 0.01)
	# A dish towel over the oven handle.
	Geo.box(s, Vector3(0.22, 0.26, 0.012), Vector3(-0.12, 0.57, 0.36), "towel", false, 0.005)
	Geo.box(s, Vector3(0.22, 0.04, 0.05), Vector3(-0.12, 0.69, 0.35), "towel", false, 0.012)
	var positions := [Vector3(-0.18, 0.905, -0.12), Vector3(0.18, 0.905, -0.12), Vector3(-0.18, 0.905, 0.15), Vector3(0.18, 0.905, 0.15)]
	for p in positions:
		Geo.cylinder(s, 0.09, 0.01, p, "chrome_worn", false, 18)
		Geo.cylinder(s, 0.035, 0.016, p + Vector3(0, 0.006, 0), "iron", false, 12)
		Geo.box(s, Vector3(0.2, 0.016, 0.018), p + Vector3(0, 0.018, 0), "iron", false, 0.006)
		Geo.box(s, Vector3(0.018, 0.016, 0.2), p + Vector3(0, 0.018, 0), "iron", false, 0.006)
		var flame := Geo.cylinder(s, 0.055, 0.02, p + Vector3(0, 0.02, 0), Geo.emissive(Color(0.25, 0.45, 1.0), 1.6), false, 16)
		flame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		flame.visible = false
		s.flames.append(flame)
	# The percolator on the back burner.
	var perc := Node3D.new()
	perc.position = positions[1] + Vector3(0, 0.02, 0)
	s.add_child(perc)
	Geo.cylinder(perc, 0.06, 0.2, Vector3(0, 0.1, 0), "chrome_worn", false, 16)
	Geo.cylinder(perc, 0.045, 0.03, Vector3(0, 0.215, 0), "chrome_worn", false, 16)
	Geo.sphere(perc, 0.018, Vector3(0, 0.24, 0), Geo.glass())
	Geo.box(perc, Vector3(0.025, 0.14, 0.03), Vector3(0.075, 0.12, 0), "black", false, 0.01)
	var glow := OmniLight3D.new()
	glow.light_color = Color(0.55, 0.65, 1.0)
	glow.omni_range = 1.4
	glow.light_energy = 0.0
	glow.position = Vector3(0, 1.0, 0.05)
	glow.visible = false
	s.add_child(glow)
	s.glow = glow
	return s


static func _sink() -> Node3D:
	var s := Sink.new()
	s.display_name = "sink"
	# Painted base cabinet: two doors and a drawer, chrome pulls, enamel top.
	Geo.box(s, Vector3(0.96, 0.84, 0.56), Vector3(0, 0.45, -0.02), "cabinet_paint", true, 0.012)
	Geo.box(s, Vector3(0.96, 0.08, 0.5), Vector3(0, 0.04, -0.05), "black", false, 0.005)
	for x in [-0.235, 0.235]:
		Geo.box(s, Vector3(0.44, 0.52, 0.025), Vector3(x, 0.38, 0.265), "cabinet_paint", false, 0.01)
		Geo.box(s, Vector3(0.34, 0.42, 0.01), Vector3(x, 0.38, 0.28), "cabinet_paint", false, 0.006)
		Geo.box(s, Vector3(0.02, 0.07, 0.03), Vector3(x + (0.17 if x < 0 else -0.17), 0.52, 0.29), "chrome_worn", false, 0.008)
	Geo.box(s, Vector3(0.9, 0.12, 0.025), Vector3(0, 0.74, 0.265), "cabinet_paint", false, 0.01)
	Geo.box(s, Vector3(0.14, 0.025, 0.03), Vector3(0, 0.74, 0.29), "chrome_worn", false, 0.008)
	# Counter and basin.
	Geo.box(s, Vector3(1.0, 0.045, 0.6), Vector3(0, 0.89, 0), "enamel_old", false, 0.015)
	Geo.box(s, Vector3(1.0, 0.025, 0.02), Vector3(0, 0.875, 0.3), "chrome_worn", false, 0.008)
	Geo.box(s, Vector3(0.5, 0.012, 0.36), Vector3(0.05, 0.909, 0.03), "chrome_worn", false, 0.03)
	Geo.box(s, Vector3(0.44, 0.01, 0.3), Vector3(0.05, 0.912, 0.03), "black", false, 0.03)
	Geo.box(s, Vector3(0.96, 0.12, 0.03), Vector3(0, 0.97, -0.285), "enamel_old", false, 0.01)
	# Gooseneck faucet and taps.
	Geo.cylinder(s, 0.016, 0.22, Vector3(0.05, 1.02, -0.22), "chrome_worn", false, 10)
	var spout := Geo.cylinder(s, 0.013, 0.16, Vector3(0.05, 1.13, -0.15), "chrome_worn", false, 10)
	spout.rotation.x = PI * 0.5
	for x in [-0.08, 0.18]:
		Geo.cylinder(s, 0.02, 0.05, Vector3(x, 0.94, -0.22), "chrome_worn", false, 8)
		Geo.box(s, Vector3(0.07, 0.012, 0.015), Vector3(x, 0.97, -0.22), "chrome_worn", false, 0.005)
	Geo.box(s, Vector3(1.0, 0.86, 0.56), Vector3(0, 0.45, -0.02), "cabinet_paint", false)
	return s


static func _wall_cabinet() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "cupboard"
	c.cid = "wall_cabinet"
	c.title = "Kitchen cupboard"
	c.verb = "Open the cupboard"
	# Painted wooden wall cabinets with raised panels, like photo-era tenements.
	Geo.box(c, Vector3(1.6, 0.72, 0.32), Vector3(0, 0.36, 0), "cabinet_paint", true, 0.01)
	Geo.box(c, Vector3(1.66, 0.05, 0.36), Vector3(0, 0.745, 0.01), "cabinet_paint", false, 0.012)
	for i in 3:
		var x := -0.53 + i * 0.53
		Geo.box(c, Vector3(0.5, 0.66, 0.02), Vector3(x, 0.36, 0.165), "cabinet_paint", false, 0.008)
		Geo.box(c, Vector3(0.38, 0.52, 0.012), Vector3(x, 0.36, 0.178), "cabinet_paint", false, 0.006)
		Geo.box(c, Vector3(0.02, 0.07, 0.03), Vector3(x + 0.19, 0.12, 0.19), "chrome_worn", false, 0.008)
	return c


static func _tub() -> Node3D:
	var t := KitchenTub.new()
	t.display_name = "tub"
	# Enamel tub on claw feet, with the board lid used as a counter.
	Geo.box(t, Vector3(1.6, 0.5, 0.74), Vector3(0, 0.36, 0), "enamel_old", true, 0.12)
	Geo.box(t, Vector3(1.64, 0.05, 0.78), Vector3(0, 0.6, 0), "enamel_old", false, 0.025)
	for x in [-0.66, 0.66]:
		for z in [-0.26, 0.26]:
			Geo.sphere(t, 0.05, Vector3(x, 0.07, z), "iron", 1.2)
	for i in 4:
		Geo.box(t, Vector3(1.66, 0.035, 0.195), Vector3(0, 0.645, -0.3 + i * 0.2), "wood_light", false, 0.008)
	Geo.box(t, Vector3(0.05, 0.02, 0.76), Vector3(-0.6, 0.67, 0), "wood_mid", false, 0.006)
	Geo.box(t, Vector3(0.05, 0.02, 0.76), Vector3(0.6, 0.67, 0), "wood_mid", false, 0.006)
	var w := Geo.box(t, Vector3(1.4, 0.01, 0.56), Vector3(0, 0.52, 0), Geo.emissive(Color(0.25, 0.32, 0.36), 1.0), false)
	w.visible = false
	t.water = w
	return t


static func _kitchen_table() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "kitchen table"
	c.cid = "kitchen_drawer"
	c.title = "Kitchen table drawer"
	c.verb = "Open the table drawer"
	# Formica dinette with a ribbed chrome edge.
	Geo.box(c, Vector3(1.0, 0.035, 0.7), Vector3(0, 0.745, 0), "formica_yellow", false, 0.03)
	Geo.box(c, Vector3(1.01, 0.03, 0.71), Vector3(0, 0.72, 0), "chrome_worn", false, 0.012)
	Geo.box(c, Vector3(0.9, 0.08, 0.6), Vector3(0, 0.67, 0), "chrome_worn", false, 0.01)
	Geo.box(c, Vector3(0.36, 0.06, 0.012), Vector3(0, 0.67, 0.305), "formica_yellow", false, 0.005)
	Geo.box(c, Vector3(0.1, 0.018, 0.025), Vector3(0, 0.67, 0.315), "chrome_worn", false, 0.008)
	for x in [-0.44, 0.44]:
		for z in [-0.29, 0.29]:
			Geo.cylinder(c, 0.017, 0.72, Vector3(x, 0.36, z), "chrome_worn", false, 10)
			Geo.cylinder(c, 0.024, 0.02, Vector3(x, 0.01, z), "black", false, 10)
	Geo.add_box_shape(c, Vector3(1.0, 0.76, 0.7), Vector3(0, 0.38, 0))
	return c


static func _chair() -> Node3D:
	var b := StaticBody3D.new()
	# Chrome dinette chair, red vinyl, a split in the seat.
	Geo.box(b, Vector3(0.42, 0.07, 0.42), Vector3(0, 0.47, 0), "vinyl_red", false, 0.03)
	Geo.box(b, Vector3(0.42, 0.24, 0.06), Vector3(0, 0.78, -0.2), "vinyl_red", false, 0.03)
	Geo.box(b, Vector3(0.1, 0.004, 0.005), Vector3(0.05, 0.506, 0.06), "black", false)
	for x in [-0.18, 0.18]:
		for z in [-0.18, 0.18]:
			Geo.cylinder(b, 0.012, 0.44, Vector3(x, 0.22, z), "chrome_worn", false, 8)
		Geo.cylinder(b, 0.012, 0.42, Vector3(x, 0.68, -0.21), "chrome_worn", false, 8)
	Geo.add_box_shape(b, Vector3(0.42, 0.5, 0.42), Vector3(0, 0.25, 0))
	return b


static func _candy_bowl() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "candy bowl"
	c.cid = "candy_bowl"
	c.title = "Bowl of Halloween candy"
	c.verb = "Take from the candy bowl"
	Geo.cylinder(c, 0.11, 0.07, Vector3(0, 0.035, 0), "pumpkin", true, 20)
	Geo.box(c, Vector3(0.05, 0.02, 0.03), Vector3(0.02, 0.075, 0.01), "cooler_red", false)
	Geo.box(c, Vector3(0.04, 0.02, 0.03), Vector3(-0.03, 0.075, -0.02), "car_yellow", false)
	Geo.box(c, Vector3(0.04, 0.018, 0.025), Vector3(0.0, 0.08, -0.05), "car_green", false)
	return c


static func _breadbox() -> Node3D:
	var c := ContainerProp.new()
	c.display_name = "breadbox"
	c.cid = "breadbox"
	c.title = "Breadbox"
	c.verb = "Open the breadbox"
	Geo.box(c, Vector3(0.36, 0.18, 0.24), Vector3(0, 0.09, 0), "chrome_worn", true, 0.06)
	Geo.box(c, Vector3(0.3, 0.025, 0.01), Vector3(0, 0.12, 0.122), "cooler_red", false, 0.004)
	return c


static func _phone() -> Node3D:
	var p := WallPhone.new()
	p.display_name = "wall phone"
	# A yellow rotary wall phone.
	Geo.box(p, Vector3(0.17, 0.23, 0.09), Vector3(0, 0.115, 0.045), "phone_yellow", true, 0.035)
	Geo.box(p, Vector3(0.05, 0.22, 0.06), Vector3(-0.11, 0.125, 0.1), "phone_yellow", false, 0.025)
	Geo.box(p, Vector3(0.06, 0.05, 0.07), Vector3(-0.11, 0.24, 0.11), "phone_yellow", false, 0.022)
	Geo.box(p, Vector3(0.06, 0.05, 0.07), Vector3(-0.11, 0.01, 0.11), "phone_yellow", false, 0.022)
	var dial := Geo.cylinder(p, 0.05, 0.012, Vector3(0.015, 0.1, 0.093), "chrome_worn", false, 20)
	dial.rotation.x = PI * 0.5
	var face := Geo.cylinder(p, 0.022, 0.014, Vector3(0.015, 0.1, 0.095), "clock_face", false, 16)
	face.rotation.x = PI * 0.5
	for i in 10:
		var a := -0.4 + i * 0.5
		var hole := Geo.cylinder(p, 0.007, 0.016, Vector3(0.015 + cos(a) * 0.036, 0.1 + sin(a) * 0.036, 0.096), "black", false, 6)
		hole.rotation.x = PI * 0.5
	# The coiled cord, hanging.
	for i in 6:
		Geo.box(p, Vector3(0.02, 0.02, 0.02), Vector3(-0.115, -0.03 - i * 0.04, 0.12 + sin(i) * 0.005), "phone_yellow", false, 0.009)
	return p


static func _ceiling_globe() -> Node3D:
	var f := Fixture.new()
	f.display_name = "ceiling light"
	f.verb = ""
	Geo.cylinder(f, 0.08, 0.04, Vector3(0, -0.02, 0), "chrome_worn", false, 16)
	Geo.sphere(f, 0.13, Vector3(0, -0.15, 0), "enamel_old", 1.05)
	Geo.cylinder(f, 0.02, 0.03, Vector3(0, -0.29, 0), "chrome_worn", false, 8)
	return f


static func _cafe_curtain() -> Node3D:
	# Cafe curtains on a tension rod over the lower half of the window.
	var n := Node3D.new()
	var w := 0.74
	Geo.cylinder(n, 0.007, w + 0.04, Vector3(0, 0.45, 0), "chrome_worn", false, 8).rotation.z = PI * 0.5
	for i in 7:
		var x := -w * 0.5 + 0.05 + i * (w - 0.1) / 6.0
		var panel := Geo.box(n, Vector3(0.1, 0.44, 0.012), Vector3(x, 0.23, 0.0 if i % 2 == 0 else 0.015), "curtain_kitchen", false, 0.005)
		panel.rotation.y = 0.35 if i % 2 == 0 else -0.35
	return n


static func _doorway_curtain() -> Node3D:
	# A curtain hung in the doorway instead of a door, tied back to each side.
	var n := Node3D.new()
	Geo.cylinder(n, 0.01, 1.0, Vector3(0, 2.0, 0), "wood_dark", false, 8).rotation.z = PI * 0.5
	for side in [-1.0, 1.0]:
		var x: float = side * 0.36
		for k in 3:
			var p := Geo.box(n, Vector3(0.09, 1.95, 0.025), Vector3(x + side * k * 0.035, 1.0, 0.02 + k * 0.012), "curtain_doorway", false, 0.01)
			p.rotation.y = 0.3 * side * (1 if k % 2 == 0 else -1)
		Geo.box(n, Vector3(0.16, 0.04, 0.07), Vector3(x + side * 0.03, 1.0, 0.04), "jar_lid", false, 0.015)
	return n


static func _paper_bags() -> Node3D:
	var b := StaticBody3D.new()
	# Grocery bags from Thursday, never unpacked.
	Geo.box(b, Vector3(0.3, 0.4, 0.18), Vector3(0, 0.2, 0), "paper_bag", false, 0.012)
	Geo.box(b, Vector3(0.3, 0.06, 0.18), Vector3(0, 0.42, -0.02), "paper_bag", false, 0.02).rotation.x = -0.25
	Geo.box(b, Vector3(0.28, 0.32, 0.17), Vector3(0.16, 0.16, 0.2), "paper_bag", false, 0.012).rotation.y = 0.4
	Geo.box(b, Vector3(0.1, 0.14, 0.1), Vector3(0.2, 0.36, 0.2), "wood_light", false, 0.03)
	Geo.sphere(b, 0.04, Vector3(0.1, 0.34, 0.22), "pumpkin_soft")
	Geo.add_box_shape(b, Vector3(0.45, 0.42, 0.42), Vector3(0.07, 0.21, 0.1))
	return b


static func _jars() -> Node3D:
	# Jars and a coffee can on the counter.
	var n := Node3D.new()
	var specs := [
		[Vector3(0, 0, 0), 0.045, 0.16, "jar_label_red"],
		[Vector3(0.1, 0, 0.02), 0.04, 0.13, "jar_label_green"],
		[Vector3(0.05, 0, 0.1), 0.05, 0.11, "jar_label_red"],
		[Vector3(-0.1, 0, 0.05), 0.055, 0.15, "can_tin"],
	]
	for s in specs:
		var p: Vector3 = s[0]
		var r: float = s[1]
		var h: float = s[2]
		Geo.cylinder(n, r, h, p + Vector3(0, h * 0.5, 0), "paper_bag" if s[3] != "can_tin" else "can_tin", false, 16)
		Geo.cylinder(n, r + 0.002, h * 0.45, p + Vector3(0, h * 0.45, 0), s[3], false, 16)
		Geo.cylinder(n, r * 0.92, 0.02, p + Vector3(0, h + 0.01, 0), "jar_lid", false, 16)
	return n


static func _wall_clock() -> Node3D:
	var n := Node3D.new()
	var face := Geo.cylinder(n, 0.13, 0.04, Vector3(0, 0, 0.02), "jar_lid", false, 24)
	face.rotation.x = PI * 0.5
	var inner := Geo.cylinder(n, 0.11, 0.045, Vector3(0, 0, 0.022), "clock_face", false, 24)
	inner.rotation.x = PI * 0.5
	# Stopped at 1:04, when the power went.
	var hr := Geo.box(n, Vector3(0.01, 0.06, 0.005), Vector3(0, 0, 0.048), "black", false)
	hr.rotation.z = -0.55
	hr.position += Vector3(sin(0.55) * 0.03, cos(0.55) * 0.03, 0)
	var mn := Geo.box(n, Vector3(0.007, 0.09, 0.005), Vector3(0, 0, 0.05), "black", false)
	mn.rotation.z = -0.42
	mn.position += Vector3(sin(0.42) * 0.045, cos(0.42) * 0.045, 0)
	return n


static func _plant() -> Node3D:
	var n := Node3D.new()
	Geo.cylinder(n, 0.06, 0.1, Vector3(0, 0.05, 0), "pumpkin_soft", false, 12)
	for i in 6:
		var a := i * 1.1
		Geo.sphere(n, 0.06, Vector3(cos(a) * 0.05, 0.14 + (i % 3) * 0.04, sin(a) * 0.05), "stem", 0.45).rotation.z = a
	return n


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
	# A red picnic cooler with a white lid and a swing handle.
	Geo.box(c, Vector3(0.42, 0.27, 0.3), Vector3(0, 0.135, 0), "cooler_red2", false, 0.04)
	Geo.box(c, Vector3(0.44, 0.06, 0.32), Vector3(0, 0.3, 0), "enamel_old", false, 0.025)
	Geo.box(c, Vector3(0.025, 0.07, 0.03), Vector3(-0.2, 0.28, 0), "chrome_worn", false, 0.01)
	Geo.box(c, Vector3(0.025, 0.07, 0.03), Vector3(0.2, 0.28, 0), "chrome_worn", false, 0.01)
	Geo.box(c, Vector3(0.022, 0.13, 0.022), Vector3(-0.2, 0.37, 0), "chrome_worn", false, 0.01)
	Geo.box(c, Vector3(0.022, 0.13, 0.022), Vector3(0.2, 0.37, 0), "chrome_worn", false, 0.01)
	Geo.box(c, Vector3(0.42, 0.025, 0.025), Vector3(0, 0.43, 0), "chrome_worn", false, 0.011)
	Geo.box(c, Vector3(0.14, 0.03, 0.035), Vector3(0, 0.43, 0), "black", false, 0.014)
	# Dial thermometer clipped to the front.
	Geo.cylinder(c, 0.05, 0.015, Vector3(0.1, 0.15, 0.155), "chrome_worn", false, 20).rotation.x = PI * 0.5
	Geo.cylinder(c, 0.043, 0.017, Vector3(0.1, 0.15, 0.157), "clock_face", false, 20).rotation.x = PI * 0.5
	var pivot := Node3D.new()
	pivot.position = Vector3(0.1, 0.15, 0.167)
	c.add_child(pivot)
	Geo.box(pivot, Vector3(0.004, 0.034, 0.003), Vector3(0, 0.017, 0), "cooler_red", false)
	c.needle = pivot
	Geo.box(c, Vector3(0.05, 0.007, 0.002), Vector3(0.1, 0.19, 0.166), Geo.emissive(Color(0.2, 0.55, 0.2), 1.0), false)
	Geo.box(c, Vector3(0.12, 0.05, 0.003), Vector3(-0.09, 0.15, 0.151), "paper", false, 0.002)
	Geo.add_box_shape(c, Vector3(0.44, 0.33, 0.32), Vector3(0, 0.165, 0))
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
	light.omni_range = 3.6
	light.omni_attenuation = 1.5
	light.light_energy = 0.9
	light.shadow_enabled = true
	light.shadow_blur = 2.0
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
