from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any


def md5_upper(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def sha1_base64(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def random_device_id() -> str:
    return f"android_{uuid.uuid4().hex}"


def request_id() -> str:
    return str(uuid.uuid4())


def parse_login_payload(text: str) -> dict[str, Any]:
    raw = text.replace("&&&START&&&", "", 1)
    if not raw.strip():
        return {}
    return json.loads(raw)
