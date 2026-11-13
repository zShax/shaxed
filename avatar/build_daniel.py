"""
Stylized 3D figurine of Daniel -> public/models/daniel-hero.glb

Run:   blender -b -P avatar/build_daniel.py
Opts:  blender -b -P avatar/build_daniel.py -- [--no-render] [--tag daniel] [--samples 48]

Coordinates while modelling: Blender, metres, Z up, figure faces -Y (the glTF exporter
converts this to Y-up / facing +Z).  The person's LEFT side is +X.
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
OUT_GLB = os.path.join(ROOT, 'public', 'models', 'daniel-hero.glb')
RENDER_DIR = os.path.join(HERE, 'renders')
TAG = arg('--tag', 'daniel')
SAMPLES = int(arg('--samples', 40))
DO_RENDER = not arg('--no-render', False)

TARGET_HEIGHT = 1.72
WEAVE_TILE = 0.16
CHIN_RAISE_DEG = -2.5      # chin slightly down (negative = down)
HEAD_ROLL_DEG = 6.0        # casual head tilt, baked into the mesh

# palette
C_SKIN = '#D6AC96'
C_LIP = '#B07068'
C_HAIR = '#675542'
C_HAIR_LT = '#968064'
C_BEARD = '#40372F'
C_BEARD_LT = '#70655C'
C_NAVY = '#3C4962'          # pinstripe blazer base (blue-grey)
C_PIN = '#7A87A2'           # pinstripe line
C_TROUSER = '#2D4873'       # denim
C_DENIM_SEAM = '#C98F4F'
C_SHIRT = '#D9E4EA'
C_PRINT = '#63BED1'
C_PRINT_DK = '#2B3845'
C_BUTTON = '#2F3745'
C_STITCH = '#9AA6BE'
C_ACCENT = '#8DB8E8'
C_SUEDE = '#F2EEE2'         # white dress shoes
C_LACE = '#A39B8A'
C_SOLE = '#BFB7A6'
C_GUN = '#2D3035'
C_SILVER = '#CDCED1'
C_LEG = '#D9B6A6'

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

def srgb8(h):
    h = h.lstrip('#'); return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])

def pinstripe_texture(n=512, period=64, width=5):
    """Blue-grey wool with light vertical pinstripes (image is sRGB-tagged, so write encoded values)."""
    base = srgb8(C_NAVY); line = srgb8(C_PIN)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    d = np.abs((x % period) - period / 2)                                # distance to the nearest stripe centre line
    m = np.clip((width / 2 + 0.8 - d) / 1.6, 0, 1)[..., None]            # soft-edged line
    h = (np.cos(2 * np.pi * x / 8) + np.cos(2 * np.pi * y / 8) + 0.8 * np.cos(2 * np.pi * (x + y) / 16)) / 2.8
    rng = np.random.RandomState(5)
    low = np.zeros((n, n))
    for _ in range(12):
        fx, fy = rng.randint(1, 9), rng.randint(1, 9)
        low += np.cos(2 * np.pi * (fx * x / n + fy * y / n) + rng.uniform(0, 6.28)) * rng.uniform(0.3, 1.0)
    low /= 12
    lum = (0.95 + 0.04 * h + 0.03 * low)[..., None]
    img = (base * (1 - m) + line * m) * lum
    return np.clip(img, 0, 1)

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

weave_base, weave_nrm = weave_textures()
IMG_WEAVE = make_image('weave_base', weave_base)
IMG_WEAVE_N = make_image('weave_normal', weave_nrm, nonColor=True)
IMG_PIN = make_image('pinstripe_base', pinstripe_texture())

MAT = {
    'skin': make_mat('Skin', vcol=True, rough=0.52, spec=0.45),
    'hair': make_mat('Hair', vcol=True, rough=0.55, spec=0.4),            # hair + beard: per-clump / per-vertex colours
    'cotton': make_mat('Denim', vcol=True, tex=IMG_WEAVE, nrm=IMG_WEAVE_N, rough=0.9, spec=0.3),
    'pin': make_mat('Pinstripe', tex=IMG_PIN, nrm=IMG_WEAVE_N, rough=0.9, spec=0.3),
    'shirt': make_mat('Tee', base=C_SHIRT, rough=0.8, spec=0.3),
    'detail': make_mat('Detail', vcol=True, rough=0.7, spec=0.35),
    'lens': make_mat('Lens', base='#EAF2FF', rough=0.03, alpha=0.07, spec=0.6),   # keeps the Head material slots stable
}

# ============================================================================= BODY PROPORTIONS
# Torso knot tables, rows: z, xc, yc, rx, ry   (blazer outer surface)
BLAZER_K = KnotProfile([        # stockier build: wider shoulders/waist, a soft belly
    (0.795, -0.008, -0.004, 0.186, 0.138),
    (0.86, -0.008, -0.006, 0.192, 0.146),
    (0.95, -0.006, -0.006, 0.188, 0.146),
    (1.02, -0.004, -0.004, 0.182, 0.138),
    (1.10, -0.002, 0.000, 0.184, 0.128),
    (1.20, 0.000, 0.003, 0.192, 0.120),
    (1.28, 0.000, 0.005, 0.198, 0.110),
    (1.31, 0.000, 0.006, 0.178, 0.103),
    (1.34, 0.000, 0.008, 0.148, 0.090),
    (1.365, 0.000, 0.010, 0.120, 0.078),
    (1.390, 0.000, 0.012, 0.082, 0.068),
    (1.405, 0.000, 0.012, 0.076, 0.066),
], smooth=6)

def blazer_ring(z): return BLAZER_K(z)
def shirt_ring(z):
    xc, yc, rx, ry = BLAZER_K(z); return xc, yc, rx - 0.012, ry - 0.011
def body_ring(z):
    xc, yc, rx, ry = BLAZER_K(z); return xc, yc, rx - 0.024, ry - 0.021

def gorge_x_old(z):
    if z >= 1.04:
        if z <= 1.34: return 0.003 + (z - 1.04) / 0.30 * 0.052
        return lerp(0.055, 0.053, clamp((z - 1.34) / 0.065, 0, 1))
    return 0.0

def gorge_x(z):
    """half-width of the V opening: the blazer hangs open, showing the tee underneath."""
    if z >= 0.96:
        if z <= 1.34: return 0.006 + (z - 0.96) / 0.38 * 0.074
        return lerp(0.080, 0.077, clamp((z - 1.34) / 0.065, 0, 1))
    return 0.0

def bl_surface(x, z, lift=0.0):
    xc, yc, rx, ry = BLAZER_K(z)
    t = clamp((x - xc) / rx, -0.995, 0.995)
    y = yc - ry * math.sqrt(1 - t * t)
    n = Vector(((x - xc) / rx ** 2, (y - yc) / ry ** 2, 0.0)).normalized()
    return Vector((x, y, z)) + n * lift, n

def sh_surface(x, z, lift=0.0):
    xc, yc, rx, ry = shirt_ring(min(z, 1.405))
    t = clamp((x - xc) / rx, -0.995, 0.995)
    y = yc - ry * math.sqrt(1 - t * t)
    n = Vector(((x - xc) / rx ** 2, (y - yc) / ry ** 2, 0.0)).normalized()
    return Vector((x, y, z)) + n * lift, n

# pose: weight on the figure's right leg (-X); left leg relaxed
SH = 0.006                         # shoulder tilt (left shoulder higher)
ARM = {
    +1: dict(S0=(0.164, 0.002, 1.268 + SH), S1=(0.190, 0.0, 1.232 + SH), E=(0.220, -0.012, 1.010 + SH * 0.5),
             W=(0.232, -0.088, 0.795)),
    -1: dict(S0=(-0.164, 0.002, 1.268 - SH), S1=(-0.190, 0.0, 1.232 - SH), E=(-0.219, -0.008, 1.012 - SH * 0.5),
             W=(-0.230, -0.070, 0.797)),
}
LEG = {
    +1: dict(H=(0.086, 0.002, 0.88), K=(0.100, -0.030, 0.47), A=(0.104, -0.044, 0.075), yaw=+0.16),
    -1: dict(H=(-0.092, 0.002, 0.89), K=(-0.100, -0.008, 0.47), A=(-0.104, -0.004, 0.075), yaw=-0.08),
}

parts = {}   # name -> object

# ============================================================================= HEAD
C = Vector((0.0, -0.004, 1.545))
HRX, HRY, HRZ = 0.0830, 0.1020, 0.1150     # broader face than Marius

def nose_disp(Z, X):
    zs = [-0.060, -0.052, -0.046, -0.038, -0.028, -0.014, 0.000, 0.016, 0.030]
    A = [0.0, 0.0105, 0.0225, 0.0255, 0.0220, 0.0150, 0.0092, 0.0045, 0.0]
    W = [0.0070, 0.0100, 0.0112, 0.0100, 0.0080, 0.0064, 0.0052, 0.0048, 0.005]
    a = float(np.interp(Z, zs, A)); w = float(np.interp(Z, zs, W))
    d = a * math.exp(-0.5 * (X / w) ** 2)
    d += 0.0095 * gauss(Z + 0.043, 0.0058) * gauss(X - 0.0138, 0.0055)       # alar wings
    d -= 0.0045 * gauss(Z + 0.053, 0.0030) * gauss(X - 0.0085, 0.0035)       # nostril underside
    return d

def head_point(d):
    x, y, z = d.x, d.y, d.z
    px, py, pz = HRX * x, HRY * y, HRZ * z
    u = z
    px *= 1 - 0.10 * smoothstep(-0.05, -0.95, u)                       # fuller jaw (less taper)
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
    grove = -0.0785 + 0.0040 * (X / 0.025) ** 2
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
    c = mixc(c, hexlin('#E5A793'), 0.20 * gauss(X - 0.042, 0.016) * gauss(Z + 0.040, 0.016) * front)
    c = mixc(c, hexlin('#C9977F'), 0.22 * gauss(X - 0.0335, 0.016) * gauss(Z - 0.002, 0.012) * front)
    # beard shadow on the skin under the beard (so no pink shows through)
    mm = smoothstep(-0.030, -0.045, Z) * smoothstep(0.075, 0.05, X)
    c = mixc(c, hexlin('#8C7A72'), 0.55 * mm * front)
    # lips
    lm = 1 - clamp(math.sqrt((X / 0.0255) ** 2 + ((Z + 0.0795) / 0.0165) ** 2), 0, 1)
    c = mixc(c, hexlin(C_LIP), 0.9 * smoothstep(0.0, 0.35, lm) * front)
    gm = gauss(Z - (-0.0785 + 0.0040 * (X / 0.025) ** 2), 0.0016) * smoothstep(0.029, 0.021, X)
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
    head_faces = [list(f.verts) for f in mb.bm.faces]                     # head surface only, outward winding
    head_vnorm = {v: v.normal.copy() for q in head_faces for v in q}
    bvh = BVHTree.FromBMesh(mb.bm)

    def hit(x, z):
        loc, nrm, idx, dist = bvh.ray_cast(Vector((x, C.y - 0.30, C.z + z)), Vector((0, 1, 0)), 0.6)
        return (loc, nrm) if loc is not None else None

    # ---- eyes ------------------------------------------------------------------------
    EYE_R = 0.0132
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
        uv_sphere(mb, E, EYE_R, mat=1, angles=ang, segs=16, colfn=eye_col)
        uv_sphere(mb, E, EYE_R * 1.075, mat=0, segs=16, colfn=lambda a, d: skin_c,
                  keep=lambda dv: dv.z > 0.44 and dv.y < 0.25)                 # upper lid
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
            vm[v.index] = mb.vert(epos(d), col('#D2A08C'))
        for f in g2.faces: mb.face([vm[v.index] for v in f.verts], None, 0)
        g2.free()
    # ---- eyebrows (dark strips lying on the skin) --------------------------------------
    for s in (+1, -1):
        nu, nvv = 16, 5
        grid = []
        for i in range(nu):
            t = i / (nu - 1)
            xc_ = lerp(0.013, 0.055, t)
            zc = 0.0246 + 0.0078 * math.sin(math.pi * t ** 0.85) - 0.0016 * t
            hh = (0.0031 * (1 - 0.5 * t ** 1.5) + 0.0008)
            row = []
            for j in range(nvv):
                v = j / (nvv - 1) * 2 - 1
                z_ = zc + v * hh
                lift = 0.0014 * (1 - abs(v) ** 2.2) * smoothstep(0.0, 0.08, t) * smoothstep(1.0, 0.9, t) + 0.0001
                h_ = hit(s * xc_, z_)
                row.append((h_[0] + h_[1] * lift, h_[1]) if h_ else None)
            grid.append(row)
        surf_patch(mb, grid, mat=2, color=col('#6A5242'))
    # ---- thin mouth line (closed, faintly smiling) ---------------------------------------
    nu = 18; grid = []
    for i in range(nu):
        t = i / (nu - 1); xx = lerp(-0.0245, 0.0245, t)
        zc = -0.0785 + 0.0042 * (xx / 0.0245) ** 2 - 0.0004
        row = []
        for sj in (-1, 0, 1):
            h_ = hit(xx, zc + sj * 0.0012 * (1 - 0.6 * abs(xx) / 0.0245))
            row.append((h_[0] + h_[1] * (0.00015 if sj == 0 else -0.0001), h_[1]) if h_ else None)
        grid.append(row)
    surf_patch(mb, grid, mat=1, color=col('#5F302D'))
    # ---- full beard: an offset skin of the lower-face faces, with a gap left for the mouth ---------
    def beard_mask(q):
        X = abs(q.x); Z = q.z
        zc = float(np.interp(X, [0.0, 0.028, 0.045, 0.060, 0.080], [-0.060, -0.058, -0.040, -0.020, -0.004]))
        m = smoothstep(zc + 0.014, zc - 0.018, Z)
        m *= smoothstep(0.040, 0.008, q.y)                                   # stop at the ears
        inz = smoothstep(-0.0770, -0.0795, Z) * smoothstep(-0.0895, -0.0870, Z)
        m *= 1.0 - inz * (1.0 - smoothstep(0.018, 0.030, X))                  # mouth opening
        return m

    bm_ = MB()
    bmask = {}; bnew = {}
    c_dark, c_lt, c_hair = hexlin(C_BEARD), hexlin(C_BEARD_LT), hexlin(C_HAIR)
    for v, n in head_vnorm.items():
        q = v.co - C
        m = beard_mask(q)
        bmask[v] = m
        X = abs(q.x); Z = q.z
        lift = (0.0050 + 0.0035 * smoothstep(-0.045, -0.090, Z) + 0.0050 * smoothstep(-0.092, -0.116, Z)
                + 0.0045 * gauss(Z + 0.066, 0.009) * smoothstep(0.034, 0.012, X))
        chinf = smoothstep(-0.088, -0.112, Z) * m * smoothstep(0.045, 0.015, X) * smoothstep(0.02, -0.02, q.y)
        pos = v.co + n * (lift * smoothstep(0.0, 0.85, m)) + Vector((0.0, -0.014 * chinf, -0.030 * chinf))
        n1 = math.sin(q.x * 310 + q.z * 70) * 0.5 + 0.5
        n2 = math.sin(q.z * 430 - q.x * 90 + 1.3) * 0.5 + 0.5
        n3 = math.sin(q.x * 95 + q.z * 160 + 0.6) * 0.5 + 0.5                       # broad patches
        t = clamp(0.25 * n1 + 0.30 * n2 + 0.45 * n3 + 0.30 * chinf - 0.12, 0, 1)
        c = mixc(c_dark, c_lt, t)
        c = mixc(c, c_hair, 0.55 * smoothstep(-0.074, -0.068, Z) * smoothstep(0.036, 0.016, X))   # warmer moustache
        under = v[mb.cl]                                                    # colour of the skin below
        c = mixc(under, c, smoothstep(0.05, 0.80, m))                       # soft fade into the skin at the beard edge
        bnew[v] = bm_.vert(pos, (c[0], c[1], c[2], 1.0))
    for q in head_faces:
        if any(bmask[v] > 0.004 for v in q) and sum(bmask[v] > 0.004 for v in q) >= 2:
            bm_.face([bnew[v] for v in q], None, 0)
    beard = bm_.build('Beard', [MAT['hair']], recalc=False)
    head = mb.build('Head', [MAT['skin'], MAT['detail'], MAT['hair'], MAT['lens']], recalc=False)
    return head, beard

# ============================================================================= HAIR
def skull_pt(psi, theta, off=0.0):
    cx = math.sin(psi) * math.cos(theta); cy = -math.cos(psi) * math.cos(theta); cz = math.sin(theta)
    return C + Vector((cx * (HRX + off), cy * (HRY + off), cz * (HRZ + off)))
def skull_n(p):
    q = p - C
    return Vector((q.x / HRX ** 2, q.y / HRY ** 2, q.z / HRZ ** 2)).normalized()

NECK_C = Vector((0.0, 0.012, 0.0))
def grow(p0, d0, length, steps, rng, steer_fn=None, steer=0.12, hull=0.010, wave=0.0, freq=2.0,
         curl=0.0, curl_start=0.55, curl_axis=None, neck_avoid=True):
    p = Vector(p0); d = Vector(d0).normalized(); pts = [p.copy()]
    ds = length / steps; ph = rng.uniform(0, 6.283)
    for i in range(steps):
        t = (i + 1) / steps
        if steer_fn: d = (d * (1 - steer) + steer_fn(p, t) * steer).normalized()
        if wave:
            side = d.cross(Vector((0, 0, 1)))
            if side.length < 1e-4: side = Vector((1, 0, 0))
            d = (d + side.normalized() * wave * math.cos(freq * 6.283 * t + ph)).normalized()
        if curl and t > curl_start:
            ax = Vector(curl_axis) if curl_axis is not None else d.cross(Vector((0, 0, 1)))
            if ax.length < 1e-4: ax = Vector((1, 0, 0))
            d = (Matrix.Rotation(curl / ((1 - curl_start) * steps), 3, ax.normalized()) @ d).normalized()
        p = p + d * ds
        q = p - C
        e = Vector((q.x / (HRX + hull), q.y / (HRY + hull), q.z / (HRZ + hull))); r = e.length
        if r < 1.0 and r > 1e-6:
            e = e / r; p = C + Vector((e.x * (HRX + hull), e.y * (HRY + hull), e.z * (HRZ + hull)))
        if neck_avoid and p.z < 1.47:
            dx, dy = p.x - NECK_C.x, p.y - NECK_C.y; rr = math.hypot(dx, dy)
            lim = 0.096 + 0.60 * max(0.0, 1.46 - p.z)          # long hair flares out and drapes over the shoulders
            if rr < lim and p.z < 1.47 and dy > -0.02:
                k = lim / max(rr, 1e-5); p.x = NECK_C.x + dx * k; p.y = NECK_C.y + dy * k
        pts.append(p.copy())
    return pts

HAIR_COL_FN = None
def clump(mb, pts, r0, rng, sides=6, tip=0.55):
    def rad(t):
        base = r0 * (1.0 - (1 - tip) * t ** 1.2) * (1 + 0.08 * math.sin(t * 9 + r0 * 900))
        return base * min(1.0, ((1 - t) / 0.14) ** 0.55 + 0.04) * (0.45 + 0.55 * smoothstep(0.0, 0.16, t))
    c = HAIR_COL_FN() if HAIR_COL_FN else col(C_HAIR)
    tube(mb, pts, rad, rad, sides=sides, mat=0, color=c, hint=(0, 0, 1), cap0=True, cap1=True)

def sp(psi, th, off=0.0):
    """point on the (offset) skull ellipsoid; theta may exceed 90 deg to continue over the crown to the back."""
    cx = math.sin(psi) * math.cos(th); cy = -math.cos(psi) * math.cos(th); cz = math.sin(th)
    return C + Vector((cx * (HRX + off), cy * (HRY + off), cz * (HRZ + off)))

def comb(mb, rng, psi0, th0, th1, dpsi, hfn, r0, n=9, wave=0.10, freq=1.5, tail=None, tip=0.55):
    """A chunky clump combed along the skull from (psi0,th0) to theta th1, optional free tail that curls."""
    ph = rng.uniform(0, 6.283)
    pts = []
    for i in range(n + 1):
        s = i / n
        th = lerp(th0, th1, s)
        psi = psi0 + dpsi * s + wave * math.sin(freq * 6.283 * s + ph)
        pts.append(sp(psi, th, hfn(s) + 0.0050 * math.sin(freq * 9.0 * s + ph)))
    if tail:
        d = (pts[-1] - pts[-2]).normalized()
        nrm = skull_n(pts[-1])
        ax = d.cross(nrm)
        if ax.length < 1e-4: ax = Vector((1, 0, 0))
        ext = grow(pts[-1], d, tail['length'], tail['steps'], rng, steer_fn=tail.get('steer'), steer=tail.get('steer_k', 0.12),
                   hull=tail.get('hull', 0.012), wave=tail.get('wave', 0.10), curl=tail.get('curl', 0.0), curl_start=0.25,
                   curl_axis=tail.get('axis', ax))
        pts += ext[1:]
    clump(mb, pts, r0, rng, tip=tip)

def build_hair():
    """Long, swept-back, wavy light-brown hair that falls to the shoulders (soft mullet-ish back)."""
    global HAIR_COL_FN
    rng = random.Random(23)
    mb = MB()
    PART = math.radians(10)
    DOWNBACK = Vector((0, 0.20, -0.98)).normalized()
    d2r = math.radians
    c_lo, c_hi = hexlin(C_HAIR), hexlin(C_HAIR_LT)
    def hc():
        t = clamp(0.12 + 0.55 * rng.random(), 0, 1)
        c = mixc(c_lo, c_hi, t); k = rng.uniform(0.92, 1.04)
        return (c[0] * k, c[1] * k, c[2] * k, 1.0)
    HAIR_COL_FN = hc
    cap_col = mixc(c_lo, (0, 0, 0), 0.25)

    # ---- scalp cap under the clumps (no bald spots); high forehead / receding temples ---------
    def hairline(psi):
        a = abs(math.degrees(psi))
        return float(np.interp(a, [0, 40, 62, 80, 98, 118, 140, 180], [0.066, 0.063, 0.052, 0.026, 0.004, -0.030, -0.068, -0.075]))
    g = bmesh.new(); bmesh.ops.create_cube(g, size=2.0)
    bmesh.ops.subdivide_edges(g, edges=g.edges[:], cuts=17, use_grid_fill=True); g.verts.index_update()
    vm = {}
    for v in g.verts:
        x, y, z = v.co
        d = Vector((x * math.sqrt(max(0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                    y * math.sqrt(max(0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                    z * math.sqrt(max(0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
        off = 0.0060
        vm[v.index] = (mb.vert(C + Vector((d.x * (HRX + off), d.y * (HRY + off), d.z * (HRZ + off))),
                               (cap_col[0], cap_col[1], cap_col[2], 1.0)), d)
    for f in g.faces:
        vs = [vm[v.index][0] for v in f.verts]
        cen = sum((vm[v.index][1] for v in f.verts), Vector()) / 4
        psi = math.atan2(cen.x, -cen.y)
        if cen.z * HRZ > hairline(psi) + 0.003: mb.face(vs, None, 0)
    g.free()
    bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces[:])

    # ---- 1) front: lifts off the hairline, sweeps back over the crown and falls down the back -----
    for psi_d in np.linspace(-62, 62, 13):
        psi0 = d2r(psi_d + rng.uniform(-2.5, 2.5))
        th0 = math.asin(clamp((hairline(psi0) + 0.000 + rng.uniform(-0.004, 0.006)) / HRZ, -0.9, 0.9))
        centre = 1 - 0.45 * abs(psi_d) / 62
        amp = rng.uniform(0.022, 0.034) * centre + 0.008
        hf = lambda s, amp=amp: 0.006 + amp * smoothstep(0, 0.22, s) * (1 - 0.35 * smoothstep(0.50, 1.0, s))
        dpsi = (psi0 - PART) * 0.18
        th1 = d2r(rng.uniform(128, 146)) if abs(psi_d) < 40 else d2r(rng.uniform(104, 124))
        tail = dict(length=rng.uniform(0.07, 0.11), steps=6, curl=rng.uniform(0.3, 1.0), hull=hf(1.0) + 0.004, wave=0.08,
                    steer=lambda p, t: DOWNBACK, steer_k=0.26)
        comb(mb, rng, psi0, th0, th1, dpsi, hf, rng.uniform(0.0150, 0.0185), n=8, wave=0.10, freq=rng.uniform(1.4, 2.4), tail=tail)

    # ---- 2) crown / top volume, flowing back -------------------------------------------------------
    for k in range(9):
        psi0 = d2r(rng.uniform(-34, 34)); th0 = d2r(rng.uniform(58, 72)); th1 = d2r(rng.uniform(112, 130))
        hf = lambda s: 0.020 + 0.016 * math.sin(math.pi * min(1, s * 1.1))
        tail = dict(length=rng.uniform(0.08, 0.12), steps=6, curl=rng.uniform(0.2, 0.9), hull=0.020, wave=0.10,
                    steer=lambda p, t: DOWNBACK, steer_k=0.26)
        comb(mb, rng, psi0, th0, th1, 0.0, hf, rng.uniform(0.0165, 0.0195), n=7, wave=0.06, tail=tail)
    for sgn in (+1, -1):          # upper sides sweeping round to the back
        for k in range(6):
            psi0 = d2r(rng.uniform(34, 92)) * sgn; th0 = d2r(rng.uniform(44, 66)); th1 = th0 - d2r(rng.uniform(0, 14))
            hf = lambda s: 0.012 + 0.012 * math.sin(math.pi * min(1, s * 1.1))
            tail = dict(length=rng.uniform(0.07, 0.11), steps=6, curl=rng.uniform(0.2, 0.9), hull=0.020, wave=0.10,
                        steer=lambda p, t: DOWNBACK, steer_k=0.26)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(rng.uniform(32, 52)), hf, rng.uniform(0.0155, 0.0185), n=7, wave=0.06, tail=tail)

    # ---- 3) long sides: cover the ears and fall past the jaw to the shoulders ----------------------
    for sgn in (+1, -1):
        for k in range(11):
            psi0 = d2r(rng.uniform(58, 102)) * sgn; th0 = d2r(rng.uniform(28, 58)); th1 = d2r(rng.uniform(-22, -6))
            hf = lambda s: 0.013 + 0.009 * math.sin(math.pi * s)
            tail = dict(length=rng.uniform(0.08, 0.125), steps=7, curl=rng.uniform(0.1, 0.6), hull=0.020, wave=0.09,
                        steer=lambda p, t: DOWNBACK, steer_k=0.28)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(rng.uniform(6, 22)), hf, rng.uniform(0.0150, 0.0185), n=8, wave=0.05, tail=tail)
        for k in range(3):        # temples
            psi0 = d2r(rng.uniform(58, 70)) * sgn; th0 = d2r(rng.uniform(22, 28)); th1 = d2r(rng.uniform(4, 10))
            hf = lambda s: 0.009 + 0.006 * math.sin(math.pi * s)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(6), hf, 0.0115, n=6, wave=0.03, tail=None, tip=0.45)

    # ---- 4) back: the longest part, curling over the collar -----------------------------------------
    for k in range(28):
        psi0 = d2r(rng.uniform(112, 248)); th0 = d2r(rng.uniform(22, 62)); th1 = d2r(rng.uniform(-38, -20))
        hf = lambda s: 0.011 + 0.008 * math.sin(math.pi * s)
        L = rng.uniform(0.090, 0.140) if th0 < d2r(44) else rng.uniform(0.060, 0.100)
        tail = dict(length=L, steps=8, curl=rng.uniform(0.3, 1.3), hull=0.018, wave=0.10,
                    steer=lambda p, t: DOWNBACK, steer_k=0.28, axis=Vector((rng.uniform(-0.7, 0.7), 1.0, rng.uniform(-0.2, 0.3))))
        comb(mb, rng, psi0, th0, th1, 0.0, hf, rng.uniform(0.0150, 0.0185), n=9, wave=0.05, tail=tail)
    HAIR_COL_FN = None
    return mb.build('Hair', [MAT['hair']], recalc=False)

# ============================================================================= BODY (skin)
def hand_geometry(mb, side, M):
    """Mitten-like, slightly curled hand. Local: wrist cuff plane at origin, fingers along -Z, palm faces medially."""
    mb.M = M
    m = -side                       # medial x direction
    sk = col(C_SKIN)
    # palm + back of hand
    palm = [Vector((0, 0.0, 0.032)), Vector((0, 0.0, 0.0)), Vector((0.0, 0.0, -0.045)), Vector((0, 0.0, -0.092))]
    tube(mb, catmull(palm, 4), [0.0300, 0.0300, 0.0420, 0.0405], [0.0140, 0.0150, 0.0165, 0.0135], sides=12,
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
        if False:   # no ring on Daniel
            ring_path = (p0 + (p1 - p0) * 0.55, d1, r)
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

def build_body():
    mb = MB()
    sk = col(C_SKIN)
    # inner torso (hidden by shirt)
    rings = []
    zs = np.linspace(0.90, 1.36, 8)
    for z in zs:
        xc, yc, rx, ry = body_ring(z)
        ring = [mb.vert((xc - rx * math.sin(2 * math.pi * j / 20), yc + ry * math.cos(2 * math.pi * j / 20), z), sk) for j in range(20)]
        rings.append(ring)
    ring_loft(mb, rings, True, True, True, 0)
    # neck
    tube(mb, [(0, 0.014, 1.30), (0, 0.010, 1.38), (0, 0.003, 1.48)], [0.0620, 0.0590, 0.0560], [0.0580, 0.0560, 0.0540],
         sides=14, mat=0, color=sk, hint=(0, -1, 0))
    # bare lower legs (cropped jeans, no socks)
    for s in (+1, -1):
        A = Vector(LEG[s]['A'])
        pts = [leg_point(s, z) for z in (0.085, 0.17, 0.26, 0.34)]
        pts[0] = Vector((A.x, A.y - 0.002, 0.085))
        tube(mb, pts, [0.0360, 0.0385, 0.0465, 0.0515], [0.0340, 0.0365, 0.0430, 0.0480], sides=12, mat=0,
             color=col(C_LEG), hint=(0, -1, 0), cap0=True, cap1=True)
    # arms (inside sleeves) + hands
    for s in (+1, -1):
        a = ARM[s]
        S1, E, W = Vector(a['S1']), Vector(a['E']), Vector(a['W'])
        f = (W - E).normalized()
        path = catmull([S1, E, W + f * 0.03], 4)
        tube(mb, path, [0.044, 0.038, 0.031, 0.0285], [0.044, 0.038, 0.031, 0.0230], sides=10, mat=0, color=sk, hint=(0, -1, 0))
        # hand frame: local -Z -> forearm direction
        R = Vector((0, 0, -1)).rotation_difference(f).to_matrix().to_4x4()
        M = Matrix.Translation(W) @ R
        hand_geometry(mb, s, M)
    return mb.build('Body', [MAT['skin'], MAT['detail']], recalc=True)

# ============================================================================= BLAZER
def sleeve_path(s):
    a = ARM[s]
    return catmull([a['S0'], a['S1'], a['E'], a['W']], 5)

def build_blazer():
    mb = MB()
    tile = WEAVE_TILE
    navy = (1.0, 1.0, 1.0, 1.0)      # colour comes from the pinstripe texture
    # ---- torso shell (open at the V, cut-away below the buttons) -----------------------
    zs = np.concatenate([np.linspace(0.795, 1.30, 17), np.linspace(1.315, 1.405, 9)])
    M_ = 40
    rings = []; phis = []
    for z in zs:
        xc, yc, rx, ry = blazer_ring(z)
        gx = gorge_x(z)
        alpha = math.asin(clamp(gx / rx, 0, 0.999))
        span = math.pi - alpha
        ring = []; ph = []
        for k in range(M_):
            phi = -span + 2 * span * k / (M_ - 1)
            ring.append(mb.vert((xc - rx * math.sin(phi), yc + ry * math.cos(phi), z), navy))
            ph.append(phi)
        rings.append(ring); phis.append(ph)
    ring_loft(mb, rings, closed=False, mat=0, uvf=lambda i, j: (-phis[i][min(j, M_ - 1)] * 0.19 / tile, zs[i] / tile))
    # ---- sleeves ----------------------------------------------------------------------
    for s in (+1, -1):
        path = sleeve_path(s)
        tube(mb, path, [0.036, 0.049, 0.0505, 0.0485, 0.0455, 0.0435], [0.036, 0.048, 0.0495, 0.0475, 0.0445, 0.0420],
             sides=14, mat=0, color=navy, hint=(0, -1, 0), cap0=True, cap1=False, uvtile=tile)
    # ---- folds: a few large, well placed ------------------------------------------------
    folds = [((0.02, -0.118, 1.01), (-0.075, -0.124, 0.88), 0.020, 0.0030),      # button -> weight-side hip
             ((0.04, -0.12, 0.93), (0.13, -0.10, 0.84), 0.022, -0.0022)]
    for s in (+1, -1):
        a = ARM[s]; E = Vector(a['E']); W = Vector(a['W'])
        fz = E.z
        folds += [((E.x - s * 0.06, E.y - 0.05, fz + 0.045), (E.x + s * 0.06, E.y - 0.05, fz + 0.045), 0.012, 0.0035),
                  ((E.x - s * 0.06, E.y - 0.05, fz + 0.005), (E.x + s * 0.06, E.y - 0.05, fz + 0.005), 0.010, -0.0030),
                  ((E.x - s * 0.06, E.y - 0.05, fz - 0.040), (E.x + s * 0.06, E.y - 0.05, fz - 0.040), 0.012, 0.0030),
                  ((W.x - s * 0.05, W.y - 0.02, W.z + 0.07), (W.x + s * 0.05, W.y - 0.02, W.z + 0.07), 0.012, 0.0020)]
    fold_displace(mb.bm, folds)
    bmesh.ops.remove_doubles(mb.bm, verts=mb.bm.verts[:], dist=2e-5)
    # check winding (torso should face outward)
    mb.bm.normal_update()
    bad = 0; tot = 0
    for f in mb.bm.faces:
        c = f.calc_center_median()
        radial = Vector((c.x, c.y - 0.0, 0)).normalized()
        if c.z < 1.35 and abs(c.x) < 0.14:
            tot += 1; bad += 1 if f.normal.dot(radial) < 0 else 0
    if tot and bad > tot / 2:
        bmesh.ops.reverse_faces(mb.bm, faces=mb.bm.faces[:])
    shell = mb.build('BlazerShell', [MAT['pin'], MAT['detail']], recalc=False)
    solidify(shell, 0.0055, -1.0)

    # ---- details on top of the shell ------------------------------------------------------
    d = MB.from_mesh(shell.data)
    bpy.data.objects.remove(shell)
    cotton_uv = lambda p: (p.x / tile + p.y * 0.3 / tile, p.z / tile)

    # notch lapels
    outer = [(1.040, 0.004), (1.080, 0.040), (1.130, 0.071), (1.190, 0.096), (1.250, 0.112), (1.296, 0.118),
             (1.310, 0.113), (1.322, 0.101), (1.340, 0.093), (1.370, 0.077), (1.398, 0.061)]
    # the blazer hangs open further than Marius's: shift the lapel edge by the extra gorge width
    oz = [0.96] + [o[0] for o in outer]
    ox = [gorge_x(0.96) + 0.002] + [o[1] + gorge_x(o[0]) - gorge_x_old(o[0]) for o in outer]
    lap_zs = np.concatenate([np.linspace(0.97, 1.30, 24), np.linspace(1.31, 1.398, 9)])
    for s in (+1, -1):
        grid = []
        for z in lap_zs:
            xi = gorge_x(z) + 0.0008
            xo = float(np.interp(z, oz, ox))
            xo = max(xo, xi + 0.004)
            row = []
            for sj in np.linspace(0, 1, 6):
                x = lerp(xi, xo, sj)
                lift = 0.0036 + 0.0085 * (1 - sj) ** 1.6
                p, n = bl_surface(s * x, z, lift)
                row.append((p, n))
            grid.append(row)
        surf_patch(d, grid, mat=0, color=navy, uvfn=cotton_uv)
        # underside closing strip along the gorge to hide the gap
    # contrast stitching along the lapel edge
    for s in (+1, -1):
        zz = 1.065; seg = 0.0046; gap = 0.0030
        pts = []
        z = 1.00
        while z < 1.385:
            xo = float(np.interp(z, oz, ox)) - 0.0042
            pts.append((z, max(xo, gorge_x(z) + 0.006)))
            z += 0.004
        for i in range(0, len(pts) - 2, 2):
            (za, xa), (zb, xb) = pts[i], pts[i + 1]
            quad = []
            for (zq, xq) in ((za, xa), (zb, xb)):
                for w in (-0.00055, 0.00055):
                    p, n = bl_surface(s * (xq + w), zq, 0.0036 + 0.0085 * 0.07 + 0.0007)
                    quad.append((p, n))
            grid = [[quad[0], quad[1]], [quad[2], quad[3]]]
            surf_patch(d, grid, mat=1, color=col(C_STITCH))
    # welt (chest) pocket on the figure's left
    def raised_rect(x0, z0, w, h, tilt, lift, lift_low=None, mat=0, colr=navy, sf=bl_surface, nx=9, ny=4):
        grid = []
        ct, st = math.cos(tilt), math.sin(tilt)
        for i in range(ny):
            vv = i / (ny - 1) * 2 - 1
            row = []
            for j in range(nx):
                uu = j / (nx - 1) * 2 - 1
                lx, lz = uu * w / 2, vv * h / 2
                x = x0 + lx * ct - lz * st; z = z0 + lx * st + lz * ct
                edge = min(1 - abs(uu), 1 - abs(vv))
                l = lift * smoothstep(0.0, 0.16, edge)
                if lift_low is not None: l += lift_low * smoothstep(0.3, -1.0, vv) * smoothstep(0.0, 0.16, edge)
                p, n = sf(x, z, l + 0.0003)
                row.append((p, n))
            grid.append(row)
        surf_patch(d, grid, mat=mat, color=colr, uvfn=cotton_uv)
    raised_rect(0.128, 1.200, 0.100, 0.015, math.radians(5), 0.0026)
    # flap hip pockets
    for s in (+1, -1):
        raised_rect(s * 0.125 + (-0.006), 0.862, 0.150, 0.046, math.radians(-3 * s), 0.0034, lift_low=0.0018)
    # front buttons (2) and cuff buttons (3-4 each)
    def button(center, nrm, r, h, color):
        ax = nrm.normalized()
        tube(d, [center - ax * 0.001, center + ax * h], r, r, sides=12, mat=1, color=color, hint=(0, 0, 1), cap0=True, cap1=True)
    for z in (0.925,):               # single button, left undone above it
        p, n = bl_surface(0.0, z, 0.0004)
        button(p, n, 0.0098, 0.0042, col(C_BUTTON))
        button(p, n, 0.0030, 0.0053, col('#262E3B'))
    for s in (+1, -1):
        path = sleeve_path(s)
        for k in range(4):
            idx = len(path) - 1 - 2 - k * 2
            # position on the outer-rear side of the sleeve
            p = path[idx]; t = (path[idx + 1] - path[idx - 1]).normalized()
            out = Vector((s, 0.25, 0)); out = (out - t * out.dot(t)).normalized()
            rr = 0.0415 - 0.0012 * (len(path) - 1 - idx) / 2
            button(p + out * (rr + 0.0003), out, 0.0052, 0.0030, col(C_BUTTON))
    blazer = d.build('Blazer', [MAT['pin'], MAT['detail']], recalc=False)
    return blazer

# ============================================================================= SHIRT (graphic tee)
def build_shirt():
    mb = MB()
    white = col(C_SHIRT)
    zs = np.concatenate([np.linspace(0.84, 1.30, 14), np.linspace(1.315, 1.40, 6)])
    rings = []
    for z in zs:
        xc, yc, rx, ry = shirt_ring(z)
        hang = 0.009 * (1 - smoothstep(0.96, 1.12, z))          # hangs loose over the jeans
        rings.append([mb.vert((xc - (rx + hang) * math.sin(2 * math.pi * j / 28),
                               yc + (ry + hang) * math.cos(2 * math.pi * j / 28), z), white) for j in range(28)])
    ring_loft(mb, rings, True, True, False, 0)
    # crew-neck rib band around the neck
    cz = [1.376, 1.388, 1.398, 1.405]
    rr = [0.0690, 0.0655, 0.0630, 0.0630]
    rings = []
    for z, r in zip(cz, rr):
        rings.append([mb.vert((0 - r * math.sin(2 * math.pi * j / 26), 0.010 + (r - 0.001) * math.cos(2 * math.pi * j / 26), z),
                              col('#D3DBE0')) for j in range(26)])
    ring_loft(mb, rings, True, True, True, 0)
    # chest print: teal scene with dark band, sun and a white stripe (vertex-coloured patch)
    pw, ph = 0.104, 0.130
    z0 = 1.150
    nx, nz = 14, 18
    grid = []; cgrid = []
    teal = hexlin(C_PRINT); dark = hexlin(C_PRINT_DK); wht = hexlin('#F2F7F8'); mid = hexlin('#3E8FA6')
    for i in range(nz):
        v = i / (nz - 1)                       # 0 bottom -> 1 top
        z = z0 + (v - 0.5) * ph
        row = []; crow = []
        for j in range(nx):
            u = j / (nx - 1) * 2 - 1           # -1..1
            x = u * pw / 2
            p, n = sh_surface(x, z, 0.0016 + 0.0006 * math.sin(math.pi * v) * math.sin(math.pi * (u + 1) / 2))
            row.append((p, n))
            c = teal
            if v < 0.22: c = dark                                           # dark foreground band
            elif v < 0.36: c = mid
            if (u + 0.45) ** 2 * 0.9 + ((v - 0.70) * 1.5) ** 2 < 0.045: c = wht   # sun / moon
            if abs((u * 0.55 + 0.1) - (v - 0.45) * 0.9) < 0.05 and 0.3 < v < 0.95: c = wht   # diagonal stripe
            crow.append((c[0], c[1], c[2], 1.0))
        grid.append(row); cgrid.append(crow)
    surf_patch(mb, grid, mat=1, colorgrid=cgrid)
    return mb.build('Shirt', [MAT['shirt'], MAT['detail']], recalc=False)

# ============================================================================= JEANS
HEM_Z = 0.27
def leg_point(s, z):
    L = LEG[s]; K = Vector(L['K']); A = Vector(L['A'])
    return K + (A - K) * ((K.z - z) / (K.z - A.z))

def leg_path(s):
    L = LEG[s]
    return catmull([L['H'], L['K'], leg_point(s, 0.36), leg_point(s, HEM_Z)], 6)

def build_trousers():
    """Loose mid-blue denim, cropped to the calf with a stitched hem."""
    mb = MB()
    tile = WEAVE_TILE
    dark = col(C_TROUSER)
    # pelvis / waist (top hidden under the tee)
    zs = np.linspace(0.93, 0.775, 7)
    rings = []
    for z in zs:
        xc, yc, rx, ry = shirt_ring(min(max(z, 0.955), 1.4))
        sh = 1.0 - 0.40 * smoothstep(0.93, 0.79, z)
        shy = 1.0 - 0.30 * smoothstep(0.92, 0.77, z)
        rings.append([mb.vert((xc - (rx + 0.004) * sh * math.sin(2 * math.pi * j / 28), yc + (ry + 0.004) * shy * math.cos(2 * math.pi * j / 28), z), dark) for j in range(28)])
    ring_loft(mb, rings, True, True, True, 0, uvpos=lambda p: (p.x / tile + p.y * 0.3 / tile, p.z / tile))
    for s in (+1, -1):
        path = leg_path(s)
        rings = tube(mb, path, [0.086, 0.094, 0.083, 0.073, 0.068, 0.069], [0.080, 0.086, 0.075, 0.066, 0.061, 0.062],
                     sides=18, mat=0, color=dark, hint=(0, -1, 0), cap0=True, cap1=True, uvtile=tile)
        # hem top-stitching: a thin tan loop just above the hem edge
        last, prev = rings[-1], rings[-2]
        cen = sum((v.co for v in last), Vector()) / len(last)
        loop = []
        for vl, vp in zip(last, prev):
            p = vl.co.lerp(vp.co, 0.28)
            out = Vector((p.x - cen.x, p.y - cen.y, 0.0)).normalized()
            loop.append(p + out * 0.0012)
        loop.append(loop[0])
        tube(mb, loop, 0.0012, 0.0012, sides=5, mat=0, color=col(C_DENIM_SEAM), hint=(0, 0, 1), cap0=False, cap1=False)
    folds = []
    for s in (+1, -1):
        L = LEG[s]; K = Vector(L['K'])
        for zz, am in ((0.34, 0.0035), (0.305, 0.0030)):
            P = leg_point(s, zz)
            folds.append(((P.x - s * 0.08, P.y - 0.07, zz), (P.x + s * 0.08, P.y - 0.07, zz), 0.0085, am))
        folds.append(((K.x - 0.05, K.y - 0.08, K.z + 0.02), (K.x + 0.05, K.y - 0.08, K.z + 0.02), 0.016, 0.0030 if s > 0 else 0.0012))
        folds.append(((K.x - 0.05, K.y - 0.08, K.z - 0.07), (K.x + 0.05, K.y - 0.08, K.z - 0.07), 0.016, 0.0020 if s > 0 else 0.0008))
    fold_displace(mb.bm, folds)
    return mb.build('Trousers', [MAT['cotton']], recalc=True)

# ============================================================================= SHOES (white lace-up dress shoes, block heel)
SHOE_Y = [0.080, 0.072, 0.056, 0.030, 0.000, -0.040, -0.080, -0.120, -0.165, -0.200, -0.232, -0.246]
SHOE_W = [0.020, 0.032, 0.038, 0.040, 0.041, 0.044, 0.046, 0.045, 0.040, 0.032, 0.020, 0.006]
SHOE_T = [0.060, 0.092, 0.104, 0.100, 0.092, 0.083, 0.072, 0.060, 0.050, 0.042, 0.034, 0.024]
SHOE_B = [0.034, 0.028, 0.022, 0.014, 0.012, 0.008, 0.004, 0.003, 0.004, 0.006, 0.010, 0.016]

def shoe_ring(y, a, zb, zt, p=2.8, S=18, ofs=0.0):
    cz = (zt + zb) / 2; b = max((zt - zb) / 2, 0.0008); a = max(a, 0.0008)
    out = []
    for j in range(S):
        th = 2 * math.pi * j / S
        c, s_ = math.cos(th), math.sin(th)
        out.append(Vector((a * sgnpow(c, 2 / p), y, cz + b * sgnpow(s_, 2 / p))))
    return out

def build_shoes():
    mb = MB()
    cream = col(C_SUEDE)
    for s in (+1, -1):
        L = LEG[s]
        M = Matrix.Translation((L['A'][0], L['A'][1], 0.0)) @ Matrix.Rotation(L['yaw'], 4, 'Z')
        mb.M = M
        rings = []
        for k in range(len(SHOE_Y)):
            rings.append([mb.vert(p, cream) for p in shoe_ring(SHOE_Y[k], SHOE_W[k], SHOE_B[k] + 0.008, SHOE_T[k])])
        ring_loft(mb, rings, True, True, True, 0)
        # thin sole (slightly wider than the upper)
        rings = []
        for k in range(len(SHOE_Y)):
            rings.append([mb.vert(p, col(C_SOLE)) for p in shoe_ring(SHOE_Y[k], SHOE_W[k] * 1.04 + 0.001, SHOE_B[k], SHOE_B[k] + 0.012, p=4.0)])
        ring_loft(mb, rings, True, True, True, 0)
        # block heel
        tube(mb, [Vector((0, 0.052, 0.0)), Vector((0, 0.052, 0.038))], [0.0300, 0.0275], [0.0265, 0.0245], sides=16, mat=0,
             color=col(C_SOLE), hint=(0, -1, 0), cap0=True, cap1=False, power=2.6)
        # laces across the vamp
        for yl in (-0.036, -0.058, -0.080, -0.102):
            a = float(np.interp(-yl, [-x for x in SHOE_Y][::-1], SHOE_W[::-1]))
            zt = float(np.interp(-yl, [-x for x in SHOE_Y][::-1], SHOE_T[::-1]))
            zb = float(np.interp(-yl, [-x for x in SHOE_Y][::-1], SHOE_B[::-1])) + 0.008
            cz = (zt + zb) / 2; b = (zt - zb) / 2
            path = []
            for u in np.linspace(-0.55, 0.55, 7):
                x = a * u
                z = cz + b * (max(0.0, 1 - abs(u) ** 2.8)) ** (1 / 2.8) + 0.0012
                path.append(Vector((x, yl, z)))
            tube(mb, path, 0.0026, 0.0026, sides=6, mat=0, color=col(C_LACE), hint=(0, 1, 0), cap0=True, cap1=True)
        def upper(yq, u):
            a = float(np.interp(-yq, [-x for x in SHOE_Y][::-1], SHOE_W[::-1]))
            zt = float(np.interp(-yq, [-x for x in SHOE_Y][::-1], SHOE_T[::-1]))
            zb = float(np.interp(-yq, [-x for x in SHOE_Y][::-1], SHOE_B[::-1])) + 0.008
            cz = (zt + zb) / 2; b = (zt - zb) / 2
            return Vector((a * u, yq, cz + b * (max(0.0, 1 - abs(u) ** 2.8)) ** (1 / 2.8)))
        seam = [upper(-0.175, u) + Vector((0, 0, 0.0009)) for u in np.linspace(-0.9, 0.9, 9)]
        tube(mb, seam, 0.0015, 0.0015, sides=5, mat=0, color=col('#CFC8B8'), hint=(0, 1, 0))
        k0 = upper(-0.026, 0.0) + Vector((0, 0, 0.0026))
        for sx in (+1, -1):
            loop = [k0, k0 + Vector((sx * 0.007, -0.003, 0.0045)), k0 + Vector((sx * 0.015, -0.002, 0.0020)), k0 + Vector((sx * 0.017, 0.004, -0.0010))]
            tube(mb, catmull(loop, 3), 0.0021, 0.0021, sides=5, mat=0, color=col(C_LACE), hint=(0, 0, 1))
        # collar: a rolled cream rim following the topline where the ankle enters the shoe
        ys = [-x for x in SHOE_Y][::-1]; ts = SHOE_T[::-1]
        loop = []
        for j in range(20):
            th = 2 * math.pi * j / 20
            xl, yl = 0.0405 * math.cos(th), 0.0395 * math.sin(th) - 0.002
            zl = float(np.interp(-yl, ys, ts)) + 0.001
            loop.append(Vector((xl, yl, zl)))
        loop.append(loop[0])
        tube(mb, loop, 0.0050, 0.0050, sides=6, mat=0, color=cream, hint=(0, 0, 1), cap0=False, cap1=False)
        mb.M = None
    return mb.build('Shoes', [MAT['detail']], recalc=True)

# ============================================================================= ASSEMBLE
def transform_obj(obj, M): obj.data.transform(M)

def assemble():
    head, beard = build_head()
    hair = build_hair()
    body = build_body()
    blazer = build_blazer()
    shirt = build_shirt()
    trousers = build_trousers()
    shoes = build_shoes()
    objs = dict(Head=head, Hair=hair, Beard=beard, Body=body, Blazer=blazer, Shirt=shirt,
                Trousers=trousers, Shoes=shoes)
    HEAD_PARTS = ('Head', 'Hair', 'Beard')

    DZ = 0.07                                   # leg shortening
    def warp_z(z):
        if z <= 0.12: return z
        if z >= 0.88: return z - DZ
        return 0.12 + (z - 0.12) * ((0.88 - DZ - 0.12) / (0.88 - 0.12))
    for o in objs.values():
        for v in o.data.vertices:
            v.co.z = warp_z(v.co.z)
        o.data.update()

    PIVOT = Vector((0.0, 0.010, 1.360 - DZ))
    # casual head pose baked into the geometry (chin slightly down, small tilt) so the node rotation stays identity
    R = (Matrix.Translation(PIVOT) @ Matrix.Rotation(-math.radians(CHIN_RAISE_DEG), 4, 'X')
         @ Matrix.Rotation(math.radians(HEAD_ROLL_DEG), 4, 'Y') @ Matrix.Translation(-PIVOT))
    HS = 1.08
    ANCHOR = Vector((0.0, 0.010, 1.425 - DZ))
    Sc = Matrix.Translation(ANCHOR) @ Matrix.Diagonal((HS, HS, HS, 1.0)) @ Matrix.Translation(-ANCHOR)
    for n in HEAD_PARTS: transform_obj(objs[n], R @ Sc)

    # normalise total height (top of hair) to the target
    zmax = max(v.co.z for v in objs['Hair'].data.vertices)
    zmin = min(v.co.z for o in objs.values() for v in o.data.vertices)
    k = TARGET_HEIGHT / (zmax - zmin)
    S = Matrix.Diagonal((k, k, k, 1.0))
    for o in objs.values(): transform_obj(o, S)
    PIVOT = PIVOT * k
    print('[build] height scale factor %.4f (raw height %.4f m)' % (k, zmax - zmin))

    # Head pivot at neck base; Hair/Beard parented to Head
    transform_obj(objs['Head'], Matrix.Translation(-PIVOT))
    objs['Head'].location = PIVOT
    bpy.context.view_layer.update()
    inv = objs['Head'].matrix_world.inverted()
    for n in ('Hair', 'Beard'):
        objs[n].parent = objs['Head']; objs[n].matrix_parent_inverse = inv
    for o in objs.values():
        o.data.update()
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
                primitives_with_COLOR_0=vc, images=len(js.get('images', [])),
                alpha_modes={m['name']: m.get('alphaMode', 'OPAQUE') for m in js['materials']})

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
    # floor
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
    for nm, size, energy in (('Key', 2.2, 380), ('Fill', 3.0, 130), ('Rim', 1.6, 320)):
        ld = bpy.data.lights.new(nm, 'AREA'); ld.size = size; ld.energy = energy
        lo = bpy.data.objects.new(nm, ld); scn.collection.objects.link(lo); lights.append(lo)

    def place(az_deg, dist, target, elev=0.0, light_scale=1.0):
        az = math.radians(az_deg)
        # az 0 = in front of the figure (-Y), + toward the figure's left (+X)
        cam.location = Vector((target[0] + math.sin(az) * dist, target[1] - math.cos(az) * dist, target[2] + elev))
        look_at(cam, target)
        # 3-point rig relative to camera azimuth
        def pos(off, d, h):
            a = math.radians(az_deg + off)
            return Vector((target[0] + math.sin(a) * d, target[1] - math.cos(a) * d, target[2] + h))
        specs = [(-42, 3.0, 1.2), (48, 3.2, 0.2), (170, 3.0, 1.1)]
        for lo, (off, d, h), base in zip(lights, specs, (380, 130, 320)):
            lo.location = pos(off, d * light_scale, h)
            look_at(lo, target)
            lo.data.energy = base * light_scale ** 2

    shots = [('front', 0, 4.5, (0, 0, 0.83), 0.0, 1.0), ('three_quarter_left', 40, 4.5, (0, 0, 0.83), 0.0, 1.0),
             ('side', 90, 4.5, (0, 0, 0.83), 0.0, 1.0), ('back', 180, 4.5, (0, 0, 0.83), 0.0, 1.0),
             ('head_front', 0, 1.25, (0, -0.02, 1.52), 0.0, 0.5), ('head_three_quarter', 35, 1.25, (0, -0.02, 1.52), 0.0, 0.5),
             ('torso_three_quarter', 30, 2.6, (0, 0, 1.10), 0.0, 0.7), ('legs_three_quarter', 30, 2.6, (0, 0, 0.45), 0.0, 0.7)]
    paths = []
    for name, az, dist, tgt, elev, ls in shots:
        place(az, dist, tgt, elev, ls)
        p = os.path.join(RENDER_DIR, '%s_%s.png' % (tag, name))
        scn.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p); print('[render]', p)
    # contact sheet of the 4 full-body views
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
if __name__ == '__main__' or True:
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
