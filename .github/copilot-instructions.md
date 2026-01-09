## Quick Orientation for AI Coding Agents

This repo implements the "Monkey Butler / Talos" device and display stack. Below are concise, actionable notes to get productive quickly and avoid breaking runtime behavior.

1) Big picture
- Core UI: `InfoPanel/` — a Pygame-based information dashboard driven by `InfoPanel/main.py` and `InfoPanel/screen.py`. The GUI must run in the main thread (Pygame requirement).
- Voice + assistant: `InfoPanel/voice_agent.py` — captures audio (SpeechRecognition/Whisper/OpenAI), calls OpenAI chat completions (function-calling), and synthesizes with AWS Polly.
- Orchestration: `InfoPanel/tasks.py` — schedules jobs (APScheduler), publishes MQTT messages, and exposes a `functions` list used by the OpenAI function-calling flow.
- Integrations: MQTT (paho-mqtt), TV CEC / ADB controls (`Peripherals/mqtt_server/control_display.py`), AWS Polly, OpenAI APIs, and local hardware (microphone, audio, display).

2) How the pieces talk
- `InfoPanel/main.py` spins up two queues: `gui_queue` (for UI text updates) and `processing_queue` (for recognized commands). It starts background listening via `voice_agent.run_voice_recognition(processing_queue)` and a worker thread that calls `voice_agent.process_commands(processing_queue, gui_queue)`.
- The OpenAI response path: `voice_agent.handle_command()` calls `client.chat.completions.create(..., functions=tasks.functions, function_call='auto')`. If OpenAI emits a function call, the code looks up and executes the corresponding function in `InfoPanel/tasks.py` and posts results back to the assistant for follow-up.

3) Critical developer workflows
- Install dependencies:
```
pip install -r requirements.txt
```
- Provide required secrets in a `.env` at repository root (dotenv is used). Minimum keys used in code:
```
OPENAI_API_KEY
AWS_ACCESS_KEY
AWS_SECRET_KEY
OPEN_WEATHER_API_KEY
```
- Run the full local system (GUI + voice listener):
```
python InfoPanel/main.py
```
This starts background listening (SpeechRecognition/whisper), the command worker, APScheduler jobs, and the Pygame GUI.

4) Project-specific patterns and gotchas
- Pygame must run in the main thread. Prefer starting via `InfoPanel/main.py` instead of importing `InfoPanel/screen.py` directly into background threads.
- Function-calling schema: `InfoPanel/tasks.py` contains the JSON schema list named `functions`. This exact structure is passed to OpenAI; when you add or change a function, update both the schema in `tasks.functions` and the implementation in `tasks.py` (names must match).
- MQTT broker details are hard-coded in `InfoPanel/tasks.py` (`BROKER = "192.168.1.160"`) and in `Peripherals/mqtt_server/control_display.py` (`BROKER = "localhost"`). Verify and align those values for your environment.
- The voice stack currently uses the new OpenAI client `openai.OpenAI(api_key=...)` and calls `client.chat.completions.create` with `model='gpt-4-0613'`. Be mindful of billing and API rate limits when testing.

5) Integration and hardware notes
- Audio: `pyaudio` is required. On headless machines or CI, audio devices may cause failures. To run without a microphone, avoid calling `voice_agent.run_voice_recognition()` or mock the microphone.
- AWS Polly: `voice_agent` writes a WAV file `speech_output.wav` and plays it via `pyaudio`. Ensure `AWS_ACCESS_KEY`/`AWS_SECRET_KEY` are configured if you test TTS.
- MQTT + TV: `Peripherals/mqtt_server/control_display.py` expects to run on a Raspberry Pi connected to the display and subscribes to `tv_display/wake_status`.

6) Debugging tips
- Use prints/logging: the code uses `print(...)` extensively. Start by scanning stdout for messages such as "Background listening started." or "FUNCTION CALL DETECTED".
- GUI state: the `gui_queue` accepts tuples like `("VOICE_CMD", recognized_command, gpt_response)`. You can inject test messages with a small script to verify rendering.
- Function-calling flow: If OpenAI returns a `function_call`, the assistant will rely on `tasks.py` implementations. Unit-test function implementations separately (they mostly interact with MQTT).
- Headless GUI testing: on Linux, `SDL_VIDEODRIVER=dummy` can be used for headless runs. On Windows, run on a machine with an attached display.

7) Tests and quick checks
- There is a `tests/` directory with multiple scripts. These are standalone scripts — run them directly, e.g.:
```
python tests/main.py
```
or run a specific test file. There is no canonical pytest harness enforced; inspect and run scripts individually.

8) Where to change things safely
- Add new assistant functions: edit `InfoPanel/tasks.py` — update the `functions` list and add the Python implementation. Keep parameter schemas accurate and minimal.
- Adjust scheduler jobs: `start_scheduler(gui_queue)` in `InfoPanel/tasks.py`.
- UI changes: `InfoPanel/screen.py` (layout, Widgets in `windows.py`). Static assets (models, fonts) are referenced by relative paths inside `InfoPanel/`.

9) Files to inspect first (examples)
- `InfoPanel/main.py` — entrypoint used for development runs.
- `InfoPanel/screen.py` — Pygame rendering logic, widgets, and main loop.
- `InfoPanel/voice_agent.py` — audio capture, OpenAI calls, AWS Polly TTS, function-calling flow.
- `InfoPanel/tasks.py` — functions schema, MQTT broker settings, APScheduler jobs.
- `Peripherals/mqtt_server/control_display.py` — TV/CEC integration examples.

If any of the environment assumptions are incorrect or you'd like more detail for a specific area (unit tests for `tasks.water_plants`, mocking audio, or CI-friendly builds), tell me which part to expand and I'll iterate.
