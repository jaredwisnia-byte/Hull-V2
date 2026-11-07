class_name WindowSash
extends Interactable
## A double-hung window. The lower sash slides up to open; open front windows
## let you climb out onto the fire escape, and let things be set down out there.

var opening_id := ""
var outside := ""          # fire_escape | airshaft
var sash: Node3D           # visual lower sash; moves up when open
var shape: CollisionShape3D  # its collider, a direct child of this body
var lift := 0.7
var is_open := false
var climb_in_point := Vector3.ZERO
var climb_out_point := Vector3.ZERO


func _ready() -> void:
	add_to_group("persist")


func prompt_primary(_p: Node) -> String:
	return "Close the window" if is_open else "Open the window"


func primary(_p: Node) -> void:
	set_open(not is_open)
	if is_open:
		say("The sash sticks, then shrieks up. Cold air and the smell of exhaust from the street." if outside == "fire_escape"
			else "You shove the sash up. The airshaft smells of damp brick and someone's cigarette.")


func prompt_secondary(p: Node) -> String:
	if not is_open or outside != "fire_escape":
		return ""
	if p.held != null and p.held.two_handed:
		return ""
	return "Climb back inside" if _player_outside(p) else "Climb out onto the fire escape"


func secondary(p: Node) -> void:
	if prompt_secondary(p) == "":
		return
	if _player_outside(p):
		p.teleport(climb_in_point)
	else:
		p.teleport(climb_out_point)
		if not Game.fired_events.has("fire_escape_first"):
			Game.fired_events["fire_escape_first"] = true
			say("Four floors up. The iron grating flexes under your weight. Sullivan Street is all stopped cars and nobody.")


func _player_outside(p: Node) -> bool:
	return p.global_position.z < 0.0


func set_open(on: bool) -> void:
	is_open = on
	Game.open_windows[opening_id] = on
	if sash:
		sash.position.y = lift if on else 0.0
	if shape:
		shape.position.y = (lift if on else 0.0) + lift * 0.5 + 0.02


func save_data() -> Dictionary:
	return {"open": is_open}


func load_data(d: Dictionary) -> void:
	set_open(bool(d.get("open", false)))
