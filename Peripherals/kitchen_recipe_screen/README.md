# Kitchen Recipe Screen

Browser-based kiosk display for recipes, timers, and kitchen task prompts.

The app is designed for a `1920x1080` screen and styled to match the old `InfoPanel` green-phosphor look: black background, CRT glow, scan lines, and a slight curved-screen feel.

## What It Does

- Shows recipe title, subtitle, servings, ingredients, steps, notes, and timer state.
- Shows the top-row link status indicator used by TALOS.
- Includes a large countdown timer with on-screen controls.
- Exposes a small HTTP API so TALOS can update the display.
- Persists the last state to `runtime/kitchen_state.json`.

## Run The Server

```bash
cd /Users/jacksal1/Desktop/Talos/Talos
python3 peripherals/kitchen_recipe_screen/main.py --host 0.0.0.0 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## Launch In Chromium Kiosk Mode

```bash
cd /Users/jacksal1/Desktop/Talos/Talos/peripherals/kitchen_recipe_screen
./launch_chromium_kiosk.sh
```

Optional environment overrides:

```bash
KITCHEN_SCREEN_URL=http://127.0.0.1:8765 ./launch_chromium_kiosk.sh
CHROMIUM_BIN=chromium-browser ./launch_chromium_kiosk.sh
```

## HTTP API

### `GET /api/health`

Returns:

```json
{"ok": true, "app": "kitchen_recipe_screen"}
```

### `GET /api/state`

Returns the current rendered state, including a resolved timer.

### `POST /api/state`

Partially updates the screen state. Nested dictionaries are merged. Lists are replaced.

Example:

```bash
curl -X POST http://127.0.0.1:8765/api/state \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Weeknight Pasta",
    "link_status": "LINK NOMINAL",
    "source": "TALOS",
    "servings": "4 bowls",
    "status": "Sauce simmering",
    "ingredients": [
      {"text": "1 lb pasta", "checked": false},
      {"text": "2 cups marinara", "checked": true},
      {"text": "4 cloves garlic", "checked": false}
    ],
    "steps": [
      {"text": "Salt the water and bring it to a boil.", "done": true},
      {"text": "Cook pasta until just shy of al dente.", "done": false},
      {"text": "Warm sauce with garlic and finish together.", "done": false}
    ],
    "notes": [
      "Reserve one mug of pasta water.",
      "Add basil at the very end."
    ]
  }'
```

### `POST /api/timer`

Controls the timer.

Supported actions:

- `set`
- `start`
- `pause`
- `reset`
- `add_seconds`

Example:

```bash
curl -X POST http://127.0.0.1:8765/api/timer \
  -H "Content-Type: application/json" \
  -d '{
    "action": "set",
    "label": "Roast timer",
    "duration_seconds": 1800,
    "remaining_seconds": 1800,
    "auto_start": false
  }'
```

Then:

```bash
curl -X POST http://127.0.0.1:8765/api/timer \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

## Suggested TALOS Integration

Have the agent send direct HTTP requests to:

- `POST /api/state` for recipe/ingredient/step updates
- `POST /api/timer` for countdown control
- `GET /api/state` if TALOS needs to inspect the live screen state
