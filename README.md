# superway

## game/ — M99 Free Roam
An endless, empty UK-style dual carriageway (three lanes and a hard shoulder each way) with overbridges,
gantry signs, buildings and trees, and just the muscle sedan. Plain HTML + three.js, no build step.

- **Keyboard / mouse:** `W A S D` drive, arrow keys look around, `Q`/`E` top speed −/+ 5, `Space` brake,
  `C` camera, `R` reset, `U` mph/km/h, `G` graphics, mouse clicks the on-screen buttons.
- **Touch (iPhone / iPad):** ◀ ▶ steer, GAS / BRAKE pedals (hold BRAKE when stopped to reverse), drag to look around.
- **Top speed:** set it any time with − / + or by typing in the box top-right; it is remembered on that device.
- The HUD and camera adapt to the screen shape (phone landscape, 16:9, iPad 4:3, portrait).

Run it locally by serving the folder (the car model and textures are loaded by URL):
```
cd game && python3 -m http.server 8000   # then open http://localhost:8000
```
GitHub Pages works too: point Pages at this branch and open `/game/`.

## car/ — the muscle sedan
- `muscle_sedan.blend` — the Blender 5.x scene (car, studio, six cameras)
- `sedan.py` (+ `studio.py`, `wheels.py`) — builds the car from scratch: `python3 sedan.py all --samples 64`
- `export_game_glb.py`, `glb_to_json.py` — export the lightweight game model (`game/car.json`)
- `tools/render_tree_sprite.py` — renders the tree billboards used in the game
- `renders/` — final studio renders

See `game/CREDITS.md` for the third-party assets.
