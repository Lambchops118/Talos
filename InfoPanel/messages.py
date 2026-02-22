from dataclasses import dataclass, field
from typing import Any, Literal
import time


MessageType = Literal["voice_cmd", "status", "event", "ui"]


@dataclass
class Message:
    type: MessageType
    payload: Any
    needs_llm: bool = False
    ts: float = field(default_factory=time.time)


@dataclass
class StatusPayload:
    key: str
    value: Any
    freshness: float


@dataclass
class VoicePayload:
    command: str


@dataclass
class EventPayload:
    name: str
    data: dict
