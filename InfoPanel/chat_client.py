from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_URL = os.getenv("TALOS_TEXT_AGENT_URL", "http://127.0.0.1:8420")
DEFAULT_TOKEN = os.getenv("TALOS_TEXT_AGENT_TOKEN", os.getenv("TEXT_AGENT_API_TOKEN", ""))
DEFAULT_SESSION_ID = os.getenv("TALOS_TEXT_AGENT_SESSION", "main-pc")
DEFAULT_TIMEOUT = float(os.getenv("TALOS_TEXT_AGENT_CLIENT_TIMEOUT", "30"))


def _build_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _request_json(
    base_url: str,
    path: str,
    payload: dict,
    token: str,
    timeout: float,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _build_url(base_url, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
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


def check_health(base_url: str, timeout: float) -> None:
    request = urllib.request.Request(_build_url(base_url, "/health"), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            print(f"Health: {body}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {base_url}: {exc.reason}") from exc


def send_message(base_url: str, token: str, session_id: str, timeout: float, message: str) -> str:
    body = _request_json(
        base_url,
        "/chat",
        {
            "message": message,
            "session_id": session_id,
            "source": "terminal",
        },
        token,
        timeout,
    )
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "Unknown server error"))
    return str(body.get("response", "")).strip()


def reset_session(base_url: str, token: str, session_id: str, timeout: float) -> None:
    body = _request_json(
        base_url,
        "/sessions/reset",
        {"session_id": session_id},
        token,
        timeout,
    )
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "Unknown server error"))


def run_repl(base_url: str, token: str, session_id: str, timeout: float) -> int:
    print(f"Connected target: {base_url}")
    print(f"Session ID: {session_id}")
    print("Commands: /reset, /health, /exit")

    while True:
        try:
            user_input = input("butler> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            return 0
        if user_input == "/reset":
            reset_session(base_url, token, session_id, timeout)
            print("Session reset.")
            continue
        if user_input == "/health":
            check_health(base_url, timeout)
            continue

        response = send_message(base_url, token, session_id, timeout, user_input)
        print(response)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal client for the TALOS text agent.")
    parser.add_argument("message", nargs="*", help="Optional one-shot message to send.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of the TALOS text agent.")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Bearer token for the TALOS text agent.")
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID, help="Conversation session ID.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    parser.add_argument("--health", action="store_true", help="Check server health and exit.")
    parser.add_argument("--reset", action="store_true", help="Reset the session and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        if args.health:
            check_health(args.url, args.timeout)
            return 0

        if args.reset:
            reset_session(args.url, args.token, args.session_id, args.timeout)
            print("Session reset.")
            return 0

        if args.message:
            response = send_message(
                args.url,
                args.token,
                args.session_id,
                args.timeout,
                " ".join(args.message).strip(),
            )
            print(response)
            return 0

        return run_repl(args.url, args.token, args.session_id, args.timeout)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
