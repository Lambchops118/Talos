import logging
import time

from door_monitor import DoorEvent, DoorMonitor, DoorMonitorConfig


def print_event(event: DoorEvent) -> None:
    print(
        f"[{time.strftime('%H:%M:%S', time.localtime(event.timestamp))}] "
        f"{event.event_type.upper()} conf={event.confidence:.2f} meta={event.metadata}"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    config = DoorMonitorConfig(
        camera_index=0,
        debug_display=True,
        fps=15,
        buffer_seconds=30,
        snippet_seconds=5,
    )

    monitor = DoorMonitor(config)
    monitor.register_callback(print_event)

    monitor.start()
    print("Door monitor running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
            events = monitor.get_recent_events()
            if events:
                latest = events[-1]
                if latest.event_type in {"enter", "exit"}:
                    snippet = monitor.get_recent_snippet(seconds=5)
                    print(f"Recent snippet frames: {len(snippet)}")
    except KeyboardInterrupt:
        print("Stopping monitor...")
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()