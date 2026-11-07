class_name RadioSim
extends RefCounted
## A battery transistor radio. Stations come and go by day.

var stations: Array = []
var p: Dictionary
var on := false
var freq := 1010
var battery_h := 7.5


func _init(radio_data: Dictionary, params: Dictionary) -> void:
	stations = radio_data.get("stations", [])
	p = params
	freq = int(p.start_freq)
	battery_h = float(p.start_battery_h)


func tune(steps: int) -> void:
	var band: Array = p.band
	freq = clampi(freq + steps * 10, int(band[0]), int(band[1]))


func _block_for(st: Dictionary, day: int) -> Dictionary:
	for b in st.blocks:
		if day >= int(b.days[0]) and day <= int(b.days[1]):
			return b
	return {}


## The station within capture range that is on the air today, or {}.
func station_at(f: int, day: int) -> Dictionary:
	var best := {}
	var best_d := 1e9
	for st in stations:
		var d: float = absf(float(st.freq) - f)
		if d <= float(p.capture_khz) and d < best_d and not _block_for(st, day).is_empty():
			best = st
			best_d = d
	return best


## What the speaker is putting out right now.
func current_text(day: int, minutes: float) -> String:
	if not on:
		return ""
	var st := station_at(freq, day)
	if st.is_empty():
		return "[%d kHz: static]" % freq
	var block := _block_for(st, day)
	var lines: Array = block.lines
	var idx := int(minutes / float(p.line_minutes)) % lines.size()
	var off: float = absf(float(st.freq) - freq)
	var text: String = lines[idx]
	if off > 0.0:
		text = "[through static] " + text
	return "%s: %s" % [st.name, text]


func tick(dt_h: float) -> bool:
	## Returns true if the batteries died this tick.
	if not on:
		return false
	battery_h -= dt_h
	if battery_h <= 0.0:
		battery_h = 0.0
		on = false
		return true
	return false


func to_dict() -> Dictionary:
	return {"on": on, "freq": freq, "battery_h": battery_h}


func from_dict(d: Dictionary) -> void:
	on = bool(d.get("on", on))
	freq = int(d.get("freq", freq))
	battery_h = float(d.get("battery_h", battery_h))
