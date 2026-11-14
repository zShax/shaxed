"""
Lifts the back print of Toma's tee out of the reference photo -> avatar/textures/toma_backprint.png (RGBA decal).

The photo is taken at an angle, so the red frame of the print is un-warped to a flat rectangle (perspective transform from
its four corners), then the picture is reduced to the print's two inks: black and red on transparent. That removes the
shirt's shadows and wrinkles, and everything around the print (arm, rock, background).
The lettering (DREAM on the top edge, THIEF on the bottom edge, hollow "DREAM THIEF" down both sides) is re-set in type,
because in the photo it is bent over the shoulder or lost in folds. The side lettering is not readable in the photo, so its
wording is a best guess.

Run:  python avatar/extract_backprint.py        (needs Pillow + numpy; make_toma_textures.py pastes the decal on the shirt)
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'reference', 'ref-toma-back.webp')
OUT = os.path.join(HERE, 'textures', 'toma_backprint.png')
FONTS = r'C:\Windows\Fonts'

PPM = 3000                                   # decal pixels per metre
FRAME_W, FRAME_H = 0.285, 0.373              # size of the red frame on the real shirt (metres, estimated)
MARGIN_X, MARGIN_Y = 0.046, 0.040            # room for the vertical side lettering / DREAM + THIEF outside the frame
# corners of the red frame in the photo (pixels): top-left, top-right, bottom-right, bottom-left
QUAD = [(406, 1092), (764, 1055), (874, 1502), (544, 1563)]

INK_BLACK = (20, 18, 18)
INK_RED = (196, 24, 30)


def homography(src, dst):
    """3x3 matrix H with H @ (x, y, 1) ~ (u, v, 1) for the four point pairs src -> dst."""
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(b, float))
    return np.append(h, 1.0).reshape(3, 3)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def distress(layer, seed, amount=0.10):
    """Worn screen-print look: knock small specks and scratches out of a decal layer's alpha."""
    rng = np.random.RandomState(seed)
    w, h = layer.size
    fine = rng.rand(h, w) < amount * 0.35
    coarse = np.asarray(Image.fromarray((rng.rand(h // 6 + 1, w // 6 + 1) * 255).astype(np.uint8))
                        .resize((w, h), Image.BICUBIC)) / 255.0
    holes = fine | (coarse > 1.0 - amount)
    a = np.asarray(layer.split()[3]).astype(np.float32)
    a[holes] *= 0.08
    out = layer.copy()
    out.putalpha(Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)))
    return out


def word(text, cap_h, outline=0, seed=1, track=0.0):
    """Heavy red capitals, cap height `cap_h` pixels. outline > 0 draws hollow letters with that stroke width."""
    size = 60.0
    for _ in range(6):
        f = ImageFont.truetype(os.path.join(FONTS, 'ariblk.ttf'), int(size))
        bb = f.getbbox('H'); size = size * cap_h / (bb[3] - bb[1])
    f = ImageFont.truetype(os.path.join(FONTS, 'ariblk.ttf'), int(size))
    sp = int(track * cap_h)
    widths = [f.getlength(ch) for ch in text]
    m = 2 * (outline + 4)
    W = int(sum(widths) + sp * (len(text) - 1)) + 2 * m
    H = int(cap_h * 1.5) + 2 * m
    y = (H - cap_h) / 2 - f.getbbox('H')[1]
    solid = Image.new('L', (W, H), 0); ds = ImageDraw.Draw(solid)
    x = m
    for ch, w in zip(text, widths):
        ds.text((x, y), ch, font=f, fill=255); x += w + sp
    if outline:                                    # hollow lettering: the letter's rim only
        grown = solid.filter(ImageFilter.MaxFilter(2 * outline + 1))
        a = np.asarray(grown).astype(np.float32) - np.asarray(solid).astype(np.float32)
        mask = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    else:
        mask = solid
    im = Image.new('RGBA', (W, H), INK_RED + (0,))
    im.putalpha(mask)
    return distress(im.crop(mask.getbbox()), seed, 0.06 if outline else 0.11)


def main():
    photo = Image.open(SRC).convert('RGB')
    mx, my = int(MARGIN_X * PPM), int(MARGIN_Y * PPM)
    fw, fh = int(FRAME_W * PPM), int(FRAME_H * PPM)
    W, H = fw + 2 * mx, fh + 2 * my
    dst = [(mx, my), (mx + fw, my), (mx + fw, my + fh), (mx, my + fh)]
    coeffs = homography(dst, QUAD).ravel()[:8]            # PIL wants the output -> input mapping
    flat = photo.transform((W, H), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    flat = flat.filter(ImageFilter.UnsharpMask(radius=3, percent=60, threshold=2))
    a = np.asarray(flat).astype(np.float32) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    red = smoothstep(0.24, 0.42, r - np.maximum(g, b))
    black = smoothstep(0.37, 0.19, lum) * (1.0 - red)

    # ---- keep only the framed picture: the red border (wavy, the shirt is wrinkled) and what lies inside it -------------
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    strong = red > 0.6

    def border(mask, lo, hi, default, k=25):
        """per line: middle of the red border found between lo and hi (median of the red pixels), smoothed along the edge"""
        idx = np.arange(lo, hi)
        v = np.array([np.median(idx[line[lo:hi]]) if line[lo:hi].any() else np.nan for line in mask])
        v = np.where(np.isnan(v), default, v)
        pad = np.pad(v, k, mode='edge')
        return np.array([np.median(pad[i:i + 2 * k + 1]) for i in range(len(v))])
    d_in, d_out = int(0.030 * PPM), int(0.012 * PPM)
    left = border(strong, mx - d_out, mx + d_in, mx)
    # the left border is partly lost in a dark fold next to the arm: keep to a straight line fitted through the rest, and
    # redraw the missing stretch of red line
    t = np.arange(H, dtype=np.float32); ok = np.ones(H, bool)
    for _ in range(3):
        k1, k0 = np.polyfit(t[ok], left[ok], 1)
        ok = np.abs(left - (k1 * t + k0)) < 10
    fit = k1 * t + k0
    left = np.where(ok, left, fit)[:, None]
    band = np.abs(xx - fit[:, None]) < 0.0022 * PPM
    has_red = (strong & (np.abs(xx - fit[:, None]) < 0.004 * PPM)).sum(1) >= 4
    patch = band & ~has_red[:, None] & (yy > my) & (yy < my + fh)
    red = np.where(patch, 1.0, red); black = np.where(patch, 0.0, black)
    right = border(strong, mx + fw - d_in, mx + fw + d_out, mx + fw)[:, None]
    top = border(strong.T, my - 2 * d_out, my + d_in, my)[None, :]
    bottom = border(strong.T, my + fh - d_in, my + fh + 2 * d_out, my + fh)[None, :]
    print('border offsets px  left %+d..%+d  right %+d..%+d  top %+d..%+d  bottom %+d..%+d' % (
        left.min() - mx, left.max() - mx, right.min() - mx - fw, right.max() - mx - fw,
        top.min() - my, top.max() - my, bottom.min() - my - fh, bottom.max() - my - fh))
    rim = 0.0045 * PPM                                   # the red border line and its splatter
    keep_red = (smoothstep(left - rim - 5, left - rim, xx) * smoothstep(right + rim + 5, right + rim, xx) *
                smoothstep(top - rim - 5, top - rim, yy) * smoothstep(bottom + rim + 5, bottom + rim, yy))
    keep_black = ((xx > left) & (xx < right) & (yy > top) & (yy < bottom)).astype(np.float32)
    # the photo's own DREAM / THIEF (bent out of shape) go; they are re-set in type below
    top_word = (xx > mx + 0.20 * fw) & (xx < mx + 0.82 * fw) & (yy < top - 3)
    bottom_word = (xx > mx + 0.22 * fw) & (xx < mx + 0.88 * fw) & (yy > bottom + 3)
    keep_red *= 1.0 - (top_word | bottom_word)
    red *= keep_red; black *= keep_black

    alpha = np.clip(red + black, 0, 1)
    wsum = np.maximum(red + black, 1e-6)
    rgb = (red[..., None] * np.array(INK_RED, np.float32) + black[..., None] * np.array(INK_BLACK, np.float32)) / wsum[..., None]
    decal = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), 'RGBA')

    # ---- lettering, re-set in type ---------------------------------------------------------------------------------------
    cap = int(0.0270 * PPM)
    w1 = word('DREAM', cap, seed=3)                       # sits on the top edge of the frame, a little left of centre
    decal.alpha_composite(w1, (int(mx + fw * 0.485 - w1.width / 2), int(my - w1.height * 0.66)))
    w2 = word('THIEF', cap, seed=4)                       # hangs from the bottom edge, a little right of centre
    decal.alpha_composite(w2, (int(mx + fw * 0.535 - w2.width / 2), int(my + fh - w2.height * 0.34)))
    side = word('DREAM THIEF', int(0.019 * PPM), outline=max(2, int(0.0011 * PPM)), seed=5, track=0.10)
    rs = side.rotate(-90, expand=True)                    # hollow letters reading downwards outside the right edge
    decal.alpha_composite(rs, (int(mx + fw + 0.0100 * PPM), int(my + fh * 0.07)))
    decal.alpha_composite(rs, (int(mx - 0.0100 * PPM - rs.width), int(my + fh * 0.20)))      # and outside the left edge

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    decal.save(OUT)
    print('wrote', OUT, W, 'x', H, 'px =', round(W / PPM, 3), 'x', round(H / PPM, 3), 'm')


if __name__ == '__main__':
    main()
