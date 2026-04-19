from __future__ import annotations

from collections import deque
from typing import Optional

from .client import XiaoAiMinaClient
from .models import ConversationMessage

_MAX_SEEN = 200


class XiaoAiMessagePoller:
    def __init__(self, client: XiaoAiMinaClient) -> None:
        self.client = client
        self._last_message: Optional[ConversationMessage] = None
        self._buffer: list[ConversationMessage] = []
        self._initialized = False
        # 基于 request_id 的消息级去重
        self._seen_keys: set[str] = set()
        self._seen_order: deque[str] = deque(maxlen=_MAX_SEEN)

    @staticmethod
    def _message_key(message: ConversationMessage) -> str:
        """生成消息唯一键，优先使用 request_id，否则退化为 timestamp:query。"""
        if message.request_id:
            return message.request_id
        return f"{message.timestamp}:{message.query}"

    def _is_seen(self, message: ConversationMessage) -> bool:
        return self._message_key(message) in self._seen_keys

    def _mark_seen(self, message: ConversationMessage) -> None:
        key = self._message_key(message)
        if key in self._seen_keys:
            return
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen_keys.discard(self._seen_order[0])
        self._seen_order.append(key)
        self._seen_keys.add(key)

    def fetch_next_message(self) -> Optional[ConversationMessage]:
        if not self._initialized:
            self._initialize_cursor()
            return None
        if self._last_message is None:
            messages = self.client.get_conversations(limit=1)
            if not messages:
                return None
            self._last_message = messages[0]
            self._mark_seen(messages[0])
            return messages[0]
        message = self._fetch_next_message()
        if message is None:
            return None
        if self._is_seen(message):
            return None
        self._mark_seen(message)
        return message

    def _initialize_cursor(self) -> None:
        messages = self.client.get_conversations(limit=1, filter_answer=False)
        if messages:
            self._last_message = messages[0]
            self._mark_seen(messages[0])
        self._initialized = True

    def _fetch_next_message(self) -> Optional[ConversationMessage]:
        if self._buffer:
            return self._pop_buffer()
        candidate = self._fetch_latest_two()
        if candidate != "continue":
            return candidate
        return self._fetch_remaining_messages()

    def _fetch_latest_two(self) -> Optional[ConversationMessage] | str:
        assert self._last_message is not None
        messages = self.client.get_conversations(limit=2)
        if not messages or messages[0].timestamp <= self._last_message.timestamp:
            return None
        if len(messages) == 1 or messages[-1].timestamp <= self._last_message.timestamp:
            self._last_message = messages[0]
            return self._last_message
        for message in messages:
            if message.timestamp > self._last_message.timestamp:
                self._buffer.append(message)
        return "continue"

    def _fetch_remaining_messages(
        self,
        *,
        max_page: int = 3,
        page_size: int = 10,
    ) -> Optional[ConversationMessage]:
        assert self._last_message is not None
        current_page = 0
        while True:
            current_page += 1
            if current_page > max_page:
                return self._pop_buffer()
            next_timestamp = self._buffer[-1].timestamp
            messages = self.client.get_conversations(limit=page_size, timestamp=next_timestamp)
            if not messages:
                return self._pop_buffer()
            for message in messages:
                if message.timestamp >= next_timestamp:
                    continue
                if message.timestamp > self._last_message.timestamp:
                    self._buffer.append(message)
                else:
                    return self._pop_buffer()

    def _pop_buffer(self) -> Optional[ConversationMessage]:
        if not self._buffer:
            return None
        message = self._buffer.pop()
        self._last_message = message
        return message
