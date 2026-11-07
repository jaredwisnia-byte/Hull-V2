class_name WallPhone
extends Interactable

var _tries := 0


func prompt_primary(_p: Node) -> String:
	return "Pick up the receiver"


func primary(_p: Node) -> void:
	_tries += 1
	if _tries == 1:
		say("No dial tone. Just your own breathing in the receiver. The last call on this line was Terry, at four in the morning: \"I'm on till morning. Stay put. I'll come to you.\"")
	elif _tries == 2:
		say("You dial the Long Lines switch room anyway. The dial whirs back. Nothing.")
	else:
		say("Dead. You hang it up gently, as if it might mind.")
