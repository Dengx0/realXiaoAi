from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class XiaoAiConfig:
    user_id: str
    pass_token: str
    did: str
    device_id: Optional[str] = None
    timeout: float = 5.0
    account_cache: str = ".mi_account.json"


@dataclass
class HttpApiConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    public_base_url: Optional[str] = None
    audio_dir: str = "generated_audio"
    max_duration_seconds: float = 30.0
    control_token: Optional[str] = None
    poll_interval: float = 2.0
    max_recent_messages: int = 50


@dataclass
class ElevenLabsConfig:
    api_key: str = ""
    prompt_influence: float = 0.3
    timeout: float = 30.0


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    system_prompt: Optional[str] = None  # None 时使用内置默认 prompt
    story_rules: Optional[dict[str, Any]] = None
    temperature: float = 0.7
    timeout: float = 60.0
    enabled: bool = True


@dataclass
class AppConfig:
    xiaoai: XiaoAiConfig
    llm: Optional[LLMConfig] = None
    http_api: HttpApiConfig = field(default_factory=HttpApiConfig)
    elevenlabs: ElevenLabsConfig = field(default_factory=ElevenLabsConfig)

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        xiaoai = XiaoAiConfig(**raw["xiaoai"])
        llm_raw = raw.get("llm")
        http_api_raw = raw.get("http_api") or {}
        elevenlabs_raw = raw.get("elevenlabs") or {}
        return cls(
            xiaoai=xiaoai,
            llm=LLMConfig(**llm_raw) if llm_raw else None,
            http_api=HttpApiConfig(**http_api_raw),
            elevenlabs=ElevenLabsConfig(**elevenlabs_raw),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "xiaoai": asdict(self.xiaoai),
            "http_api": asdict(self.http_api),
            "elevenlabs": asdict(self.elevenlabs),
        }
        if self.llm is not None:
            data["llm"] = asdict(self.llm)
        return data
