# shaxed - Marius Toma's site and hero figurines

## The website

A CV site with the Marius and Toma figurines in the hero, a list of live projects, and a blog with its own backend.
Node + Express, no build step. Blog posts live in one SQLite file (`data/blog.db`, Node's built-in driver).

```
server/index.js      <- routes: pages, /api, static files
server/cv.js         <- default CV text and project links (the admin CV tab overrides it)
server/cvstore.js    <- the CV the site shows: saved edits, else cv.js
public/js/cv-schema.js <- CV fields: drives the admin form and save checks
server/render.js     <- the HTML of every page
server/db.js         <- blog storage
server/auth.js       <- admin sign-in (one password, signed cookie)
public/css/site.css  <- all styles
public/js/hero.js    <- the 3D hero (three.js); rig.js = auto-rig + walk cycle shared with preview.html
public/js/admin.js   <- the /admin page
```

### Run it locally
Needs Node 22.13 or newer.

```
npm install
copy .env.example .env      (set ADMIN_PASSWORD, 8+ characters)
npm run dev                 -> http://localhost:3000
```

Write posts at `/admin` (Markdown, live preview, draft or published). Edit the CV text at `/admin#cv`; it is saved in the same SQLite file. Public pages: `/`, `/blog`, `/blog/<slug>`,
`/blog/feed.xml`. JSON: `GET /api/posts`, `GET /api/posts/<slug>`; writes need the admin session.

### Deploy (Linux VPS, Docker + pm2)
The image runs the app under `pm2-runtime`; nginx on the host proxies to it.

```
git clone <repo> shaxed && cd shaxed
cp .env.example .env && nano .env        # SITE_URL, ADMIN_PASSWORD, SESSION_SECRET (openssl rand -hex 32)
docker compose up -d --build             # listens on 127.0.0.1:3000
sudo cp deploy/nginx.conf /etc/nginx/sites-available/shaxed.com   # edit the domain, enable it, reload nginx, run certbot
```

- Update: `git pull && docker compose up -d --build`. Posts stay: they are in the `blogdata` volume.
- Back up the blog: `docker compose cp site:/app/data ./blog-backup`.
- Logs: `docker compose logs -f site`.
- Without Docker: `npm ci --omit=dev`, then `pm2 start ecosystem.config.cjs && pm2 save` (reads `.env` from the folder).
- Only `marius-hero.glb` and `toma-hero.glb` are served and copied into the image; other models stay private.

## The figurines

Stylized 3D figurine for the website hero.

```
public/models/marius-hero.glb   <- the model (drop into any site's /public/models)
avatar/build_avatar.py          <- Blender script that generates it
avatar/renders/                 <- preview renders (front, 3/4, side, back, close-ups)
reference/                      <- reference photo(s)
```

## Model facts
- Marius and Toma are the same person, so they share one figure: the same head / face, hands, proportions, A-pose and
  body scale (the code for those parts is the same in `build_avatar.py` and `build_toma.py`: keep it in sync). Only the
  look differs: Marius has curly hair, round glasses, a goatee, a navy blazer over a white shirt, a tartan bow tie, dark
  trousers and tan suede shoes.
- Units: metres, ~1.75 m to the top of the hair (same body as Toma, taller hair), origin on the floor between the feet,
  Y-up, facing +Z.
- ~61k triangles, 7 PBR materials, ~1.9 MB. All surfaces are smooth lofts: no cloth normal map.
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
  hem is flared ~1 cm so the swinging thighs stay inside it (pieces that reach below the knees, such as bare legs, are
  not flared: that would push the ankles out of the shoes). Meshes whose sleeves are not separate pieces fall back to a
  position-based rule.
- Feet: an ankle joint keeps the soles level, so toes and heels do not dip through the floor.
- For scripted checks the page exposes `__viewer` in the browser console (settings, camera, `setPhase()` to freeze the
  gait, `grab()` for a PNG of the current view).
- The folder listing relies on the server providing a directory index (`python -m http.server` does). Otherwise put an
  `index.json` array of file names in `public/models/`.

## Rebuild
Needs Blender 4.5 (`winget install BlenderFoundation.Blender.LTS.4.5`):

```
blender -b -P avatar/build_avatar.py                 # build + export + previews
blender -b -P avatar/build_avatar.py -- --no-render  # export only
blender -b -P avatar/build_avatar.py -- --shots front,back   # only these previews
```
Previews are written to `avatar/renders/marius_*.png` (the older `it5_*.png` show the previous Marius).

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

## Third model: Toma (stylized collectible figurine)

```
public/models/toma-hero.glb        <- the model
avatar/build_toma.py               <- Blender script
avatar/make_toma_textures.py       <- Pillow script that draws the decals (needs `pip install pillow`)
avatar/extract_backprint.py        <- lifts the tee's back print out of reference/ref-toma-back.webp
avatar/toma_backprint_prompt.md    <- text prompt describing the back print, for an AI that textures 3D models
avatar/textures/toma_*             <- shirt (2048 px JPEG) / shorts / shoes decal atlases (packed into the GLB), back print decal
avatar/renders/toma_*.png          <- preview renders
```

- Young man, A-pose, symmetrical: slicked-back hair with a small man bun + hair tie + a few flyaway strands, clean-shaven,
  calm downward gaze. Oversized cream tee (STAR print down the figure's right sleeve, chest print, graffiti tag at the lower
  hem on the viewer's left, big red-framed DREAM / THIEF butterfly print on the back), black shorts with a tonal UA logo on the right thigh, Thrasher-flame Sk8-Hi high-tops, gold curb
  chain, wooden bead bracelet + white sport watch on the left wrist.
- Logos, lettering and flames are texture decals, not geometry.
- GLB nodes: `Head` (skin, face; parent of `hair`, `bun`), `Body`, `hair`, `bun`, `shirt`, `shorts`, `shoes`, `chain`,
  `bracelet`, `watch`.
- ~56k triangles, 7 materials, 3 textures (shirt 2048 px, shorts and shoes 1024 px), ~3.3 MB.
- The back print is taken from the photo: un-warped, reduced to its black and red inks, lettering re-set in type. The hollow
  lettering down the two sides is not readable in the photo, so "DREAM THIEF" there is a guess.
- The shorts stay inside the tee above its hem and the ankles sit in the middle of the shoe collars, so nothing pokes
  through, standing or walking.
- Build: `python avatar/extract_backprint.py`, `python avatar/make_toma_textures.py`, then `blender -b -P avatar/build_toma.py`
  (add `-- --no-render` to skip previews, `-- --shots back,shoes` to render only some).
