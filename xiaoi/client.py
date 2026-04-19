from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import requests

from .config import AppConfig
from .constants import (
    CONVERSATION_API,
    DEFAULT_CONVERSATION_UA,
    DEFAULT_LOGIN_UA,
    DEFAULT_MINA_UA,
    LOGIN_API,
    MINA_API,
)
from .errors import DeviceNotFoundError, XiaomiLoginError
from .models import ConversationMessage, MiPass, XiaoAiAccount
from .storage import AccountStorage
from .utils import parse_login_payload, random_device_id, request_id, sha1_base64


class XiaoAiMinaClient:
    def __init__(
        self,
        user_id: str,
        pass_token: str,
        did: Optional[str] = None,
        device_id: Optional[str] = None,
        timeout: float = 5.0,
        account_cache: Optional[str | Path] = None,
    ) -> None:
        if not user_id or not pass_token:
            raise ValueError("Provide user_id and pass_token.")
        self.session = requests.Session()
        self.timeout = timeout
        self.storage = AccountStorage(account_cache)
        self.account = XiaoAiAccount(
            user_id=user_id,
            pass_token=pass_token,
            did=did,
            device_id=device_id or random_device_id(),
        )
        self.session.headers.update(
            {
                "Accept-Encoding": "gzip, deflate",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": DEFAULT_LOGIN_UA,
            }
        )
        self._load_cache()

    def _load_cache(self) -> None:
        cached = self.storage.load(self.account.user_id)
        if not cached:
            return
        if self.account.pass_token:
            cached.pass_token = self.account.pass_token
        if self.account.did:
            cached.did = self.account.did
        self.account = cached

    def _save_cache(self) -> None:
        self.storage.save(self.account)

    def login(self, force: bool = False) -> None:
        if self.account.service_token and self.account.pass_data.ssecurity and not force:
            return

        response = self.session.get(
            f"{LOGIN_API}/serviceLogin",
            params={"sid": "micoapi", "_json": "true", "_locale": "zh_CN"},
            cookies=self.account.login_cookies,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = parse_login_payload(response.text)

        if payload.get("code") != 0:
            raise XiaomiLoginError(
                "Login expired or pass_token invalid. Refresh pass_token in config and retry."
            )

        if "identity/authStart" in str(payload.get("notificationUrl", "")):
            raise XiaomiLoginError(
                "This account requires interactive verification. Use a valid pass_token instead."
            )
        if not payload.get("location") or not payload.get("nonce") or not payload.get("ssecurity"):
            raise XiaomiLoginError(f"Unexpected Xiaomi login response: {payload}")

        self.account.pass_data = MiPass(**{k: payload.get(k) for k in MiPass.__annotations__})
        self.account.pass_token = self.account.pass_data.passToken or self.account.pass_token
        self.account.service_token = self._get_service_token(
            location=self.account.pass_data.location,
            nonce=self.account.pass_data.nonce,
            ssecurity=self.account.pass_data.ssecurity,
        )
        self._save_cache()

    def _get_service_token(self, location: str, nonce: str, ssecurity: str) -> str:
        response = self.session.get(
            location,
            params={"_userIdNeedEncrypt": "true", "clientSign": sha1_base64(f"nonce={nonce}&{ssecurity}")},
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        token = self.session.cookies.get("serviceToken") or response.cookies.get("serviceToken")
        if not token:
            raise XiaomiLoginError("Xiaomi login succeeded but serviceToken was not returned.")
        return token

    def ensure_device(self) -> dict[str, Any]:
        if self.account.device:
            return self.account.device
        devices = self.get_devices()
        target = self.account.did
        if not target:
            raise DeviceNotFoundError("did is required to identify the target speaker.")
        for device in devices:
            if target in {
                device.get("deviceID"),
                device.get("miotDID"),
                device.get("name"),
                device.get("alias"),
                device.get("mac"),
            }:
                self.account.device = {**device, "deviceId": device.get("deviceID")}
                self._save_cache()
                return self.account.device
        raise DeviceNotFoundError(
            f"Speaker not found for did={target!r}. Try name, miotDID, deviceID, or mac."
        )

    def _mina_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, Any]] = None,
    ) -> Any:
        self.login()
        request_headers = {"User-Agent": DEFAULT_MINA_UA}
        if headers:
            request_headers.update(headers)
        request_cookies = {"userId": self.account.user_id, "serviceToken": self.account.service_token}
        if cookies:
            request_cookies.update(cookies)
        response = self.session.request(
            method=method,
            url=f"{MINA_API}{path}",
            params=params,
            data=data,
            headers=request_headers,
            cookies=request_cookies,
            timeout=self.timeout,
        )
        if response.status_code == 401:
            self.login(force=True)
            request_cookies["serviceToken"] = self.account.service_token
            response = self.session.request(
                method=method,
                url=f"{MINA_API}{path}",
                params=params,
                data=data,
                headers=request_headers,
                cookies=request_cookies,
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"MiNA request failed: {payload}")
        return payload.get("data")

    def call_ubus(self, scope: str, command: str, message: Optional[dict[str, Any]] = None) -> Any:
        device = self.ensure_device()
        return self._mina_request(
            "POST",
            "/remote/ubus",
            data={
                "deviceId": device.get("deviceId"),
                "message": json.dumps(message or {}, ensure_ascii=False, separators=(",", ":")),
                "method": command,
                "path": scope,
                "requestId": request_id(),
                "timestamp": int(time.time()),
            },
        )

    def speak_text(self, text: str, *, save: int = 0) -> bool:
        payload = self.call_ubus("mibrain", "text_to_speech", {"text": text, "save": save})
        return bool(payload and payload.get("code") == 0)

    def play_url(self, url: str) -> bool:
        payload = self.call_ubus("mediaplayer", "player_play_url", {"url": url, "type": 1})
        return bool(payload and payload.get("code") == 0)

    def set_volume(self, volume: int) -> bool:
        payload = self.call_ubus("mediaplayer", "player_set_volume", {"volume": volume})
        return bool(payload and payload.get("code") == 0)

    def do_action(self, *, siid: int, aiid: int, params: list[dict[str, Any]] | None = None) -> Any:
        return self.call_ubus(
            "miot",
            "action",
            {
                "siid": siid,
                "aiid": aiid,
                "in": params or [],
            },
        )

    def stop(self) -> bool:
        payload = self.call_ubus("mediaplayer", "player_play_operation", {"action": "stop"})
        return bool(payload and payload.get("code") == 0)

    def get_devices(self) -> list[dict[str, Any]]:
        data = self._mina_request(
            "GET",
            "/admin/v2/device_list",
            params={"requestId": request_id(), "timestamp": int(time.time())},
        )
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected device list payload: {data!r}")
        return data

    def get_conversations(
        self,
        *,
        limit: int = 10,
        timestamp: Optional[int] = None,
        filter_answer: bool = True,
    ) -> list[ConversationMessage]:
        self.login()
        device = self.ensure_device()
        params = {
            "limit": limit,
            "requestId": request_id(),
            "source": "dialogu",
            "hardware": device.get("hardware"),
        }
        if timestamp is not None:
            params["timestamp"] = timestamp
        headers = {
            "User-Agent": DEFAULT_CONVERSATION_UA,
            "Referer": "https://userprofile.mina.mi.com/dialogue-note/index.html",
        }
        cookies = {
            "userId": self.account.user_id,
            "serviceToken": self.account.service_token,
            "deviceId": device.get("deviceId"),
        }
        response = self.session.get(
            CONVERSATION_API,
            params=params,
            headers=headers,
            cookies=cookies,
            timeout=self.timeout,
        )
        if response.status_code == 401:
            self.login(force=True)
            cookies["serviceToken"] = self.account.service_token
            response = self.session.get(
                CONVERSATION_API,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Conversation request failed: {payload}")
        data = payload.get("data")
        if isinstance(data, str):
            data = json.loads(data)
        records = data.get("records") or []
        messages = [ConversationMessage.from_record(record) for record in records]
        if not filter_answer:
            return messages
        # 只过滤掉空 query 的记录，保留所有有用户输入的会话
        return [message for message in messages if message.query.strip()]


def create_client_from_config(config_path: str | Path = "config.json") -> XiaoAiMinaClient:
    config = AppConfig.load(config_path)
    return XiaoAiMinaClient(
        user_id=config.xiaoai.user_id,
        pass_token=config.xiaoai.pass_token,
        did=config.xiaoai.did,
        device_id=config.xiaoai.device_id,
        timeout=config.xiaoai.timeout,
        account_cache=config.xiaoai.account_cache,
    )
