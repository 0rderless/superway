# superway

## game/ — M99 Free Roam
An endless, empty UK-style dual carriageway (three lanes and a hard shoulder each way) with overbridges,
gantry signs, buildings and trees, and just your car. Pick your car in the Garage (`Esc` or the Garage button);
new cars are added to the `CARS` list in `game/index.html` with a model (`.json`) and a picture in `game/cars/`. Plain HTML + three.js, no build step.

- **Keyboard / mouse:** `W A S D` drive, arrow keys look around, `Q`/`E` top speed −/+ 5, `Space` brake,
  `C` camera, `R` reset, `U` mph/km/h, `G` graphics, mouse clicks the on-screen buttons.
- **Touch (iPhone / iPad):** ◀ ▶ steer, GAS / BRAKE pedals (hold BRAKE when stopped to reverse), drag to look around.
- **Traffic:** `T` or the Traffic button cycles off / normal / busy. Cars, SUVs, vans, box vans, coaches and lorries
  drive in the lanes both ways, follow the vehicle ahead, overtake and move back left; every one spawns in a random colour.
- **Rocket boost:** hold `Shift` or the rocket button. It pushes past the top-speed limiter (up to 1.5x); the ring round
  the button is fuel (4 s), which refills after a second off it.
- **HUD editor:** the HUD button lets you drag every button, the speedo, the sign and the touch pedals anywhere and
  resize them. Layouts are saved on the device, separately for phone, iPad and portrait screens.
- **Top speed:** set it any time with − / + or by typing in the box top-right; it is remembered on that device.
- The HUD and camera adapt to the screen shape (phone landscape, 16:9, iPad 4:3, portrait).

Run it locally by serving the folder (the car model and textures are loaded by URL):
```
cd game && python3 -m http.server 8000   # then open http://localhost:8000
```
**Play online:** https://0rderless.github.io/superway/ (GitHub Pages, from the `main` branch; the root page opens `game/`).

## car/ — the Hellcat (widebody muscle sedan)
- `muscle_sedan.blend` — the Blender 5.x scene (car, studio, six cameras)
- `sedan.py` (+ `studio.py`, `wheels.py`) — builds the car from scratch: `python3 sedan.py all --samples 64`
- `export_game_glb.py`, `glb_to_json.py` — export the lightweight game model (`game/car.json`)
- `tools/render_tree_sprite.py` — renders the tree billboards used in the game
- `renders/` — final studio renders

## m4/ — the M4 (two-door performance coupe)
- `m4.blend` — the Blender 5.x scene; `m4.py` builds it (uses `car/studio.py` and `car/wheels.py`)
- `export_game_m4.py` — exports the game model (`game/m4.json`)
- `renders/` — final studio renders

## traffic/ — AI traffic vehicles
`traffic.py` builds all eight traffic vehicles from one script with a short card of numbers per type
(hatchback, saloon, estate, SUV, van, box van, coach, articulated lorry).
- `python3 traffic.py lineup` renders `renders/lineup.png`
- `python3 traffic.py export ../game/traffic` writes the light game models

See `game/CREDITS.md` for the third-party assets.
