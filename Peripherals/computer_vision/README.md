# Door Monitor (OpenCV)

`DoorMonitor` is a reusable Python service that monitors a webcam pointed at a door and detects **enter/exit** direction events.

## Features
- Background capture thread with clean `start()` / `stop()`.
- ROI-aware motion detection with OpenCV background subtraction.
- Direction classification by crossing a virtual line.
- Pull APIs:
  - `get_status()`
  - `get_latest_frame()`
  - `get_recent_snippet()`
  - `get_recent_events()`
  - `poll_event()`
- Push API:
  - `register_callback(on_event)`
- Rolling frame buffer for recent snippets.
- Reconnect attempts on camera failure.

## Quick start

```python
from Peripherals.computer_vision import DoorMonitor, DoorMonitorConfig, DoorEvent

config = DoorMonitorConfig(
    camera_index=0,
    roi=(300, 100, 700, 500),
    line_orientation="vertical",
    line_position=0.5,
    save_directory="door_monitor_output",
)

monitor = DoorMonitor(config)


def on_event(event: DoorEvent) -> None:
    print(event.event_type, event.timestamp, event.direction)

monitor.register_callback(on_event)
monitor.start()

frame = monitor.get_latest_frame()
snippet_path = monitor.get_recent_snippet(seconds=5)
events = monitor.get_recent_events(limit=10)

monitor.stop()
```

## Demo
Run the demo:

```bash
python -m Peripherals.computer_vision.demo
```

## Calibration guide (ROI + line)
1. Start with `debug_display=True` in `DoorMonitorConfig`.
2. Leave `roi=None` first and observe moving boxes.
3. Set `roi=(x, y, w, h)` tightly around the doorway to reduce false positives.
4. Place `line_position` where a person clearly crosses once per passage.
   - vertical line for left/right motion through the doorway.
   - horizontal line for top/bottom motion.
5. Tune:
   - `min_contour_area`: increase if noise triggers events.
   - `match_distance_px`: increase if tracking fragments.
   - `debounce_seconds`: increase to reduce duplicate counts.

## Integration notes
- For push notifications, register callback with `register_callback`.
- For polling-only integration, ignore callback and call `poll_event()` or `get_recent_events()`.
- To attach evidence artifacts, provide `save_directory` (event snapshots + snippet exports).