class_name Screenshots
extends RefCounted
## Renders the slice from fixed viewpoints at chosen times of day.
## Run with a display (e.g. xvfb-run):  godot -- --shots=/path/to/dir

const SHOTS := [
	{"name": "p1_cans_counter", "day": 1, "time": "10:00", "pos": [1.9, 0, 10.2], "look": [2.5, 0.9, 10.75]},
	{"name": "tv1_front_room_morning", "day": 1, "time": "09:40", "pos": [1.7, 0, 2.4], "look": [0.3, 0.75, 1.6]},
	{"name": "tv2_close", "day": 1, "time": "10:30", "pos": [1.25, 0, 1.6], "look": [0.35, 0.72, 1.6]},
	{"name": "tv3_candle_night", "day": 1, "time": "21:00", "pos": [1.6, 0, 2.0], "look": [0.3, 0.75, 1.6], "candles": true},
	{"name": "a01_front_room", "day": 1, "time": "09:40", "pos": [2.9, 0, 3.0], "look": [0.8, 0.9, 0.6]},
	{"name": "a02_front_room_sofa", "day": 1, "time": "10:30", "pos": [0.9, 0, 0.9], "look": [2.4, 0.7, 3.5]},
	{"name": "a03_office", "day": 1, "time": "10:00", "pos": [0.7, 0, 4.3], "look": [3.0, 0.9, 5.4]},
	{"name": "a04_bedroom", "day": 1, "time": "11:00", "pos": [0.6, 0, 6.5], "look": [2.6, 0.6, 8.0]},
	{"name": "a05_closet", "day": 1, "time": "11:10", "pos": [2.0, 0, 7.6], "look": [2.9, 1.1, 8.9]},
	{"name": "a06_kitchen", "day": 1, "time": "09:00", "pos": [0.85, 0, 9.4], "look": [2.6, 1.0, 11.4]},
	{"name": "a07_entrance", "day": 1, "time": "12:00", "pos": [1.4, 0, 10.9], "look": [1.45, 1.1, 12.75]},
	{"name": "a08_bathroom", "day": 1, "time": "12:10", "pos": [2.75, 0, 11.75], "look": [2.75, 0.8, 12.7]},
	{"name": "a09_street_fire_escape", "day": 1, "time": "13:00", "pos": [1.6, 0.05, -0.5], "look": [3.0, -6.5, -12.0], "open": true},
	{"name": "a10_street_from_window", "day": 1, "time": "10:30", "pos": [1.5, 0, 1.0], "look": [1.0, -2.5, -12.0]},
	{"name": "a11_kitchen_candle_night", "day": 1, "time": "21:30", "pos": [0.85, 0, 9.5], "look": [1.7, 0.8, 10.8], "candles": true},
	{"name": "a12_front_room_night", "day": 1, "time": "20:00", "pos": [2.4, 0, 3.2], "look": [0.6, 0.9, 0.5], "candles": true},
]


func run(main: Node3D, dir: String, only := "") -> void:
	DirAccess.make_dir_recursive_absolute(dir)
	Game.sim_paused = true
	main.hud.close_panel()
	var player: Player = main.player
	for s in SHOTS:
		if only != "" and not String(s.name).begins_with(only):
			continue
		Game.clock.minutes = Game.clock.absolute(int(s.day), String(s.time))
		var pos := Vector3(s.pos[0], s.pos[1], s.pos[2])
		var look := Vector3(s.look[0], s.look[1], s.look[2])
		for n in main.get_tree().get_nodes_in_group("persist"):
			if n is WindowSash and n.outside == "fire_escape":
				n.set_open(s.get("open", false))
			if n is CandleProp:
				n.burn_left_h = float(Data.tuning.candle.burn_h)
				n._last_minutes = -1.0
				n.set_lit(s.get("candles", false))
		Game.set_burners(int(s.get("burners", 0)))
		player.teleport(pos)
		var eye := pos + Vector3(0, Player.EYE, 0)
		var d := look - eye
		player.set_look(atan2(-d.x, -d.z), atan2(d.y, Vector2(d.x, d.z).length()))
		for i in 8:
			await main.get_tree().process_frame
		var img := main.get_viewport().get_texture().get_image()
		img.save_png("%s/%s.png" % [dir, s.name])
		print("shot ", s.name)
	main.get_tree().quit()
