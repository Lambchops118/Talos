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
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


class DoorState(str, Enum):
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    UNKNOWN = "unknown"


class TrackLifecycle(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    LOST = "lost"
    REMOVED = "removed"


class Zone(str, Enum):
    INTERIOR = "interior"
    DOORWAY = "doorway"
    EXTERIOR = "exterior"
    NONE = "none"


@dataclass
class DoorEvent:
    event_type: str
    timestamp: float
    confidence: float
    details: Dict[str, object] = field(default_factory=dict)


@dataclass
class DoorMonitorConfig:
    camera_index: int = 0
    frame_width: int = 1280
    frame_height: int = 720
    fps: float = 15.0
    process_every_n_frames: int = 1

    # door estimation thresholds
    closed_angle_threshold: float = 10.0
    open_angle_threshold: float = 28.0
    motion_stability_frames: int = 5
    angle_smoothing: float = 0.25

    # person detection
    person_scale: float = 1.05
    person_stride: Tuple[int, int] = (8, 8)
    person_padding: Tuple[int, int] = (8, 8)
    person_hit_threshold: float = 0.0

    # tracker settings
    max_track_age: int = 30
    min_track_hits: int = 3
    association_max_distance: float = 130.0

    # frame/event buffers
    frame_buffer_seconds: int = 30
    recent_event_limit: int = 500
    event_queue_max: int = 1000

    # reasoner settings
    doorway_transition_timeout_s: float = 3.5
    require_open_door: bool = True

    calibration_path: Optional[str] = None


@dataclass
class GeometryCalibration:
    frame_corners: List[Tuple[int, int]] = field(default_factory=list)
    hinge_side: str = "left"
    latch_side: str = "right"
    closed_edge_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
    doorway_polygon: List[Tuple[int, int]] = field(default_factory=list)
    interior_polygon: List[Tuple[int, int]] = field(default_factory=list)
    exterior_polygon: List[Tuple[int, int]] = field(default_factory=list)


class FrameBuffer:
    def __init__(self, max_seconds: int, fps_hint: float) -> None:
        self._max_frames = max(1, int(max_seconds * max(fps_hint, 1.0)))
        self._frames: Deque[Tuple[float, np.ndarray]] = deque(maxlen=self._max_frames)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, ts: Optional[float] = None) -> None:
        with self._lock:
            self._frames.append((ts or time.time(), frame.copy()))

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._frames:
                return None
            return self._frames[-1][1].copy()

    def recent(self, seconds: float) -> List[Tuple[float, np.ndarray]]:
        cutoff = time.time() - seconds
        with self._lock:
            return [(ts, f.copy()) for ts, f in self._frames if ts >= cutoff]

    def export_snippet(self, seconds: float, save_to: str, fps: float = 15.0) -> Optional[str]:
        clips = self.recent(seconds)
        if not clips:
            return None
        path = Path(save_to)
        path.parent.mkdir(parents=True, exist_ok=True)
        h, w = clips[0][1].shape[:2]
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(fps, 1.0),
            (w, h),
        )
        try:
            for _, frame in clips:
                writer.write(frame)
        finally:
            writer.release()
        return str(path)


class DoorGeometryCalibrator:
    def __init__(self, calibration: Optional[GeometryCalibration] = None) -> None:
        self.calibration = calibration or GeometryCalibration()

    def load_json(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.calibration = GeometryCalibration(
            frame_corners=[tuple(p) for p in data.get("frame_corners", [])],
            hinge_side=data.get("hinge_side", "left"),
            latch_side=data.get("latch_side", "right"),
            closed_edge_line=tuple(tuple(x) for x in data["closed_edge_line"]) if data.get("closed_edge_line") else None,
            doorway_polygon=[tuple(p) for p in data.get("doorway_polygon", [])],
            interior_polygon=[tuple(p) for p in data.get("interior_polygon", [])],
            exterior_polygon=[tuple(p) for p in data.get("exterior_polygon", [])],
        )

    def save_json(self, path: str) -> None:
        payload = {
            "frame_corners": self.calibration.frame_corners,
            "hinge_side": self.calibration.hinge_side,
            "latch_side": self.calibration.latch_side,
            "closed_edge_line": self.calibration.closed_edge_line,
            "doorway_polygon": self.calibration.doorway_polygon,
            "interior_polygon": self.calibration.interior_polygon,
            "exterior_polygon": self.calibration.exterior_polygon,
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def point_in_polygon(point: Tuple[float, float], polygon: Sequence[Tuple[int, int]]) -> bool:
        if len(polygon) < 3:
            return False
        return cv2.pointPolygonTest(np.array(polygon, dtype=np.int32), point, False) >= 0

    def zone_for_point(self, point: Tuple[float, float]) -> Zone:
        c = self.calibration
        if self.point_in_polygon(point, c.doorway_polygon):
            return Zone.DOORWAY
        if self.point_in_polygon(point, c.interior_polygon):
            return Zone.INTERIOR
        if self.point_in_polygon(point, c.exterior_polygon):
            return Zone.EXTERIOR
        return Zone.NONE


class DoorStateEstimator:
    def __init__(self, config: DoorMonitorConfig, calibrator: DoorGeometryCalibrator) -> None:
        self.config = config
        self.calibrator = calibrator
        self._smoothed_angle = 0.0
        self._prev_angle = 0.0
        self._state = DoorState.UNKNOWN
        self._stable_counter = 0

    @staticmethod
    def _line_angle_deg(line: Tuple[Tuple[int, int], Tuple[int, int]]) -> float:
        (x1, y1), (x2, y2) = line
        return float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

    def _best_door_edge(self, frame: np.ndarray) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        calib = self.calibrator.calibration
        if not calib.closed_edge_line:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 75, 170)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35, minLineLength=45, maxLineGap=18)
        if lines is None:
            return None
        ref_ang = self._line_angle_deg(calib.closed_edge_line)
        ref_pt = np.array(calib.closed_edge_line[0], dtype=np.float32)
        best = None
        best_score = float("inf")
        for raw in lines[:, 0, :]:
            line = ((int(raw[0]), int(raw[1])), (int(raw[2]), int(raw[3])))
            ang = self._line_angle_deg(line)
            ang_delta = min(abs(ang - ref_ang), 180 - abs(ang - ref_ang))
            p = np.array(line[0], dtype=np.float32)
            dist = float(np.linalg.norm(p - ref_pt))
            score = ang_delta + 0.03 * dist
            if score < best_score:
                best_score = score
                best = line
        return best

    def estimate(self, frame: np.ndarray) -> Tuple[float, DoorState, float]:
        c = self.config
        calib = self.calibrator.calibration
        confidence = 0.25
        if not calib.closed_edge_line:
            return self._smoothed_angle, self._state, confidence

        ref = self._line_angle_deg(calib.closed_edge_line)
        edge = self._best_door_edge(frame)
        if edge is not None:
            edge_ang = self._line_angle_deg(edge)
            angle = min(abs(edge_ang - ref), 180 - abs(edge_ang - ref))
            self._smoothed_angle = (1 - c.angle_smoothing) * self._smoothed_angle + c.angle_smoothing * angle
            confidence = min(1.0, 0.4 + (angle / max(c.open_angle_threshold, 1e-3)) * 0.6)
        else:
            confidence = 0.1

        delta = self._smoothed_angle - self._prev_angle
        if abs(delta) < 0.7:
            self._stable_counter += 1
        else:
            self._stable_counter = 0

        prev_state = self._state
        if self._smoothed_angle <= c.closed_angle_threshold:
            state = DoorState.CLOSED
        elif self._smoothed_angle >= c.open_angle_threshold:
            state = DoorState.OPEN
        else:
            state = DoorState.OPENING if delta > 0 else DoorState.CLOSING

        if self._stable_counter < c.motion_stability_frames and prev_state in (DoorState.OPENING, DoorState.CLOSING):
            state = prev_state

        self._state = state
        self._prev_angle = self._smoothed_angle
        return self._smoothed_angle, state, confidence


class PersonDetector:
    def __init__(self, config: DoorMonitorConfig) -> None:
        self.config = config
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        boxes, weights = self.hog.detectMultiScale(
            frame,
            hitThreshold=self.config.person_hit_threshold,
            winStride=self.config.person_stride,
            padding=self.config.person_padding,
            scale=self.config.person_scale,
        )
        detections = []
        for (x, y, w, h), score in zip(boxes, weights):
            detections.append((int(x), int(y), int(w), int(h), float(score)))
        return detections


@dataclass
class PersonTrack:
    track_id: int
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[float, float]
    predicted_centroid: Tuple[float, float]
    velocity: Tuple[float, float]
    trajectory_history: Deque[Tuple[float, float]]
    time_first_seen: float
    time_last_seen: float
    current_zone: Zone = Zone.NONE
    previous_zone: Zone = Zone.NONE
    lifecycle: TrackLifecycle = TrackLifecycle.TENTATIVE
    hits: int = 1
    misses: int = 0
    kf: cv2.KalmanFilter = field(repr=False, default=None)


class PersonTracker:
    def __init__(self, config: DoorMonitorConfig) -> None:
        self.config = config
        self._next_id = 1
        self._tracks: Dict[int, PersonTrack] = {}

    @staticmethod
    def _centroid(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        x, y, w, h = bbox
        return (x + w / 2.0, y + h / 2.0)

    def _new_kf(self, c: Tuple[float, float]) -> cv2.KalmanFilter:
        kf = cv2.KalmanFilter(4, 2)
        kf.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * 1e-2
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1e-1
        kf.errorCovPost = np.eye(4, dtype=np.float32)
        kf.statePost = np.array([[c[0]], [c[1]], [0], [0]], np.float32)
        return kf

    def _predict(self) -> None:
        for track in self._tracks.values():
            pred = track.kf.predict()
            track.predicted_centroid = (float(pred[0]), float(pred[1]))

    def _associate(self, detections: List[Tuple[int, int, int, int, float]]) -> Tuple[Dict[int, int], List[int], List[int]]:
        if not self._tracks:
            return {}, [], list(range(len(detections)))
        track_ids = list(self._tracks.keys())
        det_centroids = [self._centroid(d[:4]) for d in detections]
        cost = np.full((len(track_ids), len(detections)), 1e6, dtype=np.float32)
        for i, tid in enumerate(track_ids):
            px, py = self._tracks[tid].predicted_centroid
            for j, (dx, dy) in enumerate(det_centroids):
                cost[i, j] = float(np.hypot(px - dx, py - dy))

        assignments: Dict[int, int] = {}
        unmatched_tracks = set(range(len(track_ids)))
        unmatched_dets = set(range(len(detections)))
        while unmatched_tracks and unmatched_dets:
            i, j = np.unravel_index(np.argmin(cost), cost.shape)
            if i not in unmatched_tracks or j not in unmatched_dets:
                cost[i, j] = 1e6
                continue
            if cost[i, j] > self.config.association_max_distance:
                break
            assignments[track_ids[i]] = j
            unmatched_tracks.remove(i)
            unmatched_dets.remove(j)
            cost[i, :] = 1e6
            cost[:, j] = 1e6

        return assignments, [track_ids[i] for i in unmatched_tracks], list(unmatched_dets)

    def update(self, detections: List[Tuple[int, int, int, int, float]]) -> Dict[int, PersonTrack]:
        self._predict()
        now = time.time()
        assignments, unmatched_track_ids, unmatched_det_ids = self._associate(detections)

        for tid, didx in assignments.items():
            track = self._tracks[tid]
            bbox = detections[didx][:4]
            c = self._centroid(bbox)
            measurement = np.array([[np.float32(c[0])], [np.float32(c[1])]])
            track.kf.correct(measurement)
            vx, vy = c[0] - track.centroid[0], c[1] - track.centroid[1]
            track.velocity = (vx, vy)
            track.centroid = c
            track.bbox = bbox
            track.time_last_seen = now
            track.hits += 1
            track.misses = 0
            track.trajectory_history.append(c)
            if track.lifecycle == TrackLifecycle.TENTATIVE and track.hits >= self.config.min_track_hits:
                track.lifecycle = TrackLifecycle.CONFIRMED

        for tid in unmatched_track_ids:
            track = self._tracks[tid]
            track.misses += 1
            if track.misses > self.config.max_track_age:
                track.lifecycle = TrackLifecycle.REMOVED
            elif track.lifecycle == TrackLifecycle.CONFIRMED:
                track.lifecycle = TrackLifecycle.LOST

        for didx in unmatched_det_ids:
            bbox = detections[didx][:4]
            c = self._centroid(bbox)
            tid = self._next_id
            self._next_id += 1
            self._tracks[tid] = PersonTrack(
                track_id=tid,
                bbox=bbox,
                centroid=c,
                predicted_centroid=c,
                velocity=(0.0, 0.0),
                trajectory_history=deque([c], maxlen=200),
                time_first_seen=now,
                time_last_seen=now,
                kf=self._new_kf(c),
            )

        for tid in [tid for tid, t in self._tracks.items() if t.lifecycle == TrackLifecycle.REMOVED]:
            del self._tracks[tid]

        return dict(self._tracks)


class EntryExitReasoner:
    def __init__(self, config: DoorMonitorConfig) -> None:
        self.config = config
        self._zone_histories: Dict[int, Deque[Tuple[float, Zone]]] = {}
        self._emitted: set[Tuple[int, str]] = set()

    @staticmethod
    def _compress(zones: Sequence[Zone]) -> List[Zone]:
        out: List[Zone] = []
        for z in zones:
            if not out or out[-1] != z:
                out.append(z)
        return out

    def _score(self, track: PersonTrack, door_conf: float, sequence_ok: bool) -> float:
        stability = min(1.0, track.hits / 8.0)
        speed = float(np.hypot(*track.velocity))
        smoothness = 1.0 if speed < 80 else 0.6
        completeness = 1.0 if sequence_ok else 0.35
        return max(0.0, min(1.0, 0.35 * stability + 0.25 * door_conf + 0.2 * smoothness + 0.2 * completeness))

    def update(
        self,
        tracks: Dict[int, PersonTrack],
        door_state: DoorState,
        door_confidence: float,
        now: Optional[float] = None,
    ) -> List[DoorEvent]:
        ts = now or time.time()
        events: List[DoorEvent] = []
        for tid, track in tracks.items():
            if track.lifecycle not in (TrackLifecycle.CONFIRMED, TrackLifecycle.LOST):
                continue
            hist = self._zone_histories.setdefault(tid, deque(maxlen=20))
            hist.append((ts, track.current_zone))
            recent = [z for t, z in hist if ts - t <= self.config.doorway_transition_timeout_s and z != Zone.NONE]
            if len(recent) < 3:
                continue
            seq = self._compress(recent)
            can_pass = door_state in (DoorState.OPEN, DoorState.OPENING) or not self.config.require_open_door
            if not can_pass:
                continue
            enter_key = (tid, "enter")
            exit_key = (tid, "exit")
            if len(seq) >= 3 and seq[-3:] == [Zone.EXTERIOR, Zone.DOORWAY, Zone.INTERIOR] and enter_key not in self._emitted:
                conf = self._score(track, door_confidence, True)
                events.append(DoorEvent("person_enter", ts, conf, {"track_id": tid, "sequence": [z.value for z in seq[-3:]]}))
                self._emitted.add(enter_key)
            elif len(seq) >= 3 and seq[-3:] == [Zone.INTERIOR, Zone.DOORWAY, Zone.EXTERIOR] and exit_key not in self._emitted:
                conf = self._score(track, door_confidence, True)
                events.append(DoorEvent("person_exit", ts, conf, {"track_id": tid, "sequence": [z.value for z in seq[-3:]]}))
                self._emitted.add(exit_key)
        return events


class DoorMonitor:
    def __init__(self, config: Optional[DoorMonitorConfig] = None) -> None:
        self.config = config or DoorMonitorConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.calibrator = DoorGeometryCalibrator()
        if self.config.calibration_path:
            self.calibrator.load_json(self.config.calibration_path)

        self.state_estimator = DoorStateEstimator(self.config, self.calibrator)
        self.detector = PersonDetector(self.config)
        self.tracker = PersonTracker(self.config)
        self.reasoner = EntryExitReasoner(self.config)
        self.buffer = FrameBuffer(self.config.frame_buffer_seconds, self.config.fps)

        self._callbacks: List[Callable[[DoorEvent], None]] = []
        self._event_queue: "queue.Queue[DoorEvent]" = queue.Queue(maxsize=self.config.event_queue_max)
        self._recent_events: Deque[DoorEvent] = deque(maxlen=self.config.recent_event_limit)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._door_state = DoorState.UNKNOWN
        self._door_angle = 0.0
        self._door_conf = 0.0
        self._lock = threading.Lock()

    def register_callback(self, callback: Callable[[DoorEvent], None]) -> None:
        self._callbacks.append(callback)

    def _emit_event(self, event: DoorEvent) -> None:
        self._recent_events.append(event)
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            self.logger.warning("event queue is full, dropping event: %s", event.event_type)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                self.logger.exception("callback failed")

    def _emit_door_transition(self, old: DoorState, new: DoorState, confidence: float, ts: float) -> None:
        if old == new:
            return
        if new == DoorState.OPEN:
            self._emit_event(DoorEvent("door_open", ts, confidence, {"from": old.value, "to": new.value}))
        elif new == DoorState.CLOSED:
            self._emit_event(DoorEvent("door_close", ts, confidence, {"from": old.value, "to": new.value}))

    def _open_capture(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.config.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        return cap

    def start(self) -> None:
        if self._running:
            return
        self._cap = self._open_capture()
        if not self._cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {self.config.camera_index}")
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="door-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _loop(self) -> None:
        frame_idx = 0
        while self._running and self._cap is not None:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.02)
                continue
            ts = time.time()
            self.buffer.push(frame, ts)
            if frame_idx % max(1, self.config.process_every_n_frames) != 0:
                frame_idx += 1
                continue

            old_state = self._door_state
            angle, door_state, door_conf = self.state_estimator.estimate(frame)
            tracks = self.tracker.update(self.detector.detect(frame))
            for track in tracks.values():
                track.previous_zone = track.current_zone
                track.current_zone = self.calibrator.zone_for_point(track.centroid)

            events = self.reasoner.update(tracks, door_state, door_conf, ts)
            for event in events:
                self._emit_event(event)
            self._emit_door_transition(old_state, door_state, door_conf, ts)

            with self._lock:
                self._door_angle = angle
                self._door_state = door_state
                self._door_conf = door_conf
            frame_idx += 1

    def get_latest_frame(self) -> Optional[np.ndarray]:
        return self.buffer.latest()

    def get_recent_snippet(self, seconds: float, save_to: str) -> Optional[str]:
        return self.buffer.export_snippet(seconds, save_to, self.config.fps)

    def get_recent_events(self, limit: int = 10) -> List[DoorEvent]:
        return list(self._recent_events)[-limit:]

    def get_next_event(self, timeout: Optional[float] = None) -> Optional[DoorEvent]:
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_door_state(self) -> Dict[str, object]:
        with self._lock:
            return {
                "state": self._door_state,
                "angle": float(self._door_angle),
                "confidence": float(self._door_conf),
            }

    def get_status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "running": self._running,
                "door_state": self._door_state.value,
                "door_angle": float(self._door_angle),
                "door_confidence": float(self._door_conf),
                "buffer_frames": len(self.buffer._frames),
                "recent_events": len(self._recent_events),
            }


__all__ = [
    "DoorMonitor",
    "DoorMonitorConfig",
    "DoorEvent",
    "DoorState",
    "FrameBuffer",
    "DoorGeometryCalibrator",
    "DoorStateEstimator",
    "PersonDetector",
    "PersonTracker",
    "EntryExitReasoner",
    "GeometryCalibration",
    "Zone",
]