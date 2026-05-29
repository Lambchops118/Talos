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
- `TALOS_MCP_SERVERS`

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

### MCP Tools And Resources

TALOS can expose tools from one or more MCP servers. By default, if `TALOS_MCP_SERVERS` is unset, it uses the built-in local aggregate server in `InfoPanel/mcp_server.py`. If `TALOS_MCP_SERVERS` is set, `InfoPanel/local_mcp_client.py` treats it as the full MCP server list and manages all configured connections.

The current flow is:

1. `InfoPanel/local_mcp_client.py` starts one or more MCP connections.
2. Each configured server is queried with `tools/list`.
3. The returned tools are merged into one tool surface for `InfoPanel/agent_runtime.py`.
4. The runtime also exposes host-level helper tools for MCP resources: `list_mcp_resources`, `list_mcp_resource_templates`, and `read_mcp_resource`.
5. If the model chooses a tool, TALOS routes that call back to the MCP server that owns it.

Supported transports in the current client:

- local `stdio` servers
- remote `streamable_http` servers

If two servers expose the same tool name, you must set a `tool_prefix` on at least one of them so the merged tool list stays unique.

Tool implementations are registered in provider modules under `InfoPanel/mcp_servers/providers/`. The existing home automation tools are defined in `InfoPanel/mcp_servers/providers/home_automation.py` with `@server.tool()` decorators, and their actual device logic lives in `InfoPanel/home_automation_actions.py`.

The home automation provider also exposes:

- `get_current_datetime`, which gives the agent the current local date, time, weekday, year, and timezone. Set `TALOS_TIMEZONE` in `.env` to force an IANA timezone such as `America/New_York`; otherwise TALOS falls back to the host machine's local timezone.
- `get_current_weather`, which gives the agent the current weather, temperature, humidity, UV index, wind, and today's temperature range. By default it uses `TALOS_WEATHER_LOCATION` and `TALOS_WEATHER_UNITS` from `.env`, but the tool can also take a one-off location override. UV comes from OpenWeather One Call, while the initial location lookup uses the standard current-weather endpoint.

Server assembly is separate from tool definition:

- `InfoPanel/mcp_servers/aggregate.py` defines the tool surface used by the local agent runtime.
- `InfoPanel/mcp_servers/home_automation_server.py` and `InfoPanel/mcp_servers/tv_control_server.py` expose standalone servers for specific domains.
- `InfoPanel/mcp_http_app.py` mounts those domain servers over HTTP.

Example `TALOS_MCP_SERVERS` value:

```json
[
  {
    "name": "talos-local",
    "transport": "stdio",
    "command": "python",
    "args": ["InfoPanel/mcp_server.py"]
  },
  {
    "name": "github",
    "transport": "streamable_http",
    "url": "https://example.com/mcp",
    "auth_token_env": "GITHUB_MCP_TOKEN",
    "tool_prefix": "github_"
  }
]
```

Notes:

- Once `TALOS_MCP_SERVERS` is set, it replaces the default built-in MCP list. Include your local TALOS server explicitly if you still want local home-automation tools.
- `auth_token_env` tells TALOS which environment variable contains a bearer token for that remote MCP server.
- `headers` can also be provided directly in the JSON config if a server needs custom headers.
- Use `tool_prefix` when a remote server might expose names that collide with local tools.
- TALOS now supports multi-step tool execution loops. Set `TALOS_MAX_TOOL_CALL_ROUNDS` in `.env` if you need to raise or lower the default limit of `8`.
- Resource reads are text-first. Binary resources are surfaced with MIME metadata and a base64 preview so the model can reason about what is available without flooding context.

KiCad helper integration:

- Set `KICAD_MCP_SERVER_PATH` to a local checkout of `mixelpixx/KiCAD-MCP-Server` and TALOS will append it automatically as a `stdio` MCP server.
- The helper accepts either the repo root or a direct path to `dist/index.js`.
- Use `KICAD_PYTHONPATH`, `KICAD_PYTHON`, `KICAD_AUTO_LAUNCH`, `KICAD_MCP_LOG_LEVEL`, and `KICAD_MCP_DEV` to mirror the upstream KiCad MCP server environment.

Example KiCad setup:

```env
KICAD_MCP_SERVER_PATH=/Users/you/MCP/KiCAD-MCP-Server
KICAD_MCP_COMMAND=node
KICAD_MCP_TOOL_PREFIX=kicad_
KICAD_AUTO_LAUNCH=false
KICAD_PYTHONPATH=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/lib/python3.9/site-packages
```

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
