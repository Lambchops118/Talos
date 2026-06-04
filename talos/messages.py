import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


MessageType = Literal["voice_cmd", "text_cmd", "status", "event", "ui"]

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
    benchmark: Optional[Any] = None

@dataclass
class TextPayload:
    command: str
    session_id: str
    source: str = "text"
    reply_queue: Optional[Any] = None
    requested_mode: str = "auto"

@dataclass
class EventPayload:
    name: str
    data: dict
