"""
Marius - stylized 3D collectible figurine  ->  public/models/marius-hero.glb

Same person as Toma (avatar/build_toma.py), so the two share one figure: the head / face, the hands, the proportions, the
A-pose and the body scale are the same code. Keep those parts in sync when either file changes. Only the look differs:
curly dark hair, round thin-rimmed glasses, a small goatee, navy blazer over a white shirt, tartan bow tie, dark trousers,
tan suede shoes, a silver ring on the left hand.

Everything is built from smooth lofted surfaces (no cloth normal maps, no hard-edged patches).
Mesh names in the GLB: Head (skin, face; parent of Hair, Glasses, Goatee), Body, Blazer, Shirt, BowTie, Trousers, Shoes.

Run:   blender -b -P avatar/build_avatar.py
Opts:  blender -b -P avatar/build_avatar.py -- [--no-render] [--tag it1] [--samples 48] [--shots front,back]

Coordinates while modelling: Blender, metres, Z up, figure faces -Y (the glTF exporter converts this to Y-up / facing +Z).
The figure's LEFT side is +X.
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
OUT_GLB = arg('--out') or os.path.join(ROOT, 'public', 'models', 'marius-hero.glb')
RENDER_DIR = arg('--render-dir') or os.path.join(HERE, 'renders')
TAG = arg('--tag', 'marius')
SAMPLES = int(arg('--samples', 40))
DO_RENDER = not arg('--no-render', False)
SHOTS = arg('--shots')                    # e.g. --shots back,shoes : render only these previews (no contact sheet)

BODY_SCALE = 1.0036                      # the scale Toma's build ends up with (1.70 m incl. his bun): same person, same size
CHIN_RAISE_DEG = 2.0
HEAD_SCALE = 1.12

# palette (hex, sRGB)
C_SKIN = '#C99A78'                         # skin, lips and hair are Toma's: same person
C_LIP = '#A5605A'
C_HAIR = '#1A1410'
C_GOATEE = '#2C2019'
C_NAVY = '#243257'
C_TROUSER = '#161B2C'
C_SHIRT = '#F3F3F1'
C_BUTTON = '#3B4558'
C_ACCENT = '#8DB8E8'
C_SUEDE = '#75604B'
C_LACE = '#24150F'
C_SOLE = '#B08A62'
C_SOCK = '#141824'
C_GUN = '#2D3035'
C_SILVER = '#CDCED1'


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
    cols = {'N': hexlin('#25335C'), 'S': hexlin('#5E8DBB'), 'L': hexlin('#B2D5F2'), 'W': hexlin('#F2F5F8'), 'D': hexlin('#162245')}
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

IMG_TARTAN = make_image('tartan_base', tartan_texture())

MAT = {
    'skin': make_mat('Skin', vcol=True, rough=0.55, spec=0.4),
    'hair': make_mat('Hair', vcol=True, rough=0.42, spec=0.5),
    'detail': make_mat('Detail', vcol=True, rough=0.55, spec=0.4),
    'cloth': make_mat('Cloth', vcol=True, rough=0.86, spec=0.22),
    'tartan': make_mat('Tartan', tex=IMG_TARTAN, rough=0.7, spec=0.35),
    'metal': make_mat('Metal', vcol=True, rough=0.32, metal=1.0),
    'lens': make_mat('Lens', base='#EAF2FF', rough=0.03, alpha=0.07, spec=0.6),
}
MAT['cloth'].use_backface_culling = False          # exported as doubleSided (open cuffs / hems)

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

def sweep(mb, path, ra, rb=None, sides=12, color=(1, 1, 1, 1), hint=(0, -1, 0), cap0=False, cap1=False, mat=0):
    """Tube along `path` (elliptical section ra x rb, numbers / lists / callables like tube()), built with loft() so the
    faces always point outwards. Returns the rings."""
    path = [Vector(p) for p in path]
    n = len(path)
    fa = prof(ra); fb = prof(rb if rb is not None else ra)
    T = []
    for i in range(n):
        t = path[1] - path[0] if i == 0 else path[-1] - path[-2] if i == n - 1 else path[i + 1] - path[i - 1]
        T.append(t.normalized())
    h = Vector(hint)
    N = h - T[0] * h.dot(T[0])
    if N.length < 1e-4: N = Vector((1, 0, 0)) - T[0] * T[0].x
    N.normalize()
    rings = []
    for i in range(n):
        if i > 0:
            N = T[i - 1].rotation_difference(T[i]) @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        t = i / (n - 1); a = max(fa(t), 1e-4); b = max(fb(t), 1e-4)
        rings.append([mb.vert(path[i] + N * (a * math.cos(2 * math.pi * j / sides)) + B * (b * math.sin(2 * math.pi * j / sides)), color)
                      for j in range(sides)])
    cens = [(mb.M @ p) if mb.M is not None else p for p in path]
    loft(mb, rings, mat=mat, closed=True, centers=cens)
    if cap0: fan_cap(mb, rings[0], cens[0] - cens[1], mat, color=color)
    if cap1: fan_cap(mb, rings[-1], cens[-1] - cens[-2], mat, color=color)
    return rings

def stud(mb, base, nrm, r, h, color, sides=14, mat=0):
    """small flat cylinder standing on a surface (buttons)"""
    ax = Vector(nrm).normalized()
    sweep(mb, [Vector(base) - ax * 0.001, Vector(base) + ax * h], r, r, sides=sides, color=color, hint=(0, 0, 1), cap0=True, cap1=True, mat=mat)

# ============================================================================= BODY PROPORTIONS (the skeleton is Toma's)
# blazer torso:  z, xc, yc, rx, ry, p (superellipse power: 2 = ellipse, >2 boxier)
BLAZER_K = KnotProfile([
    (0.790, 0.0, 0.002, 0.172, 0.126, 2.6),
    (0.860, 0.0, 0.002, 0.174, 0.127, 2.6),
    (0.950, 0.0, 0.003, 0.169, 0.123, 2.5),
    (1.040, 0.0, 0.004, 0.166, 0.120, 2.4),
    (1.120, 0.0, 0.004, 0.172, 0.121, 2.4),
    (1.200, 0.0, 0.005, 0.181, 0.120, 2.4),
    (1.270, 0.0, 0.006, 0.190, 0.114, 2.4),
    (1.305, 0.0, 0.007, 0.190, 0.105, 2.3),
    (1.335, 0.0, 0.008, 0.166, 0.093, 2.2),
    (1.358, 0.0, 0.010, 0.120, 0.080, 2.1),
    (1.380, 0.0, 0.012, 0.084, 0.069, 2.0),
    (1.395, 0.0, 0.013, 0.074, 0.065, 2.0),
], smooth=6)

NECK_Z = 1.395
HEM_Z = 0.790
V_Z0 = 1.035                       # bottom of the V opening = the top button
BUTTON_Z = (1.030, 0.948)
CUT_Z = 0.935                      # below this the fronts curve away from each other (cutaway)
SHIRT_IN = 0.010                   # the shirt sits this far inside the blazer

def gorge_x(z):
    """half-width of the blazer's V opening at height z (0 = closed)"""
    if z <= V_Z0: return 0.0
    if z <= 1.33: return 0.002 + (z - V_Z0) / (1.33 - V_Z0) * 0.054
    return lerp(0.056, 0.054, clamp((z - 1.33) / (NECK_Z - 1.33), 0, 1))

def hem_z(x, y):
    """height of the blazer's lower edge: level all round, swept up towards the middle at the front"""
    if y > 0: return HEM_Z
    return HEM_Z + 0.105 * (1 - smoothstep(0.0, 0.090, abs(x))) ** 1.3

def _front(x, z, lift, inset):
    def yy(xq, zq):
        xc, yc, rx, ry, p = BLAZER_K(zq)
        t = clamp((xq - xc) / (rx - inset), -0.995, 0.995)
        return yc - (ry - inset) * (1 - abs(t) ** p) ** (1.0 / p)
    h = 0.002
    fx = (yy(x + h, z) - yy(x - h, z)) / (2 * h)
    fz = (yy(x, z + h) - yy(x, z - h)) / (2 * h)
    n = Vector((fx, -1.0, fz)).normalized()
    return Vector((x, yy(x, z), z)) + n * lift, n

def blazer_front(x, z, lift=0.0):
    """point on the blazer's front surface + its normal"""
    return _front(x, z, lift, 0.0)

def shirt_front(x, z, lift=0.0):
    return _front(x, z, lift, SHIRT_IN)

# A-pose, symmetrical.  Figure's left = +X.   S1 shoulder joint, E elbow, W wrist
ARM = {
    +1: dict(S1=(0.178, 0.004, 1.272), E=(0.268, -0.006, 0.996), W=(0.322, -0.046, 0.790)),
    -1: dict(S1=(-0.178, 0.004, 1.272), E=(-0.268, -0.006, 0.996), W=(-0.322, -0.046, 0.790)),
}
def leg_pts(s):
    return [(s * 0.088, 0.000, 0.905), (s * 0.091, -0.006, 0.470), (s * 0.094, 0.000, 0.075)]
LEG_YAW = {+1: 0.07, -1: -0.07}        # toes out a touch (symmetrical)

parts = {}

# ============================================================================= HEAD (Toma's face: same person) + goatee
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
    c = mixc(c, hexlin('#9A7C70'), 0.26 * mm * front)
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
    # ---- goatee: a small soft patch on the chin (its own object, so it can be hidden) ---------------
    gm = MB()
    nu, nvv = 14, 11
    grid = []
    for i in range(nu):
        t = i / (nu - 1)
        z_ = lerp(-0.0895, -0.1070, t)
        hw = 0.0075 + 0.0068 * smoothstep(0.0, 0.5, t) - 0.0045 * smoothstep(0.80, 1.0, t)
        row = []
        for j in range(nvv):
            v = j / (nvv - 1) * 2 - 1
            lift = 0.0022 * smoothstep(1.0, 0.40, abs(v)) * smoothstep(0.0, 0.18, t) * smoothstep(1.0, 0.80, t) + 0.00005
            h_ = hit(v * hw, z_)
            row.append((h_[0] + h_[1] * lift, h_[1]) if h_ else None)
        grid.append(row)
    surf_patch(gm, grid, mat=0, color=col(C_GOATEE))
    goatee = gm.build('Goatee', [MAT['hair']], recalc=False)
    head = mb.build('Head', [MAT['skin'], MAT['detail'], MAT['hair']], recalc=False)
    return head, goatee


# ============================================================================= HANDS (Toma's)
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

# ============================================================================= HAIR (dark curls: chunky clumps combed over the skull, longer at the back)
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
        if neck_avoid and p.z < 1.458:
            dx, dy = p.x - NECK_C.x, p.y - NECK_C.y; rr = math.hypot(dx, dy)
            lim = 0.088
            if rr < lim and p.z < 1.458 and dy > -0.02:
                k = lim / max(rr, 1e-5); p.x = NECK_C.x + dx * k; p.y = NECK_C.y + dy * k
        pts.append(p.copy())
    return pts

HAIR_LIN = hexlin(C_HAIR)
def clump(mb, pts, r0, rng, sides=8, tip=0.55):
    """one lock of hair: a smooth tapered tube. The path is relaxed first so the lock flows instead of zig-zagging."""
    pts = [Vector(p) for p in pts]
    for _ in range(3):
        pts = [pts[0]] + [pts[i - 1] * 0.25 + pts[i] * 0.5 + pts[i + 1] * 0.25 for i in range(1, len(pts) - 1)] + [pts[-1]]
    def rad(t):
        base = r0 * (1.0 - (1 - tip) * t ** 1.2)
        return base * min(1.0, ((1 - t) / 0.14) ** 0.55 + 0.04) * (0.45 + 0.55 * smoothstep(0.0, 0.16, t))
    tone = rng.uniform(0.85, 1.40)
    cc = (HAIR_LIN[0] * tone, HAIR_LIN[1] * tone, HAIR_LIN[2] * tone, 1.0)
    sweep(mb, pts, rad, rad, sides=sides, color=cc, hint=(0, 0, 1), cap0=True, cap1=True)

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
    rng = random.Random(11)
    mb = MB()
    PART = math.radians(-12)   # slight side part on the figure's right (-X)
    DOWNBACK = Vector((0, 0.35, -0.94)).normalized()
    d2r = math.radians

    # ---- scalp cap under the clumps (no bald spots) ---------------------------------------
    def hairline(psi):
        a = abs(math.degrees(psi))
        return float(np.interp(a, [0, 40, 62, 80, 98, 118, 140, 180], [0.058, 0.055, 0.046, 0.022, 0.004, -0.030, -0.068, -0.075]))
    g = bmesh.new(); bmesh.ops.create_cube(g, size=2.0)
    bmesh.ops.subdivide_edges(g, edges=g.edges[:], cuts=23, use_grid_fill=True); g.verts.index_update()
    vm = {}
    for v in g.verts:
        x, y, z = v.co
        d = Vector((x * math.sqrt(max(0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                    y * math.sqrt(max(0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                    z * math.sqrt(max(0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
        psi = math.atan2(d.x, -d.y)
        hl_ = hairline(psi)
        if d.z * HRZ < hl_:                      # snap to the hairline -> a smooth edge instead of a saw-tooth brim
            th = math.asin(clamp(hl_ / HRZ, -0.95, 0.95))
            d = Vector((math.sin(psi) * math.cos(th), -math.cos(psi) * math.cos(th), math.sin(th)))
        off = 0.0016 + 0.0044 * smoothstep(0.0, 0.022, d.z * HRZ - hl_)       # thin at the hairline
        vm[v.index] = (mb.vert(C + Vector((d.x * (HRX + off), d.y * (HRY + off), d.z * (HRZ + off))), col(C_HAIR)), d)
    for f in g.faces:
        vs = [vm[v.index][0] for v in f.verts]
        cen = sum((vm[v.index][1] for v in f.verts), Vector()) / 4
        psi = math.atan2(cen.x, -cen.y)
        if cen.z * HRZ > hairline(psi) - 0.0012: mb.face(vs, None, 0)
    g.free()
    bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces[:])

    # ---- 1) front quiff: rises off the hairline, sweeps up and back over the crown ----------
    for psi_d in np.linspace(-66, 66, 15):
        psi0 = d2r(psi_d + rng.uniform(-2.5, 2.5))
        th0 = math.asin(clamp((hairline(psi0) + 0.006 + rng.uniform(-0.006, 0.008)) / HRZ, -0.9, 0.9))
        centre = 1 - 0.50 * abs(psi_d) / 66
        amp = rng.uniform(0.042, 0.056) * centre + 0.006
        hf = lambda s, amp=amp: 0.006 + amp * smoothstep(0, 0.22, s) * (1 - 0.40 * smoothstep(0.50, 1.0, s))
        dpsi = (psi0 - PART) * 0.20
        th1 = d2r(rng.uniform(86, 100)) if abs(psi_d) < 40 else d2r(rng.uniform(66, 82))
        tail = dict(length=0.034, steps=5, curl=rng.uniform(1.8, 2.8), hull=hf(1.0) + 0.002, wave=0.10)
        comb(mb, rng, psi0, th0, th1, dpsi, hf, rng.uniform(0.0150, 0.0185), n=9, wave=0.11, freq=rng.uniform(1.6, 2.6), tail=tail)

    # ---- 1b) loose curls falling/curling at the hairline and a few crown puffs ----------------
    for psi_d in (-52, -30, -8, 14, 36, 55):
        psi0 = d2r(psi_d + rng.uniform(-4, 4))
        th0 = math.asin(clamp((hairline(psi0) + rng.uniform(0.002, 0.010)) / HRZ, -0.9, 0.9))
        hf = lambda s: 0.008 + 0.010 * math.sin(math.pi * min(1, s * 1.2))
        tail = dict(length=0.034, steps=6, curl=rng.uniform(3.0, 4.2), hull=0.012, wave=0.10)
        comb(mb, rng, psi0, th0, th0 + d2r(rng.uniform(8, 16)), d2r(rng.uniform(-6, 6)), hf, rng.uniform(0.0090, 0.0115),
             n=4, wave=0.05, tail=tail, tip=0.5)
    for k in range(7):
        psi0 = d2r(rng.uniform(-60, 60)); th0 = d2r(rng.uniform(55, 80)); th1 = th0 + d2r(rng.uniform(10, 25))
        hf = lambda s: 0.022 + 0.014 * math.sin(math.pi * min(1, s * 1.1))
        tail = dict(length=0.028, steps=5, curl=rng.uniform(2.4, 3.6), hull=0.026, wave=0.12)
        comb(mb, rng, psi0, th0, th1, d2r(rng.uniform(-18, 18)), hf, rng.uniform(0.0125, 0.0155), n=6, wave=0.10, tail=tail, tip=0.5)

    # ---- 2) crown / top volume --------------------------------------------------------------
    for k in range(9):    # centre-top, flowing back
        psi0 = d2r(rng.uniform(-34, 34)); th0 = d2r(rng.uniform(58, 72)); th1 = d2r(rng.uniform(112, 128))
        hf = lambda s: 0.022 + 0.018 * math.sin(math.pi * min(1, s * 1.1))
        tail = dict(length=0.030, steps=5, curl=rng.uniform(1.6, 2.6), hull=0.020, wave=0.10,
                    steer=lambda p, t: DOWNBACK, steer_k=0.06)
        comb(mb, rng, psi0, th0, th1, 0.0, hf, rng.uniform(0.0165, 0.0195), n=8, wave=0.06, tail=tail)
    for sgn in (+1, -1):  # upper sides sweeping round to the back
        for k in range(6):
            psi0 = d2r(rng.uniform(34, 92)) * sgn; th0 = d2r(rng.uniform(44, 66)); th1 = th0 - d2r(rng.uniform(0, 14))
            hf = lambda s: 0.012 + 0.012 * math.sin(math.pi * min(1, s * 1.1))
            tail = dict(length=0.026, steps=5, curl=rng.uniform(1.4, 2.4), hull=0.020, wave=0.10,
                        steer=lambda p, t: DOWNBACK, steer_k=0.06)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(rng.uniform(32, 52)), hf, rng.uniform(0.0155, 0.0185), n=8, wave=0.06, tail=tail)

    # ---- 3) sides, half covering the ears ----------------------------------------------------
    for sgn in (+1, -1):
        for k in range(8):
            psi0 = d2r(rng.uniform(62, 108)) * sgn; th0 = d2r(rng.uniform(22, 50)); th1 = d2r(rng.uniform(-4, 8))
            hf = lambda s: 0.014 + 0.008 * math.sin(math.pi * s)
            tail = dict(length=0.018, steps=4, curl=rng.uniform(0.6, 1.2), hull=0.018, wave=0.08,
                        steer=lambda p, t: DOWNBACK, steer_k=0.10)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(rng.uniform(4, 16)), hf, rng.uniform(0.0150, 0.0180), n=8, wave=0.05, tail=tail)
        for k in range(2):  # temples
            psi0 = d2r(rng.uniform(58, 70)) * sgn; th0 = d2r(rng.uniform(22, 28)); th1 = d2r(rng.uniform(4, 10))
            hf = lambda s: 0.009 + 0.006 * math.sin(math.pi * s)
            comb(mb, rng, psi0, th0, th1, sgn * d2r(6), hf, 0.0115, n=6, wave=0.03, tail=None, tip=0.45)

    # ---- 4) back: longer, curling over the collar (soft modern mullet) ------------------------
    for k in range(26):
        psi0 = d2r(rng.uniform(112, 248)); th0 = d2r(rng.uniform(26, 62)); th1 = d2r(rng.uniform(-30, -18))
        sgn = 1 if math.sin(psi0) > 0 else -1
        hf = lambda s: 0.011 + 0.008 * math.sin(math.pi * s)
        L = rng.uniform(0.060, 0.095) if th0 < d2r(44) else rng.uniform(0.040, 0.070)
        tail = dict(length=L, steps=7, curl=rng.uniform(1.0, 1.8), hull=0.018, wave=0.10,
                    steer=lambda p, t: DOWNBACK, steer_k=0.10, axis=Vector((1.0, rng.uniform(-0.3, 0.3), 0.0)))
        comb(mb, rng, psi0, th0, th1, 0.0, hf, rng.uniform(0.0150, 0.0185), n=9, wave=0.05, tail=tail)
    return mb.build('Hair', [MAT['hair']], recalc=False)

# ============================================================================= GLASSES
def build_glasses():
    mb = MB()
    metal = col(C_GUN)
    LR = 0.0245; WR = 0.00105; EX = 0.0338; LY = -0.1045; LZ = C.z - 0.001
    for s in (+1, -1):
        cx = s * EX
        # rim (slightly squashed circle) as a swept tube along a closed circle
        nmaj, nmin = 56, 7
        rings = []
        for k in range(nmaj):
            ph = 2 * math.pi * k / nmaj
            er = Vector((math.cos(ph), 0, math.sin(ph) * 0.96))
            cen = Vector((cx, LY, LZ)) + er * LR
            ring = []
            for j in range(nmin):
                th = 2 * math.pi * j / nmin
                ring.append(mb.vert(cen + Vector((math.cos(ph), 0, math.sin(ph))) * (WR * math.cos(th)) + Vector((0, 1, 0)) * (WR * math.sin(th)), metal))
            rings.append(ring)
        ring_loft(mb, rings, True, False, False, 0)
        # lens
        lens_r = [mb.vert_raw(Vector((cx, LY, LZ)), (1, 1, 1, 1))]
        for k in range(nmaj):
            ph = 2 * math.pi * k / nmaj
            lens_r.append(mb.vert_raw(Vector((cx + math.cos(ph) * (LR - 0.0006), LY, LZ + math.sin(ph) * (LR - 0.0006) * 0.96)), (1, 1, 1, 1)))
        for k in range(nmaj):
            a, b = lens_r[1 + k], lens_r[1 + (k + 1) % nmaj]
            mb.face((lens_r[0], a, b) if s > 0 else (lens_r[0], b, a), None, 1)
        # endpiece + temple
        ex = Vector((cx + s * (LR + 0.0006), LY, LZ + 0.004))
        tp = [ex, ex + Vector((s * 0.002, 0.0035, 0.0)), Vector((s * 0.0762, C.y - 0.060, C.z + 0.002)),
              Vector((s * 0.0790, C.y + 0.012, C.z + 0.001)), Vector((s * 0.0790, C.y + 0.050, C.z - 0.001)),
              Vector((s * 0.0775, C.y + 0.066, C.z - 0.020))]
        tube(mb, catmull(tp, 4), 0.00095, 0.00095, sides=6, mat=0, color=metal, hint=(0, 0, 1))
        # tiny hinge block
        tube(mb, [ex + Vector((-s * 0.0012, 0, 0)), ex + Vector((s * 0.0036, 0.0016, 0))], 0.0016, 0.0013, sides=6, mat=0, color=metal, hint=(0, 0, 1))
        # nose pad + arm
        padc = Vector((s * 0.0128, LY + 0.0075, LZ - 0.0105))
        rimp = Vector((s * (EX - LR + 0.0015), LY, LZ - 0.0035))
        tube(mb, [rimp, rimp.lerp(padc, 0.5) + Vector((0, 0.001, 0)), padc], 0.0006, 0.0006, sides=5, mat=0, color=metal, hint=(0, 0, 1))
        uv_sphere(mb, padc + Vector((-s * 0.0008, 0.0012, 0)), 0.0034, mat=1, segs=8, angles=[0, 45, 90, 135, 180],
                  colfn=lambda a, d: (0.8, 0.82, 0.85, 1), axis=(s, 0, 0))
    # bridge: thin, straight, slightly forward of the lens plane
    b0 = Vector((EX - LR + 0.0004, LY, LZ + 0.0062)); b1 = Vector((-EX + LR - 0.0004, LY, LZ + 0.0062))
    tube(mb, catmull([b1, Vector((0, LY - 0.0065, LZ + 0.0078)), b0], 5), WR, WR, sides=6, mat=0, color=metal, hint=(0, 0, 1))
    return mb.build('Glasses', [MAT['metal'], MAT['lens']], recalc=False)

# ============================================================================= BODY (skin): neck, wrists, hands. The rest is under the clothes.
HAND_SCALE = 0.95
def build_body():
    mb = MB()
    sk = col(C_SKIN)
    tube(mb, [(0, 0.014, 1.30), (0, 0.010, 1.38), (0, 0.003, 1.48)], [0.0580, 0.0560, 0.0545], [0.0560, 0.0540, 0.0535],
         sides=14, mat=0, color=sk, hint=(0, -1, 0))
    for s in (+1, -1):
        a = ARM[s]
        E, W = Vector(a['E']), Vector(a['W'])
        f = (W - E).normalized()
        tube(mb, [E.lerp(W, 0.45), E.lerp(W, 0.75), W + f * 0.005], [0.0250, 0.0235, 0.0215], [0.0240, 0.0225, 0.0205],
             sides=12, mat=0, color=sk, hint=(0, -1, 0))
        R = Vector((0, 0, -1)).rotation_difference(f).to_matrix().to_4x4()
        M = Matrix.Translation(W) @ R @ Matrix.Diagonal((HAND_SCALE, HAND_SCALE, HAND_SCALE, 1.0))
        hand_geometry(mb, s, M)
    return mb.build('Body', [MAT['skin'], MAT['metal']], recalc=True)

# ============================================================================= BLAZER (navy, single-breasted, two buttons, notch lapels)
def sleeve_path(s):
    a = ARM[s]; S1, E, W = Vector(a['S1']), Vector(a['E']), Vector(a['W'])
    dr = (E - S1).normalized(); f = (W - E).normalized()
    return catmull([S1 - dr * 0.045 + Vector((-s * 0.026, 0, -0.016)), S1 + dr * 0.020, E, W - f * 0.016], 6)
SLEEVE_RA = prof([0.028, 0.0550, 0.0525, 0.0475, 0.0435, 0.0410])      # starts small, deep inside the shoulder
SLEEVE_RB = prof([0.028, 0.0535, 0.0505, 0.0460, 0.0425, 0.0400])

def build_blazer():
    mb = MB()
    navy = col(C_NAVY)
    lapel = tuple(min(1.0, c * 1.10) for c in navy[:3]) + (1.0,)
    # ---- body: one smooth shell, open in a V above the top button, fronts swept apart below the lower one ----------
    S = 49
    zs = np.concatenate([np.linspace(HEM_Z, 1.30, 18), np.linspace(1.312, NECK_Z, 8)])
    rings = []
    for z in zs:
        xc, yc, rx, ry, p = BLAZER_K(z)
        a0 = math.asin(clamp(gorge_x(z) / rx, 0.0, 0.999) ** (p / 2.0))       # half-angle of the opening
        ring = []
        for k in range(S):
            phi = 1.5 * math.pi + a0 + (2 * math.pi - 2 * a0) * k / (S - 1)
            x = xc + rx * sgnp(math.cos(phi), p); y = yc + ry * sgnp(math.sin(phi), p)
            zz = z
            if z < CUT_Z:
                hz = hem_z(x, y - yc)
                zz = hz + (z - HEM_Z) * (CUT_Z - hz) / (CUT_Z - HEM_Z)
            ring.append(mb.vert((x, y, zz), navy))
        rings.append(ring)
    loft(mb, rings, mat=0, closed=False)

    # ---- sleeves: shoulder to just above the wrist, following the arm -----------------------------------------------
    for s in (+1, -1):
        sweep(mb, sleeve_path(s), SLEEVE_RA, SLEEVE_RB, sides=18, color=navy, hint=(0, -1, 0), cap0=True, cap1=False)
    # a few soft folds: inside of the elbows, and one pull from the top button towards each hip
    folds = [((0.020, -0.120, 1.01), (0.110, -0.118, 0.90), 0.022, 0.0026),
             ((-0.020, -0.120, 1.01), (-0.110, -0.118, 0.90), 0.022, 0.0026)]
    for s in (+1, -1):
        E = Vector(ARM[s]['E'])
        for dz, am in ((0.040, 0.0030), (-0.005, 0.0034), (-0.050, 0.0026)):
            c = E + Vector((-s * 0.030, -0.010, dz))
            folds.append((c + Vector((-s * 0.030, -0.030, 0.010)), c + Vector((s * 0.010, 0.030, -0.010)), 0.011, am))
    fold_displace(mb.bm, folds)

    # ---- collar: a soft roll round the back of the neck, from one lapel to the other --------------------------------
    xc, yc, rx, ry, p = BLAZER_K(NECK_Z)
    a0 = math.asin(clamp(gorge_x(NECK_Z) / rx, 0.0, 0.999) ** (p / 2.0))
    N = 30; rings = []; cens = []
    for k in range(N):
        t = k / (N - 1)
        phi = 1.5 * math.pi + a0 + (2 * math.pi - 2 * a0) * t
        c_, s_ = math.cos(phi), math.sin(phi)
        ends = smoothstep(0.0, 0.14, t) * smoothstep(1.0, 0.86, t)
        cen = Vector((xc + (rx + 0.0025) * sgnp(c_, p), yc + (ry + 0.0025) * sgnp(s_, p), NECK_Z - 0.008))
        rh = Vector((c_ / rx, s_ / ry, 0)).normalized()
        mr, mz = 0.0048 * (0.45 + 0.55 * ends), 0.0135 * (0.55 + 0.45 * ends)
        rings.append([mb.vert(cen + rh * (mr * math.cos(ps)) + Vector((0, 0, mz * math.sin(ps))), navy)
                      for ps in [2 * math.pi * q / 8 for q in range(8)]])
        cens.append(cen)
    loft(mb, rings, mat=0, closed=True, centers=cens)
    fan_cap(mb, rings[0], cens[0] - cens[1], 0, color=navy); fan_cap(mb, rings[-1], cens[-1] - cens[-2], 0, color=navy)

    # ---- notch lapels: lie on the fronts along the V, rolled up at the inner edge -----------------------------------
    outer = [(1.035, 0.004), (1.075, 0.040), (1.125, 0.071), (1.185, 0.096), (1.245, 0.112), (1.288, 0.118),
             (1.300, 0.113), (1.312, 0.101), (1.330, 0.092), (1.360, 0.076), (1.388, 0.060)]
    oz = [o[0] for o in outer]; ox = [o[1] for o in outer]
    lap_zs = np.concatenate([np.linspace(V_Z0, 1.29, 22), np.linspace(1.298, 1.388, 10)])
    for s in (+1, -1):
        grid = []
        for z in lap_zs:
            xi = gorge_x(z)
            xo = max(float(np.interp(z, oz, ox)), xi + 0.004)
            row = [blazer_front(s * xi, z, 0.0003)]                     # starts on the shell's edge: no gap under the roll
            for sj in np.linspace(0, 1, 7):
                lift = 0.0028 + 0.0070 * (1 - sj) ** 1.6
                row.append(blazer_front(s * lerp(xi + 0.0006, xo, sj), z, lift))
            grid.append(row)
        surf_patch(mb, grid, mat=0, color=lapel)
    # light-blue buttonhole on the figure's left lapel
    z0 = 1.228
    xm = lerp(gorge_x(z0), float(np.interp(z0, oz, ox)), 0.64)
    pa, _ = blazer_front(xm - 0.007, z0 - 0.003, 0.0058); pb, _ = blazer_front(xm + 0.007, z0 + 0.003, 0.0058)
    sweep(mb, [pa, pb], 0.0016, 0.0016, sides=6, color=col(C_ACCENT), hint=(0, -1, 0), cap0=True, cap1=True)

    # ---- pockets: thin raised panels lying on the cloth ---------------------------------------------------------------
    def panel(x0, z0, w, h, tilt, lift, nx=11, ny=5):
        ct, st = math.cos(tilt), math.sin(tilt)
        grid = []
        for i in range(ny):
            vv = i / (ny - 1) * 2 - 1
            row = []
            for j in range(nx):
                uu = j / (nx - 1) * 2 - 1
                lx, lz = uu * w / 2, vv * h / 2
                edge = min(1 - abs(uu), 1 - abs(vv))
                row.append(blazer_front(x0 + lx * ct - lz * st, z0 + lx * st + lz * ct, 0.0002 + lift * smoothstep(0.0, 0.30, edge)))
            grid.append(row)
        surf_patch(mb, grid, mat=0, color=navy)
    panel(0.098, 1.192, 0.092, 0.013, math.radians(5), 0.0020)                  # chest welt, figure's left
    for s in (+1, -1):
        panel(s * 0.106, 0.868, 0.128, 0.040, math.radians(-3 * s), 0.0026)      # hip flaps

    # ---- buttons: two at the front, three on each cuff ----------------------------------------------------------------
    for z in BUTTON_Z:
        p_, n_ = blazer_front(0.004, z, 0.0004)
        stud(mb, p_, n_, 0.0100, 0.0038, col(C_BUTTON))
        stud(mb, p_ + n_ * 0.0038, n_, 0.0036, 0.0010, col('#262E3B'), sides=10)
    for s in (+1, -1):
        path = sleeve_path(s); n = len(path)
        for k in range(3):
            i = n - 2 - k
            t = (path[i + 1] - path[i - 1]).normalized()
            out = Vector((s, 0.45, 0)); out = (out - t * out.dot(t)).normalized()
            hint = Vector((0, -1, 0)); N_ = (hint - t * hint.dot(t)).normalized(); B_ = t.cross(N_)
            ca, cb = out.dot(N_), out.dot(B_)
            rr = 1.0 / math.sqrt((ca / SLEEVE_RA(i / (n - 1))) ** 2 + (cb / SLEEVE_RB(i / (n - 1))) ** 2)
            stud(mb, path[i] + out * (rr + 0.0002), out, 0.0050, 0.0026, col(C_BUTTON), sides=10)
    return mb.build('Blazer', [MAT['cloth']], recalc=False)

# ============================================================================= SHIRT (white dress shirt: seen in the V, at the collar and at the cuffs)
def build_shirt():
    mb = MB()
    white = col(C_SHIRT)
    S = 32
    zs = np.concatenate([np.linspace(0.985, 1.30, 10), np.linspace(1.315, NECK_Z - 0.004, 6)])
    rings = []
    for z in zs:
        xc, yc, rx, ry, p = BLAZER_K(z)
        rings.append([mb.vert((xc + (rx - SHIRT_IN) * sgnp(math.cos(2 * math.pi * j / S), p),
                               yc + (ry - SHIRT_IN) * sgnp(math.sin(2 * math.pi * j / S), p), z), white) for j in range(S)])
    loft(mb, rings, mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, -1)), 0, color=white)
    # collar band, buttoned up
    CY = 0.010
    rings = []
    for z, r in zip([1.368, 1.386, 1.402, 1.413], [0.0625, 0.0610, 0.0604, 0.0610]):
        rings.append([mb.vert((r * math.cos(2 * math.pi * j / 28), CY + (r - 0.001) * math.sin(2 * math.pi * j / 28), z), white) for j in range(28)])
    loft(mb, rings, mat=0, closed=True)
    # collar points, folded down over the band
    def collar_surf(x, z, lift):
        rx, ry = 0.0612, 0.0602
        t = clamp(x / rx, -0.995, 0.995)
        y = CY - ry * math.sqrt(1 - t * t)
        n = Vector((x / rx ** 2, (y - CY) / ry ** 2, 0)).normalized()
        return Vector((x, y, z)) + n * lift, n
    for s in (+1, -1):
        quad = [(0.012, 1.416), (0.040, 1.403), (0.046, 1.352), (0.019, 1.366)]
        P = [Vector((q[0], q[1], 0)) for q in quad]
        grid = []
        for i in range(7):
            ti = i / 6; row = []
            L = P[0].lerp(P[3], ti); R_ = P[1].lerp(P[2], ti)
            for j in range(5):
                tj = j / 4; q = L.lerp(R_, tj)
                lift = 0.0018 + 0.0040 * tj ** 1.3 * (0.5 + 0.5 * ti)
                row.append(collar_surf(s * q.x, q.y - 0.002 * tj, lift))
            grid.append(row)
        surf_patch(mb, grid, mat=0, color=white)
    # buttons down the front
    for z in (1.278, 1.178, 1.078):
        p_, n_ = shirt_front(0.0, z, 0.0003)
        stud(mb, p_, n_, 0.0040, 0.0022, col('#E4E4DE'), sides=10)
    # cuffs showing below the blazer sleeves
    for s in (+1, -1):
        a = ARM[s]; E = Vector(a['E']); W = Vector(a['W']); f = (W - E).normalized()
        sweep(mb, [W - f * 0.040, W - f * 0.012, W + f * 0.012], [0.0350, 0.0350, 0.0335], [0.0340, 0.0340, 0.0325], sides=16,
              color=white, hint=(0, -1, 0))
    return mb.build('Shirt', [MAT['cloth']], recalc=False)

# ============================================================================= BOW TIE
def build_bowtie():
    mb = MB()
    cy, cz = -0.0590, 1.3835
    rot = math.radians(32)
    tile = 0.05
    def uvpos(p):
        x, z = p.x, p.z
        u = (x * math.cos(rot) + z * math.sin(rot)) / tile
        v = (-x * math.sin(rot) + z * math.cos(rot)) / tile
        return (u, v)
    white = (1, 1, 1, 1)
    for s in (+1, -1):
        xs = [0.007, 0.014, 0.026, 0.039, 0.0515]
        ys = [cy - 0.0005, cy + 0.001, cy + 0.0075, cy + 0.0195, cy + 0.0330]
        zc = [cz + 0.0, cz + 0.0008, cz + 0.0020, cz + 0.0030, cz + 0.0034]
        hz = [0.0060, 0.0085, 0.0140, 0.0175, 0.0170]
        hy = [0.0058, 0.0062, 0.0068, 0.0070, 0.0066]
        path = [Vector((s * xs[i], ys[i], zc[i])) for i in range(5)]
        pts = catmull(path, 3)
        tube(mb, pts, hy, hz, sides=12, mat=0, color=white, hint=(0, -1, 0), cap0=False, cap1=True, power=3.0, uvpos=uvpos)
    # knot
    tube(mb, [Vector((-0.0105, cy - 0.0005, cz)), Vector((0.0105, cy - 0.0005, cz))], 0.0078, 0.0098, sides=12, mat=0,
         color=white, hint=(0, -1, 0), power=3.0, uvpos=uvpos)
    return mb.build('BowTie', [MAT['tartan']], recalc=True)

# ============================================================================= TROUSERS (dark navy, straight leg)
# Above the blazer's hem everything stays ~1.5 cm inside the blazer, so the trousers never show through it, standing or
# walking. The two legs lie flat against each other at the top and separate further down.
TROUSER_TOP, TROUSER_HEM = 0.93, 0.088
def trouser_leg(z):
    """one leg at height z: (centre x for the +X leg, half-width, half-depth, squareness of the inner side)"""
    xo = float(np.interp(z, [0.088, 0.20, 0.40, 0.60, 0.82, 0.93], [0.1405, 0.1415, 0.146, 0.152, 0.155, 0.150]))
    xi = float(np.interp(z, [0.088, 0.20, 0.47, 0.70, 0.78, 0.93], [0.0465, 0.0450, 0.030, 0.012, 0.004, 0.003]))
    ry = float(np.interp(z, [0.088, 0.20, 0.47, 0.80, 0.93], [0.0570, 0.0575, 0.068, 0.098, 0.098]))
    return (xo + xi) / 2, (xo - xi) / 2, ry, lerp(2.0, 5.0, smoothstep(0.62, 0.78, z))

def build_trousers():
    mb = MB()
    dark = col(C_TROUSER)
    S = 32
    # waist + seat (hidden under the blazer)
    rings = []
    for z in np.linspace(1.02, 0.775, 9):
        rx = float(np.interp(z, [0.775, 0.80, 0.86, 0.93, 1.02], [0.100, 0.138, 0.150, 0.150, 0.146]))
        ry = float(np.interp(z, [0.775, 0.80, 0.86, 0.93, 1.02], [0.060, 0.074, 0.094, 0.104, 0.104]))
        rings.append([mb.vert((rx * sgnp(math.cos(2 * math.pi * j / S), 2.4), 0.002 + ry * sgnp(math.sin(2 * math.pi * j / S), 2.4), z), dark)
                      for j in range(S)])
    loft(mb, rings, mat=0, closed=True)
    fan_cap(mb, rings[0], Vector((0, 0, 1)), 0, color=dark); fan_cap(mb, rings[-1], Vector((0, 0, -1)), 0, color=dark)
    for s in (+1, -1):
        pts = leg_pts(s)
        zz = [p[2] for p in pts][::-1]; ys = [p[1] for p in pts][::-1]
        rings = []
        for z in np.concatenate([np.linspace(TROUSER_TOP, 0.50, 10), np.linspace(0.45, TROUSER_HEM, 10)]):
            cx, rx, ry, p_in = trouser_leg(z)
            cy = float(np.interp(z, zz, ys)) + 0.004 * smoothstep(0.40, 0.10, z)
            ring = []
            for j in range(S):
                th = (j / S - 0.5) * 2 * math.pi
                sx, cq = math.sin(th), math.cos(th)
                if sx * s < 0: sx = sgnp(sx, p_in); cq = sgnp(cq, p_in)           # inner side: flat where the legs meet
                ring.append(mb.vert((s * cx + sx * rx, cy - cq * ry, z), dark))
            rings.append(ring)
        loft(mb, rings, mat=0, closed=True)
    # the cloth breaks softly over the shoes
    folds = []
    for s in (+1, -1):
        A = Vector(leg_pts(s)[2])
        for z_, am in ((0.175, 0.0030), (0.135, 0.0036)):
            folds.append(((A.x - 0.06, -0.060, z_), (A.x + 0.06, -0.060, z_ + s * 0.006), 0.010, am))
    fold_displace(mb.bm, folds)
    return mb.build('Trousers', [MAT['cloth']], recalc=False)

# ============================================================================= SHOES (tan suede lace-ups; the shape is Toma's sneaker without the high top)
# local frame: origin on the floor under the ankle, toe toward -Y.
Y_TOE = -0.2185                           # toe tip
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

def super_ring(mb, y, a, zb, zt, p=2.8, S=20, color=(1, 1, 1, 1)):
    cz = (zt + zb) / 2; b = max((zt - zb) / 2, 0.0008); a = max(a, 0.0008)
    ring = []
    for j in range(S):
        th = 2 * math.pi * j / S
        ring.append(mb.vert((a * sgnp(math.cos(th), p), y, cz + b * sgnp(math.sin(th), p)), color))
    return ring, cz, b, a

def build_shoes():
    mb = MB()
    suede, sole_c, lace_c, sock = col(C_SUEDE), col(C_SOLE), col(C_LACE), col(C_SOCK)
    S = 20
    stations = shoe_stations()
    ymid = (Y_TOE + Y_BACK) / 2
    for s in (+1, -1):
        A = leg_pts(s)[2]
        mb.M = Matrix.Translation((A[0], A[1], 0.0)) @ Matrix.Rotation(LEG_YAW[s], 4, 'Z')
        # suede upper (toe -> heel), closed on top: the trouser leg comes down over it
        rings = [super_ring(mb, y, sw_(y), sb_(y) + UPPER_Z0, st_(y), 2.8, S, color=suede)[0] for y in stations]
        loft(mb, rings, mat=0, closed=True)
        fan_cap(mb, rings[0], Vector((0, -1, 0)), 0, color=suede); fan_cap(mb, rings[-1], Vector((0, 1, 0)), 0, color=suede)
        # crepe sole: the shoe's outline pulled straight up, a touch longer and wider than the upper
        def outline(z_of_y, inset, grow):
            pts = []
            for sgn, ys_ in ((+1, stations), (-1, stations[::-1])):
                for y in ys_:
                    a = max(sw_(y) * 1.035 + 0.0016 - inset, 0.0002)
                    pts.append(mb.vert((sgn * a, ymid + (y - ymid) * grow, z_of_y(y)), sole_c))
            return pts
        sole_top = lambda y: SOLE_TOP - 0.003 + sb_(y)
        rings = [outline(lambda y: 0.0, 0.0030, 1.006), outline(lambda y: 0.0035, 0.0, 1.016),
                 outline(lambda y: sole_top(y) - 0.0030, 0.0, 1.016), outline(sole_top, 0.0028, 1.008)]
        loft(mb, rings, mat=0, closed=True)
        fan_cap(mb, rings[0], Vector((0, 0, -1)), 0, color=sole_c); fan_cap(mb, rings[-1], Vector((0, 0, 1)), 0, color=sole_c)
        # laces, toe seam, bow
        def upper(y, u, lift=0.0):
            a = sw_(y); zt = st_(y); zb = sb_(y) + UPPER_Z0
            cz = (zt + zb) / 2; b = (zt - zb) / 2
            return Vector((a * u, y, cz + b * (max(0.0, 1 - abs(u) ** 2.8)) ** (1 / 2.8) + lift))
        for y in (-0.050, -0.072, -0.094, -0.116):
            sweep(mb, [upper(y, u, 0.0012) for u in np.linspace(-0.5, 0.5, 7)], 0.0025, 0.0025, sides=6, color=lace_c,
                  hint=(0, 1, 0), cap0=True, cap1=True)
        sweep(mb, [upper(-0.172, u, 0.0008) for u in np.linspace(-0.88, 0.88, 11)], 0.0014, 0.0014, sides=5, color=col('#4A3626'),
              hint=(0, 1, 0), cap0=True, cap1=True)
        k0 = upper(-0.040, 0.0, 0.0026)
        for sx in (+1, -1):
            loop = [k0, k0 + Vector((sx * 0.007, -0.003, 0.0045)), k0 + Vector((sx * 0.015, -0.002, 0.0020)), k0 + Vector((sx * 0.017, 0.004, -0.0010))]
            sweep(mb, catmull(loop, 3), 0.0021, 0.0021, sides=5, color=lace_c, hint=(0, 0, 1), cap0=True, cap1=True)
        # dark sock filling the trouser leg above the shoe
        sweep(mb, [Vector((0, 0.008, 0.030)), Vector((0, 0.008, 0.100)), Vector((0, 0.006, 0.170))], 0.0370, 0.0400, sides=14,
              color=sock, hint=(0, -1, 0), cap1=True)
        mb.M = None
    return mb.build('Shoes', [MAT['cloth']], recalc=False)

# ============================================================================= ASSEMBLE
def transform_obj(obj, M): obj.data.transform(M)

def assemble():
    head, goatee = build_head()
    hair = build_hair()
    glasses = build_glasses()
    body = build_body()
    blazer = build_blazer()
    shirt = build_shirt()
    bow = build_bowtie()
    trousers = build_trousers()
    shoes = build_shoes()
    objs = dict(Head=head, Hair=hair, Glasses=glasses, Goatee=goatee, Body=body, Blazer=blazer, Shirt=shirt,
                BowTie=bow, Trousers=trousers, Shoes=shoes)
    for n, o in objs.items():
        o.name = n; o.data.name = n

    # head: chin very slightly raised + figurine head scale, baked into the geometry (the node rotation stays identity)
    PIVOT = Vector((0.0, 0.010, 1.360))
    R = Matrix.Translation(PIVOT) @ Matrix.Rotation(-math.radians(CHIN_RAISE_DEG), 4, 'X') @ Matrix.Translation(-PIVOT)
    ANCHOR = Vector((0.0, 0.010, 1.425))
    Sc = Matrix.Translation(ANCHOR) @ Matrix.Diagonal((HEAD_SCALE, HEAD_SCALE, HEAD_SCALE, 1.0)) @ Matrix.Translation(-ANCHOR)
    HEAD_PARTS = ('Head', 'Hair', 'Glasses', 'Goatee')
    for n in HEAD_PARTS: transform_obj(objs[n], R @ Sc)

    k = BODY_SCALE
    S = Matrix.Diagonal((k, k, k, 1.0))
    for o in objs.values(): transform_obj(o, S)
    PIVOT = PIVOT * k
    zmax = max(v.co.z for v in objs['Hair'].data.vertices)
    zmin = min(v.co.z for o in objs.values() for v in o.data.vertices)
    print('[build] height %.4f m (floor at z = %.4f), body scale %.4f' % (zmax - zmin, zmin, k))

    # Head pivot at the base of the neck; Hair / Glasses / Goatee parented to Head
    transform_obj(objs['Head'], Matrix.Translation(-PIVOT))
    objs['Head'].location = PIVOT
    bpy.context.view_layer.update()
    inv = objs['Head'].matrix_world.inverted()
    for n in HEAD_PARTS[1:]:
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
             ('hands', 60, 1.5, (0.30, -0.04, 0.80), 0.0, 0.45),
             ('torso_three_quarter', 30, 2.6, (0, 0, 1.12), 0.0, 0.7), ('legs_three_quarter', 30, 2.6, (0, 0, 0.45), 0.0, 0.7),
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
