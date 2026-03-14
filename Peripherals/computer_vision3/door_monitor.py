from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CALIBRATION_PATH = MODULE_DIR / "door_calibration.json"
DEFAULT_EXPORT_DIR = MODULE_DIR / "output"
CALIBRATION_FIELDS = (
    "door_roi",
    "doorway_region",
    "interior_region",
    "exterior_region",
    "hinge_side",
)


class DoorState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    OPENING = "opening"
    CLOSING = "closing"


@dataclass
class DoorEvent:
    event_type: str
    timestamp: float
    confidence: float
    metadata: Dict[str, object] = field(default_factory=dict)
    frame: Optional[np.ndarray] = None
    snippet: Optional[List[np.ndarray]] = None


@dataclass
class DoorMonitorConfig:
    camera_index: int = 0
    frame_width: int = 1280
    frame_height: int = 720
    fps: int = 60
    buffer_seconds: int = 30
    snippet_seconds: int = 5
    debug_display: bool = False
    export_directory: Optional[str] = None

    # Regions are [x, y, w, h]
    door_roi: Tuple[int, int, int, int] = (430, 170, 370, 480)
    doorway_region: Tuple[int, int, int, int] = (470, 170, 300, 500)
    interior_region: Tuple[int, int, int, int] = (780, 140, 480, 560)
    exterior_region: Tuple[int, int, int, int] = (120, 140, 330, 560)
    hinge_side: str = "left"  # "left" or "right"
    calibration_path: Optional[str] = None

    door_motion_threshold: float = 12.0
    door_edge_change_threshold: float = 0.035
    door_state_stability_frames: int = 8

    human_detection_stride: int = 1
    human_detection_confidence: float = 0.45
    max_track_lost_frames: int = 20
    max_track_match_distance: float = 120.0

    event_cooldown_seconds: float = 2.0

    reconnect_attempts: int = 10
    reconnect_backoff_seconds: float = 1.0

    @classmethod
    def from_json(cls, path: str | Path) -> "DoorMonitorConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key in ("door_roi", "doorway_region", "interior_region", "exterior_region"):
            if key in data and data[key] is not None:
                data[key] = tuple(data[key])
        return cls(**data)

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def calibration_file(self) -> Path:
        if self.calibration_path:
            return Path(self.calibration_path)
        return DEFAULT_CALIBRATION_PATH

    def load_calibration(self, path: str | Path | None = None) -> bool:
        calibration_path = Path(path) if path is not None else self.calibration_file()
        if not calibration_path.exists() or calibration_path.stat().st_size == 0:
            return False

        data = json.loads(calibration_path.read_text(encoding="utf-8"))
        for key in ("door_roi", "doorway_region", "interior_region", "exterior_region"):
            value = data.get(key)
            if value is not None:
                setattr(self, key, tuple(value))
        hinge_side = data.get("hinge_side")
        if hinge_side is not None:
            self.hinge_side = str(hinge_side)
        self.calibration_path = str(calibration_path)
        return True

    def save_calibration(self, path: str | Path | None = None) -> Path:
        calibration_path = Path(path) if path is not None else self.calibration_file()
        calibration_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {field: getattr(self, field) for field in CALIBRATION_FIELDS}
        temp_path = calibration_path.with_suffix(f"{calibration_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(calibration_path)
        self.calibration_path = str(calibration_path)
        return calibration_path


class FrameBuffer:
    def __init__(self, max_seconds: int, fps: int) -> None:
        self._max_frames = max(1, max_seconds * fps)
        self._buffer: Deque[Tuple[float, np.ndarray]] = deque(maxlen=self._max_frames)
        self._lock = threading.Lock()

    def add_frame(self, frame: np.ndarray, timestamp: float) -> None:
        with self._lock:
            self._buffer.append((timestamp, frame.copy()))

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1][1].copy()

    def get_recent_snippet(self, seconds: int = 5) -> List[np.ndarray]:
        cutoff = time.time() - seconds
        with self._lock:
            return [f.copy() for ts, f in self._buffer if ts >= cutoff]

    def export_snippet(self, path: str | Path, fps: float, seconds: int = 5) -> Optional[str]:
        frames = self.get_recent_snippet(seconds)
        if not frames:
            return None

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        height, width = frames[0].shape[:2]
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(1.0, float(fps)),
            (width, height),
        )
        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        return str(output_path)

    def save_snapshot(self, path: str | Path) -> bool:
        frame = self.get_latest_frame()
        if frame is None:
            return False
        return bool(cv2.imwrite(str(path), frame))


@dataclass
class PersonTrack:
    track_id: int
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[int, int]
    first_seen: float
    last_seen: float
    lost_frames: int = 0
    centroids: Deque[Tuple[int, int]] = field(default_factory=lambda: deque(maxlen=25))
    zones: Deque[str] = field(default_factory=lambda: deque(maxlen=25))
    emitted_open_cycle_id: Optional[int] = None

    def update(self, bbox: Tuple[int, int, int, int], centroid: Tuple[int, int], zone: str, timestamp: float) -> None:
        self.bbox = bbox
        self.centroid = centroid
        self.last_seen = timestamp
        self.lost_frames = 0
        self.centroids.append(centroid)
        self.zones.append(zone)


class DoorStateEstimator:
    def __init__(self, config: DoorMonitorConfig) -> None:
        self.config = config
        self.current_state = DoorState.CLOSED
        self._stable_candidate: Optional[DoorState] = None
        self._stable_count = 0
        self._background_gray: Optional[np.ndarray] = None
        self._last_open_score = 0.0

    def _crop_roi(self, frame: np.ndarray) -> np.ndarray:
        x, y, w, h = self.config.door_roi
        return frame[y : y + h, x : x + w]

    def update(self, frame: np.ndarray) -> Tuple[DoorState, float, Dict[str, float]]:
        roi = self._crop_roi(frame)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)

        if self._background_gray is None:
            self._background_gray = gray.astype(np.float32)

        cv2.accumulateWeighted(gray, self._background_gray, 0.03)
        bg_u8 = cv2.convertScaleAbs(self._background_gray)

        diff = cv2.absdiff(gray, bg_u8)
        motion_score = float(np.mean(diff))

        edges_now = cv2.Canny(gray, 80, 170)
        edges_bg = cv2.Canny(bg_u8, 80, 170)
        edge_diff = cv2.absdiff(edges_now, edges_bg)
        edge_change_ratio = float(np.count_nonzero(edge_diff)) / float(edge_diff.size)

        open_score = 0.6 * min(1.0, motion_score / (self.config.door_motion_threshold * 2.0)) + 0.4 * min(
            1.0, edge_change_ratio / (self.config.door_edge_change_threshold * 2.0)
        )

        raw_state = DoorState.OPEN if open_score > 0.58 else DoorState.CLOSED

        transition = self.current_state
        if raw_state != self.current_state:
            if self._stable_candidate != raw_state:
                self._stable_candidate = raw_state
                self._stable_count = 1
            else:
                self._stable_count += 1

            if self._stable_count >= self.config.door_state_stability_frames:
                if self.current_state == DoorState.CLOSED and raw_state == DoorState.OPEN:
                    transition = DoorState.OPENING
                elif self.current_state == DoorState.OPEN and raw_state == DoorState.CLOSED:
                    transition = DoorState.CLOSING
                self.current_state = raw_state
                self._stable_candidate = None
                self._stable_count = 0
        else:
            self._stable_candidate = None
            self._stable_count = 0

        self._last_open_score = open_score

        if transition in (DoorState.OPENING, DoorState.CLOSING):
            return transition, open_score, {
                "motion_score": motion_score,
                "edge_change_ratio": edge_change_ratio,
                "open_score": open_score,
            }

        return self.current_state, open_score, {
            "motion_score": motion_score,
            "edge_change_ratio": edge_change_ratio,
            "open_score": open_score,
        }


class DoorMonitor:
    def __init__(self, config: Optional[DoorMonitorConfig] = None) -> None:
        self.config = config or DoorMonitorConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._load_calibration()
        self.frame_buffer = FrameBuffer(self.config.buffer_seconds, self.config.fps)
        self.debug_frame_buffer = FrameBuffer(self.config.buffer_seconds, self.config.fps)
        self.event_queue: "queue.Queue[DoorEvent]" = queue.Queue()

        self._callbacks: List[Callable[[DoorEvent], None]] = []
        self._events: Deque[DoorEvent] = deque(maxlen=250)
        self._events_lock = threading.Lock()

        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._door_estimator = DoorStateEstimator(self.config)
        self._door_state = DoorState.CLOSED
        self._active_open_cycle_id = 0
        self._open_cycle_started_at: Optional[float] = None
        self._last_emitted_by_type: Dict[str, float] = {}

        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        self._tracks: Dict[int, PersonTrack] = {}
        self._next_track_id = 1
        self._frame_count = 0

    def _load_calibration(self) -> None:
        calibration_path = self.config.calibration_file()
        try:
            loaded = self.config.load_calibration(calibration_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.logger.warning("Failed to load calibration from %s: %s", calibration_path, exc)
            return
        if loaded:
            self.logger.info("Loaded calibration from %s", calibration_path)

    def register_callback(self, func: Callable[[DoorEvent], None]) -> None:
        self._callbacks.append(func)

    def start(self) -> None:
        if self._capture_thread and self._capture_thread.is_alive():
            return
        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=3)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        return self.frame_buffer.get_latest_frame()

    def get_recent_snippet(self, seconds: int = 5) -> List[np.ndarray]:
        return self.frame_buffer.get_recent_snippet(seconds)

    def export_recent_debug_snippet(self, seconds: Optional[int] = None, save_to: str | Path | None = None) -> Optional[str]:
        seconds = seconds or self.config.snippet_seconds
        if save_to is None:
            export_dir = Path(self.config.export_directory) if self.config.export_directory else DEFAULT_EXPORT_DIR
            save_to = export_dir / f"snippet_{int(time.time() * 1000)}.mp4"
        return self.debug_frame_buffer.export_snippet(save_to, fps=self.config.fps, seconds=seconds)

    def get_recent_events(self) -> List[DoorEvent]:
        with self._events_lock:
            return list(self._events)

    def get_door_state(self) -> DoorState:
        with self._lock:
            return self._door_state

    @staticmethod
    def _open_capture_device(config: DoorMonitorConfig) -> Optional[cv2.VideoCapture]:
        cap = cv2.VideoCapture(config.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
        cap.set(cv2.CAP_PROP_FPS, config.fps)
        return cap

    def _create_capture(self) -> Optional[cv2.VideoCapture]:
        return self._open_capture_device(self.config)

    def _capture_loop(self) -> None:
        cap = None
        attempts = 0

        while not self._stop_event.is_set():
            if cap is None:
                cap = self._create_capture()
                if cap is None:
                    attempts += 1
                    self.logger.warning("Camera open failed (%s/%s)", attempts, self.config.reconnect_attempts)
                    if attempts >= self.config.reconnect_attempts:
                        self.logger.error("Max reconnect attempts reached; retry loop continues in background")
                        attempts = 0
                    time.sleep(self.config.reconnect_backoff_seconds)
                    continue
                attempts = 0

            ok, frame = cap.read()
            if not ok or frame is None:
                self.logger.warning("Frame read failed; reopening camera")
                cap.release()
                cap = None
                time.sleep(self.config.reconnect_backoff_seconds)
                continue

            timestamp = time.time()
            self.frame_buffer.add_frame(frame, timestamp)

            door_state, door_confidence, door_meta = self._door_estimator.update(frame)
            self._handle_door_state(door_state, door_confidence, timestamp, frame, door_meta)

            detections: List[Tuple[int, int, int, int]] = []
            if self._frame_count % self.config.human_detection_stride == 0:
                detections = self._detect_people(frame)
            self._update_tracks(frame, detections, timestamp)
            debug_frame = frame.copy()
            self._draw_debug(debug_frame)
            self.debug_frame_buffer.add_frame(debug_frame, timestamp)
            self._reason_person_events(timestamp, frame)

            if self.config.debug_display:
                cv2.imshow("door-monitor-debug", debug_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self._stop_event.set()

            self._frame_count += 1

        if cap is not None:
            cap.release()
        if self.config.debug_display:
            cv2.destroyAllWindows()

    def _detect_people(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        x, y, w, h = self.config.doorway_region
        pad = 180
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(frame.shape[1], x + w + pad)
        y1 = min(frame.shape[0], y + h + pad)
        roi = frame[y0:y1, x0:x1]

        rects, weights = self._hog.detectMultiScale(roi, winStride=(6, 6), padding=(8, 8), scale=1.05)
        detections: List[Tuple[int, int, int, int]] = []
        for (rx, ry, rw, rh), conf in zip(rects, weights):
            if float(conf) < self.config.human_detection_confidence:
                continue
            detections.append((int(rx + x0), int(ry + y0), int(rw), int(rh)))
        return detections

    def _zone_for_point(self, p: Tuple[int, int]) -> str:
        if self._point_in_rect(p, self.config.exterior_region):
            return "exterior"
        if self._point_in_rect(p, self.config.doorway_region):
            return "doorway"
        if self._point_in_rect(p, self.config.interior_region):
            return "interior"
        return "unknown"

    @staticmethod
    def _point_in_rect(p: Tuple[int, int], rect: Tuple[int, int, int, int]) -> bool:
        px, py = p
        x, y, w, h = rect
        return x <= px <= x + w and y <= py <= y + h

    @staticmethod
    def _centroid(bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x, y, w, h = bbox
        return (x + w // 2, y + h // 2)

    @staticmethod
    def _distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    def _update_tracks(self, frame: np.ndarray, detections: List[Tuple[int, int, int, int]], timestamp: float) -> None:
        assigned_track_ids = set()

        for det in detections:
            c = self._centroid(det)
            zone = self._zone_for_point(c)
            if zone == "unknown":
                continue

            best_id = None
            best_dist = float("inf")
            for tid, track in self._tracks.items():
                d = self._distance(c, track.centroid)
                if d < best_dist and d <= self.config.max_track_match_distance:
                    best_dist = d
                    best_id = tid

            if best_id is None:
                tid = self._next_track_id
                self._next_track_id += 1
                track = PersonTrack(
                    track_id=tid,
                    bbox=det,
                    centroid=c,
                    first_seen=timestamp,
                    last_seen=timestamp,
                )
                track.centroids.append(c)
                track.zones.append(zone)
                self._tracks[tid] = track
                assigned_track_ids.add(tid)
            else:
                self._tracks[best_id].update(det, c, zone, timestamp)
                assigned_track_ids.add(best_id)

        to_delete = []
        for tid, track in self._tracks.items():
            if tid not in assigned_track_ids:
                track.lost_frames += 1
                if track.lost_frames > self.config.max_track_lost_frames:
                    to_delete.append(tid)
        for tid in to_delete:
            del self._tracks[tid]

    def _handle_door_state(
        self,
        door_state: DoorState,
        confidence: float,
        timestamp: float,
        frame: np.ndarray,
        metadata: Dict[str, float],
    ) -> None:
        with self._lock:
            prev = self._door_state
            self._door_state = door_state if door_state in (DoorState.OPEN, DoorState.CLOSED) else prev

        if prev != DoorState.OPEN and door_state == DoorState.OPENING:
            self._active_open_cycle_id += 1
            self._open_cycle_started_at = timestamp

        if door_state == DoorState.OPEN and prev != DoorState.OPEN:
            self._emit_event("door_open", confidence, timestamp, frame, metadata)

        if door_state == DoorState.CLOSED and prev != DoorState.CLOSED:
            self._emit_event("door_close", confidence, timestamp, frame, metadata)
            self._open_cycle_started_at = None

    def _reason_person_events(self, timestamp: float, frame: np.ndarray) -> None:
        if self.get_door_state() != DoorState.OPEN:
            return

        for track in self._tracks.values():
            if track.emitted_open_cycle_id == self._active_open_cycle_id:
                continue
            if len(track.zones) < 5:
                continue

            zone_seq = list(track.zones)
            if not self._is_valid_sequence(zone_seq):
                continue

            event_type = None
            if self._contains_order(zone_seq, ["exterior", "doorway", "interior"]):
                event_type = "enter"
            elif self._contains_order(zone_seq, ["interior", "doorway", "exterior"]):
                event_type = "exit"

            if event_type is None:
                continue

            confidence = self._event_confidence(track, zone_seq)
            metadata = {
                "track_id": track.track_id,
                "zones": zone_seq[-10:],
                "open_cycle_id": self._active_open_cycle_id,
                "track_age_s": round(timestamp - track.first_seen, 2),
            }
            self._emit_event(event_type, confidence, timestamp, frame, metadata)
            track.emitted_open_cycle_id = self._active_open_cycle_id

    @staticmethod
    def _is_valid_sequence(zones: List[str]) -> bool:
        # Require doorway participation and a full interior<->exterior traversal path.
        return "doorway" in zones and "interior" in zones and "exterior" in zones

    @staticmethod
    def _contains_order(seq: List[str], ordered: List[str]) -> bool:
        idx = 0
        for s in seq:
            if s == ordered[idx]:
                idx += 1
                if idx == len(ordered):
                    return True
        return False

    def _event_confidence(self, track: PersonTrack, zones: List[str]) -> float:
        persistence = min(1.0, len(zones) / 12.0)
        has_full_order = 1.0 if (
            self._contains_order(zones, ["exterior", "doorway", "interior"])
            or self._contains_order(zones, ["interior", "doorway", "exterior"])
        ) else 0.0
        smooth_motion = 0.7 if len(track.centroids) > 6 else 0.4
        return round(0.45 * persistence + 0.35 * has_full_order + 0.2 * smooth_motion, 3)

    def _emit_event(
        self,
        event_type: str,
        confidence: float,
        timestamp: float,
        frame: np.ndarray,
        metadata: Dict[str, object],
    ) -> None:
        last_ts = self._last_emitted_by_type.get(event_type, 0)
        if timestamp - last_ts < self.config.event_cooldown_seconds:
            return
        self._last_emitted_by_type[event_type] = timestamp

        snippet = self.frame_buffer.get_recent_snippet(self.config.snippet_seconds)
        event = DoorEvent(
            event_type=event_type,
            timestamp=timestamp,
            confidence=float(confidence),
            metadata=metadata,
            frame=frame.copy(),
            snippet=snippet,
        )

        with self._events_lock:
            self._events.append(event)

        self.event_queue.put(event)
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                self.logger.exception("Callback failed")

    def _draw_debug(self, frame: np.ndarray) -> None:
        for rect, color, label in [
            (self.config.door_roi, (0, 255, 255), "door_roi"),
            (self.config.doorway_region, (0, 200, 255), "doorway"),
            (self.config.interior_region, (0, 255, 0), "interior"),
            (self.config.exterior_region, (255, 0, 0), "exterior"),
        ]:
            x, y, w, h = rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, label, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

        cv2.putText(
            frame,
            f"door_state: {self.get_door_state().value}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        for track in self._tracks.values():
            x, y, w, h = track.bbox
            cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 220, 80), 2)
            cv2.putText(
                frame,
                f"id:{track.track_id} z:{track.zones[-1] if track.zones else '?'}",
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (80, 220, 80),
                1,
                cv2.LINE_AA,
            )


def run_calibration(
    camera_index: int = 0,
    output_path: str | Path = DEFAULT_CALIBRATION_PATH,
    config: Optional[DoorMonitorConfig] = None,
) -> None:
    """
    Interactive calibration utility.

    Draw rectangles in this order using drag+release:
    1) door_roi
    2) doorway_region
    3) exterior_region
    4) interior_region

    Press 'r' to reset current rectangle, 'q' to quit early.
    """

    regions = ["door_roi", "doorway_region", "exterior_region", "interior_region"]
    captured: Dict[str, Tuple[int, int, int, int]] = {}
    calibration_config = config or DoorMonitorConfig(camera_index=camera_index)
    calibration_config.camera_index = camera_index

    cap = DoorMonitor._open_capture_device(calibration_config)
    if cap is None:
        raise RuntimeError("Could not open camera for calibration")

    state = {
        "drawing": False,
        "start": (0, 0),
        "end": (0, 0),
        "region_idx": 0,
    }

    def mouse_cb(event: int, x: int, y: int, flags: int, param: object) -> None:
        if state["region_idx"] >= len(regions):
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            state["drawing"] = True
            state["start"] = (x, y)
            state["end"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and state["drawing"]:
            state["end"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and state["drawing"]:
            state["drawing"] = False
            sx, sy = state["start"]
            ex, ey = (x, y)
            x0, x1 = sorted([sx, ex])
            y0, y1 = sorted([sy, ey])
            rect = (x0, y0, x1 - x0, y1 - y0)
            captured[regions[state["region_idx"]]] = rect
            state["region_idx"] += 1

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", mouse_cb)

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        for name, rect in captured.items():
            x, y, w, h = rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 220, 80), 2)
            cv2.putText(frame, name, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 220, 80), 1)

        if state["drawing"]:
            sx, sy = state["start"]
            ex, ey = state["end"]
            cv2.rectangle(frame, (sx, sy), (ex, ey), (0, 200, 255), 2)

        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        prompt = "Done" if state["region_idx"] >= len(regions) else f"Draw: {regions[state['region_idx']]}"
        cv2.putText(frame, prompt, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(
            frame,
            f"{actual_width}x{actual_height} @ {calibration_config.fps}fps",
            (15, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        cv2.imshow("calibrate", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r") and state["region_idx"] > 0:
            state["region_idx"] -= 1
            captured.pop(regions[state["region_idx"]], None)
        if state["region_idx"] >= len(regions):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(captured) == len(regions):
        cfg = DoorMonitorConfig()
        cfg.door_roi = captured["door_roi"]
        cfg.doorway_region = captured["doorway_region"]
        cfg.exterior_region = captured["exterior_region"]
        cfg.interior_region = captured["interior_region"]
        saved_path = cfg.save_calibration(output_path)
        logging.info("Saved calibration to %s", saved_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_calibration()
