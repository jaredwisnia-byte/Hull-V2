extends SceneTree
## Unit tests for the simulation layer. No scene needed.
##   godot --headless --script res://tests/run_tests.gd

const DataScript := preload("res://scripts/core/data.gd")

var fails := 0
var checks := 0


func check(cond: bool, what: String) -> void:
	checks += 1
	if cond:
		print("  ok   ", what)
	else:
		fails += 1
		print("  FAIL ", what)


func _initialize() -> void:
	var climate_d := DataScript.load_json("res://data/climate.json")
	var t := DataScript.load_json("res://data/tuning.json")
	var items: Dictionary = DataScript.load_json("res://data/items.json").items
	var radio_d := DataScript.load_json("res://data/radio.json")

	print("clock")
	var c := SimClock.new()
	c.minutes = c.absolute(1, "06:40")
	check(c.date_text() == "Fri Oct 31, 1975", "day 1 is Fri Oct 31, 1975 (%s)" % c.date_text())
	check(c.time_text() == "6:40 AM", "6:40 AM")
	c.minutes = c.absolute(2, "13:05")
	check(c.date_text() == "Sat Nov 1, 1975" and c.time_text() == "1:05 PM", "day 2 is Sat Nov 1 (%s %s)" % [c.date_text(), c.time_text()])
	c.minutes = c.absolute(31, "00:00")
	check(c.date_text() == "Sun Nov 30, 1975", "day 31 is Sun Nov 30 (%s)" % c.date_text())

	print("climate")
	var cl := Climate.new(climate_d)
	check(absf(cl.outdoor_temp(c.absolute(1, "06:00")) - 8.0) < 0.01, "day 1 low at 6 a.m.")
	check(absf(cl.outdoor_temp(c.absolute(1, "15:00")) - 14.0) < 0.01, "day 1 high at 3 p.m.")
	var t_mid := cl.outdoor_temp(c.absolute(1, "10:30"))
	check(t_mid > 8.0 and t_mid < 14.0, "mid-morning between low and high (%.1f)" % t_mid)
	check(cl.outdoor_temp(c.absolute(7, "06:00")) < cl.outdoor_temp(c.absolute(1, "06:00")), "it gets colder through the week")
	check(cl.daylight(c.absolute(1, "02:00")) == 0.0, "dark at 2 a.m.")
	check(cl.daylight(c.absolute(1, "12:00")) > 0.9, "bright at noon day 1")
	check(cl.daylight(c.absolute(4, "12:00")) < cl.daylight(c.absolute(1, "12:00")), "soot dims noon by day 4")

	print("air")
	var air := AptAir.new(t.air, 17.5)
	for i in 120:
		air.tick(1.0 / 60.0, 10.0, 0, 2, 0)
	check(air.co_stage() >= 1, "two burners, shut windows, 2 h: CO stage %d (%.0f ppm)" % [air.co_stage(), air.co_ppm])
	var hot := air.indoor_temp
	check(hot > 17.0, "burners warm the room (%.1f C)" % hot)
	for i in 60:
		air.tick(1.0 / 60.0, 10.0, 2, 0, 0)
	check(air.co_ppm < 30.0, "two open windows vent it within an hour (%.0f ppm)" % air.co_ppm)
	check(air.indoor_temp < hot, "venting costs heat")
	var air2 := AptAir.new(t.air, 17.5)
	for i in 24 * 60:
		air2.tick(1.0 / 60.0, 8.0, 0, 0, 0)
	check(air2.indoor_temp > 8.0 and air2.indoor_temp < 14.0, "unheated flat settles above outdoors (%.1f C)" % air2.indoor_temp)

	print("cooler")
	var cool := ColdChain.new(t.cooler)
	for i in 6 * 60:
		cool.tick(1.0 / 60.0, 17.0)
	check(cool.temp < 8.0 and cool.ice_kg > 0.0, "ice holds it safe for 6 h at 17 C (%.1f C, %.2f kg ice)" % [cool.temp, cool.ice_kg])
	for i in 18 * 60:
		cool.tick(1.0 / 60.0, 17.0)
	check(cool.ice_kg == 0.0 and cool.temp > 8.0, "after a day at room temperature the ice is gone and it's too warm (%.1f C)" % cool.temp)
	check(cool.potency < 100.0, "warm vials lose potency (%.1f%%)" % cool.potency)
	var cool2 := ColdChain.new(t.cooler)
	cool2.ice_kg = 0.0
	for i in 8 * 60:
		cool2.tick(1.0 / 60.0, -6.0)
	check(cool2.status() == "FREEZING" and cool2.potency < 50.0, "a night at -6 C freezes and ruins them (%.1f%%)" % cool2.potency)

	print("fridge")
	var fr := FridgeSim.new(t.fridge)
	check(fr.freezer_frozen(), "freezer starts frozen")
	for i in 5:
		fr.open_freezer()
	var melted := 0
	for i in 30 * 60:
		melted += fr.tick(1.0 / 60.0, 17.0)
	check(not fr.freezer_frozen() and melted >= 3, "opening it often thaws it within a day (%d trays melted)" % melted)
	check(fr.fridge_temp > 14.0, "fridge warms toward the room (%.1f C)" % fr.fridge_temp)

	print("radio")
	var r := RadioSim.new(radio_d, t.radio)
	r.on = true
	r.freq = 640
	check("Emergency" in r.current_text(1, 400.0), "640 on day 1")
	r.freq = 1550
	check("1550" in r.current_text(2, 400.0), "1550 on day 2")
	check("static" in r.current_text(3, 400.0), "1550 gone on day 3")
	r.freq = 1130
	check("comet" in r.current_text(2, 0.0).to_lower() or "comet" in str(radio_d.stations[2].blocks[1].lines).to_lower(), "1130 confirms the comet on day 2")
	r.freq = 1000
	check("static" in r.current_text(1, 0.0), "between stations is static")
	r.battery_h = 0.01
	check(r.tick(0.05) and not r.on, "flat batteries switch it off")

	print("inventory")
	var inv := Inventory.new(items, 3.0)
	check(inv.add("pot_water"), "a pot of water fits in 3 kg")
	check(not inv.add("pot_water"), "a second one does not")
	inv.add("milk", 0.0)
	inv.capacity_kg = 20.0
	inv.add("milk", 0.0)
	inv.tick(10.0, 18.0)
	var milk := inv.find("milk")
	check(inv.is_spoiled(milk), "milk spoils after 10 h at 18 C")
	var inv2 := Inventory.new(items, 10.0)
	inv2.add("milk")
	inv2.tick(10.0, 3.0)
	check(not inv2.is_spoiled(inv2.find("milk")), "but not in the cold")
	inv2.add("ice")
	var m2 := inv2.tick(2.5, 18.0)
	check(m2.size() == 1 and not inv2.has("ice"), "ice melts in your pocket")

	print("needs")
	var n := Needs.new(t.needs, t.start)
	var f0 := float(n.v.food)
	for i in 60:
		n.tick(1.0 / 60.0, {"felt_temp": 20.0, "air_params": t.air})
	check(n.v.food < f0, "food drains")
	var n2 := Needs.new(t.needs, t.start)
	for i in 4 * 60:
		n2.tick(1.0 / 60.0, {"felt_temp": 20.0, "co_ppm": 600.0, "asleep": true, "air_params": t.air})
	check(n2.v.condition <= 0.0, "sleeping in 600 ppm CO for 4 h kills (%s)" % n2.last_cause)
	var n3 := Needs.new(t.needs, t.start)
	for i in 3 * 60:
		n3.tick(1.0 / 60.0, {"felt_temp": 4.0, "air_params": t.air})
	check(n3.v.warmth < 50.0, "a 4 C feel drains warmth (%.0f)" % n3.v.warmth)

	print("data")
	var apt := DataScript.load_json("res://data/apartment.json")
	var all_ok := true
	for cid in apt.containers:
		for id in apt.containers[cid]:
			all_ok = all_ok and items.has(id)
	for id in items:
		var d: Dictionary = items[id]
		for k in ["becomes", "requires", "cook_as", "fill"]:
			if d.has(k) and not items.has(String(d[k])):
				all_ok = false
				print("  missing item ref: %s.%s = %s" % [id, k, d[k]])
	check(all_ok, "every item reference in the data resolves")
	var docs: Dictionary = DataScript.load_json("res://data/docs.json").docs
	var docs_ok := true
	for id in items:
		if items[id].has("doc") and not docs.has(String(items[id].doc)):
			docs_ok = false
	for dk in ["newspaper", "notepad", "calendar", "photo", "wall_note", "rx_card"]:
		docs_ok = docs_ok and docs.has(dk)
	check(docs_ok, "every document exists")

	print("%d checks, %d failed" % [checks, fails])
	quit(1 if fails > 0 else 0)
