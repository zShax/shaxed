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

## Rebuild
Needs Blender 4.5 (`winget install BlenderFoundation.Blender.LTS.4.5`):

```
blender -b -P avatar/build_avatar.py                 # build + export + previews
blender -b -P avatar/build_avatar.py -- --no-render  # export only
```
