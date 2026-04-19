from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MiPass:
    qs: Optional[str] = None
    _sign: Optional[str] = None
    callback: Optional[str] = None
    location: Optional[str] = None
    ssecurity: Optional[str] = None
    passToken: Optional[str] = None
    nonce: Optional[str] = None
    userId: Optional[str] = None
    cUserId: Optional[str] = None
    psecurity: Optional[str] = None


@dataclass
class XiaoAiAccount:
    user_id: str
    device_id: str
    pass_token: Optional[str] = None
    service_token: Optional[str] = None
    did: Optional[str] = None
    pass_data: MiPass = field(default_factory=MiPass)
    device: Optional[dict[str, Any]] = None

    @property
    def login_cookies(self) -> dict[str, str]:
        cookies = {"userId": self.user_id, "deviceId": self.device_id}
        if self.pass_token:
            cookies["passToken"] = self.pass_token
        return cookies

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "device_id": self.device_id,
            "pass_token": self.pass_token,
            "service_token": self.service_token,
            "did": self.did,
            "pass_data": self.pass_data.__dict__,
            "device": self.device,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "XiaoAiAccount":
        return cls(
            user_id=data["user_id"],
            device_id=data["device_id"],
            pass_token=data.get("pass_token"),
            service_token=data.get("service_token"),
            did=data.get("did"),
            pass_data=MiPass(**(data.get("pass_data") or {})),
            device=data.get("device"),
        )


@dataclass
class ConversationMessage:
    query: str
    timestamp: int
    answers: list[dict[str, Any]]
    request_id: Optional[str] = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "ConversationMessage":
        return cls(
            query=record["query"],
            timestamp=record["time"],
            answers=record.get("answers") or [],
            request_id=record.get("requestId"),
        )


@dataclass
class LLMActionResult:
    """LLM Function Calling 返回的动作结果。"""
    action: str       # "pass_through" | "speak_text" | "generate_sound_effect"
    text: str = ""
    audio_url: str = ""
    interrupt: bool = True
    reason: str = ""
