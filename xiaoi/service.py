from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiaudio.aiaudio import GeneratedAudioResult, generate_sound_effect

from .client import XiaoAiMinaClient
from .config import AppConfig
from .llm_client import LLMClient
from .messages import XiaoAiMessagePoller
from .models import ConversationMessage, LLMActionResult

LOGGER = logging.getLogger(__name__)

_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0  # 秒，指数退避基准间隔


@dataclass(frozen=True)
class AudioGenerationService:
    output_dir: Path
    api_key: str
    prompt_influence: float
    timeout: float

    def generate(self, text: str, duration_seconds: float) -> GeneratedAudioResult:
        return generate_sound_effect(
            text=text,
            duration_seconds=duration_seconds,
            output_dir=self.output_dir,
            prompt_influence=self.prompt_influence,
            timeout=self.timeout,
            api_key=self.api_key,
        )


class XiaoAiService:
    def __init__(self, config: AppConfig, *, public_base_url: str = "") -> None:
        self.config = config
        self.public_base_url = public_base_url
        self.client = XiaoAiMinaClient(
            user_id=config.xiaoai.user_id,
            pass_token=config.xiaoai.pass_token,
            did=config.xiaoai.did,
            device_id=config.xiaoai.device_id,
            timeout=config.xiaoai.timeout,
            account_cache=config.xiaoai.account_cache,
        )
        self.poller = XiaoAiMessagePoller(self.client)
        self.llm_client = LLMClient(config.llm) if config.llm and config.llm.enabled else None
        self.audio_service = AudioGenerationService(
            output_dir=Path(config.http_api.audio_dir).resolve(),
            api_key=config.elevenlabs.api_key,
            prompt_influence=config.elevenlabs.prompt_influence,
            timeout=config.elevenlabs.timeout,
        )
        self.audio_service.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_recent_messages = config.http_api.max_recent_messages
        self.max_duration_seconds = config.http_api.max_duration_seconds
        self._recent_messages: deque[ConversationMessage] = deque(maxlen=self.max_recent_messages)
        self._pending_llm_messages: deque[ConversationMessage] = deque()
        self._monitor_thread: threading.Thread | None = None
        self._monitor_started = False
        self._lock = threading.Lock()
        self._dispatched_request_ids: deque[str] = deque(maxlen=200)
        self._llm_retry_counts: dict[str, int] = {}
        self.is_ready = False
        self.last_error: str | None = None
        self.last_llm_result: LLMActionResult | None = None
        self.last_llm_error: str | None = None

    def initialize(self) -> dict[str, Any]:
        self.client.login()
        device = self.client.ensure_device()
        self.is_ready = True
        self.last_error = None
        return device

    def get_speaker_summary(self) -> dict[str, Any]:
        account = self.client.account
        device = account.device or {}
        user_id = account.user_id
        masked_user_id = f"****{user_id[-4:]}" if len(user_id) >= 4 else user_id
        return {
            "userId": masked_user_id,
            "did": account.did,
            "name": device.get("name"),
            "deviceId": device.get("deviceId"),
            "totalRecentMessages": len(self._recent_messages),
        }

    def get_llm_summary(self) -> dict[str, Any]:
        result = self.last_llm_result
        return {
            "enabled": self.llm_client is not None,
            "configured": self.config.llm is not None,
            "model": self.config.llm.model if self.config.llm else None,
            "last_action": result.action if result else None,
            "last_reason": result.reason if result else None,
            "last_error": self.last_llm_error,
        }

    def start_message_monitor(self) -> None:
        with self._lock:
            if self._monitor_started:
                return
            self._monitor_started = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="xiaoai-message-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def list_recent_messages(self, *, limit: int) -> list[dict[str, Any]]:
        messages = list(self._recent_messages)[-limit:]
        return [
            {
                "query": message.query,
                "timestamp": message.timestamp,
                "request_id": message.request_id,
                "answers": message.answers,
            }
            for message in reversed(messages)
        ]

    def speak_text(self, text: str, *, interrupt: bool = True, save: int = 0) -> bool:
        if interrupt:
            self.client.stop()
        return self.client.speak_text(text, save=save)

    def play_audio(self, url: str, *, interrupt: bool = True) -> bool:
        if interrupt:
            self.client.stop()
        return self.client.play_url(url)

    def set_volume(self, volume: int) -> bool:
        return self.client.set_volume(volume)

    def execute_command(self, *, siid: int, aiid: int, params: list[dict[str, Any]]) -> Any:
        return self.client.do_action(siid=siid, aiid=aiid, params=params)

    def stop(self) -> bool:
        return self.client.stop()

    def generate_audio(self, text: str, duration_seconds: float) -> GeneratedAudioResult:
        return self.audio_service.generate(text, duration_seconds)

    def _monitor_loop(self) -> None:
        interval = self.config.http_api.poll_interval
        while True:
            try:
                self._flush_pending_llm_messages()
                message = self.poller.fetch_next_message()
                if message is not None:
                    self._recent_messages.append(message)
                    self._dispatch_to_llm(message)
                    self.last_error = None
                    LOGGER.info("收到消息 request_id=%s query=%s", message.request_id, message.query)
            except Exception as exc:
                self.last_error = str(exc)
                LOGGER.exception("消息轮询失败")
            time.sleep(interval)

    def _flush_pending_llm_messages(self) -> None:
        while self._pending_llm_messages:
            message = self._pending_llm_messages[0]
            request_id = message.request_id or f"timestamp:{message.timestamp}"
            try:
                self._dispatch_to_llm(message)
            except Exception as exc:
                retry_count = self._llm_retry_counts.get(request_id, 0) + 1
                self._llm_retry_counts[request_id] = retry_count
                if retry_count >= _LLM_MAX_RETRIES:
                    self._pending_llm_messages.popleft()
                    self._llm_retry_counts.pop(request_id, None)
                    LOGGER.warning(
                        "LLM 转发重试 %d 次后放弃 request_id=%s: %s",
                        _LLM_MAX_RETRIES, request_id, exc,
                    )
                else:
                    delay = min(_LLM_RETRY_BASE_DELAY * (2 ** (retry_count - 1)), 60.0)
                    LOGGER.info(
                        "LLM 转发第 %d/%d 次失败，%.1fs 后重试 request_id=%s",
                        retry_count, _LLM_MAX_RETRIES, delay, request_id,
                    )
                    time.sleep(delay)
                return
            self._pending_llm_messages.popleft()
            self._llm_retry_counts.pop(request_id, None)

    def _dispatch_to_llm(self, message: ConversationMessage) -> None:
        """将消息发送给 LLM，根据返回的动作执行对应操作。"""
        if self.llm_client is None:
            return
        request_id = message.request_id or f"timestamp:{message.timestamp}"
        if request_id in self._dispatched_request_ids:
            return
        try:
            result = self.llm_client.process_message(message.query)
        except Exception as exc:
            self.last_llm_error = str(exc)
            if not any(
                (queued.request_id or f"timestamp:{queued.timestamp}") == request_id
                for queued in self._pending_llm_messages
            ):
                self._pending_llm_messages.append(message)
            raise
        self.last_llm_result = result
        self.last_llm_error = None
        self._dispatched_request_ids.append(request_id)
        LOGGER.info(
            "LLM 动作: action=%s request_id=%s reason=%s",
            result.action, request_id, result.reason,
        )
        self._execute_llm_action(result)

    def _execute_llm_action(self, result: LLMActionResult) -> None:
        """根据 LLM 返回的动作执行对应的音箱控制。"""
        if result.action == "pass_through":
            LOGGER.info("pass_through: %s", result.reason)
            return

        if result.action == "speak_text":
            if result.text:
                self.speak_text(result.text, interrupt=result.interrupt)
            else:
                LOGGER.warning("speak_text 动作但 text 为空，跳过")
            return

        if result.action == "generate_sound_effect":
            prompt = result.text
            # 从 reason 中解析 duration（格式 "duration=5.0s"）
            duration = 5.0
            if result.reason.startswith("duration="):
                try:
                    duration = float(result.reason.removeprefix("duration=").removesuffix("s"))
                except ValueError:
                    pass
            duration = min(duration, self.max_duration_seconds)
            try:
                audio_result = self.audio_service.generate(prompt, duration)
            except Exception:
                LOGGER.exception("音效生成失败: prompt=%s", prompt)
                return
            audio_url = f"{self.public_base_url}/audio/{audio_result.filename}"
            LOGGER.info("音效已生成: %s → %s", prompt, audio_url)
            self.play_audio(audio_url, interrupt=result.interrupt)
            return

        LOGGER.warning("未知 LLM 动作: %s", result.action)
