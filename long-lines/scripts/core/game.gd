extends Node
## The apartment slice's game state: clock, climate, needs, air, cooler,
## fridge, radio, inventory and containers, all advanced together one game
## minute at a time. Scene nodes read from here and call into it.

signal message(text: String)
signal caption(text: String, kind: String)
signal slice_ended(summary: String)
signal player_died(cause: String)
signal state_loaded

const SAVE_PATH := "user://apartment_slice_save.json"

var clock: SimClock
var climate: Climate
var needs: Needs
var air: AptAir
var cooler: ColdChain
var fridge: FridgeSim
var radio: RadioSim
var inv: Inventory

## Container id -> Array of entries ({id, age_h, uses?})
var containers := {}
var flags := {}           # name -> absolute game minute it expires
var fired_events := {}
var open_windows := {}    # window id -> bool
var lit_candles := {}     # candle id -> true
var burners := 0
var cooler_place := "inside"   # inside | outside | held
var near_stove := false
var wearing_coat := false
var tub_full := false
var flashlight_on := false
var flashlight_charge_h := 3.5
var dose_taken_day := 0
var doses_missed := 0
var dose_debt := 0.0
var trick_or_treat_given := false
var talked_to_walter := false

var asleep := false
var dead := false
var ui_open := false
var sim_paused := false
var slice_over := false
var _wake_requested := false
var _last_co_stage := 0
var _warned := {}

## Set by main.gd: Callable(type: String, id: String) -> Node, used on load.
var spawner: Callable


func _ready() -> void:
	_setup_input()
	new_game()


func new_game() -> void:
	var t: Dictionary = Data.tuning
	clock = SimClock.new()
	clock.minutes = clock.absolute(int(t.time.start_day), String(t.time.start_time))
	climate = Climate.new(Data.climate)
	needs = Needs.new(t.needs, t.start)
	air = AptAir.new(t.air, float(t.start.indoor_temp))
	cooler = ColdChain.new(t.cooler)
	fridge = FridgeSim.new(t.fridge)
	radio = RadioSim.new(Data.radio, t.radio)
	inv = Inventory.new(Data.items, float(t.start.carry_capacity_kg))
	inv.add("keys")
	containers = {}
	var start_contents: Dictionary = Data.apartment.get("containers", {})
	for cid in start_contents:
		var list: Array = []
		for id in start_contents[cid]:
			list.append(Inventory.make_entry(Data.items, id))
		containers[cid] = list
	# Food in a dead fridge has already been warming since 1 a.m.
	for e in containers.get("fridge", []):
		e.age_h = 2.0
	flags = {}
	fired_events = {}
	open_windows = {}
	lit_candles = {}
	burners = 0
	cooler_place = "inside"
	wearing_coat = false
	tub_full = false
	flashlight_on = false
	flashlight_charge_h = float(t.flashlight.battery_h)
	dose_taken_day = 0
	doses_missed = 0
	dose_debt = 0.0
	trick_or_treat_given = false
	talked_to_walter = false
	asleep = false
	dead = false
	slice_over = false
	_last_co_stage = 0
	_warned = {}


# ---------------------------------------------------------------- time

func _process(delta: float) -> void:
	if sim_paused or dead or asleep:
		return
	advance(delta * float(Data.tuning.time.game_minutes_per_real_second))


## Advances the world by game minutes, in steps of at most one minute.
func advance(game_minutes: float) -> void:
	var left := game_minutes
	while left > 0.0 and not dead:
		var step := minf(left, 1.0)
		_tick(step)
		left -= step


func _tick(dt_min: float) -> void:
	var prev_day := clock.day()
	clock.minutes += dt_min
	var dt_h := dt_min / 60.0
	var out := outdoor_temp()

	air.tick(dt_h, out, open_window_count(), burners, lit_candles.size())
	var melted_trays := fridge.tick(dt_h, air.indoor_temp)
	for i in melted_trays:
		_remove_from_container("freezer", "ice")
	cooler.tick(dt_h, cooler_ambient())
	if radio.tick(dt_h):
		message.emit("The radio fades to a whisper and dies. The batteries are flat.")
	for n in inv.tick(dt_h, air.indoor_temp):
		message.emit("%s has melted into a puddle in your pocket." % n)
	_tick_containers(dt_h)
	if flashlight_on:
		flashlight_charge_h -= dt_h
		if flashlight_charge_h <= 0.0:
			flashlight_charge_h = 0.0
			if not _swap_flashlight_battery():
				flashlight_on = false
				message.emit("The flashlight browns out and dies.")

	var ctx := {
		"asleep": asleep,
		"felt_temp": felt_temp(),
		"co_ppm": air.co_ppm,
		"light": light_level(),
		"radio_on": radio.on,
		"dose_debt": dose_debt,
		"air_params": Data.tuning.air,
	}
	needs.tick(dt_h, ctx)

	if clock.day() != prev_day:
		_on_new_day(prev_day)
	_check_events()
	_check_warnings()

	if needs.v.condition <= 0.0 and not dead:
		dead = true
		player_died.emit(needs.last_cause)


func _tick_containers(dt_h: float) -> void:
	for cid in containers:
		var temp := air.indoor_temp
		if cid == "fridge":
			temp = fridge.fridge_temp
		elif cid == "freezer":
			temp = fridge.freezer_temp()
		var rate := Inventory.spoil_rate(temp)
		var list: Array = containers[cid]
		for i in range(list.size() - 1, -1, -1):
			var e: Dictionary = list[i]
			var d: Dictionary = Data.items.get(e.id, {})
			if d.has("melt_h"):
				if temp > 0.0:
					e.age_h += dt_h
					if e.age_h >= float(d.melt_h):
						list.remove_at(i)
			elif d.has("spoil_h"):
				e.age_h += dt_h * rate


func _on_new_day(prev_day: int) -> void:
	if dose_taken_day < prev_day:
		doses_missed += 1
		dose_debt += 1.0
		message.emit("You never took yesterday's dose. Your joints ache and your forehead is hot.")
	else:
		dose_debt = maxf(0.0, dose_debt - 0.5)


## Sleeps up to `hours`, waking early for knocks and danger.
## Returns the number of hours actually slept.
func sleep(hours: float) -> float:
	asleep = true
	_wake_requested = false
	var slept := 0
	var total := int(hours * 60.0)
	while slept < total and not dead:
		_tick(1.0)
		slept += 1
		if _wake_requested:
			break
		if needs.v.warmth <= 0.0 or needs.v.water <= 0.0 or needs.v.food <= 0.0:
			message.emit("You wake up shivering and parched. Something is wrong.")
			break
		if needs.v.rest >= 100.0 and slept > 60:
			break
	asleep = false
	return slept / 60.0


# ---------------------------------------------------------------- queries

func outdoor_temp() -> float:
	return climate.outdoor_temp(clock.minutes)


func daylight() -> float:
	return climate.daylight(clock.minutes)


func light_level() -> float:
	var l := daylight() * 0.85 + minf(lit_candles.size(), 3) * 0.16
	if flashlight_on:
		l += 0.25
	if burners > 0:
		l += 0.05
	return clampf(l, 0.0, 1.0)


func felt_temp() -> float:
	return needs.felt_temp(air.indoor_temp, wearing_coat, asleep, near_stove and burners > 0)


func cooler_ambient() -> float:
	match cooler_place:
		"outside":
			return outdoor_temp()
		"held":
			return air.indoor_temp + float(Data.tuning.cooler.held_body_bonus)
	return air.indoor_temp


func open_window_count() -> int:
	var n := 0
	for k in open_windows:
		if open_windows[k]:
			n += 1
	return n


func set_flag(name: String, minutes_from_now: float) -> void:
	flags[name] = clock.minutes + minutes_from_now


func flag_active(name: String) -> bool:
	return float(flags.get(name, -1.0)) > clock.minutes


func dose_due() -> bool:
	return dose_taken_day < clock.day() and cooler.vials > 0


# ---------------------------------------------------------------- events

func _check_events() -> void:
	var day := clock.day()
	var mod := clock.minute_of_day()
	for e in Data.events:
		var id: String = e.id
		if fired_events.has(id) or int(e.day) != day:
			continue
		var at := SimClock.parse_hhmm(String(e.at))
		if mod < at:
			continue
		fired_events[id] = true
		if mod > at + 90.0:
			continue  # long past (e.g. slept through it)
		if e.has("flag"):
			set_flag(String(e.flag), float(e.get("flag_minutes", 30)))
		if asleep and not e.get("wake", false):
			continue
		if asleep and e.get("wake", false):
			_wake_requested = true
			message.emit("A knock wakes you.")
		caption.emit(String(e.text), String(e.get("kind", "sound")))


func _check_warnings() -> void:
	var stage := air.co_stage()
	if stage > _last_co_stage:
		match stage:
			1:
				message.emit("A dull headache is building behind your eyes.")
			2:
				message.emit("The room tilts when you turn your head. You feel sick.")
			3:
				message.emit("You're so tired. Maybe just sit down a minute...")
	_last_co_stage = stage
	_warn_once("cooler_warm", cooler.temp > float(Data.tuning.cooler.safe_max),
		"The cooler's dial has crept past 8 degrees. The vials won't take that for long.")
	_warn_once("cooler_freeze", cooler.temp < 0.5,
		"The needle in the cooler is touching zero. If the vials freeze, they're ruined.")
	_warn_once("ice_gone", cooler.ice_kg <= 0.0,
		"The last of the ice in the cooler has melted.")
	_warn_once("freezer_thaw", not fridge.freezer_frozen(),
		"Water is dripping from the freezer door. It isn't holding cold any more.")
	_warn_once("thirsty", needs.v.water < 20.0, "Your mouth is dry and you're getting a headache.")
	_warn_once("hungry", needs.v.food < 20.0, "Your stomach is cramping. You need to eat.")
	_warn_once("tired", needs.v.rest < 15.0, "You keep reading the same line twice. You need sleep.")
	_warn_once("cold", needs.v.warmth < 30.0, "You can't stop shivering.")


func _warn_once(key: String, cond: bool, text: String) -> void:
	if cond and not _warned.get(key, false):
		_warned[key] = true
		message.emit(text)
	elif not cond and _warned.get(key, false) and key in ["cooler_warm", "cooler_freeze", "thirsty", "hungry", "tired", "cold"]:
		_warned[key] = false


# ---------------------------------------------------------------- containers

func container_contents(cid: String) -> Array:
	if not containers.has(cid):
		containers[cid] = []
	return containers[cid]


func on_container_opened(cid: String) -> void:
	if cid == "fridge":
		fridge.open_fridge()
	elif cid == "freezer":
		fridge.open_freezer()


func take_from_container(cid: String, index: int) -> String:
	var list := container_contents(cid)
	if index < 0 or index >= list.size():
		return ""
	var e: Dictionary = list[index]
	if not inv.can_take(e.id):
		return "Too heavy. You're carrying %.1f of %.0f kg." % [inv.weight(), inv.capacity_kg]
	inv.add_entry(e)
	list.remove_at(index)
	return "Took: %s." % Data.item_name(e.id)


func take_all(cid: String) -> String:
	var list := container_contents(cid)
	var took := 0
	var left := 0
	var i := 0
	while i < list.size():
		if inv.can_take(list[i].id):
			inv.add_entry(list[i])
			list.remove_at(i)
			took += 1
		else:
			left += 1
			i += 1
	if took == 0 and left == 0:
		return "Nothing left in there."
	if left > 0:
		return "Took %d things. %d too heavy to carry." % [took, left]
	return "Took %d things." % took


func put_in_container(cid: String, item_id: String) -> String:
	var e := inv.take(item_id)
	if e.is_empty():
		return ""
	container_contents(cid).append(e)
	return "Put away: %s." % Data.item_name(item_id)


func _remove_from_container(cid: String, item_id: String) -> void:
	var list := container_contents(cid)
	for i in list.size():
		if list[i].id == item_id:
			list.remove_at(i)
			return


# ---------------------------------------------------------------- actions

## Uses one item from the inventory. Returns a message, or "" if nothing happened.
## May return "spawn:<type>" for items that become props in the hand.
func use_item(id: String) -> String:
	var d: Dictionary = Data.items.get(id, {})
	if d.is_empty() or not inv.has(id):
		return ""
	if d.has("doc"):
		return "doc:" + String(d.doc)
	if d.has("spawn"):
		inv.take(id)
		return "spawn:" + String(d.spawn)
	if id == "ice":
		return add_ice_to_cooler()
	if d.get("brew", false):
		return "Coffee needs a lit burner and a pot of water. Use the stove."
	if not d.has("use"):
		return "You turn the %s over in your hands. Not much use right now." % String(d.name).to_lower()
	if d.has("requires") and not inv.has(String(d.requires)):
		return "You need a %s for that." % Data.item_name(String(d.requires)).to_lower()
	var e := inv.take(id)
	var spoiled := inv.is_spoiled(e)
	var effects: Dictionary = d.use
	for k in effects:
		needs.add(k, float(effects[k]))
	var msg := "%s." % String(d.get("verb", "Used it"))
	if spoiled:
		var bad: Dictionary = d.get("spoiled_use", {"condition": -10.0, "morale": -5.0})
		for k in bad:
			needs.add(k, float(bad[k]))
		msg = "It had turned. You get it down, and your stomach turns too."
	if d.has("becomes"):
		inv.add(String(d.becomes))
	if id == "cigarettes":
		inv.add("cigarettes")  # a pack lasts the slice
	return msg


func add_ice_to_cooler() -> String:
	if not inv.has("ice"):
		return "You have no ice."
	if cooler_place == "outside":
		return "The cooler is out on the fire escape."
	inv.take("ice")
	cooler.add_ice(float(Data.items.ice.kg))
	return "You crack the tray into the cooler around the vials and shut the lid."


func take_dose() -> String:
	if cooler.vials <= 0:
		return "The cooler is empty. No more vials."
	if dose_taken_day >= clock.day():
		return "You've had today's dose."
	if cooler.temp < -0.5:
		cooler.vials -= 1
		dose_taken_day = clock.day()
		dose_debt += 0.5
		return "The vial is a slush of ice crystals. You use it anyway. It probably won't do much."
	cooler.vials -= 1
	dose_taken_day = clock.day()
	var weak := float(Data.tuning.cooler.weak_dose_below)
	if cooler.potency < weak:
		dose_debt += 0.5
		return "You take the dose. The vial looked cloudy. You're not sure it's doing anything any more."
	needs.add("morale", 3.0)
	return "You draw the vial, find a spot on your arm, and take the dose. %d left." % cooler.vials


func drink_from_tap() -> String:
	if needs.v.water >= 99.0:
		return "You're not thirsty."
	needs.add("water", 25.0)
	advance(2.0)
	return "You cup your hands under the tap. The water is cold and tastes of old pipes. Still running."


func fill_containers() -> String:
	var filled := 0
	for e in inv.entries:
		var d: Dictionary = Data.items.get(e.id, {})
		if d.has("fill"):
			var new_id := String(d.fill)
			var extra := float(Data.items[new_id].kg) - float(d.kg)
			if inv.weight() + extra > inv.capacity_kg:
				continue
			e.id = new_id
			e.age_h = 0.0
			filled += 1
	if filled == 0:
		return "You have nothing empty to fill."
	advance(2.0 * filled)
	return "Filled %d container%s at the tap." % [filled, "" if filled == 1 else "s"]


func fill_tub() -> String:
	if tub_full:
		return "The tub is full. Forty gallons, if nobody pulls the plug."
	advance(25.0)
	tub_full = true
	needs.add("morale", 6.0)
	return "You lift the lid, put the plug in and run the cold tap. Twenty-five minutes. The tub is full."


func scoop_from_tub() -> String:
	if not tub_full:
		return "The tub is empty."
	var r := fill_containers()
	if r.begins_with("Filled"):
		return r.replace("at the tap", "from the tub")
	if needs.v.water < 99.0:
		needs.add("water", 20.0)
		return "You scoop a drink from the tub with your hands."
	return r


func set_burners(n: int) -> void:
	burners = clampi(n, 0, 4)


func cook() -> String:
	if burners <= 0:
		return "Light a burner first."
	# Coffee first: it's what Nick wants.
	if inv.has("coffee") and inv.has("pot_water"):
		var c := inv.find("coffee")
		c["uses"] = int(c.get("uses", 1)) - 1
		if int(c.uses) <= 0:
			inv.take("coffee")
		var pot := inv.take("pot_water")
		pot.id = "pot"
		inv.add_entry(pot)
		advance(10.0)
		needs.add("water", 22.0)
		needs.add("warmth", 8.0)
		needs.add("morale", 12.0)
		return "You boil the water and make coffee the way Dad did, grounds and all. It's the best thing that's happened today."
	if not inv.has("pot"):
		return "You need an empty pot to cook in."
	for id in ["lasagna", "soup_can", "beans_can", "eggs"]:
		if not inv.has(id):
			continue
		var d: Dictionary = Data.items[id]
		if d.has("requires") and not inv.has(String(d.requires)):
			continue
		var food := inv.take(id)
		var spoiled := inv.is_spoiled(food)
		inv.take("pot")
		var hot := Inventory.make_entry(Data.items, String(d.cook_as))
		if spoiled:
			hot.age_h = 999.0
		inv.add_entry(hot)
		advance(12.0)
		return "Heated: %s. It smells like a normal day." % Data.item_name(String(d.cook_as)).to_lower()
	if inv.has("soup_can") or inv.has("beans_can"):
		return "You need a can opener."
	return "You have nothing to cook."


func light_match() -> bool:
	var m := inv.find("matches")
	if m.is_empty():
		return false
	m["uses"] = int(m.get("uses", 1)) - 1
	if int(m.uses) <= 0:
		inv.take("matches")
		message.emit("That was your last match.")
	return true


func set_candle(id: String, lit: bool) -> void:
	if lit:
		lit_candles[id] = true
	else:
		lit_candles.erase(id)


func toggle_flashlight() -> String:
	if not inv.has("flashlight"):
		return "You don't have a flashlight."
	if flashlight_on:
		flashlight_on = false
		return ""
	if flashlight_charge_h <= 0.0 and not _swap_flashlight_battery():
		return "Click. Dead batteries."
	flashlight_on = true
	return ""


func _swap_flashlight_battery() -> bool:
	if inv.count("battery_d") <= 0:
		return false
	inv.take("battery_d")
	flashlight_charge_h = float(Data.tuning.flashlight.battery_h)
	message.emit("You swap in a fresh D cell.")
	return true


func talk_to_walter() -> String:
	talked_to_walter = true
	flags.erase("walter_at_door")
	needs.add("morale", 4.0)
	return ("WALTER: \"Boiler's dead. Oil burner needs the electric, so don't hold your breath for heat. "
		+ "Water's still good up to you. Fill the tub, fill everything. And don't go lighting fires in there, "
		+ "this whole building's a matchbox. I got Mrs. Bruno to check on.\"\n[His footsteps go down the stairs.]")


func answer_trick_or_treat() -> String:
	flags.erase("trick_or_treat")
	if inv.has("candy"):
		inv.take("candy")
		trick_or_treat_given = true
		needs.add("morale", 15.0)
		return ("You open the door a crack. Lola Rivera's two kids, in bedsheet ghost costumes, hold out a pillowcase. "
			+ "You drop in a handful of candy. \"Thank you, Mr. Lombardi!\" Lola mouths thank you over their heads.")
	needs.add("morale", -3.0)
	return "You open the door a crack. Two little ghosts. You have nothing to give them. Lola steers them back down the stairs."


func end_slice() -> void:
	slice_over = true
	slice_ended.emit(summary())


func summary() -> String:
	var lines: Array = []
	lines.append("%s, %s. Day %d." % [clock.date_text(), clock.time_text(), clock.day()])
	lines.append("Vials: %d left, potency %d%%. Cooler at %.1f C (%s)." % [cooler.vials, int(cooler.potency), cooler.temp, cooler.status()])
	lines.append("Doses missed: %d." % doses_missed)
	lines.append("Tub: %s." % ("full of water" if tub_full else "empty"))
	lines.append("Walter: %s." % ("you talked through the door" if talked_to_walter else "you never answered"))
	if fired_events.has("trick"):
		lines.append("Halloween: %s." % ("you gave the Rivera kids candy" if trick_or_treat_given else "no candy for the Rivera kids"))
	lines.append("Carrying %.1f kg." % inv.weight())
	return "\n".join(lines)


# ---------------------------------------------------------------- save / load

func save_game() -> bool:
	var nodes := {}
	for n in get_tree().get_nodes_in_group("persist"):
		if n.has_method("save_data") and String(n.get("persist_id")) != "":
			nodes[n.persist_id] = n.save_data()
	var d := {
		"version": 1,
		"minutes": clock.minutes,
		"needs": needs.v,
		"air": air.to_dict(),
		"cooler": cooler.to_dict(),
		"fridge": fridge.to_dict(),
		"radio": radio.to_dict(),
		"inventory": inv.entries,
		"containers": containers,
		"flags": flags,
		"fired_events": fired_events,
		"open_windows": open_windows,
		"lit_candles": lit_candles,
		"burners": burners,
		"cooler_place": cooler_place,
		"wearing_coat": wearing_coat,
		"tub_full": tub_full,
		"flashlight_charge_h": flashlight_charge_h,
		"dose_taken_day": dose_taken_day,
		"doses_missed": doses_missed,
		"dose_debt": dose_debt,
		"trick_or_treat_given": trick_or_treat_given,
		"talked_to_walter": talked_to_walter,
		"warned": _warned,
		"nodes": nodes,
	}
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f == null:
		return false
	f.store_string(JSON.stringify(d))
	return true


func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)


func load_game() -> bool:
	var d := Data.load_json(SAVE_PATH)
	if d.is_empty():
		return false
	new_game()
	clock.minutes = float(d.minutes)
	for k in d.needs:
		needs.v[k] = float(d.needs[k])
	air.from_dict(d.air)
	cooler.from_dict(d.cooler)
	fridge.from_dict(d.fridge)
	radio.from_dict(d.radio)
	inv.entries = d.inventory
	containers = d.containers
	flags = d.flags
	fired_events = d.fired_events
	open_windows = d.open_windows
	lit_candles = d.lit_candles
	burners = int(d.burners)
	cooler_place = String(d.cooler_place)
	wearing_coat = bool(d.wearing_coat)
	tub_full = bool(d.tub_full)
	flashlight_charge_h = float(d.flashlight_charge_h)
	dose_taken_day = int(d.dose_taken_day)
	doses_missed = int(d.doses_missed)
	dose_debt = float(d.dose_debt)
	trick_or_treat_given = bool(d.trick_or_treat_given)
	talked_to_walter = bool(d.talked_to_walter)
	_warned = d.get("warned", {})
	_apply_node_state(d.get("nodes", {}))
	state_loaded.emit()
	return true


func _apply_node_state(nodes: Dictionary) -> void:
	var seen := {}
	for n in get_tree().get_nodes_in_group("persist"):
		var pid := String(n.get("persist_id"))
		if nodes.has(pid):
			n.load_data(nodes[pid])
			seen[pid] = true
		elif n.get("spawned"):
			n.queue_free()  # spawned after the save was made
	for pid in nodes:
		if seen.has(pid):
			continue
		var nd: Dictionary = nodes[pid]
		if nd.get("spawned", false) and spawner.is_valid():
			var node: Node = spawner.call(String(nd.type), String(pid))
			if node:
				node.load_data(nd)


# ---------------------------------------------------------------- input

func _setup_input() -> void:
	var keys := {
		"move_forward": [KEY_W, KEY_UP],
		"move_back": [KEY_S, KEY_DOWN],
		"move_left": [KEY_A, KEY_LEFT],
		"move_right": [KEY_D, KEY_RIGHT],
		"interact": [KEY_E],
		"secondary": [KEY_R],
		"rotate_held": [KEY_Q],
		"flashlight": [KEY_F],
		"inventory": [KEY_TAB, KEY_I],
		"pause": [KEY_ESCAPE],
		"tune_up": [KEY_BRACKETRIGHT],
		"tune_down": [KEY_BRACKETLEFT],
		"crouch": [KEY_C],
		"quicksave": [KEY_F5],
		"quickload": [KEY_F9],
	}
	for action in keys:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		for k in keys[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = k
			InputMap.action_add_event(action, ev)
	if not InputMap.has_action("click"):
		InputMap.add_action("click")
		var mb := InputEventMouseButton.new()
		mb.button_index = MOUSE_BUTTON_LEFT
		InputMap.action_add_event("click", mb)
