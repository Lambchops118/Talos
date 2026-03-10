
# computer_vision2 Door Monitor

Reusable OpenCV-based door monitoring subsystem with:

- hinged door state estimation (closed/opening/open/closing)
- HOG person detection
- Kalman multi-object tracking
- rule-based temporal entry/exit reasoning
- frame snippet buffering and event callbacks/queue

## Quick start

```python
from Peripherals.computer_vision2 import DoorMonitor, DoorMonitorConfig

config = DoorMonitorConfig(calibration_path="door_calibration.json")
monitor = DoorMonitor(config)

monitor.register_callback(lambda event: print(event))
monitor.start()

print(monitor.get_door_state())
print(monitor.get_recent_events(limit=5))
monitor.get_recent_snippet(seconds=5, save_to="clips/recent.mp4")

monitor.stop()
```

## Calibration JSON

Expected keys:

- `frame_corners`
- `hinge_side`
- `latch_side`
- `closed_edge_line`
- `doorway_polygon`
- `interior_polygon`
- `exterior_polygon`

`closed_edge_line` is required for robust hinge-angle estimation.