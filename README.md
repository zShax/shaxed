# shaxed - Marius hero figurine

Stylized 3D figurine for the website hero.

```
public/models/marius-hero.glb   <- the model (drop into any site's /public/models)
avatar/build_avatar.py          <- Blender script that generates it
avatar/renders/                 <- preview renders (front, 3/4, side, back, close-ups)
reference/                      <- reference photo(s)
```

## Model facts
- Units: metres, ~1.66 m tall, origin on the floor between the feet, Y-up, facing +Z.
- 53,498 triangles, 8 PBR materials, ~1.6 MB.
- Nodes: `Head` (pivot at the base of the neck) with children `Hair`, `Glasses`, `Goatee`;
  plus `Body`, `Blazer`, `Shirt`, `BowTie`, `Trousers`, `Shoes`.
- Colours of skin/fabric/shoes live in per-vertex colours (`COLOR_0`) multiplied with the material,
  which three.js applies automatically.

## react-three-fiber

```jsx
import { useGLTF } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'

export function Marius() {
  const { scene } = useGLTF('/models/marius-hero.glb')
  useFrame(({ pointer }) => {
    const head = scene.getObjectByName('Head')
    if (!head) return
    // look toward the mouse, gently
    head.rotation.y += (pointer.x * 0.5 - head.rotation.y) * 0.08
    head.rotation.x += (-pointer.y * 0.25 - head.rotation.x) * 0.08
  })
  return <primitive object={scene} />
}
useGLTF.preload('/models/marius-hero.glb')
```

Frame the camera around y = 0.85 m for full body, or y = 1.5 m for a head-and-shoulders hero.

## Model viewer (`preview.html`)
Run `preview.bat` (serves this folder on http://localhost:8123 and opens the viewer).

- **Models**: every `.glb` / `.gltf` in `public/models/` is listed; tick any number of them to show them side by side
  (or press `1`-`9`). Drop a new file in the folder and click *Rescan* (it also rescans when the window regains focus).
  `preview.html?model=path/to/file.glb` adds a model from elsewhere.
- **Walk** (Space): speed, stride, knee/arm/elbow bend, arm spread, bob, hip sway, tilt and lean sliders, plus options for the
  scrolling floor, head-follows-mouse, synced gaits and matching model heights. Settings are remembered in the browser.
- Models without their own animation are auto-rigged at load time (hips, knees, shoulders, elbows weighted from body
  proportions; trousers/shoes are treated as legs) and driven by a procedural walk cycle. Models that ship an animation
  clip (preferring one named like "walk") play it instead. Non-humanoid models just bob.
- How the auto-rig decides what moves: each mesh is split into connected islands. An island out to the side of the body
  (sleeve, cuff, hand, ring) goes wholly to that arm, so the jacket flanks and torso stay put. Trouser legs and shoes go
  wholly to one leg. Everything else below the hips (pelvis, jacket hem, shirt tail) follows the thighs, and the jacket
  hem is flared ~1 cm so the swinging thighs stay inside it. Meshes whose sleeves are not separate pieces fall back to a
  position-based rule.
- The folder listing relies on the server providing a directory index (`python -m http.server` does). Otherwise put an
  `index.json` array of file names in `public/models/`.

## Rebuild
Needs Blender 4.5 (`winget install BlenderFoundation.Blender.LTS.4.5`):

```
blender -b -P avatar/build_avatar.py                 # build + export + previews
blender -b -P avatar/build_avatar.py -- --no-render  # export only
```

## Second model: Daniel

```
public/models/daniel-hero.glb   <- the model
avatar/build_daniel.py          <- Blender script that generates it (adapted from build_avatar.py)
avatar/renders/daniel_*.png     <- preview renders (sheet = front / 3-4 / side / back)
reference/ref-daniel-01.webp    <- reference photo
```

- Units: metres, 1.72 m tall, origin on the floor between the feet, Y-up, facing +Z.
- 51,826 triangles, 6 PBR materials, ~1.8 MB. `check_glb.py` passes with no FAIL.
- Nodes: `Head` (pivot at the base of the neck) with children `Hair` and `Beard`; plus `Body`, `Blazer`, `Shirt`
  (graphic tee), `Trousers` (cropped jeans) and `Shoes`. Same names as Marius, so the same code and the viewer's
  auto-rig work for both.
- Look: long swept-back light-brown hair, full grey-brown beard, open blue pinstripe blazer, tee with a teal print,
  loose cropped jeans, bare calves, white lace-up shoes with a block heel. Neutral standing pose with a slight head tilt
  (the reference photo is a leaning pose; this one is rig-friendly).
- Build: `blender -b -P avatar/build_daniel.py` (add `-- --no-render` to skip previews).
