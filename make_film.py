#!/usr/bin/env python3
"""Discipline Builds film renderer: Kokoro voice + procedural silhouette animation + ambient music."""
import json, math, os, subprocess, sys, random
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 720, 1280, 24
GOLD = (232, 170, 60)
DB = os.environ.get("DB_DIR", "models")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F = lambda s: ImageFont.truetype(FONT, s)

LINES = [
 ("4:30 a.m. The alarm doesn't care how you feel.", "room", 0.7),
 ("Every part of you wants to stay. Warm bed. Easy excuses. Tomorrow.", "room", 0.8),
 ("But the man who only moves when he feels like it, never moves at all.", "room", 0.9),
 ("So he stands up. Not because he's motivated. Motivation left days ago.", "room", 0.8),
 ("He stands up because he made a promise. And a promise doesn't care about his mood.", "street", 0.8),
 ("The streets are empty. The cold bites. His legs beg him to stop.", "street", 0.9),
 ("He keeps going.", "rain", 1.0),
 ("Because discipline isn't loud. It's one small step, repeated, when nobody is watching.", "rain", 0.9),
 ("One step. Then another. Until the hill is behind him.", "hill", 0.8),
 ("And when the sun finally rises, he's already there.", "hill", 1.0),
 ("Be the person who's already there. Start today. Day one.", "summit", 0.5),
]
GOLDWORDS = {"discipline","promise","day","one.","sun","already","4:30","there."}
SPEC = {}
def load_spec(p):
    global LINES, GOLDWORDS, SPEC
    SPEC = json.load(open(p))
    LINES = [tuple(x) for x in SPEC["lines"]]
    GOLDWORDS = set(w.lower() for w in SPEC.get("gold", []))

# ---------- voice ----------
def make_voice(out_wav):
    from kokoro_onnx import Kokoro
    k = Kokoro(f"{DB}/kokoro-v1.0.onnx", f"{DB}/voices-v1.0.bin")
    sr = 24000; parts = []; starts = []; t = 0.0
    lead = 0.8
    parts.append(np.zeros(int(sr * lead))); t = lead
    for text, _, gap in LINES:
        s, sr2 = k.create(text, voice="am_adam", speed=0.93, lang="en-us")
        starts.append(t); parts.append(s); t += len(s) / sr2
        parts.append(np.zeros(int(sr * gap))); t += gap
    tail = 2.0; parts.append(np.zeros(int(sr * tail))); t += tail
    a = np.concatenate(parts).astype(np.float32)
    sf.write("/tmp/_raw_voice.wav", a, sr)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i","/tmp/_raw_voice.wav","-af",
      "equalizer=f=110:t=q:w=1:g=2.5,acompressor=threshold=-18dB:ratio=3,loudnorm=I=-15", out_wav], check=True)
    ends = [starts[i] + (len(parts[1 + 2*i]) / sr) for i in range(len(LINES))]
    return starts, ends, t

# ---------- music (original, synthesized) ----------
def make_music(out_wav, dur):
    sr = 44100; n = int(dur * sr); tt = np.arange(n) / sr
    sig = np.zeros(n)
    for f, a in [(55.0, .5), (82.41, .35), (110.0, .25), (164.81, .12), (130.81, .10)]:
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.05 + f / 4000) * tt + f)
        sig += a * lfo * np.sin(2 * np.pi * f * tt)
    # slow heartbeat-like pulse
    beat = np.zeros(n); per = int(sr * 1.2)
    for i in range(0, n - sr // 2, per):
        m = np.arange(sr // 4); beat[i:i + len(m)] += np.sin(2 * np.pi * 48 * m / sr) * np.exp(-m / (sr * 0.06)) * 0.5
    sig = sig + beat
    # rise toward the end
    env = np.clip(tt / 4, 0, 1) * (0.55 + 0.45 * np.clip((tt - dur * 0.55) / (dur * 0.4), 0, 1)) * np.clip((dur - tt) / 2.5, 0, 1)
    sig = sig * env; sig /= np.max(np.abs(sig)) + 1e-9
    sf.write("/tmp/_music.wav", (sig * 0.5).astype(np.float32), sr)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i","/tmp/_music.wav","-af","lowpass=f=900,aecho=0.8:0.7:500:0.3", out_wav], check=True)

# ---------- drawing helpers ----------
def grad(top, bot, h=H, w=W):
    t = np.linspace(0, 1, h)[:, None, None]
    a = np.array(top)[None, None, :] * (1 - t) + np.array(bot)[None, None, :] * t
    return Image.fromarray(np.repeat(a, w, axis=1).astype(np.uint8))

def glow(img, xy, r, color, strength=1.0):
    layer = Image.new("RGB", img.size, (0, 0, 0)); d = ImageDraw.Draw(layer)
    d.ellipse([xy[0]-r, xy[1]-r, xy[0]+r, xy[1]+r], fill=tuple(int(c*strength) for c in color))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.8))
    arr = np.clip(np.array(img, dtype=np.int32) + np.array(layer, dtype=np.int32), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)

def limb(d, p, l1, a1, l2, a2, w, col):
    k = (p[0] + l1 * math.sin(a1), p[1] + l1 * math.cos(a1))
    e = (k[0] + l2 * math.sin(a2), k[1] + l2 * math.cos(a2))
    d.line([p, k, e], fill=col, width=w, joint="curve")
    for q in (p, k, e): d.ellipse([q[0]-w/2, q[1]-w/2, q[0]+w/2, q[1]+w/2], fill=col)
    return e

def person(d, x, gy, sc, phase, amp, sit, col=(8, 8, 12), face=1):
    """face=1 right. sit 0..1 blends seated pose. amp = stride amplitude (0 standing)."""
    L1, L2, T = 52*sc, 54*sc, 92*sc
    hip_y = gy - (L1 + L2) * (1 - 0.42 * sit) * 0.97 + abs(math.sin(phase)) * -5 * sc * (amp > 0.1)
    hip = (x, hip_y)
    lean = (0.10 + 0.25 * min(amp, 1.2)) * face + 0.55 * sit * face
    sh = (hip[0] + T * math.sin(lean), hip[1] - T * math.cos(lean))
    w = int(15 * sc)
    for off in (math.pi, 0):  # back leg then front leg
        a = amp * 0.75 * math.sin(phase + off)
        thigh = (a + 1.45 * sit) * face
        shin = (a - amp * 0.55 * (1 + math.cos(phase + off + 0.6)) * 0.5 * 1.3 - 0.15 * sit) * face if sit < 0.5 else 0.05 * face
        limb(d, hip, L1, thigh, L2, shin, w, col)
    d.line([hip, sh], fill=col, width=int(26*sc))
    d.ellipse([hip[0]-13*sc, hip[1]-13*sc, hip[0]+13*sc, hip[1]+13*sc], fill=col)
    # head
    hd = (sh[0] + 14*sc*math.sin(lean) * 1.2, sh[1] - 20*sc + 10*sc*sit)
    d.ellipse([hd[0]-17*sc, hd[1]-19*sc, hd[0]+17*sc, hd[1]+19*sc], fill=col)
    # arms
    for off in (0, math.pi):
        a = amp * 1.0 * math.sin(phase + off)
        limb(d, (sh[0], sh[1] + 6*sc), 38*sc, (a + (0.4 if amp > 0.1 else 0.15) + 0.6 * sit) * face, 36*sc, (a + (1.1 if amp > 0.6 else 0.35) + 0.9 * sit) * face, int(11*sc), col)

# ---------- backgrounds ----------
def bg_room():
    im = grad((26, 34, 62), (14, 14, 28))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 180, 330, 520], fill=(24, 38, 66))             # window
    for x in (195,): d.line([x, 180, x, 520], fill=(10, 14, 28), width=8)
    d.line([60, 350, 330, 350], fill=(10, 14, 28), width=8)
    im = glow(im, (195, 350), 230, (30, 50, 90), 0.8); d = ImageDraw.Draw(im)
    d.rectangle([0, 905, W, H], fill=(22, 20, 32))                   # floor
    d.rectangle([60, 800, 470, 905], fill=(30, 26, 40)); d.rectangle([60, 760, 140, 905], fill=(36, 30, 46))  # bed
    d.rectangle([520, 760, 650, 905], fill=(22, 20, 30))             # nightstand
    return im

def bg_street():
    wide = grad((8, 10, 24), (18, 14, 28), H, W * 4); d = ImageDraw.Draw(wide)
    random.seed(4)
    x = 0
    while x < W * 4:
        bw = random.randint(120, 230); bh = random.randint(300, 640)
        d.rectangle([x, 900 - bh, x + bw, 900], fill=(12, 12, 20))
        for wy in range(900 - bh + 30, 880, 46):
            for wx in range(x + 18, x + bw - 18, 40):
                if random.random() < 0.12: d.rectangle([wx, wy, wx + 16, wy + 22], fill=(120, 96, 50))
        x += bw + random.randint(6, 30)
    d.rectangle([0, 900, W * 4, H], fill=(10, 10, 14))
    d.rectangle([0, 900, W * 4, 912], fill=(30, 30, 40))
    for lx in range(100, W * 4, 360):
        d.line([lx, 900, lx, 640], fill=(26, 26, 34), width=8); d.line([lx, 640, lx + 40, 640], fill=(26, 26, 34), width=8)
        wide = glow(wide, (lx + 40, 650), 110, (230, 160, 70), 0.55); d = ImageDraw.Draw(wide)
    return wide

def bg_rain():
    wide = grad((6, 8, 16), (14, 14, 24), H, W * 4); d = ImageDraw.Draw(wide)
    random.seed(8)
    for x in range(0, W * 4, 90):
        h = random.randint(60, 220); d.polygon([(x, 900), (x + 45, 900 - h), (x + 90, 900)], fill=(9, 10, 16))
    d.rectangle([0, 900, W * 4, H], fill=(8, 8, 12))
    for lx in range(200, W * 4, 420):
        d.line([lx, 900, lx, 660], fill=(24, 24, 32), width=7)
        wide = glow(wide, (lx, 668), 100, (160, 180, 230), 0.45); d = ImageDraw.Draw(wide)
        d.rectangle([lx - 10, 904, lx + 10, 1240], fill=(16, 18, 26)) if False else None
    return wide

def bg_hill(h=H * 3):
    im = grad((14, 12, 34), (90, 50, 40), h, W); d = ImageDraw.Draw(im)
    for i in range(10):
        pts = [(0, h)]
        yoff = h - 1000 + i * 70
        for x in range(0, W + 40, 40): pts.append((x, yoff - 120 * math.sin(x / 170 + i) - i * 38))
        pts.append((W, h)); c = 20 + i * 5
        d.polygon(pts, fill=(c // 2, c // 2 + 2, c))
    return im

# ---------- caption ----------
def wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else: lines.append(cur); cur = w
    lines.append(cur); return lines

def caption(img, text, alpha):
    if alpha <= 0: return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    font = F(42); lines = wrap(d, text, font, W - 100)
    y = 930 - len(lines) * 26
    for ln in lines:
        words = ln.split(); total = d.textlength(ln, font=font); x = (W - total) / 2
        for w in words:
            col = GOLD if w.lower().strip(",") in GOLDWORDS else (245, 245, 245)
            d.text((x, y), w, font=font, fill=col + (int(255 * alpha),), stroke_width=4, stroke_fill=(0, 0, 0, int(255 * alpha)))
            x += d.textlength(w + " ", font=font)
        y += 58
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

# ---------- main render ----------
def main(out_mp4):
    starts, ends, total = make_voice("/tmp/_voice.wav")
    make_music("/tmp/_music_f.wav", total)
    runs = []
    for i, (_, sc, _) in enumerate(LINES):
        if not runs or runs[-1][0] != sc: runs.append((sc, starts[i]))
    sc_start = {sc: st for sc, st in runs}
    def scene_at(t):
        cur = runs[0][0]
        for sc, st in runs:
            if t >= st - 0.05: cur = sc
        return cur
    STAND = SPEC.get("stand_line", 3)
    room, street, rain, hill = bg_room(), bg_street(), bg_rain(), bg_hill()
    n = int(total * FPS)
    OUT=out_mp4; proc = subprocess.Popen(["ffmpeg","-y","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","-",
        "-i","/tmp/_voice.wav","-i","/tmp/_music_f.wav","-filter_complex","[1:a]volume=1.0[v];[2:a]volume=0.55[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]",
        "-map","0:v","-map","[a]","-c:v","libx264","-preset","medium","-crf","29","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-t",f"{total:.2f}",out_mp4], stdin=subprocess.PIPE)
    stand_t = starts[STAND] + 1.6
    for f in range(n):
        t = f / FPS; sc = scene_at(t); ts = t - sc_start[sc]
        gy = 905
        if sc == "room":
            im = room.copy(); d = ImageDraw.Draw(im)
            ringing = t < starts[STAND] + 1.0
            shake = (math.sin(t * 60) * 4) if (ringing and int(t * 8) % 2 == 0) else 0
            d.rectangle([535 + shake, 700, 635 + shake, 760], fill=(10, 10, 14))
            d.text((585 + shake, 730), SPEC.get("clock","4:30"), font=F(34), fill=GOLD, anchor="mm")
            im = glow(im, (585, 730), 70 + (12 if ringing and int(t*8) % 2 == 0 else 0), (232, 170, 60), 0.5); d = ImageDraw.Draw(im)
            stand = np.clip((t - stand_t) / 1.4, 0, 1); sit = 1 - stand
            person(d, 300 + 260 * np.clip((t - stand_t - 1.2) / 2.0, 0, 1), gy - 40 * sit, 1.5, t * 7 if stand > 0.99 else 0, 0.55 if stand > 0.99 else 0, float(sit))
        elif sc in ("street", "rain"):
            wide = street if sc == "street" else rain
            speed = 150 if sc == "street" else 260
            off = int(((t * speed) % (W * 2)))
            im = wide.crop((off, 0, off + W, H)).copy(); d = ImageDraw.Draw(im)
            amp = 0.7 if sc == "street" else 1.15
            person(d, 270, gy + 40, 1.6, t * (7 if sc == "street" else 10.5), amp, 0)
            if sc == "rain":
                random.seed(f)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dd = ImageDraw.Draw(lay)
                for _ in range(130):
                    rx, ry = random.randint(0, W), random.randint(0, H)
                    dd.line([rx, ry, rx - 12, ry + 34], fill=(170, 190, 230, 110), width=2)
                im = Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB")
            else:
                d = ImageDraw.Draw(im)
                if ts > 3.0:  # breath puff
                    a = (ts * 2) % 1.0
                    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dd = ImageDraw.Draw(glow_layer)
                    dd.ellipse([350 + a * 40, 600 - a * 10, 380 + a * 70, 625 + a * 10], fill=(200, 210, 230, int(90 * (1 - a))))
                    im = Image.alpha_composite(im.convert("RGBA"), glow_layer).convert("RGB")
        elif sc == "desk":
            im = room.copy(); d = ImageDraw.Draw(im)
            d.rectangle([0, 905, W, H], fill=(22, 20, 32))
            d.rectangle([180, 800, 640, 830], fill=(30, 24, 20)); d.rectangle([200, 830, 216, 905], fill=(30, 24, 20)); d.rectangle([600, 830, 616, 905], fill=(30, 24, 20))
            im = glow(im, (560, 700), 190, (232, 170, 60), 0.55); d = ImageDraw.Draw(im)
            d.line([560, 800, 560, 720, 520, 690], fill=(10, 10, 14), width=8)
            d.text((120, 300), SPEC.get("clock","2:10 AM"), font=F(40), fill=GOLD, anchor="mm")
            person(d, 330, gy + 5, 1.5, 0, 0, 1.0)
            d.polygon([(380, 800), (470, 800), (462, 790), (388, 790)], fill=(236, 230, 210))
        elif sc == "hill":
            span = (t - sc_start["hill"]) / max(0.1, sc_start["summit"] - sc_start["hill"])
            oy = int((1 - span) * (hill.height - H) * 0.75 + (hill.height - H) * 0.25 * 0)
            oy = int(hill.height - H - span * (hill.height - H) * 0.8)
            im = hill.crop((0, oy, W, oy + H)).copy()
            sun_y = 900 - span * 380
            im = glow(im, (360, sun_y), 190, GOLD, 0.35 + 0.5 * span); d = ImageDraw.Draw(im)
            d.ellipse([360 - 60, sun_y - 60, 360 + 60, sun_y + 60], fill=(255, 205, 110))
            person(d, 340, gy - 20, 1.5, t * 8, 0.9, 0, col=(6, 6, 10))
        else:  # summit
            span = np.clip(ts / 4.0, 0, 1)
            im = grad((int(40 + 140 * span), int(24 + 80 * span), int(50 + 20 * span)), (int(230 * span + 20), int(140 * span + 20), int(60 * span + 24)))
            d = ImageDraw.Draw(im)
            sun_y = 760 - 120 * span
            im = glow(im, (360, sun_y), 260, GOLD, 0.9); d = ImageDraw.Draw(im)
            d.ellipse([360 - 105, sun_y - 105, 360 + 105, sun_y + 105], fill=(255, 214, 130))
            d.polygon([(0, H), (0, 930), (180, 900), (360, 880), (540, 900), (W, 930), (W, H)], fill=(8, 8, 12))
            person(d, 360, 885, 1.7, 0, 0, 0, col=(6, 6, 10))
            if t > total - 3.2:
                k = np.clip((t - (total - 3.2)) / 0.8, 0, 1)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, int(235 * k))); im = Image.alpha_composite(im.convert("RGBA"), lay).convert("RGB")
                d = ImageDraw.Draw(im)
                col = lambda c: tuple(int(v * k) for v in c)
                d.text((W/2, 560), SPEC.get("end_title","DAY ONE."), font=F(88), fill=col(GOLD), anchor="mm")
                d.text((W/2, 650), "DISCIPLINE BUILDS", font=F(38), fill=col((240, 240, 240)), anchor="mm")
                d.text((W/2, 700), "New film every day", font=F(28), fill=col((170, 170, 180)), anchor="mm")
        # caption for current line
        cap = None; alpha = 0
        for i, (text, _, _) in enumerate(LINES):
            if starts[i] - 0.05 <= t <= ends[i] + 0.35:
                cap = text; alpha = min(1, (t - starts[i] + 0.05) / 0.3, (ends[i] + 0.35 - t) / 0.3)
        if cap and not (sc == "summit" and t > total - 3.2): im = caption(im, cap, max(0, alpha))
        # fade through black at scene boundaries
        fade = 1.0
        for s in sc_start.values():
            if s > 0.5: fade = min(fade, np.clip(abs(t - s) / 0.35, 0, 1))
        if t < 0.4: fade = min(fade, t / 0.4)
        if fade < 1.0: im = Image.fromarray((np.array(im) * fade).astype(np.uint8))
        proc.stdin.write(im.tobytes())
    proc.stdin.close(); proc.wait()
    print("done", out_mp4, f"{total:.1f}s")

if __name__ == "__main__":
    load_spec(sys.argv[2]); main(sys.argv[1])
