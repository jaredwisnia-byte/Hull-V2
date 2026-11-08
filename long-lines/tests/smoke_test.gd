class_name SmokeTest
extends RefCounted
## A scripted run through the slice inside the real scene: interact with props
## through the player's raycast, carry the cooler outside, cook with the gas on,
## sleep, save and load. Run with:  godot --headless -- --smoke

var main: Node3D
var player: Player
var fails: Array = []
var checks := 0


func check(cond: bool, what: String) -> void:
	checks += 1
	if cond:
		print("  ok   ", what)
	else:
		print("  FAIL ", what)
		fails.append(what)


func frames(n := 3) -> void:
	for i in n:
		await main.get_tree().physics_frame
		await main.get_tree().process_frame


## Stand at pos and look at a world point, then refresh the raycast.
func look_at_point(pos: Vector3, point: Vector3) -> void:
	player.teleport(pos)
	var eye := pos + Vector3(0, Player.EYE, 0)
	var d := point - eye
	var yaw := atan2(-d.x, -d.z)
	var pitch := atan2(d.y, Vector2(d.x, d.z).length())
	player.set_look(yaw, pitch)
	player.cam.position.y = Player.EYE
	await frames(4)


func run(m: Node3D) -> void:
	main = m
	player = m.player
	Game.sim_paused = true   # the test drives time itself
	print("SMOKE TEST: apartment slice")
	await frames(5)
	var props: Node3D = m.props_root
	check(props.get_node_or_null("cooler") is CoolerProp, "cooler prop built")
	check(props.get_node_or_null("radio") is RadioProp, "radio prop built")
	check(props.get_node_or_null("stove") is GasRange, "gas range built")
	check(Game.clock.day() == 1 and Game.clock.time_text() == "6:40 AM", "starts day 1 at 6:40 AM: %s" % Game.clock.time_text())

	# Look at the cooler on the kitchen table and take the morning dose.
	await look_at_point(Vector3(2.3, 0, 10.05), Vector3(1.85, 0.9, 10.6))
	check(player.target is CoolerProp, "raycast finds the cooler (got %s)" % [player.target])
	var vials := Game.cooler.vials
	player.try_primary()
	if m.hud.panel_is_open():
		m.hud.close_panel()
	Game.sim_paused = true
	check(Game.cooler.vials == vials - 1 and Game.dose_taken_day == 1, "took today's dose through the cooler")

	# Kitchen drawer and cupboard.
	Game.take_all("kitchen_drawer")
	Game.take_all("wall_cabinet")
	check(Game.inv.has("can_opener") and Game.inv.has("matches") and Game.inv.has("pot"), "searched drawer and cupboard")
	var food := float(Game.needs.v.food)
	Game.use_item("saltines")
	check(Game.needs.v.food > food, "ate saltines")

	# Radio: look at it on the side table by the window, switch on, tune to 640.
	await look_at_point(Vector3(1.65, 0, 1.0), Vector3(1.65, 0.68, 0.24))
	check(player.target is RadioProp, "raycast finds the radio")
	player.try_primary()
	check(Game.radio.on, "radio switched on")
	Game.radio.freq = 620
	player._scroll(1)
	player._scroll(1)
	check(Game.radio.freq == 640, "tuned to 640")
	check("Emergency" in Game.radio.current_text(1, Game.clock.minutes), "640 carries the Emergency Broadcast System")
	Game.radio.on = false

	# Open the front window and climb out to the fire escape.
	var win: WindowSash = null
	for n in main.get_tree().get_nodes_in_group("persist"):
		if n is WindowSash and n.opening_id == "window_front_left":
			win = n
	check(win != null, "front left window exists")
	await look_at_point(Vector3(0.85, 0, 0.8), Vector3(0.85, 1.1, -0.1))
	check(player.target == win, "raycast finds the window (got %s)" % [player.target])
	player.try_primary()
	await frames(2)
	check(win.is_open and Game.open_window_count() == 1, "window opened")
	await look_at_point(Vector3(0.85, 0, 0.8), Vector3(0.85, 0.74, 0.0))
	check(player.target == win, "aiming at the sill of the open window")
	player.try_secondary()
	await frames(3)
	check(player.global_position.z < -0.2, "climbed out onto the fire escape (z=%.2f)" % player.global_position.z)
	await look_at_point(player.global_position, Vector3(0.85, 0.74, -0.15))
	if player.target != win:
		var q := PhysicsRayQueryParameters3D.create(player.cam.global_position, player.cam.global_position - player.cam.global_transform.basis.z * 3.0)
		q.exclude = [player.get_rid()]
		var h := player.get_world_3d().direct_space_state.intersect_ray(q)
		print("    debug: eye ", player.cam.global_position, " hit ", h.get("collider"), " at ", h.get("position"))
	check(player.target == win, "window targetable from outside")
	player.try_secondary()
	await frames(3)
	check(player.global_position.z > 0.2, "climbed back in")

	# Carry the cooler to the fire escape and set it down outside.
	await look_at_point(Vector3(2.3, 0, 10.05), Vector3(1.85, 0.9, 10.6))
	player.try_secondary()
	check(player.held is CoolerProp and Game.cooler_place == "held", "picked up the cooler with both hands")
	player.teleport(Vector3(0.85, 0.05, -0.62))
	await frames(4)
	await look_at_point(Vector3(0.85, 0.05, -0.62), Vector3(1.5, 0.0, -0.6))
	check(not player.place_hit.is_empty(), "found a flat spot on the fire escape")
	player.try_primary()
	await frames(2)
	check(player.held == null and Game.cooler_place == "outside", "cooler set down outside (%s)" % Game.cooler_place)
	player.teleport(Vector3(0.85, 0.05, 0.7))
	win.set_open(false)
	await frames(2)

	# Gas range with the windows shut: carbon monoxide builds.
	await look_at_point(Vector3(2.3, 0, 9.75), Vector3(3.09, 0.9, 9.75))
	check(player.target is GasRange, "raycast finds the gas range")
	player.try_primary()
	player.try_primary()
	check(Game.burners == 2, "two burners lit")
	Game.take_all("fridge")
	var r := Game.cook()
	check(r.begins_with("Heated") or r.begins_with("You boil"), "cooked something: %s" % r)
	Game.advance(150)
	check(Game.air.co_stage() >= 1, "CO builds with burners on and windows shut (%.0f ppm)" % Game.air.co_ppm)
	var warm_kitchen := Game.air.indoor_temp
	win.set_open(true)
	Game.set_burners(0)
	Game.advance(60)
	check(Game.air.co_ppm < 60.0 and Game.air.co_stage() == 0, "an open window clears the air (%.0f ppm)" % Game.air.co_ppm)
	check(Game.air.indoor_temp < warm_kitchen, "and lets the heat out")
	win.set_open(false)

	# Walter knocks at 9:10.
	check(Game.fired_events.has("walter"), "Walter's knock fired by %s" % Game.clock.time_text())

	# Fill the tub.
	Game.fill_tub()
	check(Game.tub_full, "tub filled")

	# Bring the cooler back in before night and check it is safe-ish.
	var cooler: CoolerProp = props.get_node("cooler")
	cooler.global_position = Vector3(1.85, 0.76, 10.6)
	cooler.on_placed()
	check(Game.cooler_place == "inside", "cooler back on the table")

	# Halloween: advance to the trick-or-treaters.
	Game.take_all("candy_bowl")
	var target_m := Game.clock.absolute(1, "17:45")
	Game.advance(target_m - Game.clock.minutes)
	check(Game.flag_active("trick_or_treat"), "trick-or-treaters at the door at %s" % Game.clock.time_text())
	var morale := float(Game.needs.v.morale)
	Game.answer_trick_or_treat()
	check(Game.trick_or_treat_given and Game.needs.v.morale > morale, "gave the Rivera kids candy")

	# Save, change things, load.
	cooler.global_position = Vector3(1.5, 0.76, 10.7)
	check(Game.save_game(), "saved")
	var saved_min := Game.clock.minutes
	var saved_pot := Game.cooler.potency
	Game.advance(300)
	cooler.global_position = Vector3(2.0, 0.6, 11.0)
	check(Game.load_game(), "loaded")
	await frames(2)
	check(absf(Game.clock.minutes - saved_min) < 0.01, "clock restored")
	check(absf(Game.cooler.potency - saved_pot) < 0.01, "cooler restored")
	check(cooler.global_position.distance_to(Vector3(1.5, 0.76, 10.7)) < 0.01, "cooler position restored")

	# Eat and drink, then sleep the night.
	Game.use_item("hot_lasagna")
	Game.drink_from_tap()
	Game.drink_from_tap()
	Game.fill_containers()
	if Game.inv.has("pot_water"):
		Game.use_item("pot_water")
	var rest := float(Game.needs.v.rest)
	var slept := Game.sleep(8.0)
	check(slept > 1.0 and Game.needs.v.rest > rest, "slept %.1f h, rest %d -> %d" % [slept, roundi(rest), roundi(Game.needs.v.rest)])
	if Game.clock.day() == 1:
		Game.sleep(8.0)
	check(Game.clock.day() == 2, "it is day 2 (%s)" % Game.clock.date_text())
	check(Game.radio.station_at(770, 2).name.begins_with("770"), "770 still on the air day 2")
	check(Game.radio.station_at(1550, 3).is_empty(), "1550 gone by day 3")

	check(not Game.dead, "still alive (condition %d)" % roundi(Game.needs.v.condition))
	Game.end_slice()
	check(Game.slice_over, "door ends the slice")
	var libs := 0
	for n in props.get_children():
		if n.find_children("*", "MeshInstance3D", true, false).size() > 0:
			libs += 1
	check(props.get_child_count() >= 90, "the dressed apartment has %d props" % props.get_child_count())
	print(Game.summary())

	print("SMOKE TEST: %d checks, %d failed" % [checks, fails.size()])
	main.get_tree().quit(1 if fails.size() > 0 else 0)
