class_name Fixture
extends Interactable
## A fixed thing that only answers when you try it: dead TV, cold radiator,
## a light switch that clicks and does nothing.

var verb := "Try it"
var lines: Array = []
var _i := 0


func prompt_primary(_p: Node) -> String:
	return verb


func primary(_p: Node) -> void:
	if lines.is_empty():
		return
	say(String(lines[_i % lines.size()]))
	_i += 1
