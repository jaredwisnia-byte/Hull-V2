class_name Player
extends CharacterBody3D
## First-person Nick. Walk, look, interact (E), secondary action (R), carry and
## place props, flashlight (F). No crosshair aim assist; a small dot only.

const REACH := 2.1
const PLACE_REACH := 2.4
const WALK := 2.1
const CROUCH_WALK := 1.1
const EYE := 1.62
const CROUCH_EYE := 1.05
const MOUSE_SENS := 0.0022

var cam: Camera3D
var hand: Node3D
var flashlight: SpotLight3D
var hud: Node
var yaw := 0.0
var pitch := 0.0
var held: Carriable = null
var held_rot := 0.0
var target: Interactable = null
var place_hit := {}
var crouching := false
var _bob := 0.0
var _sway_t := 0.0


func _ready() -> void:
	add_to_group("player")
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.26
	cap.height = 1.7
	cs.shape = cap
	cs.position.y = 0.85
	add_child(cs)
	cam = Camera3D.new()
	cam.position.y = EYE
	cam.fov = 72.0
	cam.near = 0.05
	cam.far = 120.0
	add_child(cam)
	cam.current = true
	hand = Node3D.new()
	hand.position = Vector3(0.22, -0.32, -0.5)
	cam.add_child(hand)
	flashlight = SpotLight3D.new()
	flashlight.spot_range = 9.0
	flashlight.spot_angle = 24.0
	flashlight.light_energy = 2.2
	flashlight.light_color = Color(1.0, 0.92, 0.78)
	flashlight.position = Vector3(0.15, -0.15, 0.0)
	flashlight.visible = false
	cam.add_child(flashlight)
	floor_max_angle = deg_to_rad(50)


func set_look(yaw_rad: float, pitch_rad := 0.0) -> void:
	yaw = yaw_rad
	pitch = pitch_rad
	rotation.y = yaw
	cam.rotation.x = pitch


func teleport(pos: Vector3) -> void:
	global_position = pos
	velocity = Vector3.ZERO


func controls_enabled() -> bool:
	return not Game.ui_open and not Game.dead and not Game.slice_over


func _unhandled_input(event: InputEvent) -> void:
	if not controls_enabled():
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * MOUSE_SENS
		pitch = clampf(pitch - event.relative.y * MOUSE_SENS, -1.45, 1.45)
		rotation.y = yaw
		cam.rotation.x = pitch
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_scroll(1)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_scroll(-1)
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
			elif held:
				try_place()
	elif event.is_action_pressed("interact"):
		try_primary()
	elif event.is_action_pressed("secondary"):
		try_secondary()
	elif event.is_action_pressed("rotate_held") and held:
		held_rot += PI / 8.0
	elif event.is_action_pressed("flashlight"):
		if held and held.two_handed:
			Game.message.emit("Both hands are full.")
		else:
			var r := Game.toggle_flashlight()
			if r != "":
				Game.message.emit(r)
	elif event.is_action_pressed("tune_up"):
		_scroll(1)
	elif event.is_action_pressed("tune_down"):
		_scroll(-1)
	elif event.is_action_pressed("crouch"):
		crouching = not crouching


func _scroll(dir: int) -> void:
	var r: Node = held if held is RadioProp else target
	if r and r.has_method("scroll"):
		r.scroll(self, dir)


func _physics_process(delta: float) -> void:
	var input := Vector2.ZERO
	if controls_enabled():
		input = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var speed := CROUCH_WALK if crouching else WALK
	if held and held.two_handed:
		speed *= 0.7
	if Game.air.co_stage() >= 2:
		speed *= 0.8
	var dir := (transform.basis * Vector3(input.x, 0, input.y)).normalized()
	velocity.x = dir.x * speed
	velocity.z = dir.z * speed
	if not is_on_floor():
		velocity.y -= 9.8 * delta
	else:
		velocity.y = 0.0
	move_and_slide()

	var eye := CROUCH_EYE if crouching else EYE
	if dir.length() > 0.1:
		_bob += delta * 8.0
	cam.position.y = lerpf(cam.position.y, eye + sin(_bob) * 0.018, 10.0 * delta)
	# Carbon monoxide makes the world swim.
	_sway_t += delta
	var stage := Game.air.co_stage()
	cam.rotation.z = sin(_sway_t * 0.9) * 0.012 * stage * stage
	flashlight.visible = Game.flashlight_on and not (held and held.two_handed)
	_update_target()
	_update_held(delta)


func _update_target() -> void:
	target = null
	place_hit = {}
	var space := get_world_3d().direct_space_state
	var from := cam.global_position
	var fwd := -cam.global_transform.basis.z
	var q := PhysicsRayQueryParameters3D.create(from, from + fwd * PLACE_REACH)
	q.exclude = [get_rid()]
	var hit := space.intersect_ray(q)
	if hit.is_empty():
		return
	var dist := from.distance_to(hit.position)
	if held:
		if hit.normal.y > 0.65:
			place_hit = hit
	var c: Object = hit.collider
	if dist <= REACH and c is Interactable:
		target = c


func _update_held(delta: float) -> void:
	if held == null:
		return
	var want := Vector3(0.0, -0.42, -0.55) if held.two_handed else Vector3(0.24, -0.3, -0.48)
	held.position = held.position.lerp(want, 12.0 * delta)
	held.rotation = Vector3(0.0, held_rot, 0.0)


func try_primary() -> void:
	if held:
		if held is RadioProp:
			held.primary(self)
			return
		try_place()
		return
	if target:
		target.primary(self)


func try_secondary() -> void:
	if held:
		# Carrying stops you climbing, but still lets you open windows and doors.
		if target and target is WindowSash:
			target.primary(self)
		return
	if target:
		target.secondary(self)


func pick_up(c: Carriable, silent := false) -> void:
	if held:
		return
	held = c
	held_rot = 0.0
	c.reparent(hand, false)
	c.position = Vector3(0, -0.3, -0.4)
	c.rotation = Vector3.ZERO
	c.set_held(true)
	if c.two_handed and Game.flashlight_on:
		Game.flashlight_on = false
	if not silent and c.two_handed:
		Game.message.emit("You lift the %s with both hands." % c.display_name)


func try_place() -> void:
	if held == null:
		return
	if place_hit.is_empty():
		Game.message.emit("Find a flat surface to set it down.")
		return
	var c := held
	held = null
	c.reparent(c.world_parent, false)
	c.global_position = place_hit.position + Vector3(0, 0.002, 0)
	c.global_rotation = Vector3(0, yaw + held_rot, 0)
	c.set_held(false)
	if c is CoolerProp and Game.cooler_place == "outside":
		Game.message.emit("You set the cooler out on the fire escape, where the air is colder.")


## Used by loading: drop whatever is held back into the world without placing.
func force_release(c: Carriable) -> void:
	if held != c:
		return
	held = null
	c.reparent(c.world_parent, false)
	c.held = false
	c.collision_layer = c._layer
