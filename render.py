"""Render the Ayurix banner with a sub-progress bar. Usage: python render.py 54  -> banner.jpg"""
import os, sys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---- paths / geometry (measured from the AE composition) ----
BG_PATH, TRACK_PATH, FILL_PATH = "assets/bg.png", "assets/track.png", "assets/fill.png"
FONT_PATH = "assets/Mostwasted.ttf"
GOALS = [100, 250, 500, 1000, 2500, 5000, 10000]   # goal = first value > count
SCALE, OFFSET = 0.3325, (71, 612)  # bar-PNG (2171x724) -> banner scale / top-left
FILL_BOX = (350, 358, 1690, 424)   # inner track area in bar-PNG pixels
NUM_X, NUM_Y, NUM_H, NUM_CW, NUM_GAP = 700, 303, 175, 105, 36   # left, top, height, char width, gap around "/" (bar-PNG px)
FONT_SMOOTH = True    # False = pixel font (Press Start 2P, monospace, hard edges). True = normal/script font: any width, smooth edges
FONT_TRACK = 4        # smooth fonts only: extra space between characters (bar-PNG px)
NUM_BOLD = 3          # thickens the number: grows every stroke by this many bar-PNG px per side (0 = off). Makes thin fonts look "fat"

# heart-only layout (no progress bar): heart sits right after the number, same line, rides the same wave
HEART_PATH = "assets/heart.png"    # isolated heart (cut from track.png; no bar, no stars)
HEART_H = 250                      # base heart height in bar-PNG px (number is NUM_H=80 tall)
HEART_SIZE = (0.85, 1.25)          # random size range; seeded by the sub count -> changes whenever the count changes
HEART_GAP = 75                     # gap between number end and heart (bar-PNG px)
HEART_TURB = 0.05                  # fine wobble on the heart itself (fraction of its height); same random seed as the wave
HEART_DY = 0                       # extra vertical nudge (+ = down)
_NUM_END = 0                       # x where the number ends (set by _number_layer)

# ---- look (tune these) ----
OPACITY = 0.90                     # bar visibility
SOFTEN = 0.5                       # blur (banner px) on the bar: removes crisp "sticker" edges
TINT, DESAT, GAIN = 0.30, 0.14, 0.97   # blend toward bg colours / desaturate / highlight gain
FILL_GLOW = [(6, 0.30), (18, 0.22), (45, 0.15)]
# bar shadow: soft, low opacity, slightly below
BAR_SHADOW = dict(radius=9, opacity=0.50, dx=0, dy=6, color=(36, 24, 46))   # applied AFTER the glow so it stays visible
# Deep Glow look-alike for the bar: high radius, low exposure, threshold 80/255
DG_THRESHOLD = 80
DG_RADII = [(22, 0.40), (55, 0.36), (110, 0.28), (210, 0.18)]
DG_TINT, DG_WARM = 0.45, (1.0, 0.78, 0.60)
# number = crimson glass: dark edge -> bright core, glossy top-left rim, grainy texture, tight crisp glow
NUM_CORE = (226, 36, 70)           # crimson (centre of each stroke), a touch softer
NUM_EDGE = (150, 14, 44)            # deep crimson (stroke edges = glass thickness), lighter so edges are less harsh
NUM_DEPTH = 3.0                    # blur (banner px) that sets how far the dark edge reaches into the stroke
NUM_OPACITY = 0.88                 # fade: 1.0 = solid, lower = more see-through
NUM_SOFT = 0.8                     # blur (banner px) on the number's edge: higher = softer, lower = crisper
NUM_TEXTURE = dict(grain=0.09, mottle=0.18, seed=7)   # grain = fine noise, mottle = soft blotches (0 = off)
NUM_SPEC = dict(dx=2, dy=2, opacity=0.50, color=(255, 236, 240))    # thin white rim on the top-left edge
NUM_SHEEN = dict(dx=1, dy=6, opacity=0.28, color=(255, 160, 180))   # soft glossy band under the top edge
NUM_RIM_DARK = dict(dx=2, dy=2, opacity=0.28)                       # dark rim on the opposite (bottom-right) edge
NUM_GLOW_RADII = [(3, 0.60), (8, 0.62), (18, 0.55), (40, 0.34)]     # soft, wide, glowy (screen blend)
NUM_GLOW_COLOR = (255, 70, 105)
NUM_SHADOW = dict(radius=6, opacity=0.32, dx=2, dy=4, color=(70, 8, 30))


# flowing wave: SAME strength along the whole bar (left to right), NEW random shape every render (like the stars).
# The track, fill, number baseline and the heart (position + tilt) all follow this ONE curve.
WAVE_AMP = 44            # max vertical swing in bar-PNG px (x0.33 on the banner)
WAVE_FLOOR = 1.0         # 1.0 = uniform strength left->right (old look: 0.28 = weak at the number, strong at the heart)
WAVE_SIZE = 1.0          # wavelength multiplier: >1 = broader/longer waves, <1 = tighter waves
WAVE_TURB = 0.10         # fine turbulence on the track, as a fraction of WAVE_AMP (old: 0.04)
WAVE_X0, WAVE_X1 = 350, 1686
HEART_TILT = 0.8         # how much the heart rotates with the wave slope (0 = no tilt)
WAVE_SEED = None         # None = new random wave each render; set an int to freeze one
_WAVE = None             # (components, seed): drawn ONCE per render so track, number and heart share one curve
# scattered stars (banner px): random layout every render, thinner/more varied, sparser + dimmer far from the bar
STAR_COUNT = 24
STAR_SEED = None                         # None = new random layout each render; set an int to freeze it
STAR_AREA = (40, 430, 900, 1010)         # x0,y0,x1,y1 on the banner
STAR_KEEPOUT = (240, 610, 720, 860)       # number + heart band: no stars here
STAR_BAR = (187, 636, 742)               # bar x-range + centre y on the banner (distance is measured from this)
STAR_MIN0, STAR_MINK = 52, 0.42          # min spacing = MIN0 + MINK * distance_from_bar
STAR_FADE = 380                          # opacity falls to ~25% around this distance (px)
STAR_GLOW = [(2, 1.0), (5, 0.8), (11, 0.6), (24, 0.4)]
STAR_COLORS = [(255, 252, 255), (255, 178, 228), (170, 238, 255), (255, 240, 190)]


def goal_for(count):
    return next((g for g in GOALS if g > count), GOALS[-1])


def _blur_add(layer, radii):
    """Sum of blurred copies of a premultiplied-ish RGBA layer -> float RGB array."""
    out = None
    for r, k in radii:
        b = np.asarray(layer.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0
        b = b[..., :3] * b[..., 3:4] * k
        out = b if out is None else out + b
    return out


def _smooth_noise(shape, grid, rng):
    H, W = shape
    small = rng.uniform(-1, 1, grid).astype(np.float32)
    return np.asarray(Image.fromarray(small, "F").resize((W, H), Image.BICUBIC), dtype=np.float32)


def _new_wave(seed=None):
    """Pick this render's wave (random phases + wavelength jitter). Called once per render; returns the seed used."""
    global _WAVE
    seed = random.randrange(2 ** 31) if seed is None else seed
    r = random.Random(seed)
    comps = [(w, L * r.uniform(0.8, 1.25), r.uniform(0, 2 * np.pi)) for w, L in ((0.70, 1750), (0.34, 920), (0.07, 540))]
    _WAVE = (comps, seed)
    return seed


def _wave_dy(W):
    """1-D wave: vertical offset (bar-PNG px, +down) for every column x."""
    if _WAVE is None:
        _new_wave(WAVE_SEED)
    comps, _ = _WAVE
    xs = np.arange(W, dtype=np.float32)
    xc = np.minimum(xs, WAVE_X1)
    t = np.clip((xc - WAVE_X0) / (WAVE_X1 - WAVE_X0), 0, 1)
    A = WAVE_AMP * (WAVE_FLOOR + (1 - WAVE_FLOOR) * t ** 1.3)
    s = sum(w * np.sin(2 * np.pi * xc / (L * WAVE_SIZE) + ph) for w, L, ph in comps) / sum(w for w, _, _ in comps)
    return (A * s).astype(np.float32), A


def _displace(img):
    """Wave the track+fill (one layer = identical shape); the heart is moved AND tilted by the wave at the bar's end."""
    from scipy.ndimage import map_coordinates
    W, H = img.size
    dy1, A = _wave_dy(W)
    x1 = WAVE_X1
    bar = img.copy(); bar.paste((0, 0, 0, 0), (x1, 0, W, H))
    heart = Image.new("RGBA", img.size, (0, 0, 0, 0)); heart.paste(img.crop((x1, 0, W, H)), (x1, 0))
    a = np.asarray(bar, dtype=np.float32) / 255.0
    pm = np.dstack([a[..., :3] * a[..., 3:4], a[..., 3:4]])
    n2 = _smooth_noise((H, W), (9, 26), np.random.RandomState(_WAVE[1]))
    dy = dy1[None, :] + WAVE_TURB * A[None, :] * n2 * (np.arange(W) <= x1)[None, :]
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    pm = np.dstack([map_coordinates(pm[..., i], [Y - dy, X], order=1, mode="constant", cval=0) for i in range(4)])
    al = pm[..., 3:4]
    rgb = np.where(al > 1e-4, pm[..., :3] / np.maximum(al, 1e-4), 0)
    out = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), np.clip(al, 0, 1)]) * 255).astype(np.uint8), "RGBA")
    slope = float(dy1[x1] - dy1[x1 - 80]) / 80.0
    ang = float(np.clip(-np.degrees(np.arctan(slope)) * HEART_TILT, -22, 22))
    heart = heart.rotate(ang, resample=Image.BICUBIC, center=(x1, 391), translate=(0, float(dy1[x1])))
    out.alpha_composite(heart)
    return out


def _displace_alpha(alpha):
    """Make the number ride on the same wave (same columns -> same offset)."""
    from scipy.ndimage import map_coordinates
    W, H = alpha.size
    dy1, _ = _wave_dy(W)
    a = np.asarray(alpha, dtype=np.float32) / 255.0
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    o = map_coordinates(a, [Y - dy1[None, :], X], order=1, mode="constant", cval=0)
    return Image.fromarray((np.clip(o, 0, 1) * 255).astype(np.uint8), "L")


def _star_tile(kind, arm, thick, col, S=4):
    """Anti-aliased star on a small supersampled tile. Returns RGBA tile (size 2*arm+8)."""
    n = 2 * arm + 8
    t = Image.new("RGBA", (n * S, n * S), (0, 0, 0, 0)); d = ImageDraw.Draw(t)
    c = n * S / 2.0
    fill = col + (255,)
    if kind == "sparkle":                                   # tapered 4-point star
        a_, w = arm * S, max(0.9, arm * S * thick)
        d.polygon([(c, c - a_), (c + w, c - w), (c + a_, c), (c + w, c + w), (c, c + a_), (c - w, c + w), (c - a_, c), (c - w, c - w)], fill=fill)
        d.ellipse((c - w * 0.9, c - w * 0.9, c + w * 0.9, c + w * 0.9), fill=(255, 255, 255, 255))
    elif kind == "cross":                                   # thin 1-2 px plus
        h = thick * S / 2.0
        d.rectangle((c - h, c - arm * S, c + h, c + arm * S), fill=fill)
        d.rectangle((c - arm * S, c - h, c + arm * S, c + h), fill=fill)
        d.ellipse((c - h * 1.6, c - h * 1.6, c + h * 1.6, c + h * 1.6), fill=(255, 255, 255, 255))
    else:                                                   # dot
        h = thick * S
        d.ellipse((c - h, c - h, c + h, c + h), fill=fill)
    return t.resize((n, n), Image.LANCZOS)


def _stars_banner(size):
    """Random scattered stars. Sparser and dimmer the farther from the bar. Returns premult RGB, alpha, glow-source RGB."""
    rnd = random.Random(STAR_SEED)                          # STAR_SEED=None -> different every run
    vis = Image.new("RGBA", size, (0, 0, 0, 0)); gsrc = Image.new("RGBA", size, (0, 0, 0, 0))
    bx0, bx1, by = STAR_BAR
    pts, tries = [], 0
    while len(pts) < STAR_COUNT and tries < 8000:
        tries += 1
        x, y = rnd.randint(STAR_AREA[0], STAR_AREA[2]), rnd.randint(STAR_AREA[1], STAR_AREA[3])
        if STAR_KEEPOUT[0] < x < STAR_KEEPOUT[2] and STAR_KEEPOUT[1] < y < STAR_KEEPOUT[3]:
            continue
        dist = float(np.hypot(max(bx0 - x, 0, x - bx1), y - by))
        if rnd.random() > min(1.0, np.exp(-dist / 300.0) + 0.12):          # fewer stars far away
            continue
        mind = STAR_MIN0 + STAR_MINK * dist                                  # wider spacing far away
        if any((x - px) ** 2 + (y - py) ** 2 < mind ** 2 for px, py, _ in pts):
            continue
        pts.append((x, y, dist))
    for x, y, dist in pts:
        col = rnd.choice(STAR_COLORS)
        kind = rnd.choices(["sparkle", "cross", "dot"], [0.38, 0.30, 0.32])[0]
        fade = float(np.clip(1.12 - dist / STAR_FADE, 0.25, 1.0))           # dimmer with distance
        g = rnd.uniform(0.30, 1.0) * fade                                   # random glow strength
        if kind == "sparkle":
            arm, thick = rnd.choice([5, 6, 7, 9, 11, 14]), rnd.uniform(0.10, 0.20)
        elif kind == "cross":
            arm, thick = rnd.choice([3, 4, 5, 6, 8, 10]), rnd.choice([1, 1, 1, 1.5, 2])
        else:
            arm, thick = 2, rnd.uniform(0.7, 1.5)
        tile = _star_tile(kind, arm, thick, col)
        va = tile.copy(); va.putalpha(tile.getchannel("A").point(lambda v: int(v * fade * rnd.uniform(0.8, 1.0))))
        gt = tile.copy(); gt.putalpha(tile.getchannel("A").point(lambda v: int(v * g)))
        pos = (x - tile.width // 2, y - tile.height // 2)
        vis.alpha_composite(va, pos); gsrc.alpha_composite(gt, pos)
    V = np.asarray(vis, dtype=np.float32) / 255.0
    G = np.asarray(gsrc, dtype=np.float32) / 255.0
    return V[..., :3] * V[..., 3:4], V[..., 3:4], G[..., :3] * G[..., 3:4]


def _fill_layer(size, count, goal):
    x0, y0, x1, y1 = FILL_BOX
    w, h = x1 - x0, y1 - y0
    fill = Image.open(FILL_PATH).convert("RGBA").resize((w, h), Image.LANCZOS)
    cw = round(w * min(count, goal) / goal)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    if cw <= 0:
        return layer
    crop = fill.crop((0, 0, cw, h))
    if count < goal:                                   # ragged pixel-art leading edge
        rnd = random.Random(7)
        m = Image.new("L", (cw, h), 255)
        d = ImageDraw.Draw(m)
        for by in range(0, h, 6):
            cut = rnd.choice([0, 4, 8, 12])
            if cut:
                d.rectangle((cw - cut, by, cw, by + 5), fill=0)
        crop.putalpha(Image.composite(crop.getchannel("A"), Image.new("L", crop.size, 0), m))
    layer.paste(crop, (x0, y0))
    return layer


def _bar_layer(count, goal):
    """Track + fill + internal fill glow, straight RGBA in bar-PNG space."""
    track = Image.open(TRACK_PATH).convert("RGBA")
    fill = _fill_layer(track.size, count, goal)
    base = track.copy()
    base.alpha_composite(fill)
    b = np.asarray(base, dtype=np.float32) / 255.0
    pm = b[..., :3] * b[..., 3:4]
    pm = np.clip(pm + 0.5 * _blur_add(fill, FILL_GLOW), 0, 1)
    a = np.maximum(b[..., 3:4], pm.max(2, keepdims=True))
    rgb = np.where(a > 0, pm / np.maximum(a, 1e-6), 0)
    img = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), np.clip(a, 0, 1)]) * 255).astype(np.uint8), "RGBA")
    return _displace(img)          # (old bar look, unused)


def _heart_layer(count):
    """Only the heart, beside the number: size seeded by count, tilted + lifted by the shared wave at its x."""
    r = random.Random(count)
    k = r.uniform(*HEART_SIZE)
    h0 = Image.open(HEART_PATH).convert("RGBA")
    h = round(HEART_H * k)
    heart = h0.resize((max(1, round(h0.width * h / h0.height)), h), Image.LANCZOS)
    size = _bar_layer_size()
    cx = _NUM_END + HEART_GAP + heart.width / 2.0
    cy = NUM_Y + NUM_H / 2.0 + HEART_DY
    dy1, _ = _wave_dy(size[0])
    xi = int(min(max(cx, 80), size[0] - 1))
    dy = float(dy1[xi])
    slope = float(dy1[xi] - dy1[xi - 80]) / 80.0
    ang = float(np.clip(-np.degrees(np.arctan(slope)) * HEART_TILT, -22, 22))
    pad = 40
    tile = Image.new("RGBA", (heart.width + 2 * pad, heart.height + 2 * pad), (0, 0, 0, 0))
    tile.alpha_composite(heart, (pad, pad))
    tile = tile.rotate(ang, resample=Image.BICUBIC)
    from scipy.ndimage import map_coordinates
    tw, th = tile.size
    rs = np.random.RandomState(_WAVE[1] % (2 ** 31))
    amp = HEART_TURB * h
    ndy, ndx = _smooth_noise((th, tw), (5, 5), rs) * amp, _smooth_noise((th, tw), (5, 5), rs) * amp
    t = np.asarray(tile, dtype=np.float32) / 255.0
    pm = np.dstack([t[..., :3] * t[..., 3:4], t[..., 3:4]])
    Y, X = np.mgrid[0:th, 0:tw].astype(np.float32)
    pm = np.dstack([map_coordinates(pm[..., i], [Y - ndy, X - ndx], order=1, mode="constant", cval=0) for i in range(4)])
    al = pm[..., 3:4]
    rgb = np.where(al > 1e-4, pm[..., :3] / np.maximum(al, 1e-4), 0)
    tile = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), np.clip(al, 0, 1)]) * 255).astype(np.uint8), "RGBA")
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(tile, (round(cx - tile.width / 2.0), round(cy + dy - tile.height / 2.0)))
    return layer


def _number_layer(size, count, goal):
    """Alpha mask of "54 / 100": tighter spacing around "/", a bit larger, riding on the wave."""
    if FONT_SMOOTH:
        ft = ImageFont.truetype(FONT_PATH, 240)
        dtop = min(ft.getbbox(c)[1] for c in "0123456789")
        dbot = max(ft.getbbox(c)[3] for c in "0123456789")
        sc = NUM_H / float(dbot - dtop)                      # digits define the scale; every digit shares one baseline

        def seg(txt, trim):
            boxes = [ft.getbbox(c) for c in txt]
            top = min([b[1] for b in boxes] + [dtop]); bot = max([b[3] for b in boxes] + [dbot])
            parts, w = [], 0
            for c, b in zip(txt, boxes):
                t = Image.new("L", (b[2] - b[0] + 8, bot - top), 0)
                ImageDraw.Draw(t).text((4 - b[0], -top), c, font=ft, fill=255)
                bb = t.getbbox()
                if trim and bb:
                    t = t.crop((bb[0], 0, bb[2], t.height))      # trim sideways only, keep the vertical position
                parts.append(t); w += t.width
            canvas = Image.new("L", (int(w + FONT_TRACK / sc * len(txt)) + 1, bot - top), 0)
            px = 0
            for t in parts:
                canvas.paste(t, (int(px), 0), t); px += t.width + FONT_TRACK / sc
            img = canvas.resize((max(1, round(canvas.width * sc)), max(1, round(canvas.height * sc))), Image.LANCZOS)
            return img, round((dtop - top) * sc)             # (image, how far its top sits ABOVE the digit top)
    else:
        ft = ImageFont.truetype(FONT_PATH, 72)
        top, bot = ft.getbbox("0")[1], ft.getbbox("0")[3]
        sx, sy = NUM_CW / 72.0, NUM_H / float(bot - top)

        def seg(txt, trim):
            t = Image.new("L", (72 * len(txt) + 8, 96), 0)
            ImageDraw.Draw(t).text((0, 0), txt, font=ft, fill=255)
            t = t.crop((0, top, 72 * len(txt), bot))
            if trim:
                t = t.crop(t.getbbox())
            return t.resize((max(1, round(t.width * sx)), NUM_H), Image.NEAREST), 0

    x = NUM_X
    alpha = Image.new("L", size, 0)
    for txt, trim, gap in ((str(count), False, NUM_GAP), ("/", True, NUM_GAP), (str(goal), False, 0)):
        s_, up = seg(txt, trim)
        alpha.paste(s_, (x, NUM_Y - up), s_)
        x += s_.width + gap
    global _NUM_END
    _NUM_END = x
    if NUM_BOLD:
        alpha = alpha.filter(ImageFilter.MaxFilter(2 * NUM_BOLD + 1)).filter(ImageFilter.GaussianBlur(NUM_BOLD * 0.5))
        alpha = alpha.point(lambda v: min(255, int(v * 1.6)))     # re-sharpen the rounded edge
    return _displace_alpha(alpha)


def _over(dst, rgb, a):
    return dst * (1 - a) + rgb * a


def _paint_number(out, na):
    """Crimson glass number on top of `out` (H,W,3 float 0..1). `na` = number alpha mask (PIL "L", banner space)."""
    from scipy.ndimage import gaussian_filter
    n = np.asarray(na, dtype=np.float32) / 255.0                       # H,W in 0..1
    H, W = n.shape
    blur = lambda r: np.asarray(na.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0
    shift = lambda a, dy, dx: np.roll(a, (dy, dx), axis=(0, 1))
    rgb = lambda c: np.array(c, np.float32) / 255.0

    # 1) tight, crisp glow (screen blend): small radii = sharp neon-glass edge, big radii = faint haze
    glow = np.clip(sum(k * blur(r) for r, k in NUM_GLOW_RADII), 0, 1)[..., None] * rgb(NUM_GLOW_COLOR)
    out = 1 - (1 - np.clip(out, 0, 1)) * (1 - glow)
    # 2) soft dark shadow
    s = NUM_SHADOW
    out = _over(out, rgb(s["color"]), (shift(blur(s["radius"]), s["dy"], s["dx"]) * s["opacity"])[..., None])
    # 3) body: dark at the stroke edge (glass thickness), bright crimson in the core
    depth = np.clip((blur(NUM_DEPTH) - 0.5) / 0.5, 0, 1)[..., None]
    body = rgb(NUM_EDGE) * (1 - depth) + rgb(NUM_CORE) * depth
    #    texture: fine grain + soft mottling (fixed seed, so it doesn't flicker between renders)
    t = NUM_TEXTURE
    if t["grain"] or t["mottle"]:
        rs = np.random.RandomState(t["seed"])
        grain = gaussian_filter(rs.normal(0, 1, (H, W)).astype(np.float32), 0.8) * 2.0
        mottle = _smooth_noise((H, W), (36, 64), rs) + 0.5 * _smooth_noise((H, W), (110, 200), rs)
        body = np.clip(body * (1 + (t["grain"] * grain + t["mottle"] * mottle)[..., None]), 0, 1)
    # 4) glass edges: dark bottom-right rim, glossy sheen band under the top edge, thin sharp white rim on the top-left edge
    r_ = NUM_RIM_DARK
    rim = np.clip(n - shift(n, -r_["dy"], -r_["dx"]), 0, 1)[..., None]
    body = body * (1 - rim * r_["opacity"])
    h_ = NUM_SHEEN
    sheen = gaussian_filter(np.clip(n - shift(n, h_["dy"], h_["dx"]), 0, 1), 1.5)[..., None] * h_["opacity"]
    body = body * (1 - sheen) + rgb(h_["color"]) * sheen
    p_ = NUM_SPEC
    spec = np.clip(n - shift(n, p_["dy"], p_["dx"]), 0, 1)[..., None] * p_["opacity"]
    body = body * (1 - spec) + rgb(p_["color"]) * spec
    return _over(out, body, (n * NUM_OPACITY)[..., None])


def _shape_to_banner(img, mode):
    img = img.resize((round(img.width * SCALE), round(img.height * SCALE)), Image.LANCZOS)
    full = Image.new(mode, (W_, H_), 0 if mode == "L" else (0, 0, 0, 0))
    full.paste(img, OFFSET)
    return full


def render_banner(count, goal=None, out_path="banner.jpg"):
    global W_, H_
    goal = goal or goal_for(count)
    print("wave seed:", _new_wave(WAVE_SEED))        # new wave per render; shared by track, number and heart
    bg = Image.open(BG_PATH).convert("RGB")
    W_, H_ = bg.size
    bgf = np.asarray(bg, dtype=np.float32) / 255.0
    bgblur = np.asarray(bg.filter(ImageFilter.GaussianBlur(22)), dtype=np.float32) / 255.0

    # ---- bar ----
    num_alpha = _number_layer(_bar_layer_size(), count, goal)       # first: sets _NUM_END for the heart
    bar = _shape_to_banner(_heart_layer(count), "RGBA").filter(ImageFilter.GaussianBlur(SOFTEN))
    L = np.asarray(bar, dtype=np.float32) / 255.0
    a = L[..., 3:4]
    P = L[..., :3] * a
    lumP = P @ np.array([0.299, 0.587, 0.114], np.float32)
    P = P * (1 - DESAT) + lumP[..., None] * DESAT
    P = P * (1 - TINT) + (P * 0.55 + bgblur * a * 0.45) * TINT
    P *= GAIN
    # soft drop shadow under the bar
    s = BAR_SHADOW
    sh = Image.fromarray((a[..., 0] * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(s["radius"]))
    sh = np.asarray(sh, dtype=np.float32)[..., None] / 255.0
    sh = np.roll(sh, (s["dy"], s["dx"]), axis=(0, 1)) * s["opacity"]
    out = bgf * (1 - a * OPACITY) + P * OPACITY

    # Deep Glow for the bar
    lum_s = lumP[..., None] / np.maximum(a, 0.08)
    gate = np.clip((lum_s - DG_THRESHOLD / 255.0) / 0.35, 0, 1) ** 1.5
    src = Image.fromarray((np.clip(P * gate, 0, 1) * 255).astype(np.uint8), "RGB")
    glow = sum(k * np.asarray(src.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0 for r, k in DG_RADII)
    glow = glow * ((1 - DG_TINT) + DG_TINT * (bgblur * 1.4 + 0.1)) * np.array(DG_WARM, np.float32)
    out = 1 - (1 - np.clip(out, 0, 1)) * (1 - np.clip(glow, 0, 1))
    # drop shadow goes on AFTER the glow so the glow can't wash it out; not under the (glassy) track itself
    out = _over(out, np.array(s["color"], np.float32) / 255.0, sh * (1 - np.clip(a * 3, 0, 1)))

    # ---- glowy stars (banner space; own strong glow) ----
    sp, sa, gs = _stars_banner((W_, H_))
    out = out * (1 - sa) + sp
    sg = Image.fromarray((np.clip(gs, 0, 1) * 255).astype(np.uint8), "RGB")
    sglow = sum(k * np.asarray(sg.filter(ImageFilter.GaussianBlur(rr)), dtype=np.float32) / 255.0 for rr, k in STAR_GLOW)
    out = 1 - (1 - np.clip(out, 0, 1)) * (1 - np.clip(sglow, 0, 1))

    # ---- number: crimson glass (crisp glow -> shadow -> textured body -> glossy rims) ----
    na = _shape_to_banner(num_alpha, "L").filter(ImageFilter.GaussianBlur(NUM_SOFT))
    out = _paint_number(out, na)

    rgb8 = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGB")
    for q in (95, 90, 85, 80, 70):                                    # YouTube limit: 6 MB
        rgb8.save(out_path, "JPEG", quality=q, subsampling=0)
        if os.path.getsize(out_path) < 5.5 * 1024 * 1024:
            break
    return out_path


def _bar_layer_size():
    w, h = Image.open(TRACK_PATH).size
    return (w + 700, h)          # extra room on the right so long numbers + the heart are never clipped


if __name__ == "__main__":
    print(render_banner(int(sys.argv[1]) if len(sys.argv) > 1 else 54))
