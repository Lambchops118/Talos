"""Build voice backends from environment configuration.

The goal of this module is that the *same code* runs on the macOS dev box and the
CUDA deploy box, with only environment variables changing. Recommended profiles:

macOS dev (local, no hosted APIs)::

    TALOS_LLM_BACKEND=openai_chat
    TALOS_LLM_BASE_URL=http://127.0.0.1:11434/v1   # Ollama
    TALOS_LLM_MODEL=qwen2.5:7b-instruct

CUDA deploy (5080 runs vLLM)::

    TALOS_LLM_BACKEND=openai_chat
    TALOS_LLM_BASE_URL=http://127.0.0.1:8000/v1     # vLLM OpenAI server
    TALOS_LLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ

Only the LLM backend is wired here for now; STT/TTS factories are added alongside
their concrete implementations.
"""

from __future__ import annotations

import os

from talos.config import env_float, env_int, load_environment
from talos.voice.backends.base import LLMBackend
from talos.voice.backends.llm_openai_compat import OpenAICompatibleChatBackend


def get_llm_backend() -> LLMBackend:
    """Construct the configured streaming LLM backend.

    ``TALOS_LLM_BACKEND`` selects the implementation; currently only the
    OpenAI-compatible Chat Completions backend (``openai_chat``) is available,
    which covers Ollama, vLLM, and hosted OpenAI-compatible providers.
    """
    load_environment()
    backend = os.getenv("TALOS_LLM_BACKEND", "openai_chat").strip().lower()

    if backend in {"openai_chat", "chat", "ollama", "vllm"}:
        return OpenAICompatibleChatBackend(
            model=_required("TALOS_LLM_MODEL"),
            base_url=os.getenv("TALOS_LLM_BASE_URL", "").strip() or None,
            api_key=os.getenv("TALOS_LLM_API_KEY", "").strip() or None,
            temperature=env_float("TALOS_LLM_TEMPERATURE", 0.5),
            max_tokens=env_int("TALOS_LLM_MAX_TOKENS", 400),
        )

    raise RuntimeError(
        f"Unsupported TALOS_LLM_BACKEND '{backend}'. Expected one of: "
        "openai_chat, ollama, vllm."
    )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Configure the local model name "
            "(e.g. TALOS_LLM_MODEL=qwen2.5:7b-instruct for Ollama)."
        )
    return value
