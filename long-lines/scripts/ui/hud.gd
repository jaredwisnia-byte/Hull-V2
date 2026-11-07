extends CanvasLayer
## Everything on screen: clock, meters, prompts, captions, radio subtitles,
## and the panels (inventory, containers, documents, sleep, pause, endings).

var player: Node

var clock_label: Label
var temp_label: Label
var prompt_label: Label
var info_label: Label
var dot: ColorRect
var caption_label: RichTextLabel
var radio_label: Label
var log_box: VBoxContainer
var meters := {}
var effect: ColorRect
var hint_label: Label

var panel_root: Control
var _open_panel: Control = null
var _caption_t := 0.0
var _container_id := ""
var _container_list: ItemList
var _inv_list: ItemList
var _inv_detail: Label
var _inv_weight: Label
var _inv_ids: Array = []

const METER_COLORS := {
	"warmth": Color(0.95, 0.55, 0.25),
	"food": Color(0.80, 0.70, 0.35),
	"water": Color(0.40, 0.65, 0.90),
	"rest": Color(0.60, 0.55, 0.85),
	"condition": Color(0.85, 0.30, 0.30),
	"morale": Color(0.55, 0.80, 0.55),
}


func _ready() -> void:
	layer = 10
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	effect = ColorRect.new()
	effect.set_anchors_preset(Control.PRESET_FULL_RECT)
	effect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	effect.color = Color(0, 0, 0, 0)
	root.add_child(effect)

	clock_label = _label(root, 20, Color(0.95, 0.92, 0.85))
	clock_label.position = Vector2(20, 14)
	temp_label = _label(root, 15, Color(0.85, 0.82, 0.76))
	temp_label.position = Vector2(20, 44)

	dot = ColorRect.new()
	dot.color = Color(1, 1, 1, 0.7)
	dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(dot)
	_center(dot, -2, 2, -2, 2)

	prompt_label = _label(root, 17, Color(1, 0.97, 0.9))
	prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_center(prompt_label, -450, 450, 24, 74)
	info_label = _label(root, 14, Color(0.8, 0.85, 0.9))
	info_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_center(info_label, -450, 450, 74, 120)

	radio_label = _label(root, 16, Color(1.0, 0.82, 0.5))
	radio_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	radio_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	radio_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	radio_label.offset_left = -480
	radio_label.offset_right = 480
	radio_label.offset_top = -150
	radio_label.offset_bottom = -100

	caption_label = RichTextLabel.new()
	caption_label.bbcode_enabled = true
	caption_label.fit_content = true
	caption_label.scroll_active = false
	caption_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	caption_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	caption_label.offset_left = -480
	caption_label.offset_right = 480
	caption_label.offset_top = -96
	caption_label.offset_bottom = -20
	caption_label.add_theme_font_size_override("normal_font_size", 17)
	root.add_child(caption_label)

	log_box = VBoxContainer.new()
	log_box.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	log_box.offset_left = -470
	log_box.offset_right = -18
	log_box.offset_top = 14
	log_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(log_box)

	var mbox := VBoxContainer.new()
	mbox.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	mbox.offset_left = 20
	mbox.offset_top = -170
	mbox.offset_bottom = -16
	mbox.offset_right = 230
	mbox.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(mbox)
	for k in Needs.KEYS:
		var row := HBoxContainer.new()
		row.mouse_filter = Control.MOUSE_FILTER_IGNORE
		mbox.add_child(row)
		var l := _label(row, 13, Color(0.9, 0.88, 0.82))
		l.text = k.capitalize()
		l.custom_minimum_size = Vector2(76, 0)
		var bar := ProgressBar.new()
		bar.custom_minimum_size = Vector2(130, 14)
		bar.show_percentage = false
		bar.max_value = 100
		bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var fill := StyleBoxFlat.new()
		fill.bg_color = METER_COLORS[k]
		var bg := StyleBoxFlat.new()
		bg.bg_color = Color(0, 0, 0, 0.45)
		bar.add_theme_stylebox_override("fill", fill)
		bar.add_theme_stylebox_override("background", bg)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(bar)
		meters[k] = bar

	hint_label = _label(root, 13, Color(0.75, 0.73, 0.68))
	hint_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	hint_label.offset_left = -330
	hint_label.offset_top = -40
	hint_label.offset_right = -18
	hint_label.offset_bottom = -14
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hint_label.text = "Tab inventory · F flashlight · Esc menu · F1 help"

	panel_root = Control.new()
	panel_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(panel_root)

	Game.message.connect(_on_message)
	Game.caption.connect(_on_caption)
	Game.slice_ended.connect(_on_slice_ended)
	Game.player_died.connect(_on_died)


## Anchors a control to the screen centre with pixel offsets around it.
func _center(c: Control, l: float, r: float, t: float, b: float) -> void:
	c.anchor_left = 0.5
	c.anchor_right = 0.5
	c.anchor_top = 0.5
	c.anchor_bottom = 0.5
	c.offset_left = l
	c.offset_right = r
	c.offset_top = t
	c.offset_bottom = b


func _label(parent: Node, size: int, color: Color) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("shadow_offset_x", 1)
	l.add_theme_constant_override("shadow_offset_y", 1)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(l)
	return l


# ------------------------------------------------------------ per frame

func _process(delta: float) -> void:
	var g := Game
	clock_label.text = "%s  ·  %s  ·  Day %d" % [g.clock.date_text(), g.clock.time_text(), g.clock.day()]
	temp_label.text = "Inside %d C  ·  Outside %d C  ·  Feels like %d C%s" % [
		roundi(g.air.indoor_temp), roundi(g.outdoor_temp()), roundi(g.felt_temp()),
		"  ·  wearing coat" if g.wearing_coat else ""]
	for k in meters:
		meters[k].value = g.needs.v[k]
	radio_label.text = g.radio.current_text(g.clock.day(), g.clock.minutes)

	var prompt := ""
	var info := ""
	if player and _open_panel == null:
		if player.held:
			var h: Carriable = player.held
			prompt = "Carrying the %s.  [E] Set down  [Q] Rotate" % h.display_name
			if h is RadioProp:
				prompt = "Carrying the radio.  [E] On/off  [wheel] Tune  [LMB] Set down"
			if player.target is WindowSash:
				prompt += "  [R] %s" % player.target.prompt_primary(player)
			info = h.info(player)
		elif player.target:
			var t: Interactable = player.target
			var p1 := t.prompt_primary(player)
			var p2 := t.prompt_secondary(player)
			if p1 != "":
				prompt = "[E] " + p1
			if p2 != "":
				prompt += ("    " if prompt != "" else "") + "[R] " + p2
			info = t.info(player)
	prompt_label.text = prompt
	info_label.text = info
	dot.color = Color(1, 0.85, 0.5, 0.9) if (player and player.target) else Color(1, 1, 1, 0.55)

	if _caption_t > 0.0:
		_caption_t -= delta
		if _caption_t <= 0.0:
			caption_label.text = ""

	# Screen effects: carbon monoxide greys and darkens; deep cold tints blue.
	var co := g.air.co_stage()
	var a := 0.0
	var col := Color(0.1, 0.1, 0.08)
	if co > 0:
		a = 0.08 * co + sin(Time.get_ticks_msec() * 0.002) * 0.03 * co
	if g.needs.v.warmth < 30.0:
		col = Color(0.2, 0.3, 0.45)
		a = maxf(a, (30.0 - g.needs.v.warmth) / 30.0 * 0.25)
	effect.color = Color(col.r, col.g, col.b, clampf(a, 0.0, 0.5))

	for c in log_box.get_children():
		var lab := c as Label
		var t: float = lab.get_meta("t") - delta
		lab.set_meta("t", t)
		if t < 1.5:
			lab.modulate.a = maxf(t / 1.5, 0.0)
		if t <= 0.0:
			lab.queue_free()


func _unhandled_input(event: InputEvent) -> void:
	if Game.dead or Game.slice_over:
		return
	if event.is_action_pressed("inventory"):
		if _open_panel and _open_panel.name == "Inventory":
			close_panel()
		elif _open_panel == null:
			open_inventory()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("pause"):
		if _open_panel:
			close_panel()
		else:
			open_pause()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed and event.physical_keycode == KEY_F1:
		if _open_panel == null:
			open_help()
	elif event.is_action_pressed("quicksave"):
		_on_message("Saved." if Game.save_game() else "Could not save.")
	elif event.is_action_pressed("quickload"):
		if Game.load_game():
			_on_message("Loaded.")


func _on_message(text: String) -> void:
	var l := _label(log_box, 15, Color(0.95, 0.93, 0.88))
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(450, 0)
	l.text = text
	l.set_meta("t", 9.0 + text.length() * 0.03)
	while log_box.get_child_count() > 5:
		log_box.get_child(0).queue_free()
		log_box.remove_child(log_box.get_child(0))


func _on_caption(text: String, kind: String) -> void:
	var color: String = {"sound": "#c9c3b5", "voice": "#ffe3b0", "thought": "#b9d4ff"}.get(kind, "#ffffff")
	var t := text
	if kind == "thought":
		t = "[i]%s[/i]" % text
	caption_label.text = "[center][color=%s]%s[/color][/center]" % [color, t]
	_caption_t = 7.0 + text.length() * 0.045


# ------------------------------------------------------------ panels

func _panel(title: String, w := 620.0, h := 460.0) -> VBoxContainer:
	close_panel()
	var bg := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.08, 0.07, 0.94)
	sb.border_color = Color(0.55, 0.45, 0.3)
	sb.set_border_width_all(1)
	sb.set_content_margin_all(18)
	bg.add_theme_stylebox_override("panel", sb)
	panel_root.add_child(bg)
	_center(bg, -w * 0.5, w * 0.5, -h * 0.5, h * 0.5)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	bg.add_child(v)
	var t := _label(v, 20, Color(1.0, 0.85, 0.6))
	t.text = title
	t.mouse_filter = Control.MOUSE_FILTER_PASS
	_open_panel = bg
	Game.ui_open = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	return v


func close_panel() -> void:
	if _open_panel:
		_open_panel.queue_free()
		_open_panel = null
	Game.ui_open = false
	Game.sim_paused = false
	if not Game.dead and not Game.slice_over and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func panel_is_open() -> bool:
	return _open_panel != null


func _button(parent: Node, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", 16)
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


func _body(parent: Node, bbcode: String, min_h := 0.0) -> RichTextLabel:
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.text = bbcode
	r.fit_content = min_h == 0.0
	r.custom_minimum_size = Vector2(0, min_h)
	r.size_flags_vertical = Control.SIZE_EXPAND_FILL
	r.add_theme_font_size_override("normal_font_size", 16)
	r.add_theme_font_size_override("bold_font_size", 16)
	r.add_theme_font_size_override("italics_font_size", 16)
	parent.add_child(r)
	return r


func open_reader(doc_id: String) -> void:
	var doc: Dictionary = Data.docs.get(doc_id, {"title": doc_id, "body": "(missing)"})
	var v := _panel(String(doc.title), 640, 470)
	_body(v, String(doc.body), 330)
	_button(v, "Put it down", close_panel)


func show_dialogue(text: String) -> void:
	var v := _panel("At the door", 640, 320)
	_body(v, text, 190)
	_button(v, "OK", close_panel)


func confirm(text: String, on_yes: Callable) -> void:
	var v := _panel("Are you sure?", 520, 240)
	_body(v, text, 90)
	var row := HBoxContainer.new()
	v.add_child(row)
	_button(row, "Yes", func():
		close_panel()
		on_yes.call())
	_button(row, "Not yet", close_panel)


func open_help() -> void:
	var v := _panel("Long Lines: apartment slice", 640, 470)
	_body(v, "[b]Friday, October 31, 1975. Dawn.[/b] The power went out at 1 a.m. Terry was on the overnight shift at 33 Thomas Street and the phones are dead.\n\n"
		+ "[b]Move[/b] WASD · [b]Look[/b] mouse · [b]Use[/b] E · [b]Other action[/b] R · [b]Carry[/b] R, then E to set down, Q to rotate\n"
		+ "[b]Inventory[/b] Tab · [b]Flashlight[/b] F · [b]Tune radio[/b] mouse wheel or [ ] · [b]Crouch[/b] C\n"
		+ "[b]Save / load[/b] F5 / F9 · [b]Menu[/b] Esc\n\n"
		+ "Keep the medicine cooler between 2 and 8 C. Take a dose every day. The fridge is dead; the freezer won't hold forever. "
		+ "The gas range works, and so does carbon monoxide. Open a window.", 300)
	_button(v, "Got it", close_panel)


func open_sleep() -> void:
	var v := _panel("Sleep", 420, 330)
	var warn := ""
	if Game.air.co_stage() >= 1:
		warn = "[color=#ff9a7a]Your head is pounding. The air in here is bad.[/color]\n"
	if Game.burners > 0:
		warn += "[color=#ff9a7a]The gas is still on.[/color]\n"
	_body(v, warn + "How long?")
	for opt in [[1.0, "Nap for an hour"], [4.0, "Sleep four hours"], [8.0, "Sleep the night (8 hours)"]]:
		var hours: float = opt[0]
		_button(v, opt[1], func(): _do_sleep(hours))
	_button(v, "Not now", close_panel)


func _do_sleep(hours: float) -> void:
	close_panel()
	var slept := Game.sleep(hours)
	if not Game.dead:
		_on_message("You slept %.1f hours." % slept)
		Game.save_game()


func open_pause() -> void:
	Game.sim_paused = true
	var v := _panel("Paused", 360, 320)
	_button(v, "Resume", close_panel)
	_button(v, "Save", func(): _on_message("Saved." if Game.save_game() else "Could not save."); close_panel())
	var lb := _button(v, "Load last save", func():
		close_panel()
		if Game.load_game():
			_on_message("Loaded."))
	lb.disabled = not Game.has_save()
	_button(v, "Controls", open_help)
	_button(v, "Quit", func(): get_tree().quit())


func open_inventory() -> void:
	var v := _panel("What you're carrying", 720, 500)
	_inv_weight = _label(v, 14, Color(0.8, 0.78, 0.72))
	var row := HBoxContainer.new()
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(row)
	_inv_list = ItemList.new()
	_inv_list.custom_minimum_size = Vector2(380, 300)
	_inv_list.add_theme_font_size_override("font_size", 15)
	row.add_child(_inv_list)
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(right)
	_inv_detail = _label(right, 14, Color(0.9, 0.88, 0.82))
	_inv_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_inv_detail.custom_minimum_size = Vector2(260, 120)
	_inv_list.item_selected.connect(func(_i): _inv_select())
	_button(right, "Use", _inv_use)
	_button(v, "Close", close_panel)
	_refresh_inventory()


func _refresh_inventory() -> void:
	if _inv_list == null or not is_instance_valid(_inv_list):
		return
	var sel := _inv_list.get_selected_items()
	_inv_list.clear()
	_inv_ids.clear()
	for g in Game.inv.grouped():
		var t := "%s%s" % [g.name, ("  x%d" % g.n) if g.n > 1 else ""]
		if g.spoiled:
			t += "  (spoiled)"
		var e := Game.inv.find(g.id)
		if e.has("uses"):
			t += "  (%d left)" % int(e.uses)
		_inv_list.add_item(t)
		_inv_ids.append(g.id)
	_inv_weight.text = "%.1f / %.0f kg  ·  Doses: %s" % [Game.inv.weight(), Game.inv.capacity_kg,
		"taken today" if Game.dose_taken_day >= Game.clock.day() else "not taken today"]
	if not sel.is_empty() and sel[0] < _inv_list.item_count:
		_inv_list.select(sel[0])
	_inv_select()


func _inv_select() -> void:
	var sel := _inv_list.get_selected_items()
	if sel.is_empty():
		_inv_detail.text = "Select something."
		return
	var id: String = _inv_ids[sel[0]]
	var d: Dictionary = Data.items.get(id, {})
	var lines: Array = [String(d.get("name", id)), "%.2f kg" % float(d.get("kg", 0))]
	if d.has("verb"):
		lines.append("Use: " + String(d.verb))
	if d.has("requires"):
		lines.append("Needs: " + Data.item_name(String(d.requires)))
	if d.has("spoil_h"):
		var e := Game.inv.find(id)
		var left := float(d.spoil_h) - float(e.get("age_h", 0.0))
		lines.append("Spoiled." if left <= 0.0 else ("Going off soon." if left < 6.0 else "Fresh enough."))
	if d.has("melt_h"):
		lines.append("Melting. Get it into the cooler.")
	_inv_detail.text = "\n".join(lines)


func _inv_use() -> void:
	var sel := _inv_list.get_selected_items()
	if sel.is_empty():
		return
	var id: String = _inv_ids[sel[0]]
	var r := Game.use_item(id)
	if r.begins_with("doc:"):
		open_reader(r.substr(4))
		return
	if r.begins_with("spawn:"):
		close_panel()
		get_tree().current_scene.spawn_into_hand(r.substr(6))
		return
	if r != "":
		_on_message(r)
	_refresh_inventory()


func open_container(cid: String, title: String) -> void:
	_container_id = cid
	var v := _panel(title, 620, 440)
	_container_list = ItemList.new()
	_container_list.custom_minimum_size = Vector2(0, 250)
	_container_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_container_list.add_theme_font_size_override("font_size", 15)
	v.add_child(_container_list)
	_container_list.item_activated.connect(func(i): _take(i))
	var row := HBoxContainer.new()
	v.add_child(row)
	_button(row, "Take", func():
		var s := _container_list.get_selected_items()
		if not s.is_empty():
			_take(s[0]))
	_button(row, "Take all", func():
		_on_message(Game.take_all(_container_id))
		_refresh_container())
	_button(row, "Close", close_panel)
	_refresh_container()


func _take(i: int) -> void:
	var r := Game.take_from_container(_container_id, i)
	if r != "":
		_on_message(r)
	_refresh_container()


func _refresh_container() -> void:
	_container_list.clear()
	var list := Game.container_contents(_container_id)
	if list.is_empty():
		_container_list.add_item("(empty)")
		_container_list.set_item_disabled(0, true)
		return
	for e in list:
		var t := Data.item_name(String(e.id))
		var d: Dictionary = Data.items.get(e.id, {})
		if d.has("spoil_h") and float(e.age_h) >= float(d.spoil_h):
			t += "  (smells off)"
		_container_list.add_item(t)


func _on_slice_ended(summary: String) -> void:
	var v := _panel("End of the apartment slice", 620, 420)
	_body(v, "You slide the chain off and step out onto the landing. Below you, the stairwell is dark and full of voices.\n\n[b]Next in the full game: the building, Walter and Concetta, and Sullivan Street.[/b]\n\n" + summary, 260)
	_button(v, "Keep playing in the apartment", func():
		Game.slice_over = false
		close_panel())
	_button(v, "Quit", func(): get_tree().quit())


func _on_died(cause: String) -> void:
	var v := _panel("You died", 560, 320)
	var extra := ""
	if cause == "carbon monoxide poisoning":
		extra = "\n\nThe gas range, the shut windows. You never smelled a thing."
	_body(v, "%s, %s.\nCause: %s.%s" % [Game.clock.date_text(), Game.clock.time_text(), cause, extra], 150)
	_button(v, "Load last save", func():
		close_panel()
		if Game.load_game():
			_on_message("Loaded.")
		else:
			get_tree().reload_current_scene())
	_button(v, "Start over", func():
		close_panel()
		Game.new_game()
		get_tree().reload_current_scene())
