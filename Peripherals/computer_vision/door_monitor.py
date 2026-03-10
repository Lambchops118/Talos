"""Door monitoring subsystem based on OpenCV.

This module provides an importable component that can be integrated into a
larger application. It offers both pull and push interaction models:

- Pull: status, latest frame, recent events, video snippets.
- Push: callback notifications when entry/exit events are detected.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np


Direction = str
EventType = str


@dataclass
class DoorMonitorConfig:
    """Configuration for :class:`DoorMonitor`."""

    camera_index: int = 0
    frame_width: int = 1280
    frame_height: int = 720
    fps_target: float = 15.0
    roi: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h
    line_orientation: str = "vertical"  # "vertical" or "horizontal"
    line_position: float = 0.5  # relative (0..1) within ROI
    min_contour_area: int = 900
    max_lost_frames: int = 12
    match_distance_px: int = 70
    debounce_seconds: float = 1.5
    buffer_duration_seconds: int = 10
    default_snippet_seconds: int = 5
    reconnect_interval_seconds: float = 2.0
    debug_display: bool = False
    save_directory: Optional[str] = None


@dataclass
class DoorEvent:
    """Structured event payload emitted when a crossing is detected."""

    event_type: EventType  # "enter" or "exit"
    timestamp: datetime
    confidence: float
    track_id: int
    direction: Direction
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[int, int]
    line_position_px: int
    frame_path: Optional[str] = None
    snippet_path: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Track:
    track_id: int
    centroid: Tuple[int, int]
    bbox: Tuple[int, int, int, int]
    lost_frames: int = 0
    last_side: int = 0
    updated_at: float = field(default_factory=time.time)


@dataclass
class FramePacket:
    timestamp: float
    frame: np.ndarray


class FrameBuffer:
    """Thread-safe circular frame buffer for recent frames."""

    def __init__(self, max_seconds: int, fps_target: float) -> None:
        maxlen = max(1, int(max_seconds * max(1.0, fps_target)))
        self._buffer: Deque[FramePacket] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, frame: np.ndarray, ts: Optional[float] = None) -> None:
        with self._lock:
            self._buffer.append(FramePacket(timestamp=ts or time.time(), frame=frame.copy()))

    def latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1].frame.copy()

    def frames_since(self, seconds: int) -> List[FramePacket]:
        threshold = time.time() - max(1, seconds)
        with self._lock:
            return [pkt for pkt in self._buffer if pkt.timestamp >= threshold]


class DoorMonitor:
    """Background OpenCV service for doorway enter/exit detection."""

    def __init__(self, config: DoorMonitorConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        self._frame_buffer = FrameBuffer(config.buffer_duration_seconds, config.fps_target)
        self._events: Deque[DoorEvent] = deque(maxlen=200)
        self._event_queue: Queue[DoorEvent] = Queue(maxsize=200)
        self._event_lock = threading.Lock()
        self._callback: Optional[Callable[[DoorEvent], None]] = None

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._capture: Optional[cv2.VideoCapture] = None

        self._latest_frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None

        self._tracks: Dict[int, Track] = {}
        self._next_track_id = 1
        self._last_event_at = 0.0

        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=30, detectShadows=True)

        self._status = {
            "running": False,
            "last_frame_ts": None,
            "last_event_ts": None,
            "reconnect_attempts": 0,
        }

    def register_callback(self, callback: Optional[Callable[[DoorEvent], None]]) -> None:
        self._callback = callback

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="DoorMonitorThread", daemon=True)
        self._thread.start()
        self._status["running"] = True
        self.logger.info("DoorMonitor started")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._release_capture()
        self._status["running"] = False
        self.logger.info("DoorMonitor stopped")

    def get_status(self) -> Dict[str, object]:
        status = dict(self._status)
        status["active_tracks"] = len(self._tracks)
        status["queued_events"] = self._event_queue.qsize()
        return status

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._latest_frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def save_snapshot(self, path: str) -> Optional[str]:
        frame = self.get_latest_frame()
        if frame is None:
            return None
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), frame)
        return str(output_path)

    def get_recent_events(self, limit: int = 10) -> List[DoorEvent]:
        with self._event_lock:
            return list(self._events)[-max(1, limit) :]

    def poll_event(self, timeout: float = 0.0) -> Optional[DoorEvent]:
        try:
            return self._event_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_recent_snippet(self, seconds: Optional[int] = None, save_to: Optional[str] = None) -> Optional[str]:
        seconds = seconds or self.config.default_snippet_seconds
        packets = self._frame_buffer.frames_since(seconds=seconds)
        if not packets:
            return None

        if save_to is None:
            directory = Path(self.config.save_directory or "./door_monitor_output")
            directory.mkdir(parents=True, exist_ok=True)
            save_to = str(directory / f"snippet_{int(time.time())}.mp4")

        self._write_snippet(packets, save_to)
        return save_to

    def _run_loop(self) -> None:
        frame_interval = 1.0 / max(1.0, self.config.fps_target)
        while not self._stop_event.is_set():
            if not self._ensure_capture():
                time.sleep(self.config.reconnect_interval_seconds)
                continue

            success, frame = self._capture.read() if self._capture else (False, None)
            if not success or frame is None:
                self.logger.warning("Frame read failed; retrying camera connection")
                self._status["reconnect_attempts"] += 1
                self._release_capture()
                time.sleep(self.config.reconnect_interval_seconds)
                continue

            now = time.time()
            self._status["last_frame_ts"] = now
            processed = self._process_frame(frame)

            with self._latest_frame_lock:
                self._latest_frame = processed
            self._frame_buffer.append(processed, ts=now)

            if self.config.debug_display:
                cv2.imshow("DoorMonitor Debug", processed)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self._stop_event.set()
                    break

            time.sleep(frame_interval)

        if self.config.debug_display:
            cv2.destroyAllWindows()

    def _ensure_capture(self) -> bool:
        if self._capture and self._capture.isOpened():
            return True

        self.logger.info("Opening camera index %s", self.config.camera_index)
        cap = cv2.VideoCapture(self.config.camera_index)
        if not cap.isOpened():
            self.logger.error("Unable to open camera index %s", self.config.camera_index)
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        cap.set(cv2.CAP_PROP_FPS, self.config.fps_target)
        self._capture = cap
        return True

    def _release_capture(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        display = frame.copy()
        roi_frame, roi_origin = self._extract_roi(frame)
        fg_mask = self._bg_subtractor.apply(roi_frame)
        fg_mask = cv2.GaussianBlur(fg_mask, (5, 5), 0)
        _, thresh = cv2.threshold(fg_mask, 180, 255, cv2.THRESH_BINARY)
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
        thresh = cv2.dilate(thresh, kernel, iterations=2)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = self._contours_to_detections(contours, roi_origin)
        self._update_tracks(detections, display)

        self._draw_overlay(display)
        return display

    def _extract_roi(self, frame: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
        if self.config.roi is None:
            return frame, (0, 0)
        x, y, w, h = self.config.roi
        x = max(0, x)
        y = max(0, y)
        w = max(1, min(w, frame.shape[1] - x))
        h = max(1, min(h, frame.shape[0] - y))
        return frame[y : y + h, x : x + w], (x, y)

    def _contours_to_detections(
        self,
        contours: Iterable[np.ndarray],
        roi_origin: Tuple[int, int],
    ) -> List[Tuple[Tuple[int, int, int, int], Tuple[int, int]]]:
        detections: List[Tuple[Tuple[int, int, int, int], Tuple[int, int]]] = []
        ox, oy = roi_origin
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.config.min_contour_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            xg, yg = x + ox, y + oy
            centroid = (xg + w // 2, yg + h // 2)
            detections.append(((xg, yg, w, h), centroid))
        return detections

    def _update_tracks(
        self,
        detections: List[Tuple[Tuple[int, int, int, int], Tuple[int, int]]],
        display: np.ndarray,
    ) -> None:
        unmatched_tracks = set(self._tracks.keys())
        for bbox, centroid in detections:
            track = self._match_track(centroid)
            if track is None:
                track = Track(track_id=self._next_track_id, centroid=centroid, bbox=bbox)
                track.last_side = self._side_of_line(centroid, display.shape)
                self._tracks[track.track_id] = track
                self._next_track_id += 1
            else:
                unmatched_tracks.discard(track.track_id)
                track.centroid = centroid
                track.bbox = bbox
                track.lost_frames = 0
                track.updated_at = time.time()

                new_side = self._side_of_line(centroid, display.shape)
                if track.last_side != 0 and new_side != 0 and track.last_side != new_side:
                    self._emit_crossing_event(track=track, old_side=track.last_side, new_side=new_side, display=display)
                track.last_side = new_side

            x, y, w, h = bbox
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 200, 0), 2)
            cv2.putText(
                display,
                f"ID:{track.track_id}",
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 200, 0),
                1,
                cv2.LINE_AA,
            )

        for track_id in list(unmatched_tracks):
            tr = self._tracks[track_id]
            tr.lost_frames += 1
            if tr.lost_frames > self.config.max_lost_frames:
                del self._tracks[track_id]

    def _match_track(self, centroid: Tuple[int, int]) -> Optional[Track]:
        best_track = None
        best_distance = float("inf")
        for track in self._tracks.values():
            dist = np.linalg.norm(np.array(track.centroid) - np.array(centroid))
            if dist < self.config.match_distance_px and dist < best_distance:
                best_distance = dist
                best_track = track
        return best_track

    def _line_position_px(self, shape: Tuple[int, int, int]) -> int:
        height, width = shape[:2]
        if self.config.roi:
            x, y, w, h = self.config.roi
            if self.config.line_orientation == "vertical":
                return int(x + w * self.config.line_position)
            return int(y + h * self.config.line_position)
        if self.config.line_orientation == "vertical":
            return int(width * self.config.line_position)
        return int(height * self.config.line_position)

    def _side_of_line(self, centroid: Tuple[int, int], shape: Tuple[int, int, int]) -> int:
        line_pos = self._line_position_px(shape)
        if self.config.line_orientation == "vertical":
            delta = centroid[0] - line_pos
        else:
            delta = centroid[1] - line_pos
        if abs(delta) < 2:
            return 0
        return 1 if delta > 0 else -1

    def _event_type_for_crossing(self, old_side: int, new_side: int) -> Tuple[EventType, Direction]:
        if self.config.line_orientation == "vertical":
            if old_side < new_side:
                return "enter", "left_to_right"
            return "exit", "right_to_left"
        if old_side < new_side:
            return "enter", "top_to_bottom"
        return "exit", "bottom_to_top"

    def _emit_crossing_event(self, track: Track, old_side: int, new_side: int, display: np.ndarray) -> None:
        now = time.time()
        if now - self._last_event_at < self.config.debounce_seconds:
            return
        self._last_event_at = now

        event_type, direction = self._event_type_for_crossing(old_side, new_side)
        confidence = min(1.0, 0.6 + 0.4 * (1.0 / max(1.0, abs(new_side - old_side))))

        snapshot_path = None
        if self.config.save_directory:
            Path(self.config.save_directory).mkdir(parents=True, exist_ok=True)
            snapshot_path = os.path.join(
                self.config.save_directory,
                f"{event_type}_{track.track_id}_{int(now)}.jpg",
            )
            cv2.imwrite(snapshot_path, display)

        event = DoorEvent(
            event_type=event_type,
            timestamp=datetime.fromtimestamp(now),
            confidence=confidence,
            track_id=track.track_id,
            direction=direction,
            bbox=track.bbox,
            centroid=track.centroid,
            line_position_px=self._line_position_px(display.shape),
            frame_path=snapshot_path,
        )

        with self._event_lock:
            self._events.append(event)
        try:
            self._event_queue.put_nowait(event)
        except Exception:
            self.logger.warning("Event queue full; dropping oldest event notification")
        self._status["last_event_ts"] = now

        if self._callback:
            try:
                self._callback(event)
            except Exception as exc:
                self.logger.exception("DoorMonitor callback error: %s", exc)

        self.logger.info("Detected %s event track=%s direction=%s", event.event_type, event.track_id, event.direction)

    def _draw_overlay(self, frame: np.ndarray) -> None:
        if self.config.roi:
            x, y, w, h = self.config.roi
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 120, 0), 1)

        line_pos = self._line_position_px(frame.shape)
        if self.config.line_orientation == "vertical":
            cv2.line(frame, (line_pos, 0), (line_pos, frame.shape[0]), (0, 0, 255), 2)
        else:
            cv2.line(frame, (0, line_pos), (frame.shape[1], line_pos), (0, 0, 255), 2)

    def _write_snippet(self, packets: List[FramePacket], save_to: str) -> None:
        if not packets:
            return
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        h, w = packets[0].frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(save_to, fourcc, max(1.0, self.config.fps_target), (w, h))
        try:
            for packet in packets:
                writer.write(packet.frame)
        finally:
            writer.release()


__all__ = ["DoorMonitor", "DoorMonitorConfig", "DoorEvent"]