// Hero: the two figurines walk in from the sides, stop under their names and start their own loop (see moves.js).
// Drag one to push it around; let go and it walks back to its mark and picks the loop up again.
// Without WebGL (or if a model fails to load) the hero is simply the type.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { buildRig, newPose, walkPose, mixPose, applyPose } from './rig.js';
import { speechPose, tomaPose } from './moves.js';

const hero = document.querySelector('.hero');
const canvas = document.getElementById('figures');
const hint = document.getElementById('hero-hint');
const nameEl = hero.querySelector('.hero-name'), captions = hero.querySelector('.hero-blurbs');
const still = matchMedia('(prefers-reduced-motion: reduce)').matches;

const FOV = 22;            // long lens: little distortion on figures standing off-centre
const FIG_H = 1.78;        // metres
const FIG_FRAC_MAX = 0.66; // largest share of the hero's height a figure may take
const MIN_W = 2.0;         // metres of scene that must always fit across the hero (keeps both figures whole on phones)
const WALK_SPEED = 1.35;   // m/s
const GRAB_R = 0.42;       // metres either side of a figure where a press takes hold of it
const rad = THREE.MathUtils.degToRad, clamp = THREE.MathUtils.clamp;
const sstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
const turnTo = (from, to) => Math.atan2(Math.sin(to - from), Math.cos(to - from));   // shortest way round

const FIGS = [
  { url: '/models/marius-hero.glb', side: -1, loop: speechPose },
  { url: '/models/toma-hero.glb', side: 1, loop: tomaPose },
];

let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch { /* no WebGL: type-only hero */ }
if (renderer) start();

function start() {
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(1.5, 5, 4); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
  key.shadow.camera.near = 0.5; key.shadow.camera.far = 20; key.shadow.radius = 6;
  scene.add(key, key.target, new THREE.HemisphereLight(0xffffff, 0xe8e2da, 1.0));   // fill: keeps the faces from going muddy
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 60).rotateX(-Math.PI / 2), new THREE.ShadowMaterial({ opacity: 0.24 }));
  floor.receiveShadow = true; scene.add(floor);
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);

  let viewW = 4, viewH = 3, markX = 1, floorFrac = 0.2, rect = hero.getBoundingClientRect();
  function fit() {
    const w = hero.clientWidth, h = hero.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    rect = hero.getBoundingClientRect();
    // The figures stand between the name and the captions: floor just above the captions, hair just under the letters.
    const floorPx = rect.bottom - captions.getBoundingClientRect().top + h * 0.025;
    const nameBottom = nameEl.getBoundingClientRect().bottom - rect.top;
    floorFrac = floorPx / h;
    const figFrac = clamp((h - floorPx - nameBottom + h * 0.015) / h, 0.25, FIG_FRAC_MAX);
    const aspect = w / h;
    viewH = Math.max(FIG_H / figFrac, MIN_W / aspect); viewW = viewH * aspect;
    const camY = viewH * (0.5 - floorFrac);
    camera.aspect = aspect; camera.position.set(0, camY, viewH / (2 * Math.tan(rad(FOV / 2)))); camera.lookAt(0, camY, 0);
    camera.updateProjectionMatrix();
    markX = viewW / 4;                                   // the middle of each half
    const sc = key.shadow.camera, half = viewW / 2 + 1.5;
    sc.left = sc.bottom = -half; sc.right = sc.top = half; sc.updateProjectionMatrix();
    for (const f of FIGS) if (f.state === 'idle') f.x = f.side * markX;
  }

  /* ------------------------------------------------------------ loading */
  const loader = new GLTFLoader();
  const load = f => new Promise((resolve, reject) => loader.load(f.url, gltf => {
    const root = gltf.scene; root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root), c = box.getCenter(new THREE.Vector3());
    f.h = box.max.y - box.min.y;
    f.head = root.getObjectByName('Head');
    root.traverse(o => { if (o.isMesh) o.castShadow = true; });
    f.rig = buildRig(root, box);
    f.holder = new THREE.Group(); f.body = new THREE.Group();
    root.position.set(-c.x, -box.min.y, -c.z);          // feet on the floor, centred on the holder
    f.body.add(root); f.holder.add(f.body); f.holder.visible = false; scene.add(f.holder);
    Object.assign(f, { state: 'wait', x: 0, vx: 0, yaw: 0, phase: f.side > 0 ? Math.PI : 0, amt: 0, t: 0, act: 0, lookX: 0, lookY: 0 });
    resolve(f);
  }, undefined, reject));

  Promise.allSettled(FIGS.map(load)).then(results => {
    const ok = results.filter(r => r.status === 'fulfilled').map(r => r.value);
    if (!ok.length) return;
    fit();
    for (const f of ok) {
      f.holder.visible = true;
      if (still || !f.rig) { f.state = 'idle'; f.x = f.side * markX; }
      else { f.state = 'walk'; f.x = f.side * (viewW / 2 + 0.6); f.yaw = -f.side * Math.PI / 2; f.amt = 1; }
      f.holder.position.x = f.x; f.holder.rotation.y = f.yaw;
    }
    renderer.compile(scene, camera);
    hero.classList.add('figures-ready');
    new ResizeObserver(fit).observe(hero); new ResizeObserver(fit).observe(captions);
    document.fonts?.ready.then(fit);
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; run(); }).observe(hero);
    document.addEventListener('visibilitychange', run);
  });

  /* ------------------------------------------------------------ pointer */
  const pointer = { x: 0, y: 0 };
  const worldX = cx => ((cx - rect.left) / rect.width - 0.5) * viewW;
  const screenX = x => rect.left + rect.width * (0.5 + x / viewW);
  const floorY = () => rect.top + rect.height * (1 - floorFrac);
  // The figure under a point of the page, if it is one that can be taken hold of.
  function figAt(cx, cy) {
    const reach = Math.max(GRAB_R * rect.width / viewW, 30), floor = floorY();
    let best = null, bestD = reach;
    for (const f of FIGS) {
      if (!f.holder || f.state === 'wait') continue;
      const d = Math.abs(cx - screenX(f.x)), top = floor - (f.h * 1.25) * rect.height / viewH;
      if (d < bestD && cy > top && cy < floor + 24) { best = f; bestD = d; }
    }
    return best;
  }

  let drag = null;
  addEventListener('pointermove', e => {
    pointer.x = e.clientX; pointer.y = e.clientY;
    if (!drag && e.pointerType !== 'touch') hero.classList.toggle('can-grab', !e.target.closest?.('a') && !!figAt(e.clientX, e.clientY));
  }, { passive: true });
  addEventListener('scroll', () => { rect = hero.getBoundingClientRect(); }, { passive: true });

  hero.addEventListener('pointerdown', e => {
    if (e.button || e.target.closest('a')) return;
    const f = figAt(e.clientX, e.clientY);
    if (!f) return;
    pointer.x = e.clientX; pointer.y = e.clientY;
    drag = { f, id: e.pointerId, off: worldX(e.clientX) - f.x, from: e.clientX, moved: 0 };
    f.state = 'push'; hero.setPointerCapture(e.pointerId); hero.classList.add('dragging');
  });
  hero.addEventListener('pointermove', e => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.moved = Math.max(drag.moved, Math.abs(e.clientX - drag.from));
    if (drag.moved > 24 && hint) hint.classList.add('done');
  });
  const endDrag = e => {
    if (!drag || e.pointerId !== drag.id) return;
    const f = drag.f; drag = null; hero.classList.remove('dragging');
    if (still || !f.rig) { f.state = 'idle'; f.x = f.side * markX; f.vx = 0; }   // no walk to show: put it back
    else f.state = 'walk';
  };
  hero.addEventListener('pointerup', endDrag); hero.addEventListener('pointercancel', endDrag);

  /* ---------------------------------------------------------- animation */
  const clock = new THREE.Clock();
  const walk = newPose(), loop = newPose(), pose = newPose();
  let visible = true, running = false, hinted = false;
  function run() {
    const on = visible && !document.hidden;
    if (on === running) return;
    running = on; clock.getDelta();
    renderer.setAnimationLoop(on ? tick : null);
  }

  function tick() {
    const dt = Math.min(clock.getDelta(), 0.05), k = n => 1 - Math.exp(-dt * n);
    let allIdle = true;
    for (const f of FIGS) {
      if (!f.holder) continue;
      const target = f.side * markX, cycle = f.rig ? f.rig.cycleLen : 1;
      let wantYaw = 0, yawRate = 7;
      if (f.state === 'walk') {
        const rem = Math.abs(target - f.x), ease = clamp(rem / 0.45, 0, 1);    // slow down over the last half-step
        const step = Math.min(rem, WALK_SPEED * dt * Math.max(ease, 0.2));
        const dir = Math.sign(target - f.x);
        f.x += dir * step;
        f.phase += Math.PI * 2 * step / cycle;                                 // feet keep pace with the ground
        f.amt = ease;
        if (rem > 0.3) wantYaw = dir * Math.PI / 2;                            // face the way they walk, then turn to the front
        if (rem < 0.004) { f.state = 'idle'; f.x = target; f.t = 0; }          // home: the loop starts over
        allIdle = false;
      } else if (f.state === 'push') {
        const lim = Math.max(viewW / 2 - 0.25, 0.3);
        const nx = f.x + (clamp(worldX(pointer.x) - drag.off, -lim, lim) - f.x) * k(16);
        if (dt > 0) f.vx += ((nx - f.x) / dt - f.vx) * k(10);
        f.phase += Math.PI * 2 * Math.abs(nx - f.x) / cycle;
        f.x = nx;
        const speed = Math.abs(f.vx);
        f.amt += (sstep(0.05, 0.9, speed) - f.amt) * k(10);
        wantYaw = Math.sign(f.vx) * Math.PI / 2 * sstep(0.1, 0.7, speed);      // shoved along: turns the way it is going
        yawRate = 9;
      } else if (f.state === 'idle') {
        f.amt += (0 - f.amt) * k(8);
        if (!still) f.t += dt;
      } else allIdle = false;

      const looping = f.state === 'idle' && !still && !!f.rig;
      f.act += ((looping ? 1 : 0) - f.act) * k(looping ? 4 : 10);
      if (f.state !== 'push') f.vx += (0 - f.vx) * k(8);

      if (f.rig) walkPose(f.rig, f.phase, f.amt, walk);
      if (f.rig && f.act > 0.001) {
        mixPose(walk, f.loop(f.rig, f.t, f.side, loop), f.act, pose);
        if (f.state === 'idle') { wantYaw = pose.yaw; yawRate = 10; }
      } else mixPose(walk, walk, 0, pose);
      const shove = sstep(0.1, 1.6, Math.abs(f.vx));                           // off balance: tips forward, arms out
      pose.lean += 0.14 * shove; pose.outP += 0.6 * shove; pose.outN += 0.6 * shove;

      f.yaw = turnTo(0, f.yaw + turnTo(f.yaw, wantYaw) * k(yawRate));         // kept within one turn
      f.holder.position.x = f.x; f.holder.rotation.y = f.yaw;

      const facing = turnTo(0, f.yaw);
      let ty = 0, tx = 0;
      if (f.state === 'push' && Math.abs(facing) < 1.2) {                      // held: keeps an eye on the hand
        const fy = floorY() - rect.height * (f.h * 0.9) / viewH;
        ty = clamp(clamp((pointer.x - screenX(f.x)) / (rect.width * 0.5), -1, 1) * 0.75 - facing, -0.85, 0.85);
        tx = clamp((pointer.y - fy) / (rect.height * 0.7), -1, 1) * 0.3;
      }
      f.lookY += (ty - f.lookY) * k(5); f.lookX += (tx - f.lookX) * k(5);
      pose.hy += f.lookY; pose.hx += f.lookX;

      applyPose(f.rig, f.body, f.head, pose);
    }
    if (allIdle && !hinted) { hinted = true; hero.classList.add('hint-on'); }
    renderer.render(scene, camera);
  }

  // handle for scripted checks from the console
  window.__hero = { FIGS, camera, scene, renderer, tick };
}
