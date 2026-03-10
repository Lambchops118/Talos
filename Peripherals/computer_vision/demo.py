"""Runnable demo for DoorMonitor.

Usage:
    python -m Peripherals.computer_vision.demo
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .door_monitor import DoorEvent, DoorMonitor, DoorMonitorConfig


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def on_event(event: DoorEvent) -> None:
    logging.info(
        "POKE -> event=%s track=%s confidence=%.2f direction=%s frame=%s",
        event.event_type,
        event.track_id,
        event.confidence,
        event.direction,
        event.frame_path,
    )


def main() -> None:
    output_dir = Path("./door_monitor_output")
    config = DoorMonitorConfig(
        camera_index=0,
        frame_width=1280,
        frame_height=720,
        fps_target=15.0,
        roi=None,
        line_orientation="vertical",
        line_position=0.5,
        min_contour_area=1000,
        debounce_seconds=1.5,
        buffer_duration_seconds=12,
        default_snippet_seconds=5,
        debug_display=False,
        save_directory=str(output_dir),
    )

    monitor = DoorMonitor(config)
    monitor.register_callback(on_event)
    monitor.start()

    logging.info("DoorMonitor running. Press Ctrl+C to stop.")
    last_snippet = time.time()

    try:
        while True:
            status = monitor.get_status()
            logging.info("status=%s", status)

            frame = monitor.get_latest_frame()
            if frame is not None:
                logging.info("latest_frame shape=%s", frame.shape)

            if time.time() - last_snippet >= 10:
                snippet = monitor.get_recent_snippet(seconds=5)
                logging.info("recent snippet generated at: %s", snippet)
                last_snippet = time.time()

            polled = monitor.poll_event(timeout=0.1)
            if polled:
                logging.info("polled_event=%s @ %s", polled.event_type, polled.timestamp.isoformat())

            time.sleep(2)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received; stopping monitor")
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()