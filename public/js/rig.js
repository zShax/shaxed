// Automatic humanoid rig + procedural walk for the figurines (same method as preview.html in the repo root).
// The models ship without a skeleton: bones are placed from body proportions and every vertex is weighted to them.
import * as THREE from 'three';

const rad = THREE.MathUtils.degToRad;
const clamp = THREE.MathUtils.clamp;
const sstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); }; // works for e0 > e1 too

const HEAD_RE = /^head$/i;
const LEG_RE = /trouser|pant|jean|shoe|boot|sneaker|sock|\bleg|foot|feet|skirt|short|loafer/i;
const underHead = (o, root) => { for (let p = o; p && p !== root; p = p.parent) if (HEAD_RE.test(p.name)) return true; return false; };
const chainName = (o, root) => { let s = ''; for (let p = o; p && p !== root; p = p.parent) s += p.name + ' '; return s; };

export const WALK = { stride: 25, knee: 45, arms: 28, armOut: 4, elbow: 25, bob: 1, sway: 2, tilt: 1.5, lean: 3 };

/* Splits a mesh into islands (vertices welded by position, then joined through shared triangles) and measures each one
   in root space. Sleeves, trouser legs, shoes... are separate tubes inside one mesh, so a whole island can go to one limb. */
function meshIslands(geo, toRoot) {
  const pos = geo.attributes.position, n = pos.count, v = new THREE.Vector3();
  const P = new Float32Array(n * 3), rep = new Int32Array(n), weld = new Map();
  for (let i = 0; i < n; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(toRoot); P[i * 3] = v.x; P[i * 3 + 1] = v.y; P[i * 3 + 2] = v.z;
    const k = Math.round(pos.getX(i) * 1e5) + ',' + Math.round(pos.getY(i) * 1e5) + ',' + Math.round(pos.getZ(i) * 1e5);
    const r = weld.get(k); if (r === undefined) { weld.set(k, i); rep[i] = i; } else rep[i] = r;
  }
  const parent = new Int32Array(n); for (let i = 0; i < n; i++) parent[i] = i;
  const find = a => { while (parent[a] !== a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; };
  const idx = geo.index, count = idx ? idx.count : n, at = t => rep[idx ? idx.getX(t) : t];
  for (let t = 0; t + 2 < count; t += 3) {
    const a = find(at(t));
    for (let j = 1; j < 3; j++) { const b = find(at(t + j)); if (b !== a) parent[b] = a; }
  }
  const slot = new Map(), list = [], of = new Int32Array(n);
  for (let i = 0; i < n; i++) {
    const r = find(rep[i]); let s = slot.get(r);
    if (s === undefined) { s = list.length; slot.set(r, s); list.push({ x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity }); }
    const b = list[s]; of[i] = s;
    b.x0 = Math.min(b.x0, P[i * 3]); b.x1 = Math.max(b.x1, P[i * 3]); b.y0 = Math.min(b.y0, P[i * 3 + 1]); b.y1 = Math.max(b.y1, P[i * 3 + 1]);
  }
  for (const b of list) { b.cx = (b.x0 + b.x1) / 2; b.cy = (b.y0 + b.y1) / 2; }
  return { P, of, list };
}

export function buildRig(root, box) {
  const H = box.max.y - box.min.y, y0 = box.min.y;
  const hipY = y0 + 0.525 * H, kneeY = y0 + 0.27 * H, ankleY = y0 + 0.045 * H, shY = y0 + 0.77 * H, elY = y0 + 0.60 * H;
  const bones = [], bone = (name, x, y, z, parent) => { const b = new THREE.Bone(); b.name = 'rig_' + name; b.position.set(x, y, z); parent.add(b); bones.push(b); return b; };
  // index: 0 base | 1 hip+ 2 knee+ | 3 hip- 4 knee- | 5 shoulder+ 6 elbow+ | 7 shoulder- 8 elbow- | 9 ankle+ 10 ankle-
  const base = bone('base', 0, 0, 0, root);
  const hipP = bone('hip+', 0.055 * H, hipY, 0, base), kneeP = bone('knee+', 0, kneeY - hipY, 0, hipP);
  const hipN = bone('hip-', -0.055 * H, hipY, 0, base), kneeN = bone('knee-', 0, kneeY - hipY, 0, hipN);
  const shP = bone('sh+', 0.125 * H, shY, 0, base), elP = bone('el+', 0, elY - shY, 0, shP);
  const shN = bone('sh-', -0.125 * H, shY, 0, base), elN = bone('el-', 0, elY - shY, 0, shN);
  const anP = bone('ankle+', 0, ankleY - kneeY, 0, kneeP), anN = bone('ankle-', 0, ankleY - kneeY, 0, kneeN);
  root.updateMatrixWorld(true);
  const skeleton = new THREE.Skeleton(bones);

  const targets = []; root.traverse(o => { if (o.isMesh && !o.isSkinnedMesh && o.geometry.attributes.position && !underHead(o, root)) targets.push(o); });
  const anyLegNamed = targets.some(o => LEG_RE.test(chainName(o, root)));
  const rootInv = new THREE.Matrix4().copy(root.matrixWorld).invert(), toRoot = new THREE.Matrix4();
  const w = new Float32Array(11), order = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  let touched = 0;

  // Pass 1: split every mesh into islands and classify them, so pass 2 can see the whole model first.
  const prep = new Map(); let armsAreIslands = false, torsoHW = 0;
  for (const o of targets) {
    const named = LEG_RE.test(chainName(o, root));
    const wantArm = anyLegNamed ? !named : true;
    toRoot.multiplyMatrices(rootInv, o.matrixWorld);
    const isl = meshIslands(o.geometry, toRoot);
    for (const b of isl.list) {
      b.arm = wantArm && Math.abs(b.cx) > 0.085 * H && b.cy < shY; b.straddle = b.x0 < -0.03 * H && b.x1 > 0.03 * H; b.side = b.cx >= 0 ? 1 : -1;
      if (b.arm) armsAreIslands = true; else if (b.straddle && b.cy > hipY) torsoHW = Math.max(torsoHW, -b.x0, b.x1);
    }
    prep.set(o, { named, wantArm, isl, fromRoot: toRoot.clone().invert() });
  }

  for (const o of targets) {
    const { named, wantArm, isl, fromRoot } = prep.get(o), vv = new THREE.Vector3();
    const geo = o.geometry, n = geo.attributes.position.count;
    const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
    const islandArms = isl.list.some(b => b.arm);
    const loose = !islandArms && armsAreIslands && torsoHW > 0;
    for (let i = 0; i < n; i++) {
      const vx = isl.P[i * 3], vy = isl.P[i * 3 + 1], b = isl.list[isl.of[i]];
      w.fill(0);
      let armW = 0;
      if (wantArm) {
        if (islandArms) armW = b.arm ? sstep(shY + 0.01 * H, shY - 0.05 * H, vy) : 0;
        else armW = (loose ? sstep(torsoHW, torsoHW + 0.03 * H, Math.abs(vx)) : sstep(0.08 * H, 0.10 * H, Math.abs(vx)))
          * sstep(shY + 0.02 * H, shY - 0.06 * H, vy) * sstep(y0 + 0.25 * H, y0 + 0.33 * H, vy);
      }
      const legW = islandArms && b.arm ? 0 : (1 - armW) * sstep(hipY + 0.02 * H, hipY - 0.06 * H, vy);
      // Clothing hanging over the thighs (jacket hem, shirt tail) is flared ~1 cm so a swinging thigh stays inside it.
      if (!named && armW === 0 && !(islandArms && b.arm) && b.y0 > kneeY) {
        const f = 0.007 * H * sstep(hipY + 0.03 * H, hipY - 0.03 * H, vy), vz = isl.P[i * 3 + 2], r = Math.hypot(vx, vz);
        if (f > 0 && r > 1e-4) { vv.set(vx + vx / r * f, vy, vz + vz / r * f).applyMatrix4(fromRoot); geo.attributes.position.setXYZ(i, vv.x, vv.y, vv.z); }
      }
      w[0] = 1 - armW - legW;
      if (armW > 0) {
        const s = (islandArms ? b.side : vx) >= 0 ? 0 : 2, e = sstep(elY + 0.03 * H, elY - 0.03 * H, vy);
        w[5 + s] = armW * (1 - e); w[6 + s] = armW * e;
      }
      if (legW > 0) {
        const bw = (0.006 + (named ? 0.019 : 0.039) * sstep(hipY - (named ? 0.08 : 0.085) * H, hipY - (named ? 0.03 : 0.05) * H, vy)) * H;
        const sp = named && !b.straddle ? (b.side > 0 ? 1 : 0) : sstep(-bw, bw, vx), k = sstep(kneeY + 0.04 * H, kneeY - 0.04 * H, vy);
        const af = k * sstep(ankleY + 0.07 * H, ankleY + 0.01 * H, vy);
        w[1] = legW * sp * (1 - k); w[2] = legW * sp * (k - af); w[9] = legW * sp * af;
        w[3] = legW * (1 - sp) * (1 - k); w[4] = legW * (1 - sp) * (k - af); w[10] = legW * (1 - sp) * af;
      }
      order.sort((a, b2) => w[b2] - w[a]);
      const sum = w[order[0]] + w[order[1]] + w[order[2]] + w[order[3]] || 1;
      for (let j = 0; j < 4; j++) { si[i * 4 + j] = order[j]; sw[i * 4 + j] = w[order[j]] / sum; }
      if (armW > 0 || legW > 0) touched++;
    }
    geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(si, 4));
    geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(sw, 4));
    const sm = new THREE.SkinnedMesh(geo, o.material);
    sm.name = o.name; sm.userData = o.userData; sm.position.copy(o.position); sm.quaternion.copy(o.quaternion); sm.scale.copy(o.scale);
    sm.castShadow = true; sm.frustumCulled = false;
    const parent = o.parent; parent.add(sm); parent.remove(o);
    root.updateMatrixWorld(true); sm.bind(skeleton);
  }
  if (!touched) return null;
  const legLen = hipY - y0;
  return { hipP, kneeP, hipN, kneeN, anP, anN, shP, elP, shN, elN, H, legLen, footH: ankleY - y0, thigh: hipY - kneeY, shin: kneeY - ankleY,
    cycleLen: 4 * legLen * Math.sin(rad(WALK.stride)) };   // ground covered by one full gait cycle (two steps)
}

/* ------------------------------------------------------------------ poses
   A pose is a flat bag of numbers, so any two can be mixed. Metres and radians.
   P is the +x limb, N the -x one. hip, arm: + is forward. knee, el: + is bent. out: + is away from the body.
   hx, hy, hz: head nod (down), turn, tilt. yaw: which way the whole figure faces. toe: + points the toes down. */
export const newPose = () => ({ x: 0, y: 0, z: 0, lean: 0, roll: 0, yaw: 0, toe: 0,
  hipP: 0, kneeP: 0, hipN: 0, kneeN: 0, armP: 0, outP: 0, elP: 0, armN: 0, outN: 0, elN: 0, hx: 0, hy: 0, hz: 0 });
export const resetPose = p => { for (const k in p) p[k] = 0; return p; };
export function mixPose(a, b, t, out) { for (const k in out) out[k] = a[k] + (b[k] - a[k]) * t; return out; }   // out may be a or b

/* phase: gait angle in radians. amt: 0 = standing, 1 = full walk; everything blends between the two. */
export function walkPose(rig, phase, amt, out) {
  resetPose(out);
  const s = Math.sin(phase), c = Math.cos(phase), A = rad(WALK.stride) * amt, k = rig.H / 1.66;
  out.x = WALK.sway * 0.01 * k * amt * -c;
  out.y = -WALK.bob * (rig.legLen - rig.footH) * (1 - Math.cos(A * Math.abs(s)));
  out.lean = rad(WALK.lean) * amt; out.roll = rad(WALK.tilt) * amt * c;
  const K = rad(WALK.knee) * amt, Sw = rad(WALK.arms) * amt, E = rad(WALK.elbow) * amt;
  out.hipP = A * s; out.hipN = -A * s;
  out.kneeP = K * Math.max(0, c); out.kneeN = K * Math.max(0, -c);
  out.armP = -Sw * s; out.armN = Sw * s;                       // arms swing against the legs
  out.elP = E * (0.35 + 0.65 * (0.5 - 0.5 * s)); out.elN = E * (0.35 + 0.65 * (0.5 + 0.5 * s));
  out.outP = out.outN = rad(WALK.armOut) * amt;
  return out;
}

export function applyPose(rig, body, head, p) {
  body.position.set(p.x, p.y, p.z); body.rotation.set(p.lean, 0, p.roll);
  if (head) head.rotation.set(p.hx, p.hy, p.hz);
  if (!rig) return;
  rig.hipP.rotation.x = -p.hipP; rig.kneeP.rotation.x = p.kneeP; rig.anP.rotation.x = p.hipP - p.kneeP - p.lean + p.toe;   // sole stays level
  rig.hipN.rotation.x = -p.hipN; rig.kneeN.rotation.x = p.kneeN; rig.anN.rotation.x = p.hipN - p.kneeN - p.lean + p.toe;
  rig.shP.rotation.set(-p.armP, 0, p.outP); rig.elP.rotation.x = -p.elP;
  rig.shN.rotation.set(-p.armN, 0, -p.outN); rig.elN.rotation.x = -p.elN;
}
