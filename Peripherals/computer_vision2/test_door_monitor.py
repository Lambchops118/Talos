import time
from door_monitor import DoorMonitor, DoorMonitorConfig

def handle_event(event):
    print(f"{event.timestamp:.2f} {event.event_type} conf={event.confidence:.2f} details={event.details}")

config = DoorMonitorConfig(
    camera_index=0,
    calibration_path="Peripherals/computer_vision2/door_calibration.json",
    fps=15.0,
)

monitor = DoorMonitor(config)
monitor.register_callback(handle_event)

try:
    monitor.start()
    print("Monitor started. Press Ctrl+C to stop.")

    while True:
        print("status:", monitor.get_status())
        time.sleep(3)
        path = monitor.get_recent_snippet(seconds=5, save_to="clips/recent.mp4")
except KeyboardInterrupt:
    pass
finally:
    #path = monitor.get_recent_snippet(seconds=5, save_to="clips/recent.mp4")
    print("saved snippet:", path)
    monitor.stop()