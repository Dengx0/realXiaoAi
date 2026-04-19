# Architecture

## Goals

这个仓库提供一个面向小爱音箱的内部 LLM 决策与控制服务，负责消息轮询、意图判断、设备控制、音效生成和状态查询。

## Package Layout

- [main.py](./main.py)
  统一启动入口，加载配置并启动完整服务
- [xiaoi/service.py](./xiaoi/service.py)
  应用层服务，负责组装客户端、消息轮询、LLM 调度和音频生成
- [xiaoi/llm_client.py](./xiaoi/llm_client.py)
  OpenAI 兼容 Function Calling 客户端，负责把文本意图转换成结构化动作
- [xiaoi/http_api.py](./xiaoi/http_api.py)
  HTTP 路由、鉴权、CORS、状态接口和静态音频暴露
- [xiaoi/client.py](./xiaoi/client.py)
  Xiaomi / MiNA 调用边界，负责登录、设备发现和设备控制
- [xiaoi/messages.py](./xiaoi/messages.py)
  小爱消息轮询游标逻辑
- [xiaoi/config.py](./xiaoi/config.py)
  配置模型与 JSON 加载逻辑
- [aiaudio/aiaudio.py](./aiaudio/aiaudio.py)
  ElevenLabs 音频生成能力

## Runtime Flow

1. `main.py` 读取配置并启动统一 HTTP 服务。
2. `XiaoAiService.initialize()` 完成登录与目标设备绑定。
3. `XiaoAiService.start_message_monitor()` 在后台持续拉取最近消息。
4. 新消息会写入最近消息缓存，并在启用 LLM 时送入 `LLMClient`。
5. `LLMClient` 通过 OpenAI 兼容 Function Calling 返回结构化动作。
6. `XiaoAiService` 根据动作执行原生放行、TTS 播报或音效生成并播放。
7. `UnifiedApiHandler` 暴露状态接口、控制接口和音频文件访问。

## HTTP Endpoints

- `GET /`
  返回服务状态、设备摘要和最近一次 LLM 动作摘要
- `GET /api/xiaoai/messages`
  返回最近轮询到的消息
- `POST /api/xiaoai/tts`
  文本播报
- `POST /api/xiaoai/audio`
  播放远程音频
- `POST /api/xiaoai/volume`
  调整音量
- `POST /api/xiaoai/command`
  执行 MiOT 动作
- `POST /api/xiaoai/stop`
  停止播放
- `POST /api/xiaoai/control`
  统一动作分发入口
- `POST /api/audio/generate`
  生成音频文件
- `GET /audio/<filename>`
  访问生成的音频文件

## Maintenance Rules

- 改控制协议、设备动作或登录流程时，优先修改 [xiaoi/client.py](./xiaoi/client.py)
- 改 HTTP 路由、鉴权、跨域或返回结构时，优先修改 [xiaoi/http_api.py](./xiaoi/http_api.py)
- 改消息缓存、后台轮询或 LLM 调度行为时，优先修改 [xiaoi/service.py](./xiaoi/service.py) 与 [xiaoi/messages.py](./xiaoi/messages.py)
- 改 Function Calling prompt、工具定义或返回解析时，优先修改 [xiaoi/llm_client.py](./xiaoi/llm_client.py)
- 改音频生成逻辑时，优先修改 [aiaudio/aiaudio.py](./aiaudio/aiaudio.py)
- 改配置字段与加载逻辑时，优先修改 [xiaoi/config.py](./xiaoi/config.py)
