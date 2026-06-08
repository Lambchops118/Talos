from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from talos.config import load_environment


load_environment()


DEFAULT_KITCHEN_SCREEN_URL = os.getenv("KITCHEN_RECIPE_SCREEN_URL", "http://127.0.0.1:8765").strip() or "http://127.0.0.1:8765"
DEFAULT_KITCHEN_SCREEN_TIMEOUT = float(os.getenv("KITCHEN_RECIPE_SCREEN_TIMEOUT", "10"))
DEFAULT_LINK_STATUS = "LINK NOMINAL"
DEFAULT_SERVINGS = "4 servings"
DEFAULT_TIMER_LABEL = "Prep timer"


def get_screen_health() -> str:
    payload = _get_json("/api/health")
    return json.dumps(payload, ensure_ascii=True)


def get_screen_state() -> str:
    state = _fetch_state()
    return _json_response(state)


def set_recipe_header(title: str = "", subtitle: str = "") -> str:
    state = _update_state({"title": str(title or "").strip(), "subtitle": str(subtitle or "").strip()})
    return _summary_message("Updated recipe header.", state)


def clear_recipe_header() -> str:
    state = _update_state({"title": "", "subtitle": ""})
    return _summary_message("Cleared recipe header.", state)


def replace_recipe_content(
    title: str = "",
    subtitle: str = "",
    servings: str = "",
    ingredients: list[str] | None = None,
    steps: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    patch: dict[str, Any] = {
        "title": str(title or "").strip(),
        "subtitle": str(subtitle or "").strip(),
        "ingredients": _ingredient_items(ingredients or []),
        "steps": _step_items(steps or []),
        "notes": _normalize_text_list(notes or []),
    }
    if str(servings or "").strip():
        patch["servings"] = str(servings).strip()
    state = _update_state(patch)
    return _summary_message("Replaced recipe content on the kitchen screen.", state)


def read_ingredients() -> str:
    ingredients = _extract_lines(_fetch_state().get("ingredients"), "text")
    return _json_response({"ingredients": ingredients})


def replace_ingredients(ingredients: list[str]) -> str:
    state = _update_state({"ingredients": _ingredient_items(ingredients)})
    return _summary_message("Replaced ingredients on the kitchen screen.", state)


def remove_ingredients(
    indices: list[int] | None = None,
    matching_texts: list[str] | None = None,
    clear_all: bool = False,
) -> str:
    state = _fetch_state()
    updated = _remove_entries(
        state.get("ingredients") or [],
        indices=indices or [],
        matching_texts=matching_texts or [],
        clear_all=clear_all,
        text_getter=lambda item: str(item.get("text") or ""),
    )
    state = _update_state({"ingredients": updated})
    return _summary_message("Removed ingredients from the kitchen screen.", state)


def clear_ingredients() -> str:
    state = _update_state({"ingredients": []})
    return _summary_message("Cleared ingredients from the kitchen screen.", state)


def read_steps() -> str:
    steps = _extract_lines(_fetch_state().get("steps"), "text")
    return _json_response({"steps": steps})


def replace_steps(steps: list[str]) -> str:
    state = _update_state({"steps": _step_items(steps)})
    return _summary_message("Replaced recipe steps on the kitchen screen.", state)


def remove_steps(
    indices: list[int] | None = None,
    matching_texts: list[str] | None = None,
    clear_all: bool = False,
) -> str:
    state = _fetch_state()
    updated = _remove_entries(
        state.get("steps") or [],
        indices=indices or [],
        matching_texts=matching_texts or [],
        clear_all=clear_all,
        text_getter=lambda item: str(item.get("text") or ""),
    )
    state = _update_state({"steps": updated})
    return _summary_message("Removed recipe steps from the kitchen screen.", state)


def clear_steps() -> str:
    state = _update_state({"steps": []})
    return _summary_message("Cleared recipe steps from the kitchen screen.", state)


def read_notes() -> str:
    notes = _normalize_text_list(_fetch_state().get("notes") or [])
    return _json_response({"notes": notes})


def add_notes(notes: list[str]) -> str:
    state = _fetch_state()
    updated_notes = _normalize_text_list(state.get("notes") or []) + _normalize_text_list(notes)
    state = _update_state({"notes": updated_notes})
    return _summary_message("Added notes to the kitchen screen.", state)


def replace_notes(notes: list[str]) -> str:
    state = _update_state({"notes": _normalize_text_list(notes)})
    return _summary_message("Replaced notes on the kitchen screen.", state)


def remove_notes(
    indices: list[int] | None = None,
    matching_texts: list[str] | None = None,
    clear_all: bool = False,
) -> str:
    state = _fetch_state()
    updated = _remove_entries(
        _normalize_text_list(state.get("notes") or []),
        indices=indices or [],
        matching_texts=matching_texts or [],
        clear_all=clear_all,
        text_getter=lambda item: str(item),
    )
    state = _update_state({"notes": updated})
    return _summary_message("Removed notes from the kitchen screen.", state)


def clear_notes() -> str:
    state = _update_state({"notes": []})
    return _summary_message("Cleared notes from the kitchen screen.", state)


def set_timer(duration_seconds: int, label: str = DEFAULT_TIMER_LABEL, auto_start: bool = False) -> str:
    duration = max(0, int(duration_seconds))
    state = _timer_action(
        "set",
        {
            "label": str(label or DEFAULT_TIMER_LABEL).strip() or DEFAULT_TIMER_LABEL,
            "duration_seconds": duration,
            "remaining_seconds": duration,
            "auto_start": bool(auto_start),
        },
    )
    return _summary_message("Updated kitchen screen timer.", state)


def read_timer() -> str:
    timer = dict((_fetch_state().get("timer") or {}))
    return _json_response({"timer": timer})


def start_timer() -> str:
    state = _timer_action("start")
    return _summary_message("Started kitchen screen timer.", state)


def stop_timer() -> str:
    state = _timer_action("pause")
    return _summary_message("Stopped kitchen screen timer.", state)


def reset_timer() -> str:
    state = _timer_action("reset")
    return _summary_message("Reset kitchen screen timer.", state)


def set_link_status(link_status: str) -> str:
    normalized = str(link_status or "").strip() or DEFAULT_LINK_STATUS
    state = _update_state({"link_status": normalized})
    return _summary_message("Updated kitchen screen link status.", state)


def read_link_status() -> str:
    state = _fetch_state()
    return _json_response({"link_status": str(state.get("link_status") or DEFAULT_LINK_STATUS)})


def set_servings(servings: str) -> str:
    normalized = str(servings or "").strip()
    if not normalized:
        raise ValueError("servings must not be empty.")
    state = _update_state({"servings": normalized})
    return _summary_message("Updated servings on the kitchen screen.", state)


def reset_servings() -> str:
    state = _update_state({"servings": DEFAULT_SERVINGS})
    return _summary_message("Reset servings on the kitchen screen.", state)


def clear_recipe_screen() -> str:
    state = _update_state(
        {
            "title": "",
            "subtitle": "",
            "ingredients": [],
            "steps": [],
            "notes": [],
            "servings": DEFAULT_SERVINGS,
            "link_status": DEFAULT_LINK_STATUS,
        }
    )
    state = _timer_action(
        "set",
        {
            "label": DEFAULT_TIMER_LABEL,
            "duration_seconds": 0,
            "remaining_seconds": 0,
            "auto_start": False,
        },
    )
    return _summary_message("Cleared recipe content from the kitchen screen.", state)


def _ingredient_items(ingredients: list[str]) -> list[dict[str, Any]]:
    return [{"text": text, "checked": False} for text in _normalize_text_list(ingredients)]


def _step_items(steps: list[str]) -> list[dict[str, Any]]:
    return [{"text": text, "done": False} for text in _normalize_text_list(steps)]


def _extract_lines(items: Any, text_key: str) -> list[str]:
    lines: list[str] = []
    for item in list(items or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get(text_key) or "").strip()
        if text:
            lines.append(text)
    return lines


def _normalize_text_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            normalized.append(text)
    return normalized


def _remove_entries(
    items: list[Any],
    *,
    indices: list[int],
    matching_texts: list[str],
    clear_all: bool,
    text_getter: Callable[[Any], str],
) -> list[Any]:
    if clear_all:
        return []

    removed_indexes: set[int] = set()
    for index in indices:
        try:
            normalized = int(index)
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            removed_indexes.add(normalized - 1)
    removed_texts = {text.lower() for text in _normalize_text_list(matching_texts)}

    kept: list[Any] = []
    for index, item in enumerate(list(items or [])):
        if index in removed_indexes:
            continue
        if removed_texts and text_getter(item).strip().lower() in removed_texts:
            continue
        kept.append(item)
    return kept


def _fetch_state() -> dict[str, Any]:
    payload = _get_json("/api/state")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Kitchen recipe screen returned an invalid state payload.")
    return state


def _update_state(patch: dict[str, Any]) -> dict[str, Any]:
    payload = _post_json("/api/state", patch)
    state = payload.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Kitchen recipe screen returned an invalid update payload.")
    return state


def _timer_action(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    body["action"] = action
    response = _post_json("/api/timer", body)
    state = response.get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Kitchen recipe screen returned an invalid timer payload.")
    return state


def _get_json(path: str) -> dict[str, Any]:
    request = urllib.request.Request(_build_url(path), method="GET")
    return _read_json_response(request)


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        _build_url(path),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _read_json_response(request)


def _build_url(path: str) -> str:
    return urllib.parse.urljoin(DEFAULT_KITCHEN_SCREEN_URL.rstrip("/") + "/", path.lstrip("/"))


def _read_json_response(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_KITCHEN_SCREEN_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kitchen recipe screen HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Kitchen recipe screen connection error: {exc.reason}") from exc

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Kitchen recipe screen returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Kitchen recipe screen returned a non-object JSON payload.")
    if payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or "Kitchen recipe screen request failed."))
    return payload


def _summary_message(prefix: str, state: dict[str, Any]) -> str:
    title = str(state.get("title") or "").strip() or "(no title)"
    servings = str(state.get("servings") or "").strip() or "(no servings)"
    link_status = str(state.get("link_status") or DEFAULT_LINK_STATUS).strip()
    steps_count = len(list(state.get("steps") or []))
    ingredient_count = len(list(state.get("ingredients") or []))
    notes_count = len(list(state.get("notes") or []))
    timer = dict(state.get("timer") or {})
    timer_label = str(timer.get("label") or DEFAULT_TIMER_LABEL).strip()
    timer_remaining = int(timer.get("remaining_seconds") or 0)
    timer_running = bool(timer.get("running"))
    timer_state = "running" if timer_running else ("done" if timer.get("finished") else "idle")
    return (
        f"{prefix} Title: {title}. Servings: {servings}. Link: {link_status}. "
        f"Ingredients: {ingredient_count}. Steps: {steps_count}. Notes: {notes_count}. "
        f"Timer: {timer_label} ({timer_remaining}s remaining, {timer_state})."
    )


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)
