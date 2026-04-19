from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from .config import LLMConfig
from .models import LLMActionResult

LOGGER = logging.getLogger(__name__)

# ---------- 默认 System Prompt ----------

BASE_SYSTEM_PROMPT = """\
你是小爱音箱的 AI 大脑，负责理解用户意图并选择合适的动作。
用户主要是 3 岁左右的宝宝和他的家人。

## 动作选择规则

### pass_through — 交给小爱原生处理
适用场景：
- 播放歌曲/音乐（"播放小星星"、"来首儿歌"）
- 设置闹钟/定时器（"三分钟后叫我"、"设个早上七点的闹钟"）
- 天气查询（"今天天气怎么样"）
- 其他小爱擅长的内置技能（控制智能家居、查时间、调整音量、停止播放等）

调用时在 reason 中简要说明为什么交给小爱处理。

### speak_text — 用 TTS 朗读 LLM 生成的回答
适用场景：
- 讲故事（"给我讲个小猪佩奇的故事"）
- 回答知识问题（"恐龙为什么灭绝了"）
- 聊天对话（"你好呀"、"你是谁"）
- 任何需要 LLM 生成内容才能回答的问题

注意：面向宝宝的回答要用简单、温暖、有趣的语言，避免复杂词汇。

### generate_sound_effect — 生成音效并播放
适用场景：
- 动物叫声（"狮子怎么叫"、"小猫的声音"）
- 环境音效（"下雨的声音"、"海浪声"）
- 有趣的声音（"放个屁的声音"、"打雷的声音"）

调用时 prompt 必须是高质量的英文 ElevenLabs 提示词，描述要生成的声音效果。
例如：用户说"狮子怎么叫"，prompt 应为 "A powerful male lion roaring loudly in the African savanna"。
duration_seconds 一般 3-5 秒即可，特殊场景（如讲故事背景音）可更长。
"""

DEFAULT_STORY_RULES: dict[str, Any] = {
    "default_protagonist": "糕糕",
    "friends": ["小黄", "小红", "小蓝"],
    "cartoon_characters": [
        "赛罗奥特曼",
        "迪迦奥特曼",
        "贝利亚奥特曼（反派）",
        "汪汪队阿奇",
        "莱德队长",
        "毛毛",
        "超级飞侠乐迪",
    ],
    "locations": ["一环路", "楼下公园"],
    "education_points": [
        "简单英语单词（如 apple、hello、red、one two three），用“糕糕学会了一个新单词”等方式带出",
        "基础数学概念（数数、比大小、简单形状）",
        "生活常识（过马路看红绿灯、饭前洗手、分享玩具等）",
    ],
    "min_length": 300,
    "structure_requirements": [
        "情节要有起承转合",
        "设置小悬念或转折，避免平铺直叙",
        "结尾要温暖正面，可以有一个小道理但不说教",
    ],
}


def _format_list(items: Sequence[Any]) -> str:
    return "、".join(str(item) for item in items if str(item).strip())


def _normalize_story_rules(story_rules: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_STORY_RULES)
    if not story_rules:
        return merged

    for key, value in story_rules.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 0:
            continue
        merged[key] = value
    return merged


def _build_story_rules_prompt(story_rules: dict[str, Any]) -> str:
    protagonist = str(story_rules["default_protagonist"])
    friends = _format_list(story_rules.get("friends", []))
    cartoon_characters = _format_list(story_rules.get("cartoon_characters", []))
    locations = _format_list(story_rules.get("locations", []))
    education_points = story_rules.get("education_points", [])
    structure_requirements = story_rules.get("structure_requirements", [])
    min_length = story_rules.get("min_length", 300)

    lines = [
        "#### 讲故事专项规则",
        "当用户请求讲故事时，遵循以下设定：",
        "",
        "**角色**：",
        f'- 男主角默认为"{protagonist}"（除非用户指定了其他主角）',
    ]

    if friends:
        lines.append(f"- 常驻朋友：{friends}")
    if cartoon_characters:
        lines.append(f"- 常驻动画角色：{cartoon_characters}")
        lines.append("- 根据剧情需要选择 1-3 位朋友和动画角色中的 1-3 位出场，不必每次全部出现")
    elif friends:
        lines.append("- 根据剧情需要选择 1-3 位朋友出场，不必每次全部出现")

    lines.extend([
        "",
        "**地点**：",
    ])
    if locations:
        lines.append(f"- 优先从以下地点中选取：{locations}")
        lines.append("- 可根据情节合理选择，不要硬凑")

    lines.extend([
        "",
        "**教育元素**：",
        "- 自然地融入适合 3 岁宝宝的教育内容，包括但不限于：",
    ])
    for point in education_points:
        lines.append(f"  - {point}")
    lines.append("- 每个故事包含 1-2 个教育点即可，不要堆砌")

    lines.extend([
        "",
        "**篇幅与结构**：",
        f"- 故事不少于 {min_length} 字",
    ])
    for requirement in structure_requirements:
        lines.append(f"- {requirement}")

    return "\n".join(lines)


def _build_system_prompt(config: LLMConfig) -> str:
    if config.system_prompt:
        return config.system_prompt
    story_rules = _normalize_story_rules(config.story_rules)
    return f"{BASE_SYSTEM_PROMPT}\n\n{_build_story_rules_prompt(story_rules)}"

# ---------- Tool Schemas ----------

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "pass_through",
            "description": "交给小爱音箱原生处理（播放歌曲、设闹钟、查天气等小爱擅长的功能）",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "简要说明为什么交给小爱原生处理",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "speak_text",
            "description": "通过 TTS 朗读 LLM 生成的文本回答（讲故事、回答问题、聊天等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要朗读的文本内容",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sound_effect",
            "description": "生成音效并播放（动物叫声、环境音效等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "高质量英文 ElevenLabs 提示词，描述要生成的声音效果",
                    },
                    "duration_seconds": {
                        "type": "number",
                        "description": "音效时长（秒），不低于 6 秒",
                        "default": 6.0,
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]


class LLMClient:
    """使用 OpenAI 兼容 API 的 Function Calling 完成意图识别和响应生成。"""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        self.system_prompt = _build_system_prompt(config)

    def process_message(self, query: str) -> LLMActionResult:
        """将用户消息发送给 LLM，解析 tool_calls 返回结构化动作结果。"""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]

        LOGGER.info("发送 LLM 请求: model=%s query=%s", self.config.model, query)

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="required",
            temperature=self.config.temperature,
        )

        choice = response.choices[0]
        tool_calls = choice.message.tool_calls

        # 如果没有 tool_calls（不应发生，因为 tool_choice="required"），回退为 speak_text
        if not tool_calls:
            content = choice.message.content or ""
            LOGGER.warning("LLM 未返回 tool_calls，回退为 speak_text: %s", content)
            return LLMActionResult(action="speak_text", text=content)

        tool_call = tool_calls[0]
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        LOGGER.info("LLM 返回 tool_call: %s(%s)", function_name, arguments)

        return self._build_result(function_name, arguments)

    def _build_result(self, function_name: str, arguments: dict[str, Any]) -> LLMActionResult:
        """根据 function_name 和参数构建 LLMActionResult。"""
        if function_name == "pass_through":
            return LLMActionResult(
                action="pass_through",
                reason=arguments.get("reason", ""),
            )

        if function_name == "speak_text":
            return LLMActionResult(
                action="speak_text",
                text=arguments.get("text", ""),
            )

        if function_name == "generate_sound_effect":
            return LLMActionResult(
                action="generate_sound_effect",
                text=arguments.get("prompt", ""),
                reason=f"duration={arguments.get('duration_seconds', 5.0)}s",
            )

        # 未知 function，回退为 pass_through
        LOGGER.warning("未知的 tool function: %s，回退为 pass_through", function_name)
        return LLMActionResult(
            action="pass_through",
            reason=f"unknown function: {function_name}",
        )
