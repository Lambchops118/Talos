# TALOS

[![CI](https://github.com/Lambchops118/Talos/actions/workflows/ci.yml/badge.svg)](https://github.com/Lambchops118/Talos/actions/workflows/ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/Lambchops118/Talos)](https://github.com/Lambchops118/Talos/releases)
[![Last Commit](https://img.shields.io/github/last-commit/Lambchops118/Talos)](https://github.com/Lambchops118/Talos/commits/main)

TALOS is a home automation and voice-assistant project built around a Python host application, MQTT-connected peripherals, and a display-driven "Monkey Butler" interface.

## Project Layout

- `InfoPanel/`: desktop application, voice pipeline, scheduler, and on-screen status UI
- `Peripherals/fan/`: Raspberry Pi Pico W script for MQTT-controlled fan switching
- `Peripherals/quad_pump/`: Raspberry Pi Pico W script for MQTT-controlled plant watering
- `Peripherals/mqtt_server/control_display.py`: MQTT listener that sends TV power/input commands
- `tests/`: local experiments and prototype scripts

## Build

This repository does not currently produce packaged installers or binary artifacts. The main build target is the Python host application in `InfoPanel/`, with peripheral scripts deployed manually to MicroPython devices.

### Host Application

Recommended prerequisites:

- Python 3.11+
- PortAudio development/runtime libraries for `PyAudio`
- A reachable MQTT broker
- Valid API credentials in `.env`

Setup:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyowm
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

The application reads configuration from `.env`. At minimum, the current code references:

- `OPENAI_API_KEY`
- `AWS_ACCESS_KEY`
- `AWS_SECRET_KEY`
- `OPEN_WEATHER_API_KEY`

Optional voice settings:

- `WAKE_WORD`
- `WAKE_WORD_MODE`
- `WAKE_WORD_MODEL`
- `OPENAI_VOICE_MODEL`

Optional text-agent settings:

- `TEXT_AGENT_ENABLED`
- `TEXT_AGENT_HOST`
- `TEXT_AGENT_PORT`
- `TEXT_AGENT_API_TOKEN`
- `TEXT_AGENT_TIMEOUT`
- `TEXT_AGENT_ALLOWED_NETWORKS`

Run the host app:

```bash
python InfoPanel/main.py
```

Voice benchmark summaries print directly to the main app terminal. Each app run also creates a new timestamped CSV in `logs/`, for example `voice_benchmarks_20260511_124500_123456.csv`.

### Text Chat Over Tailscale

The host app now starts a small built-in text server alongside the voice pipeline. Voice and text both go through the same agent runtime and MCP tool path.

Recommended setup:

1. Install Tailscale on the homelab machine running TALOS and on the client machine.
2. Join both machines to the same tailnet.
3. Set `TEXT_AGENT_API_TOKEN` in `.env`.
4. Leave `TEXT_AGENT_HOST=0.0.0.0`.
5. Keep `TEXT_AGENT_ALLOWED_NETWORKS` at its default unless you need a custom allowlist.

By default the text server only accepts requests from localhost and the standard Tailscale IPv4/IPv6 ranges, which keeps it off the rest of your LAN even when bound to all interfaces.

Endpoints:

- `GET /` serves a minimal browser chat UI
- `GET /health` returns a health check
- `POST /chat` sends a text prompt
- `POST /sessions/reset` clears conversation state for one session

Example request:

```bash
curl -X POST "http://<tailscale-hostname-or-ip>:8420/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"message":"turn the fan on", "session_id":"main-pc"}'
```

Example reset:

```bash
curl -X POST "http://<tailscale-hostname-or-ip>:8420/sessions/reset" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"session_id":"main-pc"}'
```

### Terminal Client

You can also use the built-in terminal client instead of raw `curl`.

One-shot command:

```bash
python InfoPanel/chat_client.py --url "http://<tailscale-hostname-or-ip>:8420" --token "<your-token>" --session-id "main-pc" "turn the fan on"
```

Interactive mode:

```bash
python InfoPanel/chat_client.py --url "http://<tailscale-hostname-or-ip>:8420" --token "<your-token>" --session-id "main-pc"
```

On Windows, the repository root now includes `butler.cmd`, which launches the same client. If the repo root is on your `PATH`, you can run:

```powershell
butler --url "http://<tailscale-hostname-or-ip>:8420" --token "<your-token>" --session-id "main-pc"
```

### Peripheral Deployment

The peripheral code is written for MicroPython on Raspberry Pi Pico W boards and is deployed manually.

Typical flow:

1. Flash MicroPython to the Pico W.
2. Update the device-specific values in the script before deployment:
   - Wi-Fi SSID and password
   - MQTT broker address
   - Pin mappings and MQTT topic prefix
3. Copy the desired peripheral script to the board as `main.py`.
4. Copy the bundled MQTT helper alongside it if your MicroPython layout requires it.
5. Reboot the device and verify it connects to the broker.

Current peripheral entry points:

- `Peripherals/fan/main.py`
- `Peripherals/quad_pump/main.py`

## Release

There is no automated CI/CD or GitHub Actions release pipeline checked into this repository at the moment. Releases are manual.

A practical release flow is:

1. Install dependencies and run the host application locally.
2. Smoke-test any affected MQTT peripherals against the target broker.
3. Commit the release candidate.
4. Create an annotated git tag.
5. Push the branch and tag to GitHub.
6. Draft a GitHub Release summarizing user-visible changes and any hardware/config updates.

Example tagging flow:

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin main
git push origin v0.1.0
```
