#!/usr/bin/env python3
"""Thumbnail generator for Discipline Builds: python thumbs.py out.png spec.json [day_number]
1080x1920 (9:16); the title sits in the central 16:9 band so a landscape crop still reads."""
import json, os, re, sys, math
os.environ.setdefault("DB_DIR", "models")
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import make_film as mf

OW, OH = 1080, 1920
GOLD = (236, 178, 52)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F = lambda s: ImageFont.truetype(FONT, s)

def scene_img(name):
    W, H = mf.W, mf.H
    if name in ("street",):
        wide = mf.bg_street(); im = wide.crop((W // 2, 0, W // 2 + W, H)).copy()
    elif name in ("rain",):
        wide = mf.bg_rain(); im = wide.crop((W, 0, 2 * W, H)).copy()
    elif name in ("hill", "summit"):
        h = mf.bg_hill(); im = h.crop((0, h.height - H, W, h.height)).copy()
        im = mf.glow(im, (360, 820), 230, mf.GOLD, 0.85); d = ImageDraw.Draw(im)
        d.ellipse([360 - 80, 820 - 80, 360 + 80, 820 + 80], fill=(255, 205, 110))
    else:
        im = mf.bg_room()
    return im

def figure(im, scene):
    x, gy, sc = 545, 1236, 1.75
    im = mf.glow(im, (x, gy - 150), 300, GOLD, 0.55)
    d = ImageDraw.Draw(im)
    d.rectangle([0, gy, mf.W, mf.H], fill=(8, 8, 12))
    d.rectangle([0, gy, mf.W, gy + 5], fill=(120, 90, 40))
    mf.person(d, x - 5, gy, sc, 0.6, 0.0, 0, col=(244, 190, 80), face=1)   # gold rim
    mf.person(d, x, gy, sc, 0.6, 0.0, 0, col=(4, 4, 7), face=1)
    return im

def wrap_words(words, font, maxw, d):
    lines, cur = [], []
    for w in words:
        t = " ".join(cur + [w])
        if d.textlength(t, font=font) <= maxw or not cur: cur.append(w)
        else: lines.append(cur); cur = [w]
    if cur: lines.append(cur)
    return lines

def make(out, spec_path, day=None):
    spec = json.load(open(spec_path))
    title = re.split(r"\s*\|\s*", spec["title"])[0].strip().rstrip("?").upper()
    gold = {re.sub(r"[^A-Z0-9']", "", g.upper()) for g in spec.get("gold", [])}
    scene = spec["lines"][0][1]
    im = scene_img(scene); im = np.array(im).astype(float); im = Image.fromarray(np.clip(im*1.35+10,0,255).astype(np.uint8)); im = figure(im, scene)
    im = im.resize((OW, OH), Image.LANCZOS)
    # vignette + central dark band for legibility
    ov = Image.new("RGBA", (OW, OH), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    for y in range(OH):
        a = int(115 * (abs(y - OH / 2) / (OH / 2)) ** 2)
        od.line([(0, y), (OW, y)], fill=(0, 0, 0, a))
    od.rectangle([0, 600, OW, 1320], fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im.convert("RGBA"), ov)
    d = ImageDraw.Draw(im)
    words = title.split()
    # choose gold words: spec gold matches in title, else the last two words
    hl = {i for i, w in enumerate(words) if re.sub(r"[^A-Z0-9']", "", w) in gold and len(w) > 3}
    if not hl: hl = {len(words) - 1} | ({len(words) - 2} if len(words) > 3 else set())
    size = 190
    while size > 80:
        font = F(size); lines = wrap_words(words, font, 940, d)
        if len(lines) <= 4 and size * 1.15 * len(lines) <= 640 and max(d.textlength(' '.join(l), font=font) for l in lines) <= 960: break
        size -= 6
    lh = int(size * 1.16); y = 960 - lh * len(lines) / 2
    idx = 0
    for ln in lines:
        tot = d.textlength(" ".join(ln), font=font); x = (OW - tot) / 2
        for w in ln:
            col = GOLD if idx in hl else (248, 248, 248)
            d.text((x, y), w, font=font, fill=col, stroke_width=max(6, size // 16), stroke_fill=(0, 0, 0))
            x += d.textlength(w + " ", font=font); idx += 1
        y += lh
    # top badge, bottom brand
    d.text((OW / 2, 190), "A DISCIPLINE SHORT FILM", font=F(46), fill=GOLD, anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
    if day: d.text((OW / 2, 270), f"DAY {day}", font=F(70), fill=(248, 248, 248), anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
    bx, by = 70, 1690
    for i, h in enumerate([34, 62, 92, 126]):
        d.rectangle([bx + i * 30, by + 126 - h, bx + i * 30 + 22, by + 126], fill=GOLD)
    d.text((bx + 150, by + 38), "DISCIPLINE", font=F(54), fill=(248, 248, 248), anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
    d.text((bx + 150, by + 96), "BUILDS", font=F(54), fill=GOLD, anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
    im.convert("RGB").save(out, "PNG", optimize=True)

if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
