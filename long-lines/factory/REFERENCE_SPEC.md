# Reference sheet specification (AssetFactory input)

Interchangeable parts need standard gauges; this is the gauge for input images. A sheet that
follows it goes through the factory with no human work (Jared generates sheets without brand names, Nov 8).

## Multiview object sheet (hull line: furniture, electronics, appliances, street objects)
- One object per sheet. Plain flat background that contrasts with the object (light behind
  dark objects, dark behind light ones).
- **Top row: five orthographic views, left to right, all at the same scale and aligned on
  the same ground line: FRONT, RIGHT side (front to the left), BACK, LEFT side (front to
  the right), TOP (front at the bottom).** Nothing else in that row.
- Views at least 400 px tall. Below the row, anything (details, swatches) is ignored.
- Real proportions; no perspective, no shadows on the background.
- Invented brands only.

Prompt template for the image generator:
> Orthographic texture reference sheet of a [OBJECT], 1970s New York, moderately worn,
> painterly stylized game-art textures in the style of a hand-painted survival game.
> Top row only: five orthographic views left to right at identical scale on one ground line:
> front, right side, back, left side, top (front at bottom). Flat [light/dark] background,
> no perspective, no cast shadows. Fictional brand "[NAME]" only. Details may go below.

## Car sheet (car line): the `car_v1` layout (see tools/layouts/car_v1.json).
## Can label sheet (can line): wrap label strip + one plain lid.
## Surface (surface line): one seamless or near-seamless square texture, flat lighting.

## Sheet set v2: painting + depth + part map (+ section) — preferred from Nov 2026

The painting says what a thing looks like; it does not say how deep anything is. v2 adds
companion images made **from the painted sheet itself**, so every pixel lines up:

| Image | What it gives the factory | Needed |
| --- | --- | --- |
| A. painted sheet (as above: front, right, back, left, top) | colour, outline | always |
| B. depth sheet: same sheet, grayscale, white = nearest to the viewer, black = farthest | real relief: how far each key, handle, slot, window sits in or out | always |
| C. part map: same sheet, every separate part one flat colour from the key below | which region is which kind of part, so the catalogue can size it | recommended |
| D. section: a cut through the middle, side-on, as a flat light shape | hidden depths: door thickness, recess depth, moulding profile | objects with recesses or profiles |

Make them in order in **one ChatGPT conversation**: generate A, then upload A and ask for B,
then upload A for C. Editing the same picture keeps the layout identical; generating each
from scratch does not.

Part map colour key (flat colours, no shading, no outlines):
- white #FFFFFF: main body / shell
- green #00C000: separate panel that opens or moves (door, drawer, lid, flap)
- red #FF0000: sticks out (knob, handle, key, button, hinge, foot, trim, cornice, sill)
- blue #0000FF: goes in (slot, vent, grille, dispenser recess, window opening, keyhole)
- yellow #FFFF00: glass or transparent
- orange #FF8000: soft or flexible (cushion, rubber seal, cable, fabric)
- black #000000: background

Rules for all four: same canvas size, same framing, same positions; no text or labels inside
the views; flat even background; no perspective, no cast shadows.
