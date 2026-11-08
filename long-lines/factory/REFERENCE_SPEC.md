# Reference sheet specification (factory input)

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
