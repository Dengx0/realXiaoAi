# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Norms

- 优先做增量修改，避免无关重构。
- 修改 HTTP API 时，保持现有控制协议稳定。
- 统一入口固定为 `main.py`，不要再引入子命令模式。
- 小爱输入侧保留消息轮询，并会自动进入内部 LLM 决策链。
- 没有 `pyproject.toml` 或 lockfile，用轻量本地环境即可。
- 没有自动化测试套件，验证改动需手动发 HTTP 请求到真实设备。

## Common Commands

```powershell
# 安装依赖
uv pip install requests openai

# 初始化配置
copy config.example.json config.json

# 启动统一服务
python main.py --config config.json

# 诊断脚本（均可选传 config.json 路径作为第一参数）
python scripts/check_login.py       # 验证登录并打印设备名
python scripts/list_devices.py      # 列出账号下所有设备
python scripts/poll_messages.py     # 持续轮询并打印小爱消息
python scripts/check_llm.py         # 验证 LLM Function Calling 是否可用
```

## Big Picture

小爱音箱内部 LLM 决策与控制服务。核心数据流：

1. `main.py` 加载 `AppConfig` 并调用 `run_http_server()`。
2. `XiaoAiService.initialize()` 通过 `XiaoAiMinaClient` 完成 Xiaomi 登录和设备绑定。
3. `XiaoAiService.start_message_monitor()` 启动后台线程，通过 `XiaoAiMessagePoller` 持续拉取小爱消息。
4. 新消息会进入 `LLMClient` 的 Function Calling 决策链（失败时进入待重试队列）。
5. `XiaoAiService` 根据 LLM 动作执行 TTS、播放或音效生成。
6. `UnifiedApiHandler` 接收请求，通过 `XiaoAiMinaClient` 控制音箱（TTS、播放、音量、MiOT 动作）。
7. 音频生成（ElevenLabs）结果落盘到 `generated_audio/`，通过 `/audio/<filename>` 提供访问。

## Module Map

- `main.py` — 入口，加载配置并启动 HTTP 服务
- `xiaoi/config.py` — `AppConfig` 及子配置 dataclass（`XiaoAiConfig`, `LLMConfig`, `HttpApiConfig`, `ElevenLabsConfig`），从 JSON 文件加载
- `xiaoi/service.py` — `XiaoAiService`，组装客户端、消息轮询线程、LLM 调度和音频生成
- `xiaoi/http_api.py` — `UnifiedApiHandler` / `UnifiedHTTPServer`，基于 stdlib `http.server`，提供所有 HTTP 路由、鉴权和 CORS
- `xiaoi/client.py` — `XiaoAiMinaClient`，封装 Xiaomi 登录、MiNA API 调用、设备发现和 ubus 控制
- `xiaoi/llm_client.py` — `LLMClient`，基于 OpenAI 兼容 Chat Completions + Function Calling 完成动作决策
- `xiaoi/messages.py` — `XiaoAiMessagePoller`，基于时间戳游标的消息轮询逻辑（首次初始化只记游标不返回消息）
- `xiaoi/models.py` — 数据模型：`XiaoAiAccount`, `MiPass`, `ConversationMessage`, `LLMActionResult`
- `xiaoi/storage.py` — `AccountStorage`，将登录态缓存到 `.mi_account.json`
- `xiaoi/constants.py` — API URL 和 User-Agent 常量
- `xiaoi/utils.py` — hash、UUID、登录响应解析等工具函数
- `xiaoi/errors.py` — `XiaomiLoginError`, `DeviceNotFoundError`
- `aiaudio/aiaudio.py` — ElevenLabs 音频生成，调用 `/v1/sound-generation`
- `scripts/` — 独立诊断脚本（登录检查、设备列表、消息轮询、LLM 检查）
- `fixtures/` — 示例 JSON 响应，用于协议参考

## Change Boundaries

- **设备控制 / Xiaomi 协议 / 登录流程** → `xiaoi/client.py`
- **HTTP 路由 / 鉴权 / 返回结构** → `xiaoi/http_api.py`
- **服务装配 / 后台线程 / 消息缓存 / LLM 调度** → `xiaoi/service.py`
- **消息轮询游标逻辑** → `xiaoi/messages.py`
- **LLM Prompt / Function Calling / 动作解析** → `xiaoi/llm_client.py`
- **音频生成逻辑** → `aiaudio/aiaudio.py`
- **配置字段与加载** → `xiaoi/config.py`
- 文档协议示例变化后，同步更新 `README.md` 与 `ARCHITECTURE.md`。

## Config Structure

`config.json` 包含四个顶层 section：`xiaoai`（必填）、`llm`（可选）、`http_api`、`elevenlabs`。参见 `config.example.json` 和 `xiaoi/config.py` 中的 dataclass 定义。`llm` section 缺失或 `llm.enabled=false` 时，自动决策链关闭，但 HTTP 控制接口仍可用。

## Known Constraints

- `serviceToken` 过期时会自动重登一次（401 重试）。
- Xiaomi 触发二次验证需重新提供有效 `pass_token`。
- `conversation` 接口字段属于外部协议，未来可能变化。
- MiOT 动作的 `siid`/`aiid` 因设备型号而异。
- 无自动化集成测试，需通过实际设备联调验证。
