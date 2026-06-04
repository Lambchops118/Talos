from __future__ import annotations

from talos.agent.prompting import PromptContext, build_instructions


def build_monkey_butler_prompt(interaction_mode: str = "voice") -> str:
    return build_instructions(PromptContext(interaction_mode=interaction_mode))


MONKEY_BUTLER_PROMPT = build_monkey_butler_prompt()
