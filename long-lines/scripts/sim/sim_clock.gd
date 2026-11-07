class_name SimClock
extends RefCounted
## Game time, counted in minutes since midnight at the start of day 1
## (Friday, October 31, 1975).

const WEEKDAYS := ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const START_WEEKDAY := 4  # Friday

var minutes: float = 0.0


static func parse_hhmm(text: String) -> float:
	var parts := text.split(":")
	return float(parts[0]) * 60.0 + float(parts[1])


func day() -> int:
	return int(floor(minutes / 1440.0)) + 1


func minute_of_day() -> float:
	return fposmod(minutes, 1440.0)


func hour_f() -> float:
	return minute_of_day() / 60.0


func absolute(day_n: int, hhmm: String) -> float:
	return (day_n - 1) * 1440.0 + parse_hhmm(hhmm)


func date_text() -> String:
	var d := day()
	var dom := 31 + d - 1
	var month := "Oct"
	if dom > 31:
		dom -= 31
		month = "Nov"
		if dom > 30:
			dom -= 30
			month = "Dec"
	var wd: String = WEEKDAYS[(START_WEEKDAY + d - 1) % 7]
	return "%s %s %d, 1975" % [wd, month, dom]


func time_text() -> String:
	var m := int(minute_of_day())
	var h := m / 60
	var mm := m % 60
	var suffix := "AM" if h < 12 else "PM"
	var h12 := h % 12
	if h12 == 0:
		h12 = 12
	return "%d:%02d %s" % [h12, mm, suffix]
