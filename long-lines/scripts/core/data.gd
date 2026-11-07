extends Node
## Loads every data file once. Everything tunable lives in res://data.

var climate: Dictionary
var tuning: Dictionary
var items: Dictionary
var radio: Dictionary
var events: Array
var docs: Dictionary
var apartment: Dictionary


func _init() -> void:
	load_all()


func load_all() -> void:
	climate = load_json("res://data/climate.json")
	tuning = load_json("res://data/tuning.json")
	items = load_json("res://data/items.json").get("items", {})
	radio = load_json("res://data/radio.json")
	events = load_json("res://data/events.json").get("events", [])
	docs = load_json("res://data/docs.json").get("docs", {})
	apartment = load_json("res://data/apartment.json")


static func load_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_error("Missing data file: %s" % path)
		return {}
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Bad JSON in %s" % path)
		return {}
	return parsed


func item_name(id: String) -> String:
	return items.get(id, {}).get("name", id)
