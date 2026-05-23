from __future__ import annotations

import argparse
import os
import sys

from agent_service_client import check_health, reset_session, send_message

DEFAULT_URL = os.getenv("TALOS_TEXT_AGENT_URL", "http://127.0.0.1:8420")
DEFAULT_TOKEN = os.getenv("TALOS_TEXT_AGENT_TOKEN", os.getenv("TEXT_AGENT_API_TOKEN", ""))
DEFAULT_SESSION_ID = os.getenv("TALOS_TEXT_AGENT_SESSION", "main-pc")
DEFAULT_TIMEOUT = float(os.getenv("TALOS_TEXT_AGENT_CLIENT_TIMEOUT", "30"))


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
            reset_session(session_id, base_url=base_url, token=token, timeout=timeout)
            print("Session reset.")
            continue
        if user_input == "/health":
            print(f"Health: {check_health(base_url=base_url, timeout=timeout)}")
            continue

        response = send_message(
            user_input,
            session_id=session_id,
            source="terminal",
            base_url=base_url,
            token=token,
            timeout=timeout,
        )
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
            print(f"Health: {check_health(base_url=args.url, timeout=args.timeout)}")
            return 0

        if args.reset:
            reset_session(
                args.session_id,
                base_url=args.url,
                token=args.token,
                timeout=args.timeout,
            )
            print("Session reset.")
            return 0

        if args.message:
            response = send_message(
                " ".join(args.message).strip(),
                session_id=args.session_id,
                source="terminal",
                base_url=args.url,
                token=args.token,
                timeout=args.timeout,
            )
            print(response)
            return 0

        return run_repl(args.url, args.token, args.session_id, args.timeout)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
