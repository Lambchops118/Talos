from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_URL = os.getenv("TALOS_TEXT_AGENT_URL", "http://127.0.0.1:8420")
DEFAULT_TOKEN = os.getenv("TALOS_TEXT_AGENT_TOKEN", os.getenv("TEXT_AGENT_API_TOKEN", ""))
DEFAULT_TIMEOUT = float(os.getenv("TALOS_TEXT_AGENT_CLIENT_TIMEOUT", "30"))


def _normalize_timeout(timeout: float | None) -> float | None:
    if timeout is None:
        return None
    if timeout <= 0:
        return None
    return timeout


def build_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def request_json(
    base_url: str,
    path: str,
    payload: dict,
    token: str = DEFAULT_TOKEN,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        build_url(base_url, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    resolved_timeout = _normalize_timeout(timeout)
    try:
        if resolved_timeout is None:
            response_context = urllib.request.urlopen(request)
        else:
            response_context = urllib.request.urlopen(request, timeout=resolved_timeout)
        with response_context as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise RuntimeError("Server returned a non-object JSON payload.")
            return body
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        message = body_text or str(exc)
        raise RuntimeError(f"HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc


def send_message(
    message: str,
    *,
    session_id: str,
    source: str,
    base_url: str = DEFAULT_URL,
    token: str = DEFAULT_TOKEN,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> str:
    body = request_json(
        base_url,
        "/chat",
        {
            "message": message,
            "session_id": session_id,
            "source": source,
        },
        token=token,
        timeout=timeout,
    )
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "Unknown server error"))
    return str(body.get("response", "")).strip()


def reset_session(
    session_id: str,
    *,
    base_url: str = DEFAULT_URL,
    token: str = DEFAULT_TOKEN,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> None:
    body = request_json(
        base_url,
        "/sessions/reset",
        {"session_id": session_id},
        token=token,
        timeout=timeout,
    )
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "Unknown server error"))


def check_health(
    *,
    base_url: str = DEFAULT_URL,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> dict:
    request = urllib.request.Request(build_url(base_url, "/health"), method="GET")
    resolved_timeout = _normalize_timeout(timeout)
    try:
        if resolved_timeout is None:
            response_context = urllib.request.urlopen(request)
        else:
            response_context = urllib.request.urlopen(request, timeout=resolved_timeout)
        with response_context as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise RuntimeError("Server returned a non-object JSON payload.")
            return body
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {base_url}: {exc.reason}") from exc
