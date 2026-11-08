class_name CandleProp
extends Carriable
## A household candle. Light it with a match; it burns down over six hours.

var flame: Node3D
var light: OmniLight3D
var stick: Node3D
var lit := false
var burn_left_h := 6.0
var _last_minutes := -1.0


func _ready() -> void:
	super._ready()
	burn_left_h = float(Data.tuning.candle.burn_h)
	_refresh()


func prompt_primary(_p: Node) -> String:
	if burn_left_h <= 0.0:
		return "Burned down to a stub"
	return "Blow out the candle" if lit else "Light the candle"


func primary(_p: Node) -> void:
	if burn_left_h <= 0.0:
		return
	if lit:
		set_lit(false)
		return
	if not Game.light_match():
		say("You need matches.")
		return
	set_lit(true)


func set_lit(on: bool) -> void:
	lit = on
	Game.set_candle(persist_id, on)
	_refresh()


func _refresh() -> void:
	if flame:
		flame.visible = lit
	if light:
		light.visible = lit
	if stick:
		stick.scale.y = clampf(burn_left_h / float(Data.tuning.candle.burn_h), 0.08, 1.0)
		if flame:
			flame.position.y = 0.015 + 0.16 * stick.scale.y


func _process(_d: float) -> void:
	var m := Game.clock.minutes
	if _last_minutes >= 0.0 and lit:
		burn_left_h -= (m - _last_minutes) / 60.0
		if burn_left_h <= 0.0:
			burn_left_h = 0.0
			set_lit(false)
			say("A candle gutters out.")
		_refresh()
		if light:
			light.light_energy = 0.9 + sin(m * 7.0) * 0.05 + randf() * 0.05
	_last_minutes = m


func save_data() -> Dictionary:
	var d := super.save_data()
	d["lit"] = lit
	d["burn_left_h"] = burn_left_h
	return d


func load_data(d: Dictionary) -> void:
	super.load_data(d)
	burn_left_h = float(d.get("burn_left_h", burn_left_h))
	lit = bool(d.get("lit", false))
	_refresh()
