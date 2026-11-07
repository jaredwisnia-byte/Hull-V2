class_name CoolerProp
extends Carriable
## The picnic cooler holding Nick's medicine. Two hands to carry.
## Put it out on the fire escape on a cold night; bring it in before it freezes.

var needle: Node3D


func _ready() -> void:
	super._ready()
	two_handed = true


func prompt_primary(_p: Node) -> String:
	if held:
		return ""
	if Game.inv.has("ice"):
		return "Pack ice into the cooler"
	if Game.dose_due():
		return "Take today's dose"
	return "Check the thermometer"


func primary(p: Node) -> void:
	if Game.inv.has("ice"):
		say(Game.add_ice_to_cooler())
	elif Game.dose_due():
		say(Game.take_dose())
	else:
		say(_reading())
	if not Game.fired_events.has("rx_card_hint"):
		Game.fired_events["rx_card_hint"] = true
		p.hud.open_reader("rx_card")


func info(_p: Node) -> String:
	return _reading()


func _reading() -> String:
	var c := Game.cooler
	return "Thermometer %.1f C (%s) · %s · %d vials%s" % [
		c.temp, c.status(), c.ice_text(), c.vials,
		"" if Game.dose_taken_day >= Game.clock.day() else " · today's dose not taken"]


func on_picked_up() -> void:
	Game.cooler_place = "held"


func on_placed() -> void:
	Game.cooler_place = "outside" if global_position.z < -0.02 else "inside"


func _process(_d: float) -> void:
	if needle:
		# Dial: -10 C far left, +20 C far right.
		needle.rotation.z = -clampf((Game.cooler.temp + 10.0) / 30.0, 0.0, 1.0) * PI + PI * 0.5
