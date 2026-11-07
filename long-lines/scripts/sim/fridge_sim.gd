class_name FridgeSim
extends RefCounted
## A dead refrigerator. The fridge compartment warms toward the room; the
## freezer holds below zero for a while if you keep the door shut, then its
## ice trays melt one by one.

var p: Dictionary
var fridge_temp := 8.5
var freezer_hours_left := 22.0
var melt_progress := 0.0


func _init(params: Dictionary) -> void:
	p = params
	fridge_temp = float(p.start_fridge_temp)
	freezer_hours_left = float(p.freezer_frozen_hours)


func freezer_frozen() -> bool:
	return freezer_hours_left > 0.0


func freezer_temp() -> float:
	if freezer_frozen():
		return lerpf(-1.0, -12.0, clampf(freezer_hours_left / float(p.freezer_frozen_hours), 0.0, 1.0))
	return fridge_temp


## Returns the number of ice trays that melted this tick.
func tick(dt_h: float, room: float) -> int:
	fridge_temp += (room - fridge_temp) * (1.0 - exp(-dt_h / float(p.fridge_tau_h)))
	if freezer_frozen():
		freezer_hours_left -= dt_h
		return 0
	melt_progress += dt_h
	var melted := 0
	while melt_progress >= float(p.tray_melt_hours):
		melt_progress -= float(p.tray_melt_hours)
		melted += 1
	return melted


func open_fridge() -> void:
	fridge_temp += float(p.fridge_open_warm)


func open_freezer() -> void:
	freezer_hours_left = maxf(0.0, freezer_hours_left - float(p.freezer_open_cost_h))


func to_dict() -> Dictionary:
	return {"fridge_temp": fridge_temp, "freezer_hours_left": freezer_hours_left, "melt_progress": melt_progress}


func from_dict(d: Dictionary) -> void:
	fridge_temp = float(d.get("fridge_temp", fridge_temp))
	freezer_hours_left = float(d.get("freezer_hours_left", freezer_hours_left))
	melt_progress = float(d.get("melt_progress", melt_progress))
