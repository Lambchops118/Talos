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
python -m pip install "mcp[cli]"
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
- `TALOS_TIMEZONE`
- `TALOS_WEATHER_LOCATION`
- `TALOS_WEATHER_UNITS`

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

### MCP Tools

TALOS exposes local actions to the model through a local MCP server. The current flow is:

1. `InfoPanel/mcp_server.py` starts the aggregate MCP server over stdio.
2. `InfoPanel/local_mcp_client.py` connects to that server, calls `tools/list`, and converts the returned schemas into OpenAI tool definitions.
3. `InfoPanel/agent_runtime.py` sends those tool definitions with each model request.
4. If the model chooses a tool, `agent_runtime.py` calls it back through the local MCP client by tool name.

Tool implementations are registered in provider modules under `InfoPanel/mcp_servers/providers/`. The existing home automation tools are defined in `InfoPanel/mcp_servers/providers/home_automation.py` with `@server.tool()` decorators, and their actual device logic lives in `InfoPanel/home_automation_actions.py`.

The home automation provider also exposes:

- `get_current_datetime`, which gives the agent the current local date, time, weekday, year, and timezone. Set `TALOS_TIMEZONE` in `.env` to force an IANA timezone such as `America/New_York`; otherwise TALOS falls back to the host machine's local timezone.
- `get_current_weather`, which gives the agent the current weather, temperature, humidity, UV index, wind, and today's temperature range. By default it uses `TALOS_WEATHER_LOCATION` and `TALOS_WEATHER_UNITS` from `.env`, but the tool can also take a one-off location override.

Server assembly is separate from tool definition:

- `InfoPanel/mcp_servers/aggregate.py` defines the tool surface used by the local agent runtime.
- `InfoPanel/mcp_servers/home_automation_server.py` and `InfoPanel/mcp_servers/tv_control_server.py` expose standalone servers for specific domains.
- `InfoPanel/mcp_http_app.py` mounts those domain servers over HTTP.

To add a new MCP tool in an existing domain:

1. Add the real logic to the relevant actions module, such as `InfoPanel/home_automation_actions.py`.
2. Register a tool in the matching provider module with `@server.tool()`.
3. Use a clear docstring and typed parameters. The MCP SDK uses those to describe the tool and generate its input schema.
4. Restart the TALOS process so the local MCP client refreshes its cached tool list.

Example:

```python
@server.tool()
def set_thermostat(target_f: int) -> str:
    """Set the thermostat to the requested Fahrenheit temperature."""
    return actions.set_thermostat(target_f)
```

To add a new MCP tool domain:

1. Create `InfoPanel/mcp_servers/providers/<domain>.py` with a `register(server)` function.
2. Export that registrar from `InfoPanel/mcp_servers/providers/__init__.py`.
3. Add the registrar to `InfoPanel/mcp_servers/aggregate.py` if the main TALOS agent should be able to use it.
4. Optionally create a dedicated `InfoPanel/mcp_servers/<domain>_server.py`.
5. Optionally mount that server in `InfoPanel/mcp_http_app.py` if you want HTTP access.

### Split Agent And Voice Worker

TALOS can now run as two separate processes:

- main agent process: router, scheduler, text server, GUI, MCP/runtime
- voice worker process: microphone, wake word, Whisper, Polly playback

Start the main agent:

```bash
python InfoPanel/agent_main.py
```

or equivalently:

```bash
python InfoPanel/main.py
```

Start the voice worker separately:

```bash
python InfoPanel/voice_worker.py
```

The voice worker sends recognized commands to the main agent over the text-agent HTTP API using `TALOS_TEXT_AGENT_URL` and `TALOS_TEXT_AGENT_TOKEN`.

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
