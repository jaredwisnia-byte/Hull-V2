class_name Inventory
extends RefCounted
## What Nick carries. Every entry is one physical thing with its own age, so
## milk taken out of the fridge keeps going off in your bag.

var defs: Dictionary
var capacity_kg := 14.0
var entries: Array = []  # [{id, age_h, uses}]


func _init(item_defs: Dictionary, capacity: float) -> void:
	defs = item_defs
	capacity_kg = capacity


static func make_entry(defs_: Dictionary, id: String, age_h := 0.0) -> Dictionary:
	var e := {"id": id, "age_h": age_h}
	var d: Dictionary = defs_.get(id, {})
	if d.has("uses"):
		e["uses"] = int(d.uses)
	return e


func def(id: String) -> Dictionary:
	return defs.get(id, {})


func weight() -> float:
	var w := 0.0
	for e in entries:
		w += float(def(e.id).get("kg", 0.0))
	return w


func can_take(id: String) -> bool:
	return weight() + float(def(id).get("kg", 0.0)) <= capacity_kg + 0.0001


func add_entry(e: Dictionary) -> bool:
	if not can_take(e.id):
		return false
	entries.append(e)
	return true


func add(id: String, age_h := 0.0) -> bool:
	return add_entry(make_entry(defs, id, age_h))


func count(id: String) -> int:
	var n := 0
	for e in entries:
		if e.id == id:
			n += 1
	return n


func has(id: String) -> bool:
	return count(id) > 0


func find(id: String) -> Dictionary:
	for e in entries:
		if e.id == id:
			return e
	return {}


## Removes one, preferring the oldest (eat the milk before it turns).
func take(id: String) -> Dictionary:
	var best := -1
	for i in entries.size():
		if entries[i].id == id and (best < 0 or entries[i].age_h > entries[best].age_h):
			best = i
	if best < 0:
		return {}
	var e: Dictionary = entries[best]
	entries.remove_at(best)
	return e


func is_spoiled(e: Dictionary) -> bool:
	var d := def(e.id)
	return d.has("spoil_h") and float(e.age_h) >= float(d.spoil_h)


## Spoilage runs faster the warmer it is. 4 C or below barely ages food.
static func spoil_rate(temp: float) -> float:
	return clampf((temp - 4.0) / 8.0, 0.0, 3.0)


## Ages items. Returns names of things that melted away.
func tick(dt_h: float, temp: float) -> Array:
	var melted: Array = []
	var rate := spoil_rate(temp)
	for i in range(entries.size() - 1, -1, -1):
		var e: Dictionary = entries[i]
		var d := def(e.id)
		if d.has("melt_h"):
			e.age_h += dt_h
			if e.age_h >= float(d.melt_h):
				melted.append(d.name)
				entries.remove_at(i)
		elif d.has("spoil_h"):
			e.age_h += dt_h * rate
	return melted


## Grouped for display: [{id, name, n, kg, spoiled}]
func grouped() -> Array:
	var out: Array = []
	var index := {}
	for e in entries:
		var key: String = e.id + ("!" if is_spoiled(e) else "")
		if not index.has(key):
			index[key] = out.size()
			out.append({"id": e.id, "name": def(e.id).get("name", e.id), "n": 0, "kg": 0.0, "spoiled": is_spoiled(e)})
		var g: Dictionary = out[index[key]]
		g.n += 1
		g.kg += float(def(e.id).get("kg", 0.0))
	return out
