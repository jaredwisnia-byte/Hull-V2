class_name HallDoor
extends Interactable
## The door to the landing. Chained on the inside. Stepping out ends the slice.


func prompt_primary(_p: Node) -> String:
	if Game.flag_active("walter_at_door"):
		return "Answer Walter through the door"
	if Game.flag_active("trick_or_treat"):
		return "Open the door a crack (with the chain on)"
	return "Unchain the door and step out onto the landing"


func primary(p: Node) -> void:
	if Game.flag_active("walter_at_door"):
		p.hud.show_dialogue(Game.talk_to_walter())
		return
	if Game.flag_active("trick_or_treat"):
		p.hud.show_dialogue(Game.answer_trick_or_treat())
		return
	p.hud.confirm("Leave the apartment?\nThe test slice covers the apartment only, so this ends it.", func(): Game.end_slice())


func prompt_secondary(_p: Node) -> String:
	return "Listen at the door"


func secondary(_p: Node) -> void:
	var day := Game.clock.day()
	var h := Game.clock.hour_f()
	if h < 6.0 or h > 22.0:
		say("The landing is silent. Somewhere below, a radiator pipe ticks as it cools.")
	elif day == 1:
		say("Doors opening and shutting downstairs. A transistor radio on the third floor. Lenny's voice: \"...I'm telling you, it's the Russians.\"")
	elif day == 2:
		say("Someone is carrying water up the stairs, one heavy step at a time.")
	else:
		say("Quiet. Then Mrs. Bruno coughing, two floors down, for a long time.")


func info(_p: Node) -> String:
	return "4A. Chain on, deadbolt thrown."
