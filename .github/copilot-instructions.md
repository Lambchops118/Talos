## Quick Orientation for AI Coding Agents

This repo implements the TALOS locally-run voice/text agent plus a pygame display.

1. Big Picture
- Core agent: `talos/` contains the main process, router, agent runtime, text server/client, voice worker, scheduler, services, MCP client, and MCP servers.
- Display artifact: `InfoPanel/` contains pygame display modules and visual assets. It should stay UI-focused.
- Peripherals: `Peripherals/` contains MicroPython and MQTT helper scripts for hardware devices.
- Archive and experiments: `archive/` and `experiments/` are not part of the main runtime.

2. Runtime Flow
- `.venv-main/bin/python -m talos` starts the main process in `talos/main.py`.
- `talos/router.py` consumes central messages and calls `talos.agent.runtime.run_command(...)` for foreground agent work.
- `talos/text/server.py` exposes the local HTTP chat API.
- `talos/voice/worker.py` starts the microphone/wake-word/STT/TTS voice process.
- `InfoPanel/screen.py` is imported by `talos/main.py` and must run in the main thread because of pygame.

3. Common Commands
```bash
.venv-main/bin/python -m talos
.venv-voice/bin/python -m talos.voice.worker
.venv-main/bin/python -m talos.text.client --health
.venv-main/bin/python -m unittest tests/test_agent_runtime_recovery.py tests/test_local_mcp_client_resources.py
```

4. Where To Change Things
- Agent/tool loop behavior: `talos/agent/runtime.py`
- System prompt: `talos/agent/prompts.py`
- Text HTTP API: `talos/text/server.py`
- Terminal client: `talos/text/client.py`
- Voice pipeline: `talos/voice/agent.py`
- Scheduled jobs: `talos/scheduler/tasks.py`
- Device and data actions: `talos/services/`
- MCP server providers: `talos/mcp_servers/providers/`
- MCP client routing/resources: `talos/mcp_client/client.py`
- Display layout/assets: `InfoPanel/`

5. Gotchas
- Pygame belongs on the main thread.
- Audio dependencies can fail on headless machines.
- The main process is intended to run from Python 3.10+ so MCP can operate normally.
- The voice worker is intended to run from Python 3.12 and is the only path that imports Whisper/openwakeword.
- Do not put new agent/runtime files under `InfoPanel`; that directory is only the GUI/display artifact now.
- Keep hardware/MQTT changes isolated in `talos/services/` or `Peripherals/`.
