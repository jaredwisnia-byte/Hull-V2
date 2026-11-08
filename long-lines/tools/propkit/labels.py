"""Period print graphics drawn with PIL: can labels, boxes, sleeves, spines,
newspapers, paintings. Every brand is invented. Images are cached in
assets/labels/ so recipes can share them.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "labels"))
FONTS = {
    "black": "/usr/share/fonts/opentype/inter/Inter-Black.otf",
    "blackit": "/usr/share/fonts/opentype/inter/Inter-BlackItalic.otf",
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "cond": "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "serifit": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
    "book": "/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
}


def font(kind, size):
    path = FONTS.get(kind, FONTS["bold"])
    if not os.path.exists(path):
        path = FONTS["bold"]
    return ImageFont.truetype(path, size)


def _path(name):
    os.makedirs(ROOT, exist_ok=True)
    return os.path.join(ROOT, name + ".png")


def _centered(d, xy, text, f, fill):
    w = d.textlength(text, font=f)
    d.text((xy[0] - w / 2, xy[1]), text, font=f, fill=fill)


def _age(img, amount=0.25, seed=0):
    """Yellowing, specks and a soft blur: nothing printed in 1975 looks new now."""
    rnd = random.Random(seed)
    img = img.convert("RGB")
    over = Image.new("RGB", img.size, (205, 185, 140))
    img = Image.blend(img, over, amount * 0.35)
    d = ImageDraw.Draw(img)
    for _ in range(int(img.size[0] * img.size[1] / 4000 * amount)):
        x, y = rnd.randrange(img.size[0]), rnd.randrange(img.size[1])
        r = rnd.choice((1, 1, 2, 3))
        c = rnd.randint(90, 160)
        d.ellipse((x, y, x + r, y + r), fill=(c, c - 10, c - 25))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def wrap_label(name, brand, product, bg, fg, accent, sub="", w=1024, h=320, seed=1):
    """A label that wraps around a can or bottle (u = around, v = up)."""
    p = _path(name)
    if os.path.exists(p):
        return p
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 26), fill=accent)
    d.rectangle((0, h - 26, w, h), fill=accent)
    for cx in (w * 0.25, w * 0.75):
        d.ellipse((cx - 130, h * 0.18, cx + 130, h * 0.82), fill=fg)
        _centered(d, (cx, h * 0.28), brand, font("blackit", 54), bg)
        _centered(d, (cx, h * 0.5), product, font("cond", 34), accent)
        if sub:
            _centered(d, (cx, h * 0.66), sub, font("bold", 18), bg)
    img = _age(img, 0.2, seed)
    img.save(p)
    return p


def box_art(name, brand, product, bg, fg, accent, w=512, h=640, seed=2, motif="sun"):
    """Front of a carton or packet."""
    p = _path(name)
    if os.path.exists(p):
        return p
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, int(h * 0.22)), fill=accent)
    _centered(d, (w / 2, h * 0.04), brand, font("blackit", int(w * 0.14)), fg)
    if motif == "sun":
        for i in range(16):
            a = i * math.pi / 8
            d.line((w / 2, h * 0.58, w / 2 + math.cos(a) * w * 0.5, h * 0.58 + math.sin(a) * w * 0.5), fill=fg, width=10)
        d.ellipse((w * 0.3, h * 0.45, w * 0.7, h * 0.72), fill=accent)
    elif motif == "bowl":
        d.ellipse((w * 0.15, h * 0.42, w * 0.85, h * 0.75), fill=(240, 238, 225))
        for i in range(30):
            x = w * 0.25 + (i * 37 % int(w * 0.5))
            y = h * 0.5 + (i * 53 % int(h * 0.12))
            d.ellipse((x, y, x + 22, y + 16), fill=(205, 160, 70))
    elif motif == "stripes":
        for i in range(6):
            d.rectangle((0, h * 0.3 + i * h * 0.08, w, h * 0.3 + i * h * 0.08 + h * 0.035), fill=fg)
    _centered(d, (w / 2, h * 0.8), product, font("cond", int(w * 0.09)), fg)
    img = _age(img, 0.22, seed)
    img.save(p)
    return p


def record_sleeve(name, title, artist, seed=3, w=512):
    p = _path(name)
    if os.path.exists(p):
        return p
    rnd = random.Random(seed)
    pal = rnd.choice([((222, 120, 40), (40, 30, 30)), ((40, 90, 120), (240, 220, 180)), ((180, 40, 50), (250, 230, 200)),
                      ((90, 120, 60), (30, 30, 20)), ((230, 200, 80), (60, 30, 20)), ((30, 30, 30), (230, 120, 60))])
    img = Image.new("RGB", (w, w), pal[0])
    d = ImageDraw.Draw(img)
    style = seed % 3
    if style == 0:
        for i in range(8):
            r = w * (0.45 - i * 0.05)
            d.ellipse((w / 2 - r, w * 0.55 - r, w / 2 + r, w * 0.55 + r), outline=pal[1], width=8)
    elif style == 1:
        for i in range(10):
            d.polygon([(0, w * i / 10), (w, w * (i + 0.6) / 10), (w, w * (i + 1) / 10), (0, w * (i + 0.4) / 10)], fill=pal[1] if i % 2 else pal[0])
    else:
        d.rectangle((w * 0.1, w * 0.3, w * 0.9, w * 0.9), fill=pal[1])
        d.ellipse((w * 0.3, w * 0.4, w * 0.7, w * 0.8), fill=pal[0])
    d.text((w * 0.06, w * 0.05), artist.upper(), font=font("black", int(w * 0.07)), fill=pal[1])
    d.text((w * 0.06, w * 0.15), title, font=font("serifit", int(w * 0.06)), fill=pal[1])
    img = _age(img, 0.3, seed)
    img.save(p)
    return p


def spines(name, count=24, w=1024, h=256, seed=4):
    """A strip of book spines; books sample random slices of it."""
    p = _path(name)
    if os.path.exists(p):
        return p
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (40, 30, 20))
    d = ImageDraw.Draw(img)
    cols = [(120, 30, 25), (30, 50, 90), (40, 70, 45), (150, 120, 60), (60, 40, 30), (180, 160, 120), (20, 20, 20), (110, 80, 120)]
    words = ["HISTORY", "POEMS", "THE SEA", "BASEBALL", "SAINTS", "NAPLES", "RADIO", "ATLAS", "WAR", "NOVELS", "COOKING", "BRIDGES"]
    x = 0
    sw = w / count
    for i in range(count):
        c = rnd.choice(cols)
        d.rectangle((x, 0, x + sw, h), fill=c)
        light = tuple(min(255, v + 90) for v in c)
        d.rectangle((x, h * 0.1, x + sw, h * 0.13), fill=light)
        d.rectangle((x, h * 0.87, x + sw, h * 0.9), fill=light)
        t = Image.new("RGBA", (int(h * 0.6), int(sw)), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((4, 2), rnd.choice(words), font=font("book", int(sw * 0.6)), fill=light)
        img.paste(t.rotate(90, expand=True), (int(x + 2), int(h * 0.2)), t.rotate(90, expand=True))
        x += sw
    img = _age(img, 0.3, seed)
    img.save(p)
    return p


def newspaper(name, headline, masthead="New York Daily Record", sub="", w=768, h=1024, seed=5):
    p = _path(name)
    if os.path.exists(p):
        return p
    img = Image.new("RGB", (w, h), (226, 220, 200))
    d = ImageDraw.Draw(img)
    _centered(d, (w / 2, 20), masthead, font("serif", 52), (25, 25, 25))
    d.line((20, 90, w - 20, 90), fill=(30, 30, 30), width=3)
    y = 110
    for line in headline.split("\n"):
        _centered(d, (w / 2, y), line, font("black", 110), (15, 15, 15))
        y += 125
    if sub:
        _centered(d, (w / 2, y + 10), sub, font("serifit", 30), (40, 40, 40))
    rnd = random.Random(seed)
    for col in range(4):
        for row in range(26):
            yy = y + 70 + row * 18
            if yy > h - 30:
                break
            d.line((24 + col * (w - 48) / 4, yy, 24 + col * (w - 48) / 4 + rnd.randint(110, 170), yy), fill=(90, 90, 90), width=5)
    img = _age(img, 0.35, seed)
    img.save(p)
    return p


def painting(name, kind="landscape", w=512, h=384, seed=6):
    """Cheap framed art: a landscape, the Bay of Naples, a saint print, a family portrait."""
    p = _path(name)
    if os.path.exists(p):
        return p
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    if kind in ("landscape", "naples"):
        for y in range(h):
            t = y / h
            d.line((0, y, w, y), fill=(int(120 + 110 * t), int(150 + 70 * t), int(200 - 40 * t)))
        if kind == "naples":
            d.polygon([(w * 0.45, h * 0.55), (w * 0.62, h * 0.25), (w * 0.8, h * 0.55)], fill=(110, 100, 120))
            d.rectangle((0, h * 0.55, w, h), fill=(40, 90, 140))
            for i in range(12):
                x = rnd.randint(0, w)
                d.rectangle((x, h * 0.62, x + 20, h * 0.65), fill=(240, 230, 210))
        else:
            for k, col in enumerate([(70, 110, 70), (50, 90, 55), (40, 70, 40)]):
                pts = [(0, h)] + [(x, h * (0.45 + k * 0.12) + math.sin(x * 0.02 + k * 2 + seed) * 20) for x in range(0, w + 16, 16)] + [(w, h)]
                d.polygon(pts, fill=col)
    elif kind == "saint":
        d.rectangle((0, 0, w, h), fill=(180, 150, 90))
        d.ellipse((w * 0.35, h * 0.08, w * 0.65, h * 0.38), fill=(240, 210, 120))
        d.ellipse((w * 0.42, h * 0.14, w * 0.58, h * 0.32), fill=(220, 180, 150))
        d.polygon([(w * 0.3, h), (w * 0.4, h * 0.34), (w * 0.6, h * 0.34), (w * 0.7, h)], fill=(70, 60, 130))
        d.polygon([(w * 0.38, h), (w * 0.45, h * 0.4), (w * 0.55, h * 0.4), (w * 0.62, h)], fill=(160, 40, 40))
    elif kind == "portrait":
        d.rectangle((0, 0, w, h), fill=(120, 105, 85))
        for k, x in enumerate((0.3, 0.5, 0.7)):
            d.ellipse((w * (x - 0.08), h * (0.25 + k % 2 * 0.04), w * (x + 0.08), h * (0.5 + k % 2 * 0.04)), fill=(200, 175, 150))
            d.rectangle((w * (x - 0.12), h * (0.5 + k % 2 * 0.04), w * (x + 0.12), h), fill=(50, 45, 40))
        img = img.convert("L").convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    img = _age(img, 0.35, seed)
    img.save(p)
    return p
