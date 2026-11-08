# Critiquing a prop: walk around it

Every new or rebuilt prop gets this review before it goes into a scene.

```bash
blender -b --factory-startup -P tools/critique.py -- PROP [VIEWS_FOLDER]
```

This writes `assets/props/PROP/_critique.png` (8 angles + 2 close-ups, complaints listed
underneath) and `_critique.json` (measurements). The script checks the measurable things;
the reviewer (Claude or a person) looks at the image and checks the rest.

## Measured automatically
- **Silhouette vs painting** from front, back, sides and top (IoU; below 85% = shape is off).
  Views marked `paint_only` in `HULLS` are skipped.
- **Front relief:** under 5 mm of depth means painted details have no geometry.
- **Painted parts:** every knob or button detected in the painting must stand out by
  roughly what `propkit/part_rules.py` says a real one does (at least 40%, at most 200%).
- **Floor contact:** the lowest point must be at z = 0 (no floating, no sinking).
- **Holes:** see-through gaps in the front.

## Look for, in the turnaround
1. **Is anything painted that should be modelled?** Knobs, handles, hinges, feet, buttons,
   switches, lids, trim. If it would cast a shadow in real life, it needs depth. Add a rule
   to `part_rules.py` (size range, how far it protrudes) so the builder handles it next time.
2. **Real-world size:** is the object the size the real thing would be? (A 19" TV is about
   65 cm wide; a dining chair seat is 45 cm high.)
3. **Every side:** back, underside and top are textured, not stretched or smeared.
4. **Lumpy edges** on things that should be straight (marching-cubes artifacts): raise the
   resolution, or use `convex=True` for boxy objects.
5. **Texture stretching** where a face is lit by a view at a steep angle.
6. **Does it match the Long Dark look:** chunky silhouette, worn edges, grime in creases.
7. **Evidence first:** if the painting shows how something is shaped (e.g. a side view
   shows how far the knobs stick out), the model follows the painting; rules fill in only
   what the painting doesn't say.

Fix, rebuild, critique again. Record any new kind of mistake in `docs/LESSONS.md`.
