# computer_vision_3 door monitor

This module provides a reusable, production-style local door monitoring service with:

- explicit door state estimation (`OPEN`, `CLOSED`, transitional `OPENING`/`CLOSING`),
- human detection near the doorway (OpenCV HOG detector),
- lightweight person tracking with temporal memory,
- entry/exit event reasoning tied to *door-open windows* and doorway traversal order.

## Why this is not line crossing

`enter` and `exit` are emitted only when the reasoning pipeline observes a full temporal sequence:

1. door is open (or opens into active cycle),
2. person track history includes exterior/interior + doorway,
3. ordered traversal is completed (`exterior -> doorway -> interior` for enter, inverse for exit),
4. event is debounced to avoid duplicate spam.

A simple boundary crossing or screen-edge appearance is intentionally insufficient.

## Files

- `door_monitor.py`: main module, config, frame buffer, state machine, tracker, calibration utility.
- `demo.py`: runnable demo that prints events and shows debug overlay.

## Calibration

Run interactive calibration and save JSON:

```bash
python Peripherals/computer_vision3/door_monitor.py
```

Calibration process:

1. Draw `door_roi` (the moving door panel area).
2. Draw `doorway_region` (the doorway traversal zone).
3. Draw `exterior_region` (outside side of door).
4. Draw `interior_region` (inside side of door).

Controls:

- mouse drag: draw current rectangle
- `r`: reset previous rectangle
- `q`: quit without saving unless all 4 regions were completed

When complete, calibration is saved to `Peripherals/computer_vision3/door_calibration.json`.
`DoorMonitor` now auto-loads that file on startup if it exists and contains valid JSON.
Calibration now opens the camera with the same configured frame width, frame height, and FPS as the monitor.

## Demo

```bash
python Peripherals/computer_vision3/demo.py
```

Demo behavior:

- starts background webcam capture thread,
- prints `door_open`, `door_close`, `enter`, `exit` events,
- renders debug window with ROIs, tracks, and door state,
- exports a recent debug MP4 after `enter` / `exit` events,
- stops cleanly on `Ctrl+C`.

## Integration API

`DoorMonitor` public API:

- `start()` / `stop()`
- `register_callback(func)`
- `get_latest_frame()`
- `get_recent_snippet(seconds=5)`
- `export_recent_debug_snippet(seconds=5, save_to=None)`
- `get_recent_events()`
- `get_door_state()`
- `event_queue` (`queue.Queue[DoorEvent]`) for thread-safe push integration

`DoorEvent` fields:

- `event_type` in `{"door_open", "door_close", "enter", "exit"}`
- `timestamp`, `confidence`, `metadata`
- optional `frame`, optional `snippet`

## Notes for Windows deployment

- Uses `cv2.CAP_DSHOW` for stable webcam selection on Windows.
- If your environment is noisy (lighting flicker), increase:
  - `door_state_stability_frames`
  - `door_motion_threshold`
  - `door_edge_change_threshold`
- Tune `interior_region` / `exterior_region` to avoid overlap.
