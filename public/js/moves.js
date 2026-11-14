// What each figurine does while it stands on its mark. Every function fills a pose (see rig.js) for a time in seconds.
// Marius holds a speech. Toma runs on the spot, jumps twice, climbs, drops back down, and starts over.
import * as THREE from 'three';
import { newPose, resetPose, mixPose } from './rig.js';

const rad = THREE.MathUtils.degToRad, clamp = THREE.MathUtils.clamp, lerp = THREE.MathUtils.lerp;
const sstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
const TAU = Math.PI * 2;

/* Stand lower on bent legs, feet where they were. bend: thigh angle from upright. lean: torso pitch about the hips. */
function squat(rig, p, bend, lean = 0) {
  p.hipP = p.hipN = bend + lean; p.kneeP = p.kneeN = 2 * bend; p.lean = lean;
  p.y = -(rig.thigh + rig.shin) * (1 - Math.cos(bend)) - rig.legLen * (1 - Math.cos(lean));
  p.z = -rig.legLen * Math.sin(lean);
}

/* ---------------------------------------------------------------- Marius */
// One row per gesture, in degrees. N is his right arm, P his left: [raise, out, elbow]. H: head [nod, turn, tilt].
// beat: how hard the hands mark the rhythm of the sentence. d: seconds the gesture is held.
const SPEECH = [
  { N: [38, 10, 95], P: [34, 12, 90], H: [0, 0, 0], beat: 0.5, d: 2.4 },     // both hands up: explaining
  { N: [62, 6, 28], P: [6, 4, 22], H: [-4, -10, 0], beat: 0.3, d: 2.0 },     // right arm out at the room
  { N: [42, 4, 100], P: [12, 5, 55], H: [3, 6, 0], beat: 1, d: 2.6 },        // chopping the point home
  { N: [26, 38, 55], P: [26, 38, 55], H: [-5, 0, 0], beat: 0.2, d: 2.2 },    // arms wide open
  { N: [8, 4, 25], P: [50, 2, 128], H: [8, 12, 6], beat: 0, d: 2.2 },        // hand to the chin: a pause
];
const SPEECH_LEN = SPEECH.reduce((n, g) => n + g.d, 0);

export function speechPose(rig, t, side, p) {
  resetPose(p);
  let u = t % SPEECH_LEN, i = 0; while (u >= SPEECH[i].d) u -= SPEECH[i++].d;
  const a = SPEECH[(i + SPEECH.length - 1) % SPEECH.length], b = SPEECH[i], w = sstep(0, 0.6, u);
  const g = (k, j) => rad(lerp(a[k][j], b[k][j], w));
  const beat = lerp(a.beat, b.beat, w), hit = Math.sin(t * TAU * 2.2) * beat, talk = clamp(beat * 4, 0, 1);

  p.armN = g('N', 0) + rad(4) * hit; p.outN = g('N', 1); p.elN = g('N', 2) + rad(12) * hit;
  p.armP = g('P', 0) + rad(2) * hit; p.outP = g('P', 1); p.elP = g('P', 2) + rad(6) * hit;

  const shift = Math.sin(t * 0.75);                                  // weight from one foot to the other
  p.x = 0.008 * rig.H * shift; p.roll = -0.012 * shift;
  p.lean = 0.015 + 0.012 * Math.sin(t * 1.1 + 0.4);
  p.yaw = -side * 0.05 + 0.16 * Math.sin(t * 0.6 - 0.6);            // the body follows the head round the room

  p.hx = g('H', 0) + 0.035 * hit + 0.012 * Math.sin(t * TAU * 4.3) * talk;
  p.hy = g('H', 1) - side * 0.08 + 0.22 * Math.sin(t * 0.6) + 0.1 * Math.sin(t * 1.37 + 1);   // eyes across the audience
  p.hz = g('H', 2) + 0.03 * Math.sin(t * 0.8 + 2);
  return p;
}

/* ------------------------------------------------------------------ Toma */
const RUN = 3.4, JUMP = 1.4, CLIMB = 4.4, DROP = 1.1, FADE = 0.22;
const climbTop = rig => 0.22 * rig.H;

function run(rig, u, side, p) {
  const ph = u * TAU * 1.5, s = Math.sin(ph), c = Math.cos(ph);
  p.hipP = rad(18 + 40 * s); p.hipN = rad(18 - 40 * s);
  p.kneeP = rad(15 + 80 * Math.max(0, c)); p.kneeN = rad(15 + 80 * Math.max(0, -c));
  p.armP = rad(10 - 40 * s); p.armN = rad(10 + 40 * s);
  p.elP = rad(85 - 10 * s); p.elN = rad(85 + 10 * s); p.outP = p.outN = rad(6);
  p.y = rig.H * (0.03 * Math.abs(s) - 0.012); p.lean = rad(8); p.roll = rad(2) * c;
  p.yaw = -side * 0.6;                                               // three-quarter view, turned to the middle
  p.hx = -0.05; p.hy = side * 0.35; p.hz = 0.03 * c;                 // eyes stay on the viewer
}

function jump(rig, u, side, p) {
  const v = u % JUMP, a = 0.4, b = 0.5, c = 1.02;                    // crouched, off the ground, back on it
  const crouch = sstep(0, a, v) * (1 - sstep(a, b, v));
  const land = v > c ? Math.sin(Math.PI * Math.pow((v - c) / (JUMP - c), 0.6)) : 0;
  const q = clamp((v - b) / (c - b), 0, 1), air = Math.sin(Math.PI * q);
  squat(rig, p, rad(40) * crouch + rad(30) * land, rad(16) * crouch + rad(10) * land);
  const tuck = rad(24) * air;
  p.hipP += tuck; p.hipN += tuck; p.kneeP += 2 * tuck; p.kneeN += 2 * tuck; p.toe = rad(30) * air;
  p.y += 4 * 0.17 * rig.H * q * (1 - q);
  p.armP = p.armN = rad(-40 * sstep(0, a, v) + 190 * sstep(a - 0.02, b + 0.1, v) - 100 * sstep(b + 0.2, c + 0.1, v) - 45 * sstep(c, JUMP, v));
  p.elP = p.elN = rad(20); p.outP = p.outN = rad(6 + 10 * air);
  p.hx = 0.15 * crouch - 0.2 * air + 0.1 * land;
}

function climb(rig, u, side, p) {
  const e = sstep(0, 0.5, u), ph = u * TAU * 0.8, r = 0.5 + 0.5 * Math.sin(ph);   // r: how far the P hand has reached
  p.armP = e * rad(lerp(75, 165, r)); p.elP = e * rad(lerp(110, 20, r)); p.outP = e * rad(8 + 6 * r);
  p.armN = e * rad(lerp(165, 75, r)); p.elN = e * rad(lerp(20, 110, r)); p.outN = e * rad(14 - 6 * r);
  p.hipN = e * rad(lerp(5, 70, r)); p.kneeN = e * rad(lerp(15, 95, r));        // the far leg steps up as the hand reaches
  p.hipP = e * rad(lerp(70, 5, r)); p.kneeP = e * rad(lerp(95, 15, r));
  p.toe = e * rad(20);
  p.y = climbTop(rig) * clamp((u - 0.3) / (CLIMB - 0.3), 0, 1) + e * 0.01 * rig.H * Math.sin(2 * ph);
  p.x = e * 0.015 * rig.H * Math.sin(ph); p.roll = e * rad(5) * Math.sin(ph); p.lean = e * rad(5);
  p.yaw = Math.PI;                                                   // back to the room, print on show
  p.hx = -0.35 * e; p.hy = 0.25 * e * Math.sin(ph);                  // watching the next hold
}

function drop(rig, u, side, p) {
  const fall = 0.38, q = clamp(u / fall, 0, 1), r = clamp((u - fall) / (DROP - fall), 0, 1), k = sstep(0, 1, r);
  const hit = Math.sin(Math.PI * Math.pow(r, 0.6));
  squat(rig, p, rad(36) * hit, rad(10) * hit);
  const tuck = rad(22) * Math.sin(Math.PI * q);
  p.hipP += tuck; p.hipN += tuck; p.kneeP += 2 * tuck; p.kneeN += 2 * tuck; p.toe = rad(25) * (1 - q);
  p.y += climbTop(rig) * (1 - q * q);
  p.armP = p.armN = rad(lerp(lerp(120, 50, q), 5, k)); p.outP = p.outN = rad(lerp(28, 4, k)); p.elP = p.elN = rad(lerp(30, 12, k));
  p.yaw = Math.PI * (1 - sstep(0, fall + 0.1, u));                   // turns round on the way down
  p.hx = 0.2 * hit;
}

const TOMA = [[RUN, run], [JUMP * 2, jump], [CLIMB, climb], [DROP, drop]];
const TOMA_LEN = TOMA.reduce((n, m) => n + m[0], 0);
const prev = newPose();

export function tomaPose(rig, t, side, p) {
  let u = t % TOMA_LEN, i = 0; while (u >= TOMA[i][0]) u -= TOMA[i++][0];
  TOMA[i][1](rig, u, side, resetPose(p));
  if (u < FADE) {                                                    // ease out of the move before
    const m = TOMA[(i + TOMA.length - 1) % TOMA.length];
    m[1](rig, m[0] + u, side, resetPose(prev));
    mixPose(prev, p, sstep(0, FADE, u), p);
  }
  return p;
}
