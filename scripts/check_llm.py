import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xiaoi import AppConfig, LLMClient


def _has_output(action: str, text: str, reason: str) -> bool:
    if action in {"speak_text", "generate_sound_effect"}:
        return bool(text.strip())
    if action == "pass_through":
        return bool(reason.strip())
    return bool(text.strip() or reason.strip())


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    query = sys.argv[2] if len(sys.argv) > 2 else "hello"

    config = AppConfig.load(config_path)
    if not config.llm:
        raise RuntimeError("配置文件缺少 llm section")
    if not config.llm.enabled:
        raise RuntimeError("当前 llm.enabled=false，LLM 功能未启用")

    client = LLMClient(config.llm)
    result = client.process_message(query)
    has_output = _has_output(result.action, result.text, result.reason)

    payload = {
        "query": query,
        "model": config.llm.model,
        "action": result.action,
        "text": result.text,
        "reason": result.reason,
        "has_output": has_output,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not has_output:
        raise RuntimeError("LLM 返回结果缺少有效输出")


if __name__ == "__main__":
    main()
