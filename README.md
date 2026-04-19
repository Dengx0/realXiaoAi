# xiaoi

小爱音箱内部 LLM 决策与控制服务。

## Current Scope

- Xiaomi 登录与设备绑定
- 小爱消息轮询
- 基于 OpenAI 兼容接口的内部 LLM Function Calling 决策
- 小爱设备控制（TTS、音频播放、音量、MiOT 命令）
- 统一 HTTP API 服务
- ElevenLabs 音效生成与静态音频访问
- 最近消息与最近一次 LLM 动作状态查询

## Quick Start

安装依赖：

```bash
uv pip install requests openai
```

复制配置文件：

```bash
copy config.example.json config.json
```

编辑 `config.json`：

- `xiaoai.user_id`
- `xiaoai.pass_token`
- `xiaoai.did`
- `llm.api_key`
- `llm.base_url`
- `llm.model`
- `http_api.host`
- `http_api.port`
- `http_api.public_base_url`
- `http_api.audio_dir`
- `http_api.control_token`（可选，建议配置）
- `elevenlabs.api_key`（可选；仅在启用音效生成时需要）

统一入口：

```bash
python main.py --config config.json
```

启动后会默认完成这些事情：

- 登录并初始化目标音箱
- 后台轮询最近消息
- 将新消息送入内部 LLM 决策链
- 按 LLM 返回的动作执行 TTS、音频播放或音效生成
- 提供 HTTP 控制接口和音频生成接口

## 业务流程

1. 用户唤起小爱音箱并说话。
2. 程序轮询到新的小爱消息后，写入最近消息缓存。
3. 若 `llm.enabled=true`，消息会进入 `LLMClient` 的 Function Calling 决策流程。
4. LLM 返回 `pass_through`、`speak_text` 或 `generate_sound_effect` 动作。
5. `XiaoAiService` 按动作执行原生放行、TTS 播报或 ElevenLabs 音效生成并播放。
6. HTTP API 同时提供状态查询、消息查看、手动控制和音频生成能力。

## HTTP API

服务监听在 `http_api.host:port`。

### 状态接口

```bash
GET /
```

返回服务状态、目标设备信息、`llm` 摘要和接口列表。

### 最近消息

```bash
GET /api/xiaoai/messages?limit=20
```

返回最近轮询到的消息列表。

### 控制接口

```bash
POST /api/xiaoai/tts
{"text":"今天天气晴朗","interrupt":true,"save":0}
```

```bash
POST /api/xiaoai/audio
{"url":"https://example.com/audio.mp3","interrupt":true}
```

```bash
POST /api/xiaoai/volume
{"volume":50}
```

```bash
POST /api/xiaoai/command
{"siid":3,"aiid":1,"params":[]}
```

```bash
POST /api/xiaoai/stop
{}
```

### 统一控制接口

```bash
POST /api/xiaoai/control
{"action":"tts","text":"今天天气晴朗","interrupt":true}
```

支持 `tts`、`audio`、`volume`、`command`、`stop`、`audio_generate`。

### 音频生成接口

```bash
POST /api/audio/generate
{"text":"生成一段下雨的环境音","duration_seconds":5.0}
```

返回：

```json
{
  "audio_url": "http://your-server:8090/audio/sound_xxx.mp3",
  "filename": "sound_xxx.mp3",
  "duration_seconds": 5.0
}
```

## LLM 配置说明

`llm` section 使用 OpenAI 兼容接口，支持：

- `api_key`：API Key
- `base_url`：兼容 OpenAI Chat Completions 的服务地址
- `model`：模型名
- `system_prompt`：可选，自定义系统提示词
- `story_rules`：可选，讲故事规则
- `temperature`：采样温度
- `timeout`：请求超时
- `enabled`：是否启用 LLM 决策

当 `llm.enabled=false` 或未配置 `llm` 时，服务仍可启动，但不会自动对消息执行 LLM 动作。

## 鉴权

如果配置了 `http_api.control_token`，可使用：

```bash
Authorization: Bearer your-secret-token
X-XiaoAI-Token: your-secret-token
```

## CORS

所有接口默认允许跨域：

```bash
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-XiaoAI-Token
```

## 文档

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [CLAUDE.md](./CLAUDE.md)

## License

MIT License
