"""
Decal textures for the Toma figurine (shirt, shorts, shoes) -> avatar/textures/toma_*.png

Run with a normal Python that has Pillow:   python avatar/make_toma_textures.py
build_toma.py (Blender) loads the PNGs and packs them into the GLB.

Every atlas region is documented with the UV mapping that build_toma.py uses, so decals sit on the right garment area:

SHIRT 2048x2048 (JPEG)     (u,v, v=1 is the top of the image; pixel boxes below are for a 1024 atlas, the file is 2x that)
  front torso   x 0..512    y 0..512     x in [-0.21,0.21] m (left -> right), z in [0.80,1.40] m
  back torso    x 512..1024 y 0..512     seen from behind: x from +0.21 (left edge) to -0.21, same z range.
                                         Carries the big DREAM / THIEF back print (toma_backprint.png, made by extract_backprint.py)
  right sleeve  x 0..512    y 512..768   u = angle around the sleeve (0.5 = outer side), v = along (top = shoulder)
  left sleeve   x 512..1024 y 512..768   plain
  collar rib    x 0..1024   y 896..1024  plain, slightly darker
SHORTS 1024x1024
  right leg     x 0..1024   y 0..683     u = angle around the leg (0.5 = front), top = hip (z 0.93), bottom = hem (z 0.52)
  plain black   y 683..1024  (pelvis + left leg)
SHOES 1024x1024
  canvas + flames x 0..1024 y 0..512     u = toe -> heel (0.311 m), v = sole -> collar (0.16 m)
  white patch (100,640)-(200,740), red patch (228,640)-(328,740)
"""
import os, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'textures')
os.makedirs(OUT, exist_ok=True)
FONTS = r'C:\Windows\Fonts'
PPM = 3000                       # drawing resolution for decal layers (pixels per metre)
BACK_PRINT_Z = 1.092             # height of the middle of the back print's red frame (metres, model space)


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), int(size))


def hexrgb(h, a=255):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def noisy(size, rgb, amp=1.6, seed=1):
    w, h = size
    rng = np.random.RandomState(seed)
    a = np.zeros((h, w, 3), dtype=np.float32) + np.array(rgb[:3], dtype=np.float32)
    a += rng.normal(0, amp, (h, w, 1))
    # very soft low-frequency mottling so the cloth is not a flat fill
    lo = rng.normal(0, 1, (h // 32 + 2, w // 32 + 2))
    lo = np.array(Image.fromarray(lo.astype(np.float32), mode='F').resize((w, h), Image.BICUBIC))
    a += lo[..., None] * amp * 0.8
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def layer(w_m, h_m):
    W, H = int(round(w_m * PPM)), int(round(h_m * PPM))
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def paste_phys(base, lay, region, region_phys, center_m, rot=0.0):
    """Paste a physically sized decal layer into an atlas region.
    region = (x0,y0,x1,y1) pixels; region_phys = (W,H) metres the region covers; center_m = decal centre in metres from the
    region's top-left corner (y down)."""
    if rot:
        lay = lay.rotate(rot, expand=True, resample=Image.BICUBIC)
    x0, y0, x1, y1 = region
    sx = (x1 - x0) / region_phys[0]
    sy = (y1 - y0) / region_phys[1]
    w = max(1, int(round(lay.width / PPM * sx)))
    h = max(1, int(round(lay.height / PPM * sy)))
    lay = lay.resize((w, h), Image.LANCZOS)
    px = int(round(x0 + center_m[0] * sx - w / 2))
    py = int(round(y0 + center_m[1] * sy - h / 2))
    base.paste(lay, (px, py), lay)


def fit_text(draw_font, text, target_cap_h_px):
    """Pick a font size whose cap height ('H') is target_cap_h_px."""
    size = 40
    for _ in range(6):
        f = font(draw_font, size)
        bb = f.getbbox('H')
        ch = bb[3] - bb[1]
        size = size * target_cap_h_px / ch
    return font(draw_font, size)


# ----------------------------------------------------------------------------------------------------------- SHIRT
def make_shirt():
    cream = hexrgb('#F2EFE8')
    K = 2                                                         # atlas is 2048 px so the back print stays crisp
    img = noisy((1024 * K, 1024 * K), cream, amp=1.1, seed=11)
    # collar rib band (slightly darker, ribbed)
    rib = noisy((1024 * K, 128 * K), hexrgb('#E7E2D6'), amp=1.0, seed=12)
    img.paste(rib, (0, 896 * K))

    FRONT = (0, 0, 512 * K, 512 * K); FRONT_PHYS = (0.42, 0.60)  # x -0.21..0.21, z 1.40 (top) .. 0.80
    # ---- chest print (small black & white rectangle with red lettering), just below the collar
    pw, ph = 0.100, 0.062
    lay, d = layer(pw, ph)
    W, H = lay.size
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=int(0.004 * PPM), fill=hexrgb('#0D0D0D'))
    m = int(0.0045 * PPM)
    d.rectangle((m, m, W - 1 - m, int(H * 0.60)), fill=hexrgb('#F4F2EC'))                 # white panel
    f = fit_text('ariblk.ttf', 'STAR', (int(H * 0.60) - 2 * m) * 0.58)
    tw = d.textlength('STAR', font=f)
    d.text(((W - tw) / 2, m + (int(H * 0.60) - 2 * m) * 0.20), 'STAR', font=f, fill=hexrgb('#D3202A'))
    # barcode-like white bars on the black strip
    rng = random.Random(4)
    x = m + 4
    while x < W - m - 6:
        bw = rng.choice([3, 5, 8, 4, 6])
        d.rectangle((x, int(H * 0.68), x + bw, H - m - 4), fill=hexrgb('#F4F2EC'))
        x += bw + rng.choice([4, 6, 9])
    chest_z = 1.235
    paste_phys(img, lay, FRONT, FRONT_PHYS, (0.21, 1.40 - chest_z))

    # ---- red/pink graffiti tag near the lower hem (viewer's left = figure's right)
    gw, gh = 0.150, 0.100
    lay, d = layer(gw, gh)
    W, H = lay.size
    f = font('segoescb.ttf', 0.100 * PPM)
    text = 'star'
    bb = d.textbbox((0, 0), text, font=f)
    tx, ty = (W - (bb[2] - bb[0])) / 2 - bb[0], (H * 0.78 - (bb[3] - bb[1])) / 2 - bb[1]
    red, pink, dark = hexrgb('#E0183F'), hexrgb('#FF7BAA'), hexrgb('#8A1028')
    d.text((tx, ty), text, font=f, fill=pink, stroke_width=11, stroke_fill=dark)
    d.text((tx, ty), text, font=f, fill=pink, stroke_width=4, stroke_fill=red)
    d.text((tx, ty), text, font=f, fill=pink)
    d.arc((int(W * 0.03), int(H * 0.42), int(W * 0.97), int(H * 1.05)), 205, 335, fill=red, width=int(0.006 * PPM))
    rng = random.Random(9)
    for k in range(4):                                                              # drips
        x = int(W * (0.22 + 0.19 * k + rng.uniform(-0.02, 0.02)))
        y0 = int(H * 0.70); y1 = int(H * rng.uniform(0.84, 0.98))
        d.line((x, y0, x, y1), fill=red, width=int(0.0036 * PPM))
        d.ellipse((x - int(0.0028 * PPM), y1 - int(0.0026 * PPM), x + int(0.0028 * PPM), y1 + int(0.0036 * PPM)), fill=red)
    for k in range(26):                                                             # spray speckle
        x = rng.uniform(0, W); y = rng.uniform(0, H * 0.35)
        r = rng.uniform(1.5, 4)
        d.ellipse((x - r, y - r, x + r, y + r), fill=pink if k % 2 else red)
    lay = lay.filter(ImageFilter.GaussianBlur(1.0))
    paste_phys(img, lay, FRONT, FRONT_PHYS, (0.21 - 0.092, 1.40 - 0.915), rot=7)

    # ---- STAR on the outer side of the right sleeve (reads downwards, letter tops toward the front)
    SLEEVE = (0, 512 * K, 512 * K, 768 * K); SLEEVE_PHYS = (0.40, 0.135)
    lay, d = layer(0.125, 0.034)
    W, H = lay.size
    f = fit_text('ariblk.ttf', 'STAR', 0.0275 * PPM)
    bb = d.textbbox((0, 0), 'STAR', font=f)
    d.text(((W - (bb[2] - bb[0])) / 2 - bb[0], (H - (bb[3] - bb[1])) / 2 - bb[1]), 'STAR', font=f, fill=hexrgb('#0A0A0A'))
    paste_phys(img, lay, SLEEVE, SLEEVE_PHYS, (0.20, 0.0675), rot=-90)

    # ---- back print: red-framed butterfly / hands picture with DREAM above and THIEF below (lifted from the photo)
    BACK = (512 * K, 0, 1024 * K, 512 * K)                        # x +0.21 .. -0.21 as seen from behind, z 1.40 (top) .. 0.80
    decal = Image.open(os.path.join(OUT, 'toma_backprint.png')).convert('RGBA')
    paste_phys(img, decal, BACK, FRONT_PHYS, (0.21, 1.40 - BACK_PRINT_Z))
    img.save(os.path.join(OUT, 'toma_shirt.jpg'), quality=90, subsampling=0)


# ----------------------------------------------------------------------------------------------------------- SHORTS
def make_shorts():
    img = noisy((1024, 1024), hexrgb('#111111'), amp=1.3, seed=21)
    # subtle technical-fabric diagonal micro texture
    a = np.array(img).astype(np.float32)
    yy, xx = np.mgrid[0:1024, 0:1024]
    a += (np.sin((xx + yy) * 0.9) * 1.1)[..., None]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')

    LEG = (0, 0, 1024, 683); LEG_PHYS = (0.64, 0.41)
    # Under Armour-style "UA": a bold U with an interlocking A, tonal charcoal
    lw, lh = 0.135, 0.095
    lay, d = layer(lw, lh)
    W, H = lay.size
    col = hexrgb('#3A3A3C')
    t = int(0.0125 * PPM)                                                   # stroke weight
    top, bot = int(H * 0.08), int(H * 0.92)
    ux0, ux1 = int(W * 0.05), int(W * 0.50)
    r = (ux1 - ux0) // 2
    d.line((ux0 + t // 2, top, ux0 + t // 2, bot - r), fill=col, width=t)                  # U
    d.line((ux1 - t // 2, top, ux1 - t // 2, bot - r), fill=col, width=t)
    d.arc((ux0, bot - 2 * r, ux1, bot), 0, 180, fill=col, width=t)
    ax = int(W * 0.66); half = int(W * 0.30)                                                # A (overlaps the U)
    d.line((ax - half, bot, ax, top), fill=col, width=t)
    d.line((ax + half, bot, ax, top), fill=col, width=t)
    d.line((ax - half * 0.55, int(H * 0.66), ax + half * 0.55, int(H * 0.66)), fill=col, width=int(t * 0.8))
    lay = lay.filter(ImageFilter.GaussianBlur(0.9))
    # right thigh, front of the leg (u = 0.5), a little above mid-thigh
    paste_phys(img, lay, LEG, LEG_PHYS, (0.32, 0.93 - 0.700))
    img.save(os.path.join(OUT, 'toma_shorts.png'))


# ----------------------------------------------------------------------------------------------------------- SHOES
def flame_poly(cx, base_y, w, h, sway, phase, n=24):
    left, right = [], []
    for k in range(n + 1):
        t = k / n
        half = w / 2 * (1 - t) ** 0.85 * (1 + 0.15 * math.sin(t * 5 + phase))
        off = sway * math.sin(t * 3.2 + phase) * t + sway * 0.8 * t * t
        y = base_y - h * t
        left.append((cx - half + off, y))
        right.append((cx + half + off, y))
    return left + right[::-1]


def make_shoes():
    S = 2                                                                    # supersample
    W, H = 1024 * S, 512 * S
    can = Image.new('RGB', (W, H), hexrgb('#1E120C')[:3])
    d = ImageDraw.Draw(can)
    rng = random.Random(5)
    RED, ORG, YEL = hexrgb('#E02B00')[:3], hexrgb('#FF7A00')[:3], hexrgb('#FFC107')[:3]
    base_y = H + 10 * S
    # three rows of tongues, tallest first
    tongues = []
    for row, (cnt, hmin, hmax, wmin, wmax) in enumerate([(15, 0.72, 1.00, 100, 150), (19, 0.55, 0.88, 74, 112), (24, 0.32, 0.62, 56, 84)]):
        for k in range(cnt):
            cx = (k + rng.uniform(0.0, 1.0)) / cnt * W
            tongues.append((row, cx, rng.uniform(hmin, hmax) * H, rng.uniform(wmin, wmax) * S, rng.uniform(-60, 60) * S,
                            rng.uniform(0, 6.28)))
    tongues.sort(key=lambda t: t[0])
    for row, cx, h, w, sway, ph in tongues:
        d.polygon(flame_poly(cx, base_y, w, h, sway, ph), fill=RED)
        d.polygon(flame_poly(cx + sway * 0.04, base_y, w * 0.72, h * 0.80, sway * 0.85, ph), fill=ORG)
        d.polygon(flame_poly(cx + sway * 0.06, base_y, w * 0.40, h * 0.52, sway * 0.7, ph), fill=YEL)
    d.rectangle((0, H - 22 * S, W, H), fill=RED)                              # solid base so no dark seam at the sole
    d.rectangle((0, H - 12 * S, W, H), fill=ORG)

    # Vans-style side stripe (toe -> heel is u 0 -> 1; sole is the bottom)
    stripe = []
    pts_top = [(0.90, 0.036), (0.76, 0.042), (0.60, 0.055), (0.45, 0.072), (0.36, 0.090)]
    pts_bot = [(0.90, 0.021), (0.76, 0.026), (0.60, 0.037), (0.45, 0.054), (0.36, 0.090)]
    def px(u, v): return (u * W, H - v / 0.16 * H)
    stripe = [px(*p) for p in pts_top] + [px(*p) for p in pts_bot[::-1]]
    d.polygon(stripe, fill=hexrgb('#F5F5F5')[:3])
    can = can.resize((1024, 512), Image.LANCZOS)

    img = noisy((1024, 1024), hexrgb('#1E120C'), amp=0.0, seed=31)
    img.paste(can, (0, 0))
    # slight canvas grain over the printed area
    a = np.array(img).astype(np.float32)
    rng2 = np.random.RandomState(2)
    a[:512] += rng2.normal(0, 4.0, (512, 1024, 1))
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    dd = ImageDraw.Draw(img)
    dd.rectangle((100, 640, 200, 740), fill=hexrgb('#F5F5F5')[:3])            # white rubber / laces / toe cap
    dd.rectangle((228, 640, 328, 740), fill=hexrgb('#D4161B')[:3])            # red heel tab
    dd.rectangle((356, 640, 456, 740), fill=hexrgb('#1E120C')[:3])            # dark lining
    img.save(os.path.join(OUT, 'toma_shoes.png'))


if __name__ == '__main__':
    make_shirt(); make_shorts(); make_shoes()
    print('textures written to', OUT)
