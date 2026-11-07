class_name RadioProp
extends Carriable
## A battery transistor radio. E switches it on, the mouse wheel or [ ] tunes.

var dial_label: Label3D


func prompt_primary(_p: Node) -> String:
	if Game.radio.battery_h <= 0.0:
		return "Turn the knob (batteries flat)"
	return "Switch the radio off" if Game.radio.on else "Switch the radio on"


func primary(_p: Node) -> void:
	if Game.radio.battery_h <= 0.0:
		say("Not even a hiss. The batteries are done.")
		return
	Game.radio.on = not Game.radio.on


func scroll(_p: Node, dir: int) -> bool:
	Game.radio.tune(dir)
	return true


func info(_p: Node) -> String:
	var r := Game.radio
	var s := "AM %d kHz" % r.freq
	if r.on:
		s += "  ·  wheel or [ ] to tune"
	s += "  ·  batteries %s" % ("good" if r.battery_h > 4.0 else ("weak" if r.battery_h > 1.0 else "nearly dead"))
	return s


func _process(_d: float) -> void:
	if dial_label:
		dial_label.text = "%d" % Game.radio.freq
		dial_label.modulate = Color(1.0, 0.75, 0.3) if Game.radio.on else Color(0.25, 0.22, 0.18)
