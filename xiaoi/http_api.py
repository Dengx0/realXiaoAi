from __future__ import annotations

import json
import logging
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from aiaudio.aiaudio import ElevenLabsAudioError

from .config import AppConfig
from .service import XiaoAiService

LOGGER = logging.getLogger(__name__)


class UnifiedApiHandler(SimpleHTTPRequestHandler):
    server: "UnifiedHTTPServer"
    server_version = "XiaoAIHTTP/2.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        request_path = urlsplit(self.path).path
        try:
            if request_path == "/":
                self._send_json(HTTPStatus.OK, self.server.build_status_payload())
                return
            if request_path == "/api/xiaoai/messages":
                limit = self._parse_limit()
                messages = self.server.service.list_recent_messages(limit=limit)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "messages": messages,
                        "count": len(messages),
                    },
                )
                return
            if request_path.startswith("/audio/"):
                super().do_GET()
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在。"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:
        request_path = urlsplit(self.path).path.rstrip("/")
        if not self._check_auth():
            return

        try:
            payload = self._read_json_body()
            if request_path == "/api/xiaoai/tts":
                self._handle_tts(payload)
            elif request_path == "/api/xiaoai/audio":
                self._handle_audio(payload)
            elif request_path == "/api/xiaoai/volume":
                self._handle_volume(payload)
            elif request_path == "/api/xiaoai/command":
                self._handle_command(payload)
            elif request_path == "/api/xiaoai/stop":
                self._handle_stop()
            elif request_path == "/api/xiaoai/control":
                self._handle_unified_control(payload)
            elif request_path == "/api/audio/generate":
                self._handle_generate(payload)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在。"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except ElevenLabsAudioError as exc:
            LOGGER.exception("音频生成失败")
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception:
            LOGGER.exception("接口处理失败")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "服务内部错误。"})

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
        prefix = "/audio/"
        if not request_path.startswith(prefix):
            return str(self.server.audio_dir)
        filename = Path(request_path[len(prefix) :]).name
        return str((self.server.audio_dir / filename).resolve())

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("HTTP %s - %s", self.address_string(), format % args)

    def end_headers(self) -> None:
        self._send_cors_headers()
        super().end_headers()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-XiaoAI-Token")

    def _check_auth(self) -> bool:
        token = self.server.control_token
        if not token:
            return True
        auth_header = self.headers.get("Authorization", "")
        custom_header = self.headers.get("X-XiaoAI-Token", "")
        bearer_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
        if custom_header == token or bearer_token == token:
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "鉴权失败。"})
        return False

    def _read_json_body(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if not content_length:
            return {}
        try:
            size = int(content_length)
        except ValueError as exc:
            raise ValueError("无效的 Content-Length。") from exc
        raw_body = self.rfile.read(size)
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求体必须是合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象。")
        return payload

    def _parse_limit(self) -> int:
        query = parse_qs(urlsplit(self.path).query)
        raw_limit = (query.get("limit") or ["20"])[0]
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValueError("limit 必须是整数。") from exc
        if limit <= 0:
            raise ValueError("limit 必须大于 0。")
        return min(limit, self.server.service.max_recent_messages)

    def _handle_tts(self, payload: dict[str, Any]) -> None:
        text = self._require_text(payload, "text")
        interrupt = self._as_bool(payload.get("interrupt", True), "interrupt")
        save = self._as_int(payload.get("save", 0), "save", minimum=0)
        result = self.server.service.speak_text(text, interrupt=interrupt, save=save)
        self._send_json(HTTPStatus.OK, {"ok": result})

    def _handle_audio(self, payload: dict[str, Any]) -> None:
        url = self._require_text(payload, "url")
        interrupt = self._as_bool(payload.get("interrupt", True), "interrupt")
        result = self.server.service.play_audio(url, interrupt=interrupt)
        self._send_json(HTTPStatus.OK, {"ok": result})

    def _handle_volume(self, payload: dict[str, Any]) -> None:
        volume = self._as_int(payload.get("volume"), "volume", minimum=0, maximum=100)
        result = self.server.service.set_volume(volume)
        self._send_json(HTTPStatus.OK, {"ok": result, "volume": volume})

    def _handle_command(self, payload: dict[str, Any]) -> None:
        siid = self._as_int(payload.get("siid"), "siid", minimum=1)
        aiid = self._as_int(payload.get("aiid"), "aiid", minimum=1)
        params = payload.get("params", [])
        if not isinstance(params, list):
            raise ValueError("params 必须是数组。")
        result = self.server.service.execute_command(siid=siid, aiid=aiid, params=params)
        self._send_json(HTTPStatus.OK, {"ok": True, "result": result})

    def _handle_stop(self) -> None:
        result = self.server.service.stop()
        self._send_json(HTTPStatus.OK, {"ok": result})

    def _handle_unified_control(self, payload: dict[str, Any]) -> None:
        action = self._require_text(payload, "action").lower()
        if action in {"tts", "speak_text"}:
            self._handle_tts(payload)
            return
        if action in {"audio", "play_url"}:
            self._handle_audio(payload)
            return
        if action == "volume":
            self._handle_volume(payload)
            return
        if action == "command":
            self._handle_command(payload)
            return
        if action == "stop":
            self._handle_stop()
            return
        if action == "audio_generate":
            self._handle_generate(payload)
            return
        raise ValueError(f"不支持的 action: {action}")

    def _handle_generate(self, payload: dict[str, Any]) -> None:
        text = payload.get("text", payload.get("prompt"))
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text 必须为非空字符串。")
        duration_seconds = self._as_float(
            payload.get("duration_seconds", 5.0),
            "duration_seconds",
            minimum=0.1,
            maximum=self.server.service.max_duration_seconds,
        )
        result = self.server.service.generate_audio(text.strip(), duration_seconds)
        audio_url = self.server.build_audio_url(result.filename)
        self._send_json(
            HTTPStatus.OK,
            {
                "audio_url": audio_url,
                "filename": result.filename,
                "duration_seconds": duration_seconds,
            },
        )

    def _require_text(self, payload: dict[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} 必须为非空字符串。")
        return value.strip()

    def _as_bool(self, value: Any, field_name: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} 必须是布尔值。")
        return value

    def _as_int(
        self,
        value: Any,
        field_name: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field_name} 必须是整数。")
        if minimum is not None and value < minimum:
            raise ValueError(f"{field_name} 不能小于 {minimum}。")
        if maximum is not None and value > maximum:
            raise ValueError(f"{field_name} 不能大于 {maximum}。")
        return value

    def _as_float(
        self,
        value: Any,
        field_name: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} 必须是数字。")
        number = float(value)
        if minimum is not None and number < minimum:
            raise ValueError(f"{field_name} 不能小于 {minimum:g}。")
        if maximum is not None and number > maximum:
            raise ValueError(f"{field_name} 不能大于 {maximum:g}。")
        return number

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class UnifiedHTTPServer(ThreadingHTTPServer):
    def __init__(self, config: AppConfig) -> None:
        self.audio_dir = Path(config.http_api.audio_dir).resolve()
        self.public_base_url = _resolve_public_base_url(config)
        self.control_token = config.http_api.control_token
        self.service = XiaoAiService(config, public_base_url=self.public_base_url)
        super().__init__((config.http_api.host, config.http_api.port), UnifiedApiHandler)

    def build_audio_url(self, filename: str) -> str:
        return f"{self.public_base_url}/audio/{filename}"

    def build_status_payload(self) -> dict[str, Any]:
        speaker = self.service.get_speaker_summary()
        return {
            "status": "running",
            "engine_ready": self.service.is_ready,
            "last_error": self.service.last_error,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "config": {
                "speaker": speaker,
                "llm": self.service.get_llm_summary(),
                "http_api": {
                    "host": self.server_address[0],
                    "port": self.server_address[1],
                    "token_set": bool(self.control_token),
                },
            },
            "endpoints": {
                "GET /": "服务状态",
                "GET /api/xiaoai/messages": "最近消息列表",
                "POST /api/xiaoai/tts": "body: { text, interrupt?, save? }",
                "POST /api/xiaoai/audio": "body: { url, interrupt? }",
                "POST /api/xiaoai/volume": "body: { volume }",
                "POST /api/xiaoai/command": "body: { siid, aiid, params }",
                "POST /api/xiaoai/stop": "body: {}",
                "POST /api/xiaoai/control": "body: { action, ... }",
                "POST /api/audio/generate": "body: { text, duration_seconds? }",
                "GET /audio/<filename>": "访问生成的音频文件",
            },
        }


def create_http_server(config: AppConfig) -> UnifiedHTTPServer:
    return UnifiedHTTPServer(config)


def run_http_server(config: AppConfig) -> None:
    server = create_http_server(config)
    server.service.initialize()
    server.service.start_message_monitor()
    LOGGER.info(
        "HTTP API listening on %s:%s",
        config.http_api.host,
        config.http_api.port,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_audio_http_server(config: AppConfig) -> UnifiedHTTPServer:
    return create_http_server(config)


def create_control_http_server(config: AppConfig) -> UnifiedHTTPServer:
    return create_http_server(config)


def run_audio_http_server(config: AppConfig) -> None:
    run_http_server(config)


def run_control_http_server(config: AppConfig) -> None:
    run_http_server(config)


def _resolve_public_base_url(config: AppConfig) -> str:
    if config.http_api.public_base_url:
        return config.http_api.public_base_url.rstrip("/")
    return f"http://{config.http_api.host}:{config.http_api.port}"
