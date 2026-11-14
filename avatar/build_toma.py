"""
Toma - stylized 3D collectible figurine of a young man  ->  public/models/toma-hero.glb

Outfit: oversized cream tee ("STAR" sleeve print, chest print, graffiti hem tag), black athletic shorts with a tonal "UA" logo,
Thrasher-flame Sk8-Hi high-tops, gold curb chain, wooden bead bracelet + white sport watch (left wrist).
Hair: slicked straight back, short tapered sides, small man bun with a hair tie, a few flyaway strands.

Logos / lettering / flames are TEXTURE DECALS (avatar/textures/*.png, made by avatar/make_toma_textures.py), not geometry.
Mesh names in the GLB: Head (skin, face), Body (skin), hair, bun, shirt, shorts, shoes, chain, bracelet, watch.

Run:   python avatar/make_toma_textures.py
       blender -b -P avatar/build_toma.py
Opts:  blender -b -P avatar/build_toma.py -- [--no-render] [--tag it1] [--samples 48]

Coordinates while modelling: Blender, metres, Z up, figure faces -Y (the glTF exporter converts this to Y-up / facing +Z).
The figure's LEFT side is +X (so the figure's RIGHT sleeve, the one with STAR, is on -X = viewer's left).
"""
import bpy, bmesh, math, os, sys, random, struct, json
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# ----------------------------------------------------------------------------- config
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) and not ARGS[i + 1].startswith('--') else True
    return default

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.path.abspath('avatar')
ROOT = os.path.dirname(HERE)
OUT_GLB = arg('--out') or os.path.join(ROOT, 'public', 'models', 'toma-hero.glb')
RENDER_DIR = arg('--render-dir') or os.path.join(HERE, 'renders')
TEX_DIR = os.path.join(HERE, 'textures')
TAG = arg('--tag', 'toma')
SAMPLES = int(arg('--samples', 40))
DO_RENDER = not arg('--no-render', False)
SHOTS = arg('--shots')                    # e.g. --shots back,shoes : render only these previews (no contact sheet)

TARGET_HEIGHT = 1.70
CHIN_RAISE_DEG = 2.0
HEAD_SCALE = 1.12

# palette (hex, sRGB)
C_SKIN = '#C99A78'
C_LIP = '#A5605A'
C_HAIR = '#1A1410'
C_TIE = '#4A4A4E'
C_GOLD = '#D4AF37'
C_BEAD = '#A0522D'
C_WATCH_STRAP = '#F7F7F5'
C_WATCH_FACE = '#EDEAE0'


# ----------------------------------------------------------------------------- math helpers
# ----------------------------------------------------------------------------- math helpers
def lerp(a, b, t): return a + (b - a) * t
def clamp(x, a, b): return max(a, min(b, x))
def smoothstep(a, b, x):
    if a == b: return 0.0 if x < a else 1.0
    t = clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)
def gauss(d, s): return math.exp(-0.5 * (d / s) ** 2)
def s2l(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def hexlin(h):
    h = h.lstrip('#'); r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return (s2l(r), s2l(g), s2l(b))
def col(h, a=1.0):
    r, g, b = hexlin(h); return (r, g, b, a)
def mixc(c1, c2, t):
    return tuple(lerp(c1[i], c2[i], t) for i in range(3))
def sgnpow(x, p):
    return math.copysign(abs(x) ** p, x)

def catmull(pts, per_seg=4):
    P = [Vector(p) for p in pts]
    if len(P) == 2:
        return [P[0].lerp(P[1], k / per_seg) for k in range(per_seg + 1)]
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1].copy())
    return out

def prof(v):
    """Radius profile: number, callable, or list of equally spaced keys (smoothed)."""
    if callable(v): return v
    if isinstance(v, (int, float)): return lambda t: float(v)
    keys = list(v); xs = np.linspace(0, 1, len(keys))
    dense_t = np.linspace(0, 1, 200)
    dense = np.interp(dense_t, xs, keys)
    k = 9
    pad = np.pad(dense, k, mode='edge')
    dense = np.convolve(pad, np.ones(2 * k + 1) / (2 * k + 1), mode='valid')
    dense = dense[:200]
    return lambda t: float(np.interp(t, dense_t, dense))

class KnotProfile:
    """Smoothly interpolated table: rows (z, v1, v2, ...)."""
    def __init__(self, rows, smooth=10):
        a = np.array(rows, dtype=float)
        self.z = np.linspace(a[0, 0], a[-1, 0], 400)
        self.v = []
        for k in range(1, a.shape[1]):
            d = np.interp(self.z, a[:, 0], a[:, k])
            pad = np.pad(d, smooth, mode='edge')
            d = np.convolve(pad, np.ones(2 * smooth + 1) / (2 * smooth + 1), mode='valid')[:400]
            self.v.append(d)
    def __call__(self, z):
        return tuple(float(np.interp(z, self.z, v)) for v in self.v)

# ----------------------------------------------------------------------------- mesh builder
class MB:
    def __init__(self):
        self.bm = bmesh.new()
        self.uvl = self.bm.loops.layers.uv.new('UVMap')
        self.cl = self.bm.verts.layers.float_color.new('Col')
        self.M = None

    @classmethod
    def from_mesh(cls, mesh):
        mb = cls.__new__(cls)
        mb.bm = bmesh.new(); mb.bm.from_mesh(mesh)
        mb.uvl = mb.bm.loops.layers.uv['UVMap']
        mb.cl = mb.bm.verts.layers.float_color['Col']
        mb.M = None
        return mb

    def vert(self, p, c=(1, 1, 1, 1)):
        p = Vector(p)
        if self.M is not None: p = self.M @ p
        v = self.bm.verts.new(p)
        v[self.cl] = tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 1.0)
        return v

    def vert_raw(self, p, c=(1, 1, 1, 1)):
        v = self.bm.verts.new(Vector(p))
        v[self.cl] = tuple(c) if len(c) == 4 else (c[0], c[1], c[2], 1.0)
        return v

    def face(self, vs, uvs=None, mat=0):
        try:
            f = self.bm.faces.new(vs)
        except ValueError:
            return None
        f.smooth = True; f.material_index = mat
        if uvs:
            for l, uv in zip(f.loops, uvs): l[self.uvl].uv = uv
        return f

    def build(self, name, mats, recalc=True):
        if recalc:
            bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
        self.bm.normal_update()
        mesh = bpy.data.meshes.new(name)
        self.bm.to_mesh(mesh); self.bm.free()
        for m in mats: mesh.materials.append(m)
        ca = mesh.color_attributes.get('Col')
        if ca:
            mesh.color_attributes.active_color = ca
            mesh.color_attributes.render_color_index = list(mesh.color_attributes).index(ca)
        mesh.polygons.foreach_set('use_smooth', [True] * len(mesh.polygons))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj

def apply_modifiers(obj):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear(); obj.data = me
    bpy.data.meshes.remove(old)

def solidify(obj, thickness, offset=-1.0):
    m = obj.modifiers.new('Solid', 'SOLIDIFY')
    m.thickness = thickness; m.offset = offset; m.use_even_offset = False; m.use_rim = True
    apply_modifiers(obj)

def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)

# ----------------------------------------------------------------------------- primitives
def ring_loft(mb, rings, closed=True, cap0=False, cap1=False, mat=0, uvf=None, uvpos=None, color=(1, 1, 1, 1)):
    S = len(rings[0]); R = len(rings)
    nj = S if closed else S - 1
    for i in range(R - 1):
        for j in range(nj):
            j2 = (j + 1) % S
            a, b, c, d = rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]
            uvs = None
            if uvf: uvs = [uvf(i, j), uvf(i, j + 1), uvf(i + 1, j + 1), uvf(i + 1, j)]
            elif uvpos: uvs = [uvpos(v.co) for v in (a, b, c, d)]
            mb.face((a, b, c, d), uvs, mat)
    def cap(ring, flip):
        cen = sum((v.co for v in ring), Vector()) / len(ring)
        cv = mb.vert_raw(cen, color)
        for j in range(len(ring)):
            a, b = ring[j], ring[(j + 1) % len(ring)]
            mb.face((cv, b, a) if flip else (cv, a, b), None, mat)
    if cap0: cap(rings[0], True)
    if cap1: cap(rings[-1], False)

def tube(mb, path, ra, rb=None, sides=10, mat=0, color=(1, 1, 1, 1), hint=(0, -1, 0),
         cap0=True, cap1=True, uvtile=None, power=2.0, uvpos=None):
    path = [Vector(p) for p in path]
    n = len(path)
    fa = prof(ra); fb = prof(rb if rb is not None else ra)
    T = []
    for i in range(n):
        if i == 0: t = path[1] - path[0]
        elif i == n - 1: t = path[-1] - path[-2]
        else: t = path[i + 1] - path[i - 1]
        T.append(t.normalized())
    h = Vector(hint)
    N = (h - T[0] * h.dot(T[0]))
    if N.length < 1e-4: N = Vector((1, 0, 0)) - T[0] * T[0].x
    N.normalize()
    frames = []
    for i in range(n):
        if i > 0:
            q = T[i - 1].rotation_difference(T[i]); N = q @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
        frames.append((N.copy(), T[i].cross(N)))
    rings = []; cum = [0.0]
    for i in range(1, n): cum.append(cum[-1] + (path[i] - path[i - 1]).length)
    per = []
    for i, p in enumerate(path):
        t = i / (n - 1); a = max(fa(t), 1e-4); b = max(fb(t), 1e-4)
        Nn, Bb = frames[i]
        ring = []
        for j in range(sides):
            th = 2 * math.pi * j / sides
            c, s = math.cos(th), math.sin(th)
            if power != 2.0: c, s = sgnpow(c, 2 / power), sgnpow(s, 2 / power)
            ring.append(mb.vert(p + Nn * (a * c) + Bb * (b * s), color))
        rings.append(ring); per.append(2 * math.pi * (a + b) / 2)
    uvf = None
    if uvtile:
        uvf = lambda i, j: (j / sides * per[i] / uvtile, cum[i] / uvtile)
    ring_loft(mb, rings, True, cap0, cap1, mat, uvf=uvf, uvpos=uvpos, color=color)
    return rings

def uv_sphere(mb, c, r, mat=0, angles=None, segs=16, colfn=None, keep=None, axis=(0, -1, 0)):
    """UV sphere with poles on `axis` (default: front, -Y)."""
    c = Vector(c)
    if angles is None: angles = [180 * k / 12 for k in range(13)]
    ax = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0))
    u = (ref - ax * ref.dot(ax)).normalized(); v = ax.cross(u)
    rings = []
    for k, a in enumerate(angles):
        ar = math.radians(a); ring = []
        n = 1 if k in (0, len(angles) - 1) else segs
        for j in range(n):
            ph = 2 * math.pi * j / segs
            d = ax * math.cos(ar) + (u * math.cos(ph) + v * math.sin(ph)) * math.sin(ar)
            cc = colfn(a, d) if colfn else (1, 1, 1, 1)
            ring.append(mb.vert(c + d * r, cc))
        rings.append(ring)
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        for j in range(segs):
            j2 = (j + 1) % segs
            if len(A) == 1:
                vs = (A[0], B[j2], B[j])
            elif len(B) == 1:
                vs = (A[j], A[j2], B[0])
            else:
                vs = (A[j], A[j2], B[j2], B[j])
            if keep:
                cen = sum((vv.co for vv in vs), Vector()) / len(vs)
                if not keep((cen - (mb.M @ c if mb.M else c)).normalized()): continue
            mb.face(vs, None, mat)
    return rings

def fold_displace(bm, folds):
    bm.normal_update()
    for v in bm.verts:
        d = 0.0
        for (a, b, sig, amp) in folds:
            a = Vector(a); b = Vector(b); ab = b - a
            t = clamp((v.co - a).dot(ab) / ab.length_squared, 0, 1)
            dist = (v.co - (a + ab * t)).length
            if dist < sig * 3.5: d += amp * math.exp(-0.5 * (dist / sig) ** 2)
        if d: v.co += v.normal * d

def surf_patch(mb, grid, mat=0, color=(1, 1, 1, 1), uvfn=None, colorgrid=None):
    """grid[i][j] = (pos, normal) or None.  Winding is corrected against the supplied normals."""
    R = len(grid); S = len(grid[0])
    vg = [[None] * S for _ in range(R)]
    for i in range(R):
        for j in range(S):
            g = grid[i][j]
            if g is not None:
                cc = colorgrid[i][j] if colorgrid else color
                vg[i][j] = mb.vert(g[0], cc)
    for i in range(R - 1):
        for j in range(S - 1):
            q = [vg[i][j], vg[i][j + 1], vg[i + 1][j + 1], vg[i + 1][j]]
            if any(v is None for v in q): continue
            gs = [grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]]
            nref = sum((g[1] for g in gs), Vector())
            nf = (q[1].co - q[0].co).cross(q[3].co - q[0].co)
            if nf.dot(nref) < 0: q = q[::-1]
            uvs = None
            if uvfn: uvs = [uvfn(v.co) for v in q]
            mb.face(q, uvs, mat)
    return vg

# ----------------------------------------------------------------------------- textures / materials
def make_image(name, arr, nonColor=False):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = 'Non-Color' if nonColor else 'sRGB'   # must precede the pixel write
    a = np.ones((h, w, 4), dtype=np.float32); a[..., :3] = arr[..., :3]
    img.pixels.foreach_set(a.ravel())
    img.pack()
    return img

def weave_textures(n=512, p=8):
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    h = (np.cos(2 * np.pi * x / p) + np.cos(2 * np.pi * y / p) + 0.8 * np.cos(2 * np.pi * (x + y) / (2 * p))) / 2.8
    rng = np.random.RandomState(3)
    low = np.zeros((n, n))
    for _ in range(14):
        fx, fy = rng.randint(1, 10), rng.randint(1, 10)
        low += np.cos(2 * np.pi * (fx * x / n + fy * y / n) + rng.uniform(0, 6.28)) * rng.uniform(0.3, 1.0)
    low /= 14
    lum = 0.955 + 0.035 * h + 0.03 * low
    base = np.stack([lum, lum, lum], -1)
    gx = np.roll(h, -1, 1) - np.roll(h, 1, 1); gy = np.roll(h, -1, 0) - np.roll(h, 1, 0)
    k = 2.0
    nx, ny, nz = -gx * k, -gy * k, np.ones_like(h)
    ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nrm = np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], -1)
    return base, nrm

def tartan_texture(n=512):
    cols = {'N': hexlin('#5C2530'), 'S': hexlin('#B05A66'), 'L': hexlin('#E8B8A8'), 'W': hexlin('#F5F0E6'), 'D': hexlin('#3A1219')}
    sett = [('N', 50), ('S', 26), ('N', 8), ('W', 3), ('N', 8), ('L', 16), ('N', 8), ('W', 3), ('N', 8), ('S', 26), ('N', 50), ('D', 50)]
    tot = sum(w for _, w in sett)
    seq = []
    for c, w in sett: seq += [c] * w
    seq = (seq * (n // len(seq)))[:n]
    line = np.array([cols[c] for c in seq])
    y, x = np.mgrid[0:n, 0:n]
    warp = line[x]; weft = line[y]
    twill = (((x + y) // 2) % 2 == 0)[..., None]
    img = np.where(twill, warp, weft) * 0.5 + (warp + weft) * 0.25
    return img

def make_mat(name, base='#FFFFFF', rough=0.6, metal=0.0, vcol=False, tex=None, nrm=None, nrm_strength=0.45,
             alpha=None, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); bs = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bs.outputs[0], out.inputs[0])
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Metallic'].default_value = metal
    try: bs.inputs['Specular IOR Level'].default_value = spec
    except Exception: pass
    bs.inputs['Base Color'].default_value = col(base)
    src = None
    if tex is not None:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = tex; tn.interpolation = 'Linear'
        src = tn.outputs['Color']
    if vcol:
        vn = nt.nodes.new('ShaderNodeVertexColor'); vn.layer_name = 'Col'
        if src is None:
            src = vn.outputs['Color']
        else:
            mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'
            mx.inputs[0].default_value = 1.0
            nt.links.new(src, mx.inputs[6]); nt.links.new(vn.outputs['Color'], mx.inputs[7])
            src = mx.outputs[2]
    if src is not None: nt.links.new(src, bs.inputs['Base Color'])
    if nrm is not None:
        nn = nt.nodes.new('ShaderNodeTexImage'); nn.image = nrm
        nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = nrm_strength
        nt.links.new(nn.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], bs.inputs['Normal'])
    if alpha is not None:
        bs.inputs['Alpha'].default_value = alpha
        try: m.blend_method = 'BLEND'
        except Exception: pass
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
        try: m.use_backface_culling = False
        except Exception: pass
    return m


# ----------------------------------------------------------------------------- scene reset + materials
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 1.0

def load_tex(fname):
    img = bpy.data.images.load(os.path.join(TEX_DIR, fname))
    img.colorspace_settings.name = 'sRGB'
    img.pack()
    return img

IMG_SHIRT = load_tex('toma_shirt.jpg')
IMG_SHORTS = load_tex('toma_shorts.png')
IMG_SHOES = load_tex('toma_shoes.png')

MAT = {
    'skin': make_mat('Skin', vcol=True, rough=0.55, spec=0.4),
    'hair': make_mat('Hair', vcol=True, rough=0.42, spec=0.5),
    'shirt': make_mat('Shirt', tex=IMG_SHIRT, rough=0.92, spec=0.25),
    'shorts': make_mat('Shorts', tex=IMG_SHORTS, rough=0.62, spec=0.38),
    'shoes': make_mat('Shoes', tex=IMG_SHOES, rough=0.72, spec=0.3),
    'gold': make_mat('Gold', base=C_GOLD, rough=0.3, metal=0.9),
    'detail': make_mat('Detail', vcol=True, rough=0.55, spec=0.4),
}
for k in ('shirt', 'shorts'):
    MAT[k].use_backface_culling = False          # exported as doubleSided (open hems / sleeves)

# ----------------------------------------------------------------------------- generic loft with correct winding + per-face UVs
def loft(mb, rings, uvfn=None, mat=0, closed=True, flip=None, centers=None):
    """Quad loft between rings. uvfn(corners) -> list of 4 (u,v); corners = [(vert, ring_i, j_float)] in face order.
    Winding is chosen so normals point away from the loft axis (flip=None -> automatic)."""
    S = len(rings[0]); R = len(rings); nj = S if closed else S - 1
    cen = [sum((v.co for v in r), Vector()) / len(r) for r in rings]
    ax = cen[-1] - cen[0]
    ax = ax.normalized() if ax.length > 1e-6 else Vector((0, 0, 1))
    quads = []; score = 0.0
    for i in range(R - 1):
        c = (cen[i] + cen[i + 1]) * 0.5
        for j in range(nj):
            j2 = (j + 1) % S
            corners = [(rings[i][j], i, j), (rings[i][j2], i, j + 1), (rings[i + 1][j2], i + 1, j + 1), (rings[i + 1][j], i + 1, j)]
            q = [cc[0] for cc in corners]
            n = (q[1].co - q[0].co).cross(q[3].co - q[0].co)
            fc = sum((v.co for v in q), Vector()) / 4
            if centers is not None:
                out = fc - (centers[i] + centers[min(i + 1, len(centers) - 1)]) * 0.5
            else:
                out = fc - c; out = out - ax * out.dot(ax)
            score += n.dot(out)
            quads.append(corners)
    fl = (score < 0) if flip is None else flip
    for corners in quads:
        uvs = uvfn(corners) if uvfn else None
        if fl:
            corners = corners[::-1]
            if uvs: uvs = uvs[::-1]
        mb.face([cc[0] for cc in corners], uvs, mat)

def fan_cap(mb, ring, outward, mat=0, uv=(0.5, 0.5), color=(1, 1, 1, 1)):
    cen = sum((v.co for v in ring), Vector()) / len(ring)
    cv = mb.vert_raw(cen, color)
    n = len(ring)
    for j in range(n):
        a, b = ring[j], ring[(j + 1) % n]
        nrm = (a.co - cen).cross(b.co - cen)
        vs = (cv, a, b) if nrm.dot(outward) > 0 else (cv, b, a)
        mb.face(vs, [uv, uv, uv], mat)

def plain_uv(u, v):
    return lambda corners: [(u, v)] * 4

def sgnp(c, p):
    return math.copysign(abs(c) ** (2.0 / p), c)

# ============================================================================= BODY PROPORTIONS
# shirt torso (oversized, boxy):  z, xc, yc, rx, ry, p (superellipse power: 2 = ellipse, >2 boxier)
SHIRT_K = KnotProfile([
    (0.835, 0.0, 0.002, 0.178, 0.130, 3.0),
    (0.90, 0.0, 0.002, 0.182, 0.132, 3.0),
    (1.00, 0.0, 0.003, 0.185, 0.130, 2.8),
    (1.10, 0.0, 0.004, 0.188, 0.127, 2.7),
    (1.20, 0.0, 0.005, 0.192, 0.122, 2.6),
    (1.28, 0.0, 0.006, 0.195, 0.113, 2.5),
    (1.31, 0.0, 0.007, 0.194, 0.104, 2.4),
    (1.340, 0.0, 0.008, 0.166, 0.092, 2.2),
    (1.360, 0.0, 0.010, 0.116, 0.078, 2.1),
    (1.382, 0.0, 0.012, 0.080, 0.067, 2.0),
    (1.392, 0.0, 0.013, 0.070, 0.063, 2.0),
], smooth=6)

NECK_Z = 1.392
def neck_dip(phi):
    """crew-neck drop at the front (phi measured like the shirt rings: y = yc + ry*sin)"""
    return 0.020 * max(0.0, -math.sin(phi)) ** 1.4

def shirt_front(x, z, lift=0.0):
    """point on the shirt's front surface (for the chain, decals, ...)"""
    xc, yc, rx, ry, p = SHIRT_K(z)
    t = clamp((x - xc) / rx, -0.995, 0.995)
    y = yc - ry * (1 - abs(t) ** p) ** (1.0 / p)
    h = 0.002
    def yy(xq, zq):
        xc2, yc2, rx2, ry2, p2 = SHIRT_K(zq)
        t2 = clamp((xq - xc2) / rx2, -0.995, 0.995)
        return yc2 - ry2 * (1 - abs(t2) ** p2) ** (1.0 / p2)
    fx = (yy(x + h, z) - yy(x - h, z)) / (2 * h)
    fz = (yy(x, z + h) - yy(x, z - h)) / (2 * h)
    n = Vector((fx, -1.0, fz)).normalized()
    return Vector((x, y, z)) + n * lift, n

# A-pose, symmetrical.  Figure's left = +X.   S1 shoulder joint, E elbow, W wrist
ARM = {
    +1: dict(S1=(0.178, 0.004, 1.272), E=(0.268, -0.006, 0.996), W=(0.322, -0.046, 0.790)),
    -1: dict(S1=(-0.178, 0.004, 1.272), E=(-0.268, -0.006, 0.996), W=(-0.322, -0.046, 0.790)),
}
def leg_pts(s):
    return [(s * 0.088, 0.000, 0.905), (s * 0.091, -0.006, 0.470), (s * 0.094, 0.000, 0.075)]
LEG_YAW = {+1: 0.07, -1: -0.07}        # toes out a touch (symmetrical)

parts = {}

# ============================================================================= HEAD
C = Vector((0.0, -0.004, 1.533))
HRX, HRY, HRZ = 0.0785, 0.1000, 0.1130

def nose_disp(Z, X):
    zs = [-0.060, -0.052, -0.046, -0.038, -0.028, -0.014, 0.000, 0.016, 0.030]
    A = [0.0, 0.0085, 0.0180, 0.0205, 0.0178, 0.0120, 0.0075, 0.0038, 0.0]
    W = [0.0070, 0.0100, 0.0112, 0.0100, 0.0080, 0.0064, 0.0052, 0.0048, 0.005]
    a = float(np.interp(Z, zs, A)); w = float(np.interp(Z, zs, W))
    d = a * math.exp(-0.5 * (X / w) ** 2)
    d += 0.0072 * gauss(Z + 0.043, 0.0058) * gauss(X - 0.0130, 0.0055)       # alar wings
    d -= 0.0045 * gauss(Z + 0.053, 0.0030) * gauss(X - 0.0085, 0.0035)       # nostril underside
    return d

def head_point(d):
    x, y, z = d.x, d.y, d.z
    px, py, pz = HRX * x, HRY * y, HRZ * z
    u = z
    px *= 1 - 0.16 * smoothstep(-0.05, -0.95, u)                       # slim jaw taper
    fr = smoothstep(0.35, -0.65, y)
    py -= 0.030 * smoothstep(-0.28, -1.0, u) * fr                       # chin forward
    # squarer jaw: push the lower-side verts slightly outward
    px *= 1 + 0.05 * gauss(u + 0.55, 0.22)
    X = abs(px); Z = pz
    front = smoothstep(0.12, 0.70, -y)
    disp = 0.0
    disp += 0.0048 * gauss(Z - 0.031, 0.0100) * gauss(X - 0.030, 0.026)                       # brow ridge
    disp -= 0.0060 * gauss(Z - 0.002, 0.0125) * gauss(X - 0.0335, 0.0135)                    # eye sockets
    disp += nose_disp(Z, X)
    disp += 0.0045 * gauss(Z + 0.018, 0.016) * gauss(X - 0.050, 0.016)                       # cheekbones
    disp -= 0.0040 * gauss(Z + 0.060, 0.020) * gauss(X - 0.046, 0.014)                       # cheek hollow
    disp += 0.0048 * gauss(Z + 0.0705, 0.0052) * gauss(X, 0.0175)                            # upper lip
    disp += 0.0060 * gauss(Z + 0.0870, 0.0060) * gauss(X, 0.0165)                            # lower lip
    grove = -0.0785 + 0.0014 * (X / 0.025) ** 2
    disp -= 0.0034 * gauss(Z - grove, 0.0017) * smoothstep(0.029, 0.021, X)                  # mouth line (smile)
    disp -= 0.0030 * gauss(Z + 0.0990, 0.0045) * gauss(X, 0.0155)                            # mentolabial
    disp += 0.0050 * gauss(Z + 0.1085, 0.0105) * gauss(X, 0.0165)                            # chin
    disp -= 0.0030 * gauss(Z - 0.040, 0.014) * gauss(X - 0.062, 0.010)                       # temple dip
    py -= disp * front
    # cheekbone sideways width
    sgn = 1 if px >= 0 else -1
    px += sgn * 0.0035 * gauss(Z + 0.020, 0.020) * gauss(X - 0.062, 0.016)
    return C + Vector((px, py, pz))

SKIN_LIN = hexlin(C_SKIN)
def head_color(pw, d):
    q = pw - C; X = abs(q.x); Z = q.z
    front = smoothstep(0.05, 0.6, -d.y)
    c = SKIN_LIN
    # cheek flush + eye-socket warmth
    c = mixc(c, hexlin('#D18F70'), 0.20 * gauss(X - 0.042, 0.016) * gauss(Z + 0.040, 0.016) * front)
    c = mixc(c, hexlin('#A87454'), 0.22 * gauss(X - 0.0335, 0.016) * gauss(Z - 0.002, 0.012) * front)
    # faint moustache shadow
    mm = smoothstep(0.030, 0.018, X) * smoothstep(-0.049, -0.056, Z) * smoothstep(-0.074, -0.066, Z)
    c = mixc(c, hexlin('#9A7C70'), 0.06 * mm * front)
    # clean-shaven: only a very faint jaw / chin shadow
    jw = smoothstep(-0.050, -0.090, Z) * (0.55 + 0.45 * smoothstep(0.0, 0.05, X)) * smoothstep(-0.3, 0.3, -d.y)
    c = mixc(c, hexlin('#7A5A48'), 0.15 * jw)
    # lips
    lm = 1 - clamp(math.sqrt((X / 0.0255) ** 2 + ((Z + 0.0795) / 0.0165) ** 2), 0, 1)
    c = mixc(c, hexlin(C_LIP), 0.8 * smoothstep(0.0, 0.35, lm) * front)
    gm = gauss(Z - (-0.0785 + 0.0014 * (X / 0.025) ** 2), 0.0016) * smoothstep(0.029, 0.021, X)
    c = mixc(c, hexlin('#8B534D'), 0.8 * gm * front)
    # nostrils
    c = mixc(c, hexlin('#5E3B33'), 0.85 * gauss(Z + 0.0525, 0.0030) * gauss(X - 0.0090, 0.0036) * front)
    return (c[0], c[1], c[2], 1.0)

def build_head():
    mb = MB()
    N = 28
    g = bmesh.new(); bmesh.ops.create_cube(g, size=2.0)
    bmesh.ops.subdivide_edges(g, edges=g.edges[:], cuts=N - 1, use_grid_fill=True)
    g.verts.index_update()
    vmap = {}
    for v in g.verts:
        x, y, z = v.co
        d = Vector((x * math.sqrt(max(0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                    y * math.sqrt(max(0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                    z * math.sqrt(max(0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
        p = head_point(d)
        vmap[v.index] = mb.vert(p, head_color(p, d))
    for f in g.faces:
        mb.face([vmap[v.index] for v in f.verts], None, 0)
    g.free()
    bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces[:]); mb.bm.normal_update()
    bvh = BVHTree.FromBMesh(mb.bm)

    def hit(x, z):
        loc, nrm, idx, dist = bvh.ray_cast(Vector((x, C.y - 0.30, C.z + z)), Vector((0, 1, 0)), 0.6)
        return (loc, nrm) if loc is not None else None

    # ---- eyes ------------------------------------------------------------------------
    EYE_R = 0.0148
    ang = [0, 14, 27, 33, 40, 60, 85, 115, 145, 165, 180]
    cols = {0: '#080504', 14: '#1B100B', 27: '#3A2216', 33: '#150C08', 40: '#E9E3DC'}
    def eye_col(a, d):
        if a >= 40: return col('#E7E0D9')
        ks = sorted(cols)
        for k0, k1 in zip(ks, ks[1:]):
            if k0 <= a <= k1:
                t = (a - k0) / (k1 - k0); c = mixc(hexlin(cols[k0]), hexlin(cols[k1]), t)
                return (c[0], c[1], c[2], 1.0)
        return col('#E7E0D9')
    skin_c = col(C_SKIN)
    for s in (+1, -1):
        E = Vector((s * 0.0335, C.y - 0.0805, C.z + 0.0))
        uv_sphere(mb, E, EYE_R, mat=1, angles=ang, segs=16, colfn=eye_col, axis=(0, -1, -0.14))     # gaze slightly downward
        uv_sphere(mb, E, EYE_R * 1.075, mat=0, segs=16, colfn=lambda a, d: skin_c,
                  keep=lambda dv: dv.z > 0.30 and dv.y < 0.25)                 # upper lid (relaxed, half-lowered)
        uv_sphere(mb, E, EYE_R * 1.06, mat=0, segs=16, colfn=lambda a, d: skin_c,
                  keep=lambda dv: dv.z < -0.74 and dv.y < 0.25)                # lower lid
    # ---- ears ------------------------------------------------------------------------
    for s in (+1, -1):
        rot = Matrix.Rotation(s * 0.22, 3, 'Z')
        def epos(d, s=s, rot=rot):
            p = Vector((0.0075 * d.x, 0.0175 * d.y, 0.0295 * d.z))
            ro = math.sqrt((d.y) ** 2 + d.z ** 2)
            p.x -= s * 0.0045 * gauss(ro, 0.45) * (1 if d.x * s > 0 else 0)      # concha dent
            p.x += s * 0.0028 * smoothstep(0.65, 0.95, ro) * (1 if d.x * s > 0 else 0)  # helix rim
            return C + Vector((s * 0.0785, 0.012, -0.010)) + rot @ p
        g2 = bmesh.new(); bmesh.ops.create_cube(g2, size=2.0)
        bmesh.ops.subdivide_edges(g2, edges=g2.edges[:], cuts=8, use_grid_fill=True); g2.verts.index_update()
        vm = {}
        for v in g2.verts:
            x, y, z = v.co
            d = Vector((x * math.sqrt(max(0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                        y * math.sqrt(max(0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                        z * math.sqrt(max(0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
            vm[v.index] = mb.vert(epos(d), col('#BA8866'))
        for f in g2.faces: mb.face([vm[v.index] for v in f.verts], None, 0)
        g2.free()
    # ---- eyebrows (dark strips lying on the skin) --------------------------------------
    for s in (+1, -1):
        nu, nvv = 16, 5
        grid = []
        for i in range(nu):
            t = i / (nu - 1)
            xc_ = lerp(0.013, 0.055, t)
            zc = 0.0236 + 0.0024 * math.sin(math.pi * t ** 0.9) + 0.0004 * t
            hh = (0.0040 * (1 - 0.28 * t ** 1.5) + 0.0008)
            row = []
            for j in range(nvv):
                v = j / (nvv - 1) * 2 - 1
                z_ = zc + v * hh
                lift = 0.0014 * (1 - abs(v) ** 2.2) * smoothstep(0.0, 0.08, t) * smoothstep(1.0, 0.9, t) + 0.0001
                h_ = hit(s * xc_, z_)
                row.append((h_[0] + h_[1] * lift, h_[1]) if h_ else None)
            grid.append(row)
        surf_patch(mb, grid, mat=2, color=col(C_HAIR))
    # ---- thin mouth line (closed, faintly smiling) ---------------------------------------
    nu = 18; grid = []
    for i in range(nu):
        t = i / (nu - 1); xx = lerp(-0.0245, 0.0245, t)
        zc = -0.0785 + 0.0012 * (xx / 0.0245) ** 2 - 0.0004
        row = []
        for sj in (-1, 0, 1):
            h_ = hit(xx, zc + sj * 0.0012 * (1 - 0.6 * abs(xx) / 0.0245))
            row.append((h_[0] + h_[1] * (0.00015 if sj == 0 else -0.0001), h_[1]) if h_ else None)
        grid.append(row)
    surf_patch(mb, grid, mat=1, color=col('#5F302D'))
    head = mb.build('Head', [MAT['skin'], MAT['detail'], MAT['hair']], recalc=False)
    return head


def hand_geometry(mb, side, M):
    """Mitten-like, slightly curled hand. Local: wrist cuff plane at origin, fingers along -Z, palm faces medially."""
    mb.M = M
    m = -side                       # medial x direction
    sk = col(C_SKIN)
    # palm + back of hand
    palm = [Vector((0, 0.0, 0.032)), Vector((0, 0.0, 0.0)), Vector((0.0, 0.0, -0.045)), Vector((0, 0.0, -0.092))]
    tube(mb, catmull(palm, 4), [0.0185, 0.0250, 0.0410, 0.0400], [0.0170, 0.0175, 0.0165, 0.0135], sides=12,
         mat=0, color=sk, hint=(0, -1, 0), cap0=True, cap1=True)
    fy = [-0.0285, -0.0095, 0.0095, 0.0285]
    flen = [0.074, 0.080, 0.072, 0.057]
    frad = [0.0090, 0.0092, 0.0085, 0.0072]
    ring_path = None
    for k in range(4):
        y = fy[k]; L = flen[k]
        l1, l2, l3 = L * 0.45, L * 0.30, L * 0.25
        a1, a2, a3 = math.radians(14 + 3 * k), math.radians(40 + 3 * k), math.radians(72 + 3 * k)
        p0 = Vector((0, y, -0.088))
        d1 = Vector((m * math.sin(a1), 0, -math.cos(a1)))
        p1 = p0 + d1 * l1
        d2 = Vector((m * math.sin(a2), 0, -math.cos(a2)))
        p2 = p1 + d2 * l2
        d3 = Vector((m * math.sin(a3), 0, -math.cos(a3)))
        p3 = p2 + d3 * l3
        pts = catmull([p0, p1, p2, p3], 3)
        r = frad[k]
        tube(mb, pts, [r, r * 0.97, r * 0.88, r * 0.62], [r * 0.95, r * 0.9, r * 0.82, r * 0.6], sides=8, mat=0, color=sk,
             hint=(0, -1, 0), cap0=False, cap1=True)
        if k == 2 and side > 0:
            pass
    # thumb
    t0 = Vector((m * 0.002, -0.036, -0.030))
    thumb = [t0, Vector((m * 0.004, -0.050, -0.058)), Vector((m * 0.010, -0.052, -0.086)), Vector((m * 0.016, -0.048, -0.106))]
    tube(mb, catmull(thumb, 3), [0.0112, 0.0100, 0.0088, 0.0066], [0.0105, 0.0095, 0.0085, 0.0064], sides=8, mat=0,
         color=sk, hint=(0, -1, 0), cap0=True, cap1=True)
    # brushed silver ring (left hand, ring finger)
    if ring_path:
        c0, dirv, r = ring_path
        ax = dirv.normalized()
        u = Vector((0, -1, 0)); u = (u - ax * u.dot(ax)).normalized(); v = ax.cross(u)
        nmaj, nmin = 20, 6; rings = []
        for kk in range(nmaj):
            ph = 2 * math.pi * kk / nmaj
            rad = u * math.cos(ph) + v * math.sin(ph)
            cen = c0 + rad * (r * 0.97 + 0.0003)
            ring = []
            for j in range(nmin):
                th = 2 * math.pi * j / nmin
                ring.append(mb.vert(cen + rad * (0.0017 * math.cos(th)) + ax * (0.0032 * math.sin(th)), col(C_SILVER)))
            rings.append(ring)
        ring_loft(mb, rings, True, False, False, 1)
    mb.M = None

# ============================================================================= HAIR (slicked straight back) + BUN
def sdir(psi, th):
    """unit direction on the skull sphere: psi = azimuth (0 = front, +psi toward +X), th = elevation"""
    return Vector((math.sin(psi) * math.cos(th), -math.cos(psi) * math.cos(th), math.sin(th)))
def dpt(d, off=0.0):
    return C + Vector((d.x * (HRX + off), d.y * (HRY + off), d.z * (HRZ + off)))
def dnrm(d):
    return Vector((d.x / HRX, d.y / HRY, d.z / HRZ)).normalized()
def slerp(a, b, t):
    om = math.acos(clamp(a.dot(b), -1.0, 1.0))
    if om < 1e-5: return a.copy()
    return (a * math.sin((1 - t) * om) + b * math.sin(t * om)) / math.sin(om)

HL_PSI = [0, 22, 42, 58, 70, 80, 90, 98, 108, 118, 130, 150, 180]
HL_Z = [0.072, 0.070, 0.064, 0.053, 0.037, 0.015, 0.011, 0.020, 0.027, -0.008, -0.038, -0.054, -0.060]
def hairline(psi):
    """height (relative to the skull centre) of the lower hair edge, psi in radians (symmetrical)"""
    return float(np.interp(abs(math.degrees(psi)), HL_PSI, HL_Z))

BUN_TH = math.radians(60)
DB0 = Vector((0.0, math.cos(BUN_TH), math.sin(BUN_TH)))          # bun base direction (crown-back)
BUN_BASE = dpt(DB0, 0.0035)
BUN_N = dnrm(DB0)
BUN_C = BUN_BASE + BUN_N * 0.0150
BUN_R = (0.0215, 0.0205, 0.0195)

def build_hair():
    rng = random.Random(21)
    mb = MB()
    hair_lin = hexlin(C_HAIR); edge_lin = hexlin('#6B5242')

    # ---- scalp cap: crisp front hairline, thin + faded (tapered) short sides / nape --------------------
    g = bmesh.new(); bmesh.ops.create_cube(g, size=2.0)
    bmesh.ops.subdivide_edges(g, edges=g.edges[:], cuts=29, use_grid_fill=True); g.verts.index_update()
    vm = {}
    for v in g.verts:
        x, y, z = v.co
        d = Vector((x * math.sqrt(max(0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                    y * math.sqrt(max(0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                    z * math.sqrt(max(0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
        psi = math.atan2(d.x, -d.y)
        hl_ = hairline(psi)
        if d.z * HRZ < hl_:                      # snap to the hairline -> smooth edge
            d = sdir(psi, math.asin(clamp(hl_ / HRZ, -0.95, 0.95)))
        dz = d.z * HRZ - hl_
        w_edge = smoothstep(0.0, 0.032, dz)
        ts = smoothstep(math.radians(52), math.radians(88), abs(psi))
        off = 0.0046 - 0.0032 * ts * (1 - w_edge)
        k = 0.62 * ts * (1 - w_edge) ** 1.2
        c = mixc(hair_lin, edge_lin, k)
        vm[v.index] = (mb.vert(dpt(d, off), (c[0], c[1], c[2], 1.0)), d)
    for f in g.faces:
        cen = sum((vm[v.index][1] for v in f.verts), Vector()) / 4
        psi = math.atan2(cen.x, -cen.y)
        if cen.z * HRZ > hairline(psi) - 0.0015:
            mb.face([vm[v.index][0] for v in f.verts], None, 0)
    g.free()
    bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces[:])

    # ---- combed streaks: from the hairline, back over the skull, gathering under the bun -----------------
    def streak(psi0, z_extra=0.003, r0=0.0036, crest=1.0, jitter=True):
        z0 = hairline(psi0) + z_extra
        th0 = math.asin(clamp(z0 / HRZ, -0.95, 0.95))
        d0 = sdir(psi0, th0)
        tdir = d0 - DB0 * d0.dot(DB0)
        tdir = tdir.normalized() if tdir.length > 1e-5 else Vector((1, 0, 0))
        end = (DB0 + tdir * 0.115).normalized()
        n = 12
        ph = rng.uniform(0, 6.283); amp = rng.uniform(0.006, 0.014); fq = rng.uniform(1.0, 2.0)
        pts = []
        prev = None
        for i in range(n + 1):
            s = i / n
            d = slerp(d0, end, s)
            if jitter:
                nxt = slerp(d0, end, min(1.0, s + 0.05))
                lat = d.cross(nxt - d)
                if lat.length > 1e-6:
                    d = (d + lat.normalized() * amp * math.sin(6.283 * fq * s + ph) * smoothstep(0, 0.2, s)).normalized()
            off = 0.0032 + 0.0020 * smoothstep(0, 0.15, s) + 0.0030 * crest * math.sin(math.pi * s) ** 1.2
            pts.append(dpt(d, off))
        tone = rng.uniform(0.80, 1.45)
        cc = (hair_lin[0] * tone, hair_lin[1] * tone, hair_lin[2] * tone, 1.0)
        def rad(t):
            return r0 * (0.45 + 0.55 * smoothstep(0.0, 0.12, t)) * (1 - 0.30 * smoothstep(0.7, 1.0, t))
        tube(mb, pts, rad, rad, sides=5, mat=0, color=cc, hint=(0, 0, 1), cap0=True, cap1=True)

    for psi_d in np.arange(-80, 80.1, 4.6):                        # front + crown
        crest = 1.0 if abs(psi_d) < 50 else 0.45
        streak(math.radians(psi_d + rng.uniform(-0.8, 0.8)), r0=rng.uniform(0.0034, 0.0042), crest=crest)
    for sgn in (+1, -1):
        for psi_d in (86, 93, 101, 110, 119):                      # sides (above and in front of the ears)
            streak(sgn * math.radians(psi_d + rng.uniform(-1.5, 1.5)), z_extra=0.012, r0=rng.uniform(0.0030, 0.0036), crest=0.3)
        for psi_d in (130, 142, 154, 166, 176):                    # nape -> bun
            streak(sgn * math.radians(psi_d + rng.uniform(-2, 2)), z_extra=0.016, r0=rng.uniform(0.0034, 0.0040), crest=0.5)

    # ---- a few thin loose flyaway strands near the bun and the temples ----------------------------------
    def flyaway(p0, d_out, length, droop, r0=0.0011, curl=1.0):
        p0 = Vector(p0); d_out = Vector(d_out).normalized()
        side = d_out.cross(Vector((0, 0, 1)))
        side = side.normalized() if side.length > 1e-5 else Vector((1, 0, 0))
        pts = []
        n = 7
        for i in range(n + 1):
            s = i / n
            pts.append(p0 + d_out * (length * s) + Vector((0, 0, -droop * s * s)) + side * (curl * 0.006 * math.sin(3.2 * s)))
        rad = lambda t: r0 * (1.0 - 0.8 * t)
        c = mixc(hair_lin, hexlin('#3A2A20'), rng.uniform(0.0, 0.5))
        tube(mb, pts, rad, rad, sides=4, mat=0, color=(c[0], c[1], c[2], 1.0), hint=(0, 0, 1), cap0=False, cap1=True)
    for k in range(5):                                             # around the bun
        a = rng.uniform(0, 6.283)
        ux = Vector((1, 0, 0)); uy = BUN_N.cross(ux).normalized(); ux = uy.cross(BUN_N).normalized()
        dirv = (ux * math.cos(a) + uy * math.sin(a)) * 0.9 + BUN_N * rng.uniform(0.0, 0.35)
        flyaway(BUN_C + dirv.normalized() * 0.0195, dirv, rng.uniform(0.018, 0.032), rng.uniform(0.008, 0.016), r0=0.0010, curl=rng.uniform(-1, 1))
    for sgn in (+1, -1):                                           # temples / hairline
        for k in range(2):
            psi = sgn * math.radians(rng.uniform(52, 70))
            d0 = sdir(psi, math.asin(clamp((hairline(psi) + 0.004) / HRZ, -0.9, 0.9)))
            nrm = dnrm(d0)
            tang = Vector((sgn * 0.20, 0.90, 0.40)).normalized()
            flyaway(dpt(d0, 0.0045), (tang + nrm * rng.uniform(0.15, 0.35)), rng.uniform(0.016, 0.028), rng.uniform(0.002, 0.008),
                    r0=0.0009, curl=rng.uniform(-1, 1))
    obj = mb.build('hair', [MAT['hair']], recalc=False)
    return obj

def build_bun():
    mb = MB()
    hair_lin = hexlin(C_HAIR)
    z_ax = BUN_N.copy()
    y_ax = z_ax.cross(Vector((1, 0, 0))).normalized()
    x_ax = y_ax.cross(z_ax).normalized()
    NT, NP = 14, 28
    rings = []
    for k in range(1, NT):
        th = math.pi * k / NT
        ring = []
        for j in range(NP):
            ph = 2 * math.pi * j / NP
            # spiral wrap: bands of strands winding around the knot
            sw = math.sin(3 * ph + 5.0 * (1 - math.cos(th)))
            disp = 1.0 + 0.085 * sw
            lx = BUN_R[0] * math.sin(th) * math.cos(ph) * disp
            ly = BUN_R[1] * math.sin(th) * math.sin(ph) * disp
            lz = BUN_R[2] * math.cos(th) * (1 + 0.02 * sw)
            tone = 0.85 + 0.32 * (0.5 + 0.5 * sw)
            ring.append(mb.vert(BUN_C + x_ax * lx + y_ax * ly + z_ax * lz,
                                (hair_lin[0] * tone, hair_lin[1] * tone, hair_lin[2] * tone, 1.0)))
        rings.append(ring)
    loft(mb, rings, mat=0, closed=True)
    fan_cap(mb, rings[0], z_ax, 0, color=(hair_lin[0], hair_lin[1], hair_lin[2], 1.0))
    fan_cap(mb, rings[-1], -z_ax, 0, color=(hair_lin[0], hair_lin[1], hair_lin[2], 1.0))
    # hair tie: a small band around the base of the knot
    tie_c = BUN_BASE + BUN_N * 0.0042
    R, wr = 0.0172, 0.0021
    tl = hexlin(C_TIE); tc = (tl[0], tl[1], tl[2], 1.0)
    rings = []
    NM = 28
    for k in range(NM):
        ph = 2 * math.pi * k / NM
        rad = x_ax * math.cos(ph) + y_ax * math.sin(ph)
        cen = tie_c + rad * R
        ring = [mb.vert(cen + rad * (wr * math.cos(ps)) + z_ax * (wr * 1.25 * math.sin(ps)), tc)
                for ps in [2 * math.pi * m / 6 for m in range(6)]]
        rings.append(ring)
    rings.append(rings[0])
    tie_cs = [tie_c + (x_ax * math.cos(2 * math.pi * k / NM) + y_ax * math.sin(2 * math.pi * k / NM)) * R for k in range(NM)] + [tie_c + x_ax * R]
    loft(mb, rings, mat=0, closed=True, centers=tie_cs)
    return mb.build('bun', [MAT['hair']], recalc=False)

# ============================================================================= BODY (skin): torso core, neck, arms, hands, legs
HAND_SCALE = 0.95
def hairy(mb, weight_fn, strength=0.5, seed=77):
    """soft darker overlay (arm / leg hair) on vertex colours"""
    rng = random.Random(seed)
    dark = hexlin('#5E3E2B')
    for v in mb.bm.verts:
        w = weight_fn(v.co)
        if w <= 0: continue
        k = w * strength * (0.30 + 0.70 * rng.random())
        c = v[mb.cl]
        v[mb.cl] = (lerp(c[0], dark[0], k), lerp(c[1], dark[1], k), lerp(c[2], dark[2], k), 1.0)

def build_body():
    mb = MB()
    sk = col(C_SKIN)
    # inner torso (hidden by the shirt)
    rings = []
    for z in np.linspace(0.95, 1.345, 8):
        xc, yc, rx, ry, p = SHIRT_K(z)
        rx -= 0.040; ry -= 0.030
        rings.append([mb.vert((xc + rx * sgnp(math.cos(2 * math.pi * j / 24), 2.3), yc + ry * sgnp(math.sin(2 * math.pi * j / 24), 2.3), z), sk)
                      for j in range(24)])
    loft(mb, rings, mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, -1)), 0, color=sk); fan_cap(mb, rings[-1], Vector((0, 0, 1)), 0, color=sk)
    # neck
    tube(mb, [(0, 0.014, 1.30), (0, 0.010, 1.38), (0, 0.003, 1.48)], [0.0580, 0.0560, 0.0545], [0.0560, 0.0540, 0.0535],
         sides=14, mat=0, color=sk, hint=(0, -1, 0))
    # arms (forearm hair overlay applied before the hands are added)
    def region_arm(p):
        if abs(p.x) > 0.26 and 0.77 < p.z < 1.03: return smoothstep(1.03, 0.95, p.z) * smoothstep(0.745, 0.80, p.z)
        return 0.0
    hands = []
    for s in (+1, -1):
        a = ARM[s]
        S1, E, W = Vector(a['S1']), Vector(a['E']), Vector(a['W'])
        f = (W - E).normalized()
        path = catmull([S1 + Vector((-s * 0.030, 0, -0.030)), E, W + f * 0.005], 4)
        tube(mb, path, [0.046, 0.039, 0.030, 0.0215], [0.044, 0.037, 0.029, 0.0205], sides=12, mat=0, color=sk, hint=(0, -1, 0))
        hands.append((s, W, f))
    hairy(mb, region_arm, 0.55)
    # legs (shins visible below the shorts, down into the shoes)
    for s in (+1, -1):
        H_, K_, A_ = [Vector(p) for p in leg_pts(s)]
        # The thigh starts inside the shorts (well below the hips: nothing of it is seen higher up) and the ankle sits over
        # the heel, in the middle of the shoe collar.
        top = H_.lerp(K_, (H_.z - 0.800) / (H_.z - K_.z))
        path = catmull([top, K_, Vector((A_.x, A_.y + 0.010, 0.050))], 6)
        tube(mb, path, [0.060, 0.056, 0.049, 0.041, 0.031], [0.060, 0.055, 0.048, 0.040, 0.031], sides=16, mat=0, color=sk,
             hint=(0, -1, 0))
    def region_leg(p):
        if 0.16 < p.z < 0.50 and abs(p.x) > 0.04: return smoothstep(0.16, 0.24, p.z) * smoothstep(0.50, 0.44, p.z)
        return 0.0
    hairy(mb, region_leg, 0.5, seed=78)
    for s, W, f in hands:
        R = Vector((0, 0, -1)).rotation_difference(f).to_matrix().to_4x4()
        M = Matrix.Translation(W) @ R @ Matrix.Diagonal((HAND_SCALE, HAND_SCALE, HAND_SCALE, 1.0))
        hand_geometry(mb, s, M)
    return mb.build('Body', [MAT['skin']], recalc=True)

# ============================================================================= SHIRT (oversized boxy tee)
def build_shirt():
    mb = MB()
    S = 44
    zs = np.concatenate([np.linspace(0.835, 1.30, 15), np.linspace(1.31, NECK_Z, 9)])
    rings = []
    for z in zs:
        xc, yc, rx, ry, p = SHIRT_K(z)
        ring = []
        for j in range(S):
            phi = 2 * math.pi * j / S
            x = xc + rx * sgnp(math.cos(phi), p); y = yc + ry * sgnp(math.sin(phi), p)
            zz = z
            if z > 1.335:
                zz = z - neck_dip(phi) * clamp((z - 1.335) / (NECK_Z - 1.335), 0, 1) ** 1.2
            ring.append(mb.vert((x, y, zz)))
        rings.append(ring)
    # distance along the cloth from the front / back centre line (ring vertex S*3/4 is the front centre, S/4 the back centre)
    arcs = []
    for ring in rings:
        a = [0.0]
        for j in range(S):
            p0, p1 = ring[j].co, ring[(j + 1) % S].co
            a.append(a[-1] + math.hypot(p1.x - p0.x, p1.y - p0.y))
        arcs.append(a)
    def uv_torso(corners):
        cy = sum(c[0].co.y for c in corners) / 4
        out = []
        for v, i, jf in corners:
            vv = 0.5 + clamp((v.co.z - 0.80) / 0.60, 0, 1) * 0.5
            a = arcs[i]
            if cy < 0.006:                       # front: +x to the right of the atlas region
                d = a[jf] - a[S * 3 // 4]
                u = (d + 0.21) / 0.42 * 0.5
            else:                                # back, seen from behind: +x to the left
                d = a[S // 4] - a[jf]
                u = 0.5 + (0.21 - d) / 0.42 * 0.5
                u = clamp(u, 0.502, 0.998)
            out.append((clamp(u, 0.002, 0.998) if cy >= 0.006 else clamp(u, 0.002, 0.498), vv))
        return out
    loft(mb, rings, uvfn=uv_torso, mat=0, closed=True)
    # soft fabric wrinkles (front and back)
    folds = [((-0.150, -0.112, 1.17), (-0.085, -0.134, 0.90), 0.014, 0.0050),
             ((0.150, -0.112, 1.16), (0.100, -0.134, 0.92), 0.014, 0.0040),
             ((-0.10, -0.136, 0.87), (0.12, -0.136, 0.865), 0.010, 0.0030),
             ((-0.05, -0.128, 1.05), (0.02, -0.132, 0.95), 0.010, 0.0024),
             ((0.17, 0.0, 1.00), (0.172, 0.04, 0.88), 0.012, 0.0030),
             ((-0.17, 0.0, 1.02), (-0.172, 0.05, 0.87), 0.012, 0.0030),
             ((-0.12, 0.125, 1.15), (0.00, 0.14, 0.93), 0.013, 0.0040),
             ((0.12, 0.125, 1.12), (0.04, 0.14, 0.90), 0.013, 0.0035),
             ((-0.15, 0.06, 1.24), (-0.18, -0.03, 1.19), 0.012, 0.0030),
             ((0.15, 0.06, 1.24), (0.18, -0.03, 1.19), 0.012, 0.0030)]
    fold_displace(mb.bm, folds)

    # crew-neck rib collar
    N = 44; rx_c, ry_c, m = 0.0715, 0.0655, 0.0085
    rings = []
    for k in range(N):
        phi = 2 * math.pi * k / N
        c_, s_ = math.cos(phi), math.sin(phi)
        cen = Vector((rx_c * c_, 0.013 + ry_c * s_, NECK_Z - neck_dip(phi) + 0.001))
        rh = Vector((c_ / rx_c, s_ / ry_c, 0)).normalized()
        rings.append([mb.vert(cen + rh * (m * math.cos(ps)) + Vector((0, 0, m * 0.85 * math.sin(ps))))
                      for ps in [2 * math.pi * q / 8 for q in range(8)]])
    rings.append(rings[0])
    loft(mb, rings, uvfn=plain_uv(0.25, 0.06), mat=0, closed=True)

    # short wide drop-shoulder sleeves ending mid-bicep; the right sleeve (-X) carries the STAR print
    for s in (+1, -1):
        a = ARM[s]; S1 = Vector(a['S1']); E = Vector(a['E'])
        dr = (E - S1).normalized()
        out_h = Vector((s, 0, 0)); e_out = (out_h - dr * out_h.dot(dr)).normalized()
        e_front = Vector((0, -1, 0))
        L = 0.135; SS = 36
        ts = list(np.linspace(-0.03, L, 11))
        rings = []
        for t in ts:
            capk = clamp((t + 0.03) / 0.06, 0, 1)
            r = (0.044 + 0.014 * smoothstep(0, 1, capk)) + 0.0095 * clamp((t - 0.03) / (L - 0.03), 0, 1)
            ctr = S1 + dr * t + Vector((-s * 0.010 * (1 - capk) + s * 0.002, 0, -0.010 * (1 - capk)))
            ring = []
            for j in range(SS):
                th = (j / SS - 0.5) * 2 * math.pi
                wr = 1 + 0.030 * math.sin(5 * th + 11 * t) * smoothstep(0.0, 0.05, t) + 0.018 * math.sin(3 * th - 7 * t)
                ring.append(mb.vert(ctr + e_out * (math.cos(th) * r * wr) + e_front * (math.sin(th) * r * 0.97 * wr)))
            rings.append(ring)
        u0 = 0.0 if s < 0 else 0.5
        def uv_sl(corners, ts=ts, u0=u0):
            out = []
            for v, i, jf in corners:
                along = 1 - clamp(ts[i], 0, L) / L
                out.append((u0 + clamp(jf / SS, 0.004, 0.996) * 0.5 * 0.99 + 0.0025, 0.25 + along * 0.25))
            return out
        loft(mb, rings, uvfn=uv_sl, mat=0, closed=True)
        fan_cap(mb, rings[0], -dr, 0, uv=(0.25, 0.06))
    return mb.build('shirt', [MAT['shirt']], recalc=False)

# ============================================================================= SHORTS (black athletic, loose, above the knee)
# Everything above the tee's hem (z = 0.835) is kept at least ~1.5 cm inside the tee, so the shorts never show through it,
# standing or walking. Below the hem the legs flare out a little.
SHORTS_TOP, SHORTS_HEM = 0.93, 0.52
def shorts_leg(z):
    """one leg at height z: (centre x for the +X leg, half-width, half-depth). The two legs meet in the middle."""
    xo = float(np.interp(z, [0.52, 0.70, 0.82, 0.93], [0.186, 0.176, 0.160, 0.154]))      # outer edge
    xi = 0.003                                                                           # inner edge
    ry = float(np.interp(z, [0.52, 0.80, 0.93], [0.108, 0.103, 0.099]))
    return (xo + xi) / 2, (xo - xi) / 2, ry

def build_shorts():
    mb = MB()
    S = 36
    # waist + seat (hidden under the tee)
    zs = np.linspace(1.00, 0.770, 9)
    rings = []
    for z in zs:
        rx = float(np.interp(z, [0.770, 0.80, 0.86, 0.93, 1.00], [0.100, 0.140, 0.154, 0.154, 0.148]))
        ry = float(np.interp(z, [0.770, 0.80, 0.86, 0.93, 1.00], [0.060, 0.074, 0.096, 0.108, 0.106]))
        rings.append([mb.vert((rx * sgnp(math.cos(2 * math.pi * j / S), 2.4), 0.002 + ry * sgnp(math.sin(2 * math.pi * j / S), 2.4), z))
                      for j in range(S)])
    loft(mb, rings, uvfn=plain_uv(0.5, 0.15), mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, 1)), 0, uv=(0.5, 0.15)); fan_cap(mb, rings[-1], Vector((0, 0, -1)), 0, uv=(0.5, 0.15))
    ZT, ZH = SHORTS_TOP, SHORTS_HEM
    for s in (+1, -1):
        pts = leg_pts(s)
        zz = [p[2] for p in pts][::-1]; ys = [p[1] for p in pts][::-1]
        rings = []
        zlist = list(np.linspace(ZT, ZH, 14))
        for z in zlist:
            cx, rx, ry = shorts_leg(z)
            cy = float(np.interp(z, zz, ys)) - 0.002
            ring = []
            for j in range(S):
                th = (j / S - 0.5) * 2 * math.pi
                # soft folds, only where the leg hangs free below the tee
                wr = 1 + (0.022 * math.sin(4 * th + 14 * z) + 0.010 * math.sin(7 * th - 20 * z)) * smoothstep(0.82, 0.66, z)
                # outer half: plain ellipse. inner half: boxy, so the two legs lie flat against each other in the middle
                # and the front / back of the shorts read as one garment with a centre seam
                sx = math.sin(th)
                if sx * s < 0: sx = sgnp(sx, 5.0); cq = sgnp(math.cos(th), 5.0)
                else: cq = math.cos(th)
                ring.append(mb.vert((s * cx + sx * rx * wr, cy - cq * ry * wr, z)))
            rings.append(ring)
        def uv_leg(corners, zlist=zlist, s=s):
            out = []
            for v, i, jf in corners:
                if s < 0:
                    along = (zlist[i] - ZH) / (ZT - ZH)
                    out.append((clamp(jf / S, 0.003, 0.997), 0.333 + along * 0.667))
                else:
                    out.append((0.5, 0.15))
            return out
        loft(mb, rings, uvfn=uv_leg, mat=0, closed=True)
    return mb.build('shorts', [MAT['shorts']], recalc=False)

# ============================================================================= SHOES (Vans Sk8-Hi style, Thrasher flames)
# local frame: origin on the floor under the ankle, toe toward -Y.
# One rounded canvas body (toe -> heel counter), a high-top shaft that rises out of it at a clear angle (no two surfaces lying
# on top of each other), a white foxing sole around everything, laces and a red heel tab.
Y_TOE, Y_HEEL = -0.2185, 0.0925          # the texture's u runs toe -> heel over this range
Y_BACK = 0.066                            # back of the heel counter
UPPER_Z0 = 0.016                          # the canvas starts inside the sole
SOLE_TOP = 0.023
_PY = [-0.2185, -0.190, -0.160, -0.120, -0.080, -0.040, 0.000, 0.030, 0.066]
_PW = [0.0465, 0.0490, 0.0510, 0.0520, 0.0510, 0.0490, 0.0470, 0.0460, 0.0450]     # half width
_PT = [0.0400, 0.0460, 0.0540, 0.0640, 0.0720, 0.0780, 0.0820, 0.0830, 0.0800]     # top of the canvas
def end_round(y):
    """1 along the shoe, falling to 0 in a quarter circle at the toe tip and at the back of the heel"""
    a = clamp((y - Y_TOE) / 0.044, 0, 1); b = clamp((Y_BACK - y) / 0.034, 0, 1)
    return math.sqrt(max(0.0, 1 - (1 - a) ** 2)) * math.sqrt(max(0.0, 1 - (1 - b) ** 2))
def sb_(y): return 0.009 * smoothstep(-0.150, Y_TOE, y) ** 1.5                      # toe spring
def sw_(y): return float(np.interp(y, _PY, _PW)) * end_round(y) ** 0.9
def st_(y):
    return UPPER_Z0 + (float(np.interp(y, _PY, _PT)) - UPPER_Z0) * (0.30 + 0.70 * end_round(y) ** 0.8) + 0.5 * sb_(y)
def shoe_stations():
    toe = [0.00001, 0.0002, 0.0010, 0.0032, 0.0075, 0.0140, 0.0225, 0.0325, 0.0440]
    heel = [0.0340, 0.0240, 0.0150, 0.0080, 0.0032, 0.0010, 0.0002, 0.00001]
    mid = list(np.linspace(Y_TOE + 0.044, Y_BACK - 0.034, 9))[1:-1]
    return [Y_TOE + d for d in toe] + mid + [Y_BACK - d for d in heel]

SHAFT_CY = 0.012
SHAFT_KY = 1.18
# (z, radius): 7 outer rings bottom -> collar, then the padded collar rolls over into the dark lining
SHAFT_PROFILE = [(0.045, 0.0390), (0.070, 0.0425), (0.095, 0.0440), (0.125, 0.0452), (0.150, 0.0470), (0.166, 0.0482),
                 (0.174, 0.0470), (0.178, 0.0432), (0.176, 0.0394), (0.166, 0.0378), (0.150, 0.0372)]
def shaft_r(z):
    zs = [p[0] for p in SHAFT_PROFILE[:7]]; rs = [p[1] for p in SHAFT_PROFILE[:7]]
    return float(np.interp(z, zs, rs))

U_PATCH_WHITE = (150 / 1024, 1 - 690 / 1024)
U_PATCH_RED = (278 / 1024, 1 - 690 / 1024)
U_PATCH_DARK = (406 / 1024, 1 - 690 / 1024)

def shoe_u(y): return clamp((y - Y_TOE) / (Y_HEEL - Y_TOE), 0.003, 0.997)

def super_ring(mb, y, a, zb, zt, p=2.8, S=20, color=(1, 1, 1, 1)):
    cz = (zt + zb) / 2; b = max((zt - zb) / 2, 0.0008); a = max(a, 0.0008)
    ring = []
    for j in range(S):
        th = 2 * math.pi * j / S
        ring.append(mb.vert((a * sgnp(math.cos(th), p), y, cz + b * sgnp(math.sin(th), p)), color))
    return ring, cz, b, a

def half_arc(a, b, p, n=48):
    """cumulative arclength along the right half of a super-ellipse from th=0 (side) up to th=pi/2 (top)"""
    ths = np.linspace(0, math.pi / 2, n)
    xs = a * np.sign(np.cos(ths)) * np.abs(np.cos(ths)) ** (2 / p); zs = b * np.sign(np.sin(ths)) * np.abs(np.sin(ths)) ** (2 / p)
    seg = np.hypot(np.diff(xs), np.diff(zs))
    return ths, np.concatenate([[0], np.cumsum(seg)])

def build_shoe_into(mb, M, tmp_bvh_holder=None):
    mb.M = M
    Minv = M.inverted()
    S = 20
    stations = shoe_stations()
    # ---- canvas body (toe -> heel) -----------------------------------------------------------------------------
    rings = []; meta = []
    for y in stations:
        ring, cz, b, a = super_ring(mb, y, sw_(y), sb_(y) + UPPER_Z0, st_(y), 2.8, S)
        rings.append(ring); meta.append((y, cz, b, a))
    arcs = [half_arc(a, b, 2.8) for (y, cz, b, a) in meta]
    def uv_upper(corners):
        out = []
        for v, i, jf in corners:
            y, cz, b, a = meta[i]
            th = 2 * math.pi * (jf % S) / S
            t = th if th <= math.pi else th - 2 * math.pi
            if abs(t) > math.pi / 2: t = math.copysign(math.pi, t) - t
            ths, arc = arcs[i]
            sgn = 1 if t >= 0 else -1
            ar = float(np.interp(abs(t), ths, arc)) * sgn
            vv = clamp((cz - 0.030) + ar, 0.0, 0.158)
            out.append((shoe_u(y), 0.5 + vv / 0.16 * 0.5))
        return out
    loft(mb, rings, uvfn=uv_upper, mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, -1, 0)), 0, uv=(shoe_u(Y_TOE), 0.62))
    fan_cap(mb, rings[-1], Vector((0, 1, 0)), 0, uv=(shoe_u(Y_BACK), 0.62))

    # ---- high-top shaft with padded collar ---------------------------------------------------------------
    rings = []
    for k, (z, r) in enumerate(SHAFT_PROFILE):
        ring = []
        for j in range(24):
            th = 2 * math.pi * j / 24
            ring.append(mb.vert((r * math.cos(th), SHAFT_CY + r * SHAFT_KY * math.sin(th), z)))
        rings.append(ring)
    def uv_shaft(corners):
        out = []
        for v, i, jf in corners:
            if i >= 8:
                out.append(U_PATCH_DARK)
            else:
                out.append((shoe_u((Minv @ v.co).y), 0.5 + clamp(SHAFT_PROFILE[i][0] - 0.03, 0, 0.158) / 0.16 * 0.5))
        return out
    loft(mb, rings, uvfn=uv_shaft, mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, -1)), 0, uv=U_PATCH_DARK)

    # ---- white rubber sole / foxing: a touch longer and wider than the canvas, slightly taller at the toe ----------
    # Built as the shoe's outline (seen from above) pulled straight up, so the wall runs smoothly round toe and heel.
    ymid = (Y_TOE + Y_BACK) / 2
    def outline(z_of_y, inset, grow):
        pts = []
        for sgn, ys_ in ((+1, stations), (-1, stations[::-1])):
            for y in ys_:
                a = max(sw_(y) * 1.035 + 0.0016 - inset, 0.0002)
                pts.append(mb.vert((sgn * a, ymid + (y - ymid) * grow, z_of_y(y))))
        return pts
    sole_top = lambda y: SOLE_TOP + sb_(y) + 0.003 * smoothstep(-0.165, -0.195, y)
    rings = [outline(lambda y: 0.0, 0.0030, 1.006), outline(lambda y: 0.0035, 0.0, 1.016),
             outline(lambda y: sole_top(y) - 0.0030, 0.0, 1.016), outline(sole_top, 0.0028, 1.008)]
    loft(mb, rings, uvfn=plain_uv(*U_PATCH_WHITE), mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, -1)), 0, uv=U_PATCH_WHITE); fan_cap(mb, rings[-1], Vector((0, 0, 1)), 0, uv=U_PATCH_WHITE)

    # ---- red heel tab on the back of the sole ------------------------------------------------------------------
    ytab = ymid + (Y_BACK - ymid) * 1.016
    rings = []
    for dy in (-0.004, 0.0012):
        rings.append([mb.vert((0.0125 * sgnp(math.cos(2 * math.pi * q / 14), 4.0), ytab + dy, 0.0125 + 0.0070 * sgnp(math.sin(2 * math.pi * q / 14), 4.0)))
                      for q in range(14)])
    loft(mb, rings, uvfn=plain_uv(*U_PATCH_RED), mat=0, closed=True)
    fan_cap(mb, rings[-1], Vector((0, 1, 0)), 0, uv=U_PATCH_RED)

    # ---- white laces: bars across the vamp and up the shaft front, plus a small bow ---------------------------
    lace_uv = U_PATCH_WHITE
    def vamp_pt(x, y):
        a = sw_(y); zt = st_(y); zb = sb_(y) + UPPER_Z0
        cz = (zt + zb) / 2; b = (zt - zb) / 2
        u = clamp(x / a, -0.98, 0.98)
        return Vector((x, y, cz + b * (1 - abs(u) ** 2.8) ** (1 / 2.8) + 0.0016))
    def shaft_pt(x, z):
        r = shaft_r(z)
        u = clamp(x / r, -0.98, 0.98)
        return Vector((x, SHAFT_CY - r * SHAFT_KY * math.sqrt(1 - u * u) - 0.0016, z))
    bars = []
    for y in (-0.118, -0.098, -0.078, -0.058):
        bars.append([vamp_pt(x, y) for x in np.linspace(-0.0235, 0.0235, 7)])
    for z in (0.094, 0.110, 0.126, 0.142):
        bars.append([shaft_pt(x, z) for x in np.linspace(-0.0235, 0.0235, 7)])
    for pts in bars:
        tube(mb, pts, 0.0024, 0.0024, sides=6, mat=0, color=(1, 1, 1, 1), hint=(0, 1, 0), cap0=True, cap1=True,
             uvpos=lambda p: lace_uv)
    top = shaft_pt(0.0, 0.156) + Vector((0, -0.0020, 0.0040))
    for sx in (+1, -1):
        loop = [top, top + Vector((sx * 0.008, -0.004, 0.006)), top + Vector((sx * 0.016, -0.003, 0.002)), top + Vector((sx * 0.016, 0.002, -0.004))]
        tube(mb, catmull(loop, 3), 0.0021, 0.0021, sides=5, mat=0, color=(1, 1, 1, 1), hint=(0, 0, 1), uvpos=lambda p: lace_uv)
        tail = [top, top + Vector((sx * 0.004, -0.006, -0.010)), top + Vector((sx * 0.007, -0.010, -0.024))]
        tube(mb, catmull(tail, 3), 0.0019, 0.0016, sides=5, mat=0, color=(1, 1, 1, 1), hint=(0, 0, 1), uvpos=lambda p: lace_uv)
    mb.M = None

def build_shoes():
    mb = MB()
    for s in (+1, -1):
        A = leg_pts(s)[2]
        M = Matrix.Translation((A[0], A[1], 0.0)) @ Matrix.Rotation(LEG_YAW[s], 4, 'Z')
        build_shoe_into(mb, M)
    return mb.build('shoes', [MAT['shoes']], recalc=False)

# ============================================================================= GOLD CHAIN (curb / Cuban links)
def closed_loop_tube(mb, pts, B, wr, sides=4, color=(1, 1, 1, 1), mat=0):
    """thin torus-like wire along a closed polyline `pts`, lying in the plane with normal B"""
    n = len(pts)
    rings = []
    for k in range(n):
        t = (pts[(k + 1) % n] - pts[k - 1]).normalized()
        rad = t.cross(B).normalized()
        rings.append([mb.vert(pts[k] + rad * (wr * math.cos(2 * math.pi * q / sides)) + B * (wr * math.sin(2 * math.pi * q / sides)), color)
                      for q in range(sides)])
    rings.append(rings[0])
    loft(mb, rings, uvfn=None, mat=mat, closed=True, centers=list(pts) + [pts[0]])

def build_chain():
    mb = MB()
    # closed necklace path: bottom centre -> up the figure's left -> round the back of the neck -> down the right
    def front_pt(side, tau):
        x = side * 0.082 * math.cos(tau)
        z = NECK_Z + 0.003 - 0.122 * math.sin(tau) ** 1.25
        p, n = shirt_front(x, z, 0.0042)
        return p
    left = [front_pt(+1, tau) for tau in np.linspace(math.pi / 2, 0.0, 9)]
    back = []
    for phi in np.linspace(0.0, math.pi, 11)[1:-1]:
        back.append(Vector((0.0830 * math.cos(phi), 0.013 + 0.0765 * math.sin(phi), NECK_Z + 0.0095)))
    right = [front_pt(-1, tau) for tau in np.linspace(0.0, math.pi / 2, 9)]
    key = left + back + right
    # close it smoothly at the bottom
    dense = catmull(key + [key[0]], 6)
    # the first/last points coincide (bottom centre); drop the duplicate
    dense = dense[:-1]
    # arc-length resample into evenly spaced link centres
    cum = [0.0]
    for i in range(1, len(dense)): cum.append(cum[-1] + (dense[i] - dense[i - 1]).length)
    total = cum[-1] + (dense[0] - dense[-1]).length
    pitch = 0.0092
    nl = int(round(total / pitch)); nl += nl % 2
    def at(sv):
        sv = sv % total
        i = int(np.searchsorted(cum, sv, side='right')) - 1
        i = min(i, len(dense) - 1)
        p0 = dense[i]; p1 = dense[(i + 1) % len(dense)]
        seg = (p1 - p0).length
        t = (sv - cum[i]) / seg if seg > 1e-9 else 0
        return p0.lerp(p1, t), (p1 - p0).normalized() if seg > 1e-9 else Vector((1, 0, 0))
    gold = col(C_GOLD)
    Lx, Ly, wr = 0.0070, 0.0042, 0.00125
    for k in range(nl):
        c, T = at(total * k / nl)
        up = Vector((0, -0.35, 1.0)) if c.z > 1.33 else Vector((0, -1, 0))
        # surface normal estimate: toward the outside (front -Y below the collar, outward from the neck above it)
        if c.y > 0.02 or c.z > 1.36:
            n_ = (Vector((c.x, c.y - 0.013, 0)).normalized() + Vector((0, 0, 0.6))).normalized()
        else:
            n_ = shirt_front(c.x, c.z)[1]
        n_ = (n_ - T * n_.dot(T)).normalized()
        lat = T.cross(n_).normalized()
        if k % 2 == 0:
            B = n_; ax2 = lat          # flat link lying on the shirt
        else:
            B = lat; ax2 = n_          # link standing on edge
        pts = [c + T * (Lx * sgnp(math.cos(2 * math.pi * q / 10), 2.6)) + ax2 * (Ly * sgnp(math.sin(2 * math.pi * q / 10), 2.6))
               for q in range(10)]
        closed_loop_tube(mb, pts, B, wr, sides=4, color=gold, mat=0)
    return mb.build('chain', [MAT['gold']], recalc=False)

# ============================================================================= WRIST: wooden bead bracelet + white sport watch (LEFT wrist, +X)
def left_wrist_frame():
    a = ARM[+1]
    E, W = Vector(a['E']), Vector(a['W'])
    f = (W - E).normalized()
    e_out = (Vector((1, 0, 0)) - f * f.x).normalized()
    e_side = f.cross(e_out).normalized()
    return W, f, e_out, e_side

def build_bracelet():
    mb = MB()
    W, f, e_out, e_side = left_wrist_frame()
    rng = random.Random(3)
    base = hexlin(C_BEAD)
    cen = W - f * 0.068
    R = 0.0262 + 0.0053
    nb = 17
    for k in range(nb):
        ph = 2 * math.pi * k / nb
        d = e_out * math.cos(ph) + e_side * math.sin(ph)
        tone = rng.uniform(0.82, 1.15)
        cc = (base[0] * tone, base[1] * tone, base[2] * tone, 1.0)
        uv_sphere(mb, cen + d * R, 0.0058, mat=0, segs=8, angles=[0, 40, 80, 120, 160, 180], colfn=lambda a, dv, cc=cc: cc, axis=tuple(d))
    # thin dark elastic cord
    cord = [cen + (e_out * math.cos(2 * math.pi * k / 24) + e_side * math.sin(2 * math.pi * k / 24)) * (R - 0.0045) for k in range(24)]
    closed_loop_tube(mb, cord, f, 0.0009, sides=4, color=(0.02, 0.012, 0.008, 1.0))
    return mb.build('bracelet', [MAT['detail']], recalc=False)

def build_watch():
    mb = MB()
    W, f, e_out, e_side = left_wrist_frame()
    c0 = W - f * 0.030
    strap = hexlin(C_WATCH_STRAP); face = hexlin(C_WATCH_FACE)
    # silicone strap: a short wide band round the wrist
    rings = []
    for z_off in (-0.0105, -0.0070, 0.0070, 0.0105):
        r = 0.0292 - (0.0010 if abs(z_off) > 0.008 else 0.0)
        ring = []
        for k in range(28):
            ph = 2 * math.pi * k / 28
            d = e_out * math.cos(ph) + e_side * math.sin(ph) * 1.0
            ring.append(mb.vert(c0 + f * z_off + d * r, (strap[0], strap[1], strap[2], 1.0)))
        rings.append(ring)
    loft(mb, rings, mat=0, closed=True)
    # inner lining ring so the band has thickness from inside
    rings = []
    for z_off in (-0.0105, 0.0105):
        ring = []
        for k in range(28):
            ph = 2 * math.pi * k / 28
            d = e_out * math.cos(ph) + e_side * math.sin(ph)
            ring.append(mb.vert(c0 + f * z_off + d * 0.0255, (strap[0] * 0.85, strap[1] * 0.85, strap[2] * 0.85, 1.0)))
        rings.append(ring)
    loft(mb, rings, mat=0, closed=True)
    # rounded case on the back of the wrist
    ctr = c0 + e_out * 0.0285
    prof = [(0.0000, 0.0000), (0.0150, 0.0000), (0.0162, 0.0030), (0.0158, 0.0070), (0.0140, 0.0098), (0.0108, 0.0108), (0.0000, 0.0108)]
    rings = []
    for (r, h) in prof[1:-1]:
        ring = []
        for k in range(28):
            ph = 2 * math.pi * k / 28
            d = f * math.cos(ph) + e_side * math.sin(ph)
            ring.append(mb.vert(ctr + e_out * h + d * (r * (1.0 if True else 1.0)), (strap[0], strap[1], strap[2], 1.0)))
        rings.append(ring)
    loft(mb, rings, mat=0, closed=True)
    fan_cap(mb, rings[0], -e_out, 0, color=(strap[0], strap[1], strap[2], 1.0))
    # off-white face disc with a tiny dark indicator
    ring = []
    for k in range(28):
        ph = 2 * math.pi * k / 28
        d = f * math.cos(ph) + e_side * math.sin(ph)
        ring.append(mb.vert(ctr + e_out * 0.0110 + d * 0.0100, (face[0], face[1], face[2], 1.0)))
    fan_cap(mb, ring, e_out, 0, color=(face[0], face[1], face[2], 1.0))
    return mb.build('watch', [MAT['detail']], recalc=False)

# ============================================================================= ASSEMBLE
def transform_obj(obj, M): obj.data.transform(M)

def assemble():
    head = build_head()
    hair = build_hair()
    bun = build_bun()
    body = build_body()
    shirt = build_shirt()
    shorts = build_shorts()
    shoes = build_shoes()
    chain = build_chain()
    bracelet = build_bracelet()
    watch = build_watch()
    objs = {'Head': head, 'hair': hair, 'bun': bun, 'Body': body, 'shirt': shirt, 'shorts': shorts, 'shoes': shoes,
            'chain': chain, 'bracelet': bracelet, 'watch': watch}
    for n, o in objs.items():
        o.name = n; o.data.name = n

    PIVOT = Vector((0.0, 0.010, 1.360))
    R = Matrix.Translation(PIVOT) @ Matrix.Rotation(-math.radians(CHIN_RAISE_DEG), 4, 'X') @ Matrix.Translation(-PIVOT)
    ANCHOR = Vector((0.0, 0.010, 1.425))
    Sc = Matrix.Translation(ANCHOR) @ Matrix.Diagonal((HEAD_SCALE, HEAD_SCALE, HEAD_SCALE, 1.0)) @ Matrix.Translation(-ANCHOR)
    for n in ('Head', 'hair', 'bun'): transform_obj(objs[n], R @ Sc)

    zmax = max(v.co.z for n in ('hair', 'bun') for v in objs[n].data.vertices)
    zmin = min(v.co.z for o in objs.values() for v in o.data.vertices)
    k = TARGET_HEIGHT / (zmax - zmin)
    S = Matrix.Diagonal((k, k, k, 1.0))
    for o in objs.values(): transform_obj(o, S)
    PIVOT = PIVOT * k
    print('[build] height scale factor %.4f (raw height %.4f m)' % (k, zmax - zmin))

    transform_obj(objs['Head'], Matrix.Translation(-PIVOT))
    objs['Head'].location = PIVOT
    bpy.context.view_layer.update()
    inv = objs['Head'].matrix_world.inverted()
    for n in ('hair', 'bun'):
        objs[n].parent = objs['Head']; objs[n].matrix_parent_inverse = inv
    for o in objs.values(): o.data.update()
    return objs

# ============================================================================= EXPORT / STATS
def export_glb(objs):
    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs.values(): o.select_set(True)
    bpy.context.view_layer.objects.active = objs['Body']
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    want = dict(filepath=OUT_GLB, export_format='GLB', use_selection=True, export_apply=True, export_yup=True,
                export_texcoords=True, export_normals=True, export_materials='EXPORT', export_image_format='AUTO',
                export_cameras=False, export_lights=False, export_animations=False, export_extras=False,
                export_vertex_color='MATERIAL', export_active_vertex_color_when_no_material=False,
                export_all_vertex_colors=False)
    kw = {k_: v for k_, v in want.items() if k_ in props}
    bpy.ops.export_scene.gltf(**kw)
    print('[export] wrote', OUT_GLB, os.path.getsize(OUT_GLB) // 1024, 'KB')

def glb_report(path):
    with open(path, 'rb') as f:
        data = f.read()
    jl = struct.unpack('<I', data[12:16])[0]
    js = json.loads(data[20:20 + jl].decode())
    tris = 0
    for m in js['meshes']:
        for p in m['primitives']:
            if p.get('mode', 4) == 4:
                tris += js['accessors'][p['indices']]['count'] // 3
    names = [n['name'] for n in js['nodes']]
    hier = {n['name']: [js['nodes'][c]['name'] for c in n.get('children', [])] for n in js['nodes'] if n.get('children')}
    vc = sum(1 for m in js['meshes'] for p in m['primitives'] if 'COLOR_0' in p['attributes'])
    return dict(triangles=tris, nodes=names, hierarchy=hier, materials=[m['name'] for m in js['materials']],
                primitives_with_COLOR_0=vc, images=[(i.get('name'), i.get('mimeType')) for i in js.get('images', [])],
                double_sided=[m['name'] for m in js['materials'] if m.get('doubleSided')])

# ============================================================================= RENDER
def render_previews(objs, tag):
    os.makedirs(RENDER_DIR, exist_ok=True)
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    scn.cycles.device = 'CPU'; scn.cycles.samples = SAMPLES
    try: scn.cycles.use_denoising = True
    except Exception: pass
    scn.render.resolution_x = 640; scn.render.resolution_y = 960; scn.render.resolution_percentage = 100
    try: scn.view_settings.view_transform = 'Standard'
    except Exception: pass
    world = bpy.data.worlds.new('Studio'); world.use_nodes = True
    bg = world.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.215, 0.215, 0.215, 1); bg.inputs[1].default_value = 1.0
    scn.world = world
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    floor = bpy.context.active_object
    fm = bpy.data.materials.new('Floor'); fm.use_nodes = True
    fb = fm.node_tree.nodes['Principled BSDF']; fb.inputs['Base Color'].default_value = (0.215, 0.215, 0.215, 1); fb.inputs['Roughness'].default_value = 0.85
    floor.data.materials.append(fm)
    floor.is_shadow_catcher = True

    def look_at(obj, target):
        d = Vector(target) - obj.location
        obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    cam_d = bpy.data.cameras.new('Cam'); cam_d.lens = 85
    cam = bpy.data.objects.new('Cam', cam_d); scn.collection.objects.link(cam); scn.camera = cam
    lights = []
    for nm, size, energy in (('Key', 2.2, 215), ('Fill', 3.0, 90), ('Rim', 1.6, 190)):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.size = size; ld.energy = energy
        lo = bpy.data.objects.new(nm, ld); scn.collection.objects.link(lo); lights.append(lo)

    def place(az_deg, dist, target, elev=0.0, light_scale=1.0):
        az = math.radians(az_deg)
        cam.location = Vector((target[0] + math.sin(az) * dist, target[1] - math.cos(az) * dist, target[2] + elev))
        look_at(cam, target)
        def pos(off, d, h):
            a = math.radians(az_deg + off)
            return Vector((target[0] + math.sin(a) * d, target[1] - math.cos(a) * d, target[2] + h))
        specs = [(-42, 3.0, 1.2), (48, 3.2, 0.2), (170, 3.0, 1.1)]
        for lo, (off, d, h), base in zip(lights, specs, (215, 90, 190)):
            lo.location = pos(off, d * light_scale, h)
            look_at(lo, target)
            lo.data.energy = base * light_scale ** 2

    shots = [('front', 0, 4.6, (0, 0, 0.85), 0.0, 1.0), ('three_quarter_left', 40, 4.6, (0, 0, 0.85), 0.0, 1.0),
             ('side', 90, 4.6, (0, 0, 0.85), 0.0, 1.0), ('back', 180, 4.6, (0, 0, 0.85), 0.0, 1.0),
             ('head_front', 0, 1.25, (0, -0.02, 1.56), 0.0, 0.5), ('head_three_quarter', 35, 1.25, (0, -0.02, 1.56), 0.0, 0.5),
             ('head_back', 160, 1.25, (0, 0.0, 1.56), 0.0, 0.5),
             ('torso_three_quarter', 30, 2.6, (0, 0, 1.12), 0.0, 0.7), ('legs_three_quarter', 30, 2.6, (0, 0, 0.45), 0.0, 0.7),
             ('right_sleeve', -90, 2.0, (-0.2, 0, 1.15), 0.0, 0.6), ('left_wrist', 70, 1.3, (0.32, -0.04, 0.84), 0.0, 0.45),
             ('shoes', 35, 1.5, (0, -0.05, 0.14), 0.15, 0.45)]
    if isinstance(SHOTS, str):
        shots = [sh for sh in shots if sh[0] in SHOTS.split(',')]
    paths = []
    for name, az, dist, tgt, elev, ls in shots:
        place(az, dist, tgt, elev, ls)
        p = os.path.join(RENDER_DIR, '%s_%s.png' % (tag, name))
        scn.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p); print('[render]', p)
    if isinstance(SHOTS, str): return
    imgs = []
    for p in paths[:4]:
        im = bpy.data.images.load(p); w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4); imgs.append(a)
    sheet = np.concatenate(imgs, axis=1)
    sh, sw = sheet.shape[:2]
    out = bpy.data.images.new('sheet', sw, sh, alpha=False)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw = os.path.join(RENDER_DIR, '%s_sheet.png' % tag); out.file_format = 'PNG'; out.save()
    print('[render] contact sheet', out.filepath_raw)

# ============================================================================= MAIN
objs = assemble()
tot = 0
for n, o in objs.items():
    t = tri_count(o); tot += t
    print('[tris] %-9s %6d   verts %6d' % (n, t, len(o.data.vertices)))
print('[tris] TOTAL     %6d' % tot)
export_glb(objs)
rep = glb_report(OUT_GLB)
print('[glb]', json.dumps(rep, indent=1))
if DO_RENDER:
    render_previews(objs, TAG)
