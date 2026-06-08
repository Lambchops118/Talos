from __future__ import annotations

import argparse
import calendar
import json
import threading
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
RUNTIME_ROOT = APP_ROOT / "runtime"
DEFAULT_STATE_PATH = RUNTIME_ROOT / "kitchen_state.json"
INFOPANEL_FONT_PATH = APP_ROOT.parents[1] / "InfoPanel" / "VT323-Regular.ttf"


def build_default_state() -> dict[str, Any]:
    return {
        "title": "",
        "link_status": "LINK NOMINAL",
        "source": "TALOS",
        "servings": "4 servings",
        "status": "Awaiting recipe uplink.",
        "subtitle": "",
        "updated_at": iso_now(),
        "ingredients": [
            {"text": "2 tbsp olive oil", "checked": False},
            {"text": "1 yellow onion, diced", "checked": False},
            {"text": "4 cloves garlic, minced", "checked": False},
            {"text": "1 can crushed tomatoes", "checked": False},
        ],
        "steps": [
            {"text": "Heat the pan and warm the oil.", "done": False},
            {"text": "Cook onion until soft and glossy.", "done": False},
            {"text": "Add garlic briefly, then stir in tomatoes.", "done": False},
            {"text": "Simmer gently while TALOS tracks the timer.", "done": False},
        ],
        "notes": [
            "The agent can replace this recipe over HTTP.",
            "Use the timer panel for hands-free countdowns.",
        ],
        "timer": {
            "label": "Prep timer",
            "duration_seconds": 900,
            "remaining_seconds": 900,
            "running": False,
            "finished": False,
            "updated_at": iso_now(),
        },
    }


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def epoch_now() -> float:
    return time.time()


def parse_iso_timestamp(value: Any) -> float:
    if not value:
        return epoch_now()
    text = str(value)
    try:
        return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return epoch_now()


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def clamp_seconds(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def resolve_timer(timer: dict[str, Any]) -> dict[str, Any]:
    resolved = deepcopy(timer or {})
    duration_seconds = clamp_seconds(resolved.get("duration_seconds"))
    remaining_seconds = clamp_seconds(resolved.get("remaining_seconds", duration_seconds))
    running = bool(resolved.get("running"))
    finished = bool(resolved.get("finished"))

    if running:
        updated_ts = parse_iso_timestamp(resolved.get("updated_at"))
        elapsed = max(0, int(epoch_now() - updated_ts))
        remaining_seconds = max(0, remaining_seconds - elapsed)
        if remaining_seconds == 0:
            running = False
            finished = True

    resolved["duration_seconds"] = duration_seconds
    resolved["remaining_seconds"] = remaining_seconds
    resolved["running"] = running
    resolved["finished"] = finished
    return resolved


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(state)
    normalized["title"] = str(normalized.get("title") or "")
    normalized["link_status"] = str(normalized.get("link_status") or "LINK NOMINAL")
    normalized["source"] = str(normalized.get("source") or "TALOS")
    normalized["servings"] = str(normalized.get("servings") or "")
    normalized["status"] = str(normalized.get("status") or "")
    normalized["subtitle"] = str(normalized.get("subtitle") or "")
    normalized["updated_at"] = str(normalized.get("updated_at") or iso_now())
    normalized["ingredients"] = list(normalized.get("ingredients") or [])
    normalized["steps"] = list(normalized.get("steps") or [])
    normalized["notes"] = list(normalized.get("notes") or [])
    normalized["timer"] = resolve_timer(dict(normalized.get("timer") or {}))
    return normalized


class KitchenStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self._lock = threading.RLock()
        self._state = build_default_state()
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._state = normalize_state(deep_merge(build_default_state(), payload))

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, indent=2),
            encoding="utf-8",
        )

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return normalize_state(self._state)

    def update_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = normalize_state(self._state)
            merged = deep_merge(current, patch)
            merged["updated_at"] = iso_now()
            if "timer" in merged:
                timer = resolve_timer(dict(merged.get("timer") or {}))
                if "timer" in patch or timer.get("running"):
                    timer["updated_at"] = iso_now()
                else:
                    timer.setdefault("updated_at", iso_now())
                merged["timer"] = timer
            self._state = normalize_state(merged)
            self._save()
            return normalize_state(self._state)

    def update_timer(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip().lower()
        if not action:
            raise ValueError("Missing timer action.")

        with self._lock:
            state = normalize_state(self._state)
            timer = resolve_timer(dict(state.get("timer") or {}))
            now = iso_now()

            if action == "set":
                label = payload.get("label")
                if label is not None:
                    timer["label"] = str(label)
                if "duration_seconds" in payload:
                    timer["duration_seconds"] = clamp_seconds(payload.get("duration_seconds"))
                if "remaining_seconds" in payload:
                    timer["remaining_seconds"] = clamp_seconds(payload.get("remaining_seconds"))
                elif "duration_seconds" in payload:
                    timer["remaining_seconds"] = timer["duration_seconds"]
                timer["finished"] = timer["remaining_seconds"] == 0
                timer["running"] = bool(payload.get("auto_start"))
                timer["updated_at"] = now
            elif action == "start":
                if timer["remaining_seconds"] <= 0 and timer["duration_seconds"] > 0:
                    timer["remaining_seconds"] = timer["duration_seconds"]
                timer["running"] = timer["remaining_seconds"] > 0
                timer["finished"] = False
                timer["updated_at"] = now
            elif action == "pause":
                timer["running"] = False
                timer["updated_at"] = now
            elif action == "reset":
                timer["remaining_seconds"] = timer["duration_seconds"]
                timer["running"] = False
                timer["finished"] = timer["remaining_seconds"] == 0
                timer["updated_at"] = now
            elif action == "add_seconds":
                timer["remaining_seconds"] = clamp_seconds(timer["remaining_seconds"] + clamp_seconds(payload.get("seconds")))
                timer["duration_seconds"] = max(timer["duration_seconds"], timer["remaining_seconds"])
                timer["finished"] = timer["remaining_seconds"] == 0
                timer["updated_at"] = now
            else:
                raise ValueError(f"Unsupported timer action: {action}")

            state["timer"] = resolve_timer(timer)
            state["updated_at"] = now
            self._state = normalize_state(state)
            self._save()
            return normalize_state(self._state)


class KitchenRecipeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], state_store: KitchenStateStore) -> None:
        super().__init__(server_address, KitchenRecipeHandler)
        self.state_store = state_store


class KitchenRecipeHandler(BaseHTTPRequestHandler):
    server: KitchenRecipeHTTPServer
    server_version = "KitchenRecipeScreen/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._serve_file(STATIC_ROOT / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._serve_file(STATIC_ROOT / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/assets/VT323-Regular.ttf":
            self._serve_file(INFOPANEL_FONT_PATH, "font/ttf")
            return
        if path == "/api/health":
            self._write_json(HTTPStatus.OK, {"ok": True, "app": "kitchen_recipe_screen"})
            return
        if path == "/api/state":
            self._write_json(HTTPStatus.OK, {"ok": True, "state": self.server.state_store.get_state()})
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self._set_cors_headers()
            self.end_headers()
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        try:
            if path == "/api/state":
                state = self.server.state_store.update_state(payload)
                self._write_json(HTTPStatus.OK, {"ok": True, "state": state})
                return
            if path == "/api/timer":
                state = self.server.state_store.update_timer(payload)
                self._write_json(HTTPStatus.OK, {"ok": True, "state": state})
                return
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        except OSError as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[kitchen-recipe-screen] {self.address_string()} - {fmt % args}")

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc.msg}") from exc
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        return body

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "File not found"})
            return
        try:
            data = path.read_bytes()
        except OSError as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kitchen recipe kiosk server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/interface to bind.")
    parser.add_argument("--port", default=8765, type=int, help="Port to bind.")
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help="Path to the persisted JSON state file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_store = KitchenStateStore(Path(args.state_path).expanduser())
    server = KitchenRecipeHTTPServer((args.host, args.port), state_store)
    print(f"Kitchen recipe screen serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down kitchen recipe screen.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
