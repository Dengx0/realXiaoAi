from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import requests

SOUND_GENERATION_URL = "https://api.elevenlabs.io/v1/sound-generation"


@dataclass(frozen=True)
class GeneratedAudioResult:
    file_path: Path
    filename: str
    content_type: str = "audio/mpeg"


class ElevenLabsAudioError(RuntimeError):
    pass


def generate_sound_effect(
    text: str,
    duration_seconds: int | float,
    output_dir: Path,
    prompt_influence: float = 0.3,
    timeout: float = 30.0,
    api_key: str = "",
) -> GeneratedAudioResult:
    prompt = text.strip()
    if not prompt:
        raise ValueError("text 不能为空。")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds 必须大于 0。")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"sound_{uuid.uuid4().hex}.mp3"
    file_path = output_dir / filename

    response = requests.post(
        SOUND_GENERATION_URL,
        json={
            "text": prompt,
            "duration_seconds": duration_seconds,
            "prompt_influence": prompt_influence,
        },
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )

    if not response.ok:
        message = _extract_error_message(response)
        raise ElevenLabsAudioError(f"ElevenLabs 请求失败: HTTP {response.status_code} - {message}")

    file_path.write_bytes(response.content)
    return GeneratedAudioResult(file_path=file_path, filename=filename)


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "unknown error"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return "unknown error"
