from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from talos.phone.provider import OutboundCallRequest, PhoneConfig, PhoneProvider
from talos.phone.store import PhoneCallRecord, PhoneCallStore


class ElevenLabsTwilioProvider(PhoneProvider):
    def __init__(
        self,
        config: PhoneConfig,
        *,
        store: PhoneCallStore,
    ) -> None:
        self.config = config
        self.store = store

    def start_outbound_call(self, request: OutboundCallRequest) -> PhoneCallRecord:
        if not self.config.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured.")
        if not self.config.agent_id:
            raise RuntimeError("TALOS_PHONE_AGENT_ID is not configured.")
        if not self.config.phone_number_id:
            raise RuntimeError("TALOS_PHONE_NUMBER_ID is not configured.")

        payload = {
            "agent_id": self.config.agent_id,
            "agent_phone_number_id": self.config.phone_number_id,
            "to_number": request.to_number,
            "conversation_initiation_client_data": {
                "session_id": request.session_id,
                "purpose": request.purpose,
                "brief_context": request.brief_context,
                "contact_name": request.contact_name or "",
            },
        }
        response = self._request_json(
            "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
            payload=payload,
        )
        call_id = str(response.get("conversation_id") or "").strip()
        if not call_id:
            raise RuntimeError("ElevenLabs outbound call response did not include a conversation_id.")

        existing = self.store.get_call(call_id)
        if existing is None:
            record = self.store.create_call(
                call_id=call_id,
                provider="elevenlabs_twilio",
                provider_call_id=str(response.get("callSid") or "").strip() or None,
                conversation_id=call_id,
                agent_id=self.config.agent_id,
                session_id=request.session_id,
                direction="outbound",
                remote_number=request.to_number,
                contact_name=request.contact_name,
                purpose=request.purpose,
                brief_context=request.brief_context,
                status="initiated",
                metadata={"provider_response": response},
            )
        else:
            record = self.store.update_call(
                call_id,
                provider_call_id=str(response.get("callSid") or "").strip() or existing.provider_call_id,
                agent_id=self.config.agent_id,
                session_id=request.session_id,
                direction="outbound",
                remote_number=request.to_number,
                contact_name=request.contact_name or existing.contact_name,
                purpose=request.purpose or existing.purpose,
                brief_context=request.brief_context or existing.brief_context,
                status="initiated",
                metadata={"provider_response": response},
            )
        self.store.add_event(
            call_id=record.call_id,
            event_type="outbound_call_requested",
            message="Outbound call requested via ElevenLabs/Twilio.",
            payload=response,
        )
        return record

    def get_call(self, call_id: str) -> PhoneCallRecord | None:
        return self.store.get_call(call_id)

    def list_recent_calls(self, *, limit: int = 25) -> list[PhoneCallRecord]:
        return self.store.list_recent_calls(limit=limit)

    def ingest_call_event(self, payload: dict[str, Any]) -> PhoneCallRecord:
        event_type = str(payload.get("type") or "").strip()
        data = dict(payload.get("data") or {})
        if not event_type:
            raise ValueError("Phone webhook payload is missing 'type'.")

        if event_type == "post_call_transcription":
            return self._ingest_transcription_event(payload, data)
        if event_type == "call_initiation_failure":
            return self._ingest_failure_event(payload, data)
        return self._ingest_generic_event(payload, data, event_type=event_type)

    def fetch_transcript(self, call_id: str) -> list[dict[str, Any]] | None:
        record = self.store.get_call(call_id)
        if record is None:
            return None
        return record.transcript or []

    def sync_call_snapshot(self, snapshot: dict[str, Any]) -> PhoneCallRecord:
        return self.store.upsert_snapshot(snapshot)

    def _ingest_transcription_event(
        self,
        payload: dict[str, Any],
        data: dict[str, Any],
    ) -> PhoneCallRecord:
        call_id = str(data.get("conversation_id") or "").strip()
        if not call_id:
            raise ValueError("Transcription webhook is missing data.conversation_id.")

        transcript = data.get("transcript") if isinstance(data.get("transcript"), list) else []
        record = self.store.get_call(call_id)
        snapshot = {
            "call_id": call_id,
            "provider": "elevenlabs_twilio",
            "conversation_id": call_id,
            "agent_id": data.get("agent_id"),
            "session_id": _extract_session_id(record, transcript, payload),
            "direction": record.direction if record else _infer_direction(transcript),
            "remote_number": record.remote_number if record else "unknown",
            "contact_name": record.contact_name if record else None,
            "purpose": record.purpose if record else None,
            "brief_context": record.brief_context if record else None,
            "status": "completed" if str(data.get("status") or "").strip().lower() == "done" else "completed",
            "outcome": "completed",
            "ended_at": _event_timestamp(payload),
            "transcript": transcript,
            "summary": record.summary if record else None,
            "metadata": _merge_metadata(record, {"transcription_event": payload}),
        }
        updated = self.store.upsert_snapshot(snapshot)
        self.store.add_event(
            call_id=call_id,
            event_type="post_call_transcription",
            message="Post-call transcription received.",
            payload=payload,
        )
        return updated

    def _ingest_failure_event(
        self,
        payload: dict[str, Any],
        data: dict[str, Any],
    ) -> PhoneCallRecord:
        call_id = str(data.get("conversation_id") or "").strip()
        if not call_id:
            raise ValueError("Failure webhook is missing data.conversation_id.")
        metadata = dict(data.get("metadata") or {})
        metadata_body = dict(metadata.get("body") or {})
        record = self.store.get_call(call_id)
        remote_number = (
            str(metadata_body.get("To") or "").strip()
            or str(metadata_body.get("Called") or "").strip()
            or str(metadata_body.get("to_number") or "").strip()
            or (record.remote_number if record else "unknown")
        )
        updated = self.store.upsert_snapshot(
            {
                "call_id": call_id,
                "provider": "elevenlabs_twilio",
                "provider_call_id": (
                    str(metadata_body.get("CallSid") or "").strip()
                    or str(metadata_body.get("call_sid") or "").strip()
                    or (record.provider_call_id if record else None)
                ),
                "conversation_id": call_id,
                "agent_id": data.get("agent_id"),
                "session_id": record.session_id if record else None,
                "direction": record.direction if record else "outbound",
                "remote_number": remote_number,
                "contact_name": record.contact_name if record else None,
                "purpose": record.purpose if record else None,
                "brief_context": record.brief_context if record else None,
                "status": "failed",
                "outcome": str(data.get("failure_reason") or "failed"),
                "ended_at": _event_timestamp(payload),
                "last_error": str(data.get("failure_reason") or "Call initiation failed."),
                "metadata": _merge_metadata(record, {"failure_event": payload}),
            }
        )
        self.store.add_event(
            call_id=call_id,
            event_type="call_initiation_failure",
            message=f"Call initiation failed: {str(data.get('failure_reason') or 'failed')}",
            payload=payload,
        )
        return updated

    def _ingest_generic_event(
        self,
        payload: dict[str, Any],
        data: dict[str, Any],
        *,
        event_type: str,
    ) -> PhoneCallRecord:
        call_id = str(data.get("conversation_id") or "").strip()
        if not call_id:
            raise ValueError(f"{event_type} webhook is missing data.conversation_id.")
        record = self.store.get_call(call_id)
        updated = self.store.upsert_snapshot(
            {
                "call_id": call_id,
                "provider": "elevenlabs_twilio",
                "conversation_id": call_id,
                "agent_id": data.get("agent_id"),
                "session_id": record.session_id if record else None,
                "direction": record.direction if record else "unknown",
                "remote_number": record.remote_number if record else "unknown",
                "status": record.status if record else "updated",
                "metadata": _merge_metadata(record, {event_type: payload}),
            }
        )
        self.store.add_event(
            call_id=call_id,
            event_type=event_type,
            message=f"Received {event_type} webhook event.",
            payload=payload,
        )
        return updated

    def _request_json(self, url: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self.config.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            message = body_text or str(exc)
            raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"ElevenLabs connection error: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except Exception as exc:
            raise RuntimeError("ElevenLabs returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("ElevenLabs returned a non-object response.")
        return parsed


def _event_timestamp(payload: dict[str, Any]) -> str | None:
    event_timestamp = payload.get("event_timestamp")
    if event_timestamp in (None, ""):
        return None
    return str(event_timestamp)


def _merge_metadata(record: PhoneCallRecord | None, updates: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(record.metadata or {}) if record is not None else {}
    metadata.update(updates)
    return metadata


def _infer_direction(transcript: list[dict[str, Any]]) -> str:
    return "inbound" if transcript else "unknown"


def _extract_session_id(
    record: PhoneCallRecord | None,
    transcript: list[dict[str, Any]],
    payload: dict[str, Any],
) -> str | None:
    if record is not None and record.session_id:
        return record.session_id
    data = dict(payload.get("data") or {})
    candidate = str(data.get("session_id") or "").strip()
    if candidate:
        return candidate
    if transcript:
        return "phone:inbound"
    return None
