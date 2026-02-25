# MVP Spec: macOS Speech Framework 流式 ASR + Context Management + 词云 TopTerms

## 目标
在 macOS（MacBook）上实现一个本地运行的实时语音转写 Demo：
- 从系统麦克风实时获取语音
- 调用 macOS Speech Framework 获得增量 ASR（partial / final）
- 通过“事件式（B）基于稳定片段累加”的策略，维护一个稳定的上下文语料
- 每 2 秒输出一次 TopTerms（作为词云输入），用于后续可视化（word cloud / UI）

本 MVP 不做复杂 UI，先以 CLI + JSON/文本输出为主，形成稳定闭环。

---

## 范围（In Scope）
### 1) 流式 ASR（macOS Speech Framework）
- 语言可配置（默认 `en-US`，可选 `zh-CN`）
- 能持续收到 partial 结果，并在停顿/句末收到 final 结果
- 输出统一事件流 `TranscriptEvent`

### 2) Context Management（事件式 B 策略）
- 仅将 **final 片段**写入“稳定语料库”（Stable Buffer）
- partial 仅进入“短期临时缓冲”（Ephemeral Buffer），用于提升实时感，但权重更低、且会过期
- 支持滑动窗口（例如最近 60s）或按条数（例如最近 50 条 final）
- 每 2 秒（可配置）生成 TopTerms：
  - 权重 = `final_weight * freq(final_window) + partial_weight * freq(partial_recent)`
  - 默认 `final_weight=1.0`，`partial_weight=0.3`
- 具备去重/避免重复计数机制：只对“final 片段”做累计；partial 不累计到 final 语料中

### 3) TopTerms 输出（作为词云输入）
- 每 2 秒输出一次 TopTerms（默认 Top 60）
- 输出格式：JSON Lines（每行一个 JSON），便于后续 UI/WebSocket 接入
- JSON 结构示例：
  >>>json
  {
    "ts": 1730000000.123,
    "window_sec": 60,
    "top_k": 60,
    "terms": [["model", 12.3], ["speech", 9.1], ["context", 7.8]]
  }
  >>>


4) CLI 工具

命令：python -m realtime_asr.cli ...
make setup 安装依赖
make run 默认启动麦克风实时识别并打印：

partial/final 转写（可选开关）
TopTerms JSON Lines（必开）



非目标（Out of Scope）

不做前端 UI / web 页面 / 实时词云渲染（只输出 TopTerms）
不做复杂中文分词（MVP 阶段只做最小可用 tokenization；后续可替换）
不做模型替换（如 Whisper）——但要预留接口，后续可加后端



运行环境与依赖

macOS 13+（建议）
Python 3.11+
pyobjc（用于调用 macOS frameworks）
使用 macOS 自带 Speech Framework（系统 API），不引入云端 ASR 依赖

权限要求：


麦克风权限（Microphone）
语音识别权限（Speech Recognition）



架构与模块

建议目录结构：

repo/
  src/
    realtime_asr/
      __init__.py
      cli.py
      events.py
      asr_backend/
        __init__.py
        base.py
        mac_speech.py
      context/
        __init__.py
        tokenizer.py
        manager.py
      util/
        __init__.py
        time.py
  docs/
    mvp_stream_asr_wordcloud_spec.md
  examples/
    sample.wav            # 可选：用于 dry-run（后续里程碑）
  Makefile
  pyproject.toml
  README.md


1) 事件定义（
events.py
）

TranscriptEvent：

text: str（本次事件的转写文本。建议为“全量 bestTranscription 文本”或“增量片段”，但必须在 backend 文档里写清楚）
is_final: bool
ts: float（事件产生时间，time.time()）
lang: str | None
source: str（例如 "mac_speech"）

推荐：backend 统一输出“本轮 bestTranscription 的全量文本 + is_final”，由 context manager 做差分/稳定化。



2) ASR 后端接口（
asr_backend/base.py
）

ASRBackend 抽象类：

start(callback: Callable[[TranscriptEvent], None]) -> None
stop() -> None
is_running() -> bool

mac_speech.py 实现使用 Speech Framework 的流式识别，并调用 callback 发事件。



3) Context Manager（
context/manager.py
）

职责：


接收 TranscriptEvent
维护：

stable_segments: deque[(ts, text)] 仅 final
ephemeral_text: str 最近一次 partial（或最近 N 次 partial 合并）+ ephemeral_ts
每 update_interval_sec 触发一次 compute_top_terms()，输出 TopTerms（返回结构或直接 yield）
Tokenize 策略（tokenizer.py）：

英文：re.findall(r"[a-zA-Z']+", lower_text)
中文（MVP）：re.findall(r"[\u4e00-\u9fff]+", text) 作为粗粒度 token（后续替换）
stopwords：提供最小集合（英文 + 中文各一份小列表）

窗口策略：


final_window_sec（默认 60s）：只统计 stable_segments 中 ts 在窗口内
partial_window_sec（默认 10s）：只统计 ephemeral（或近几次 partial）并乘以 partial_weight

输出：


TopTermsEvent（可定义在 events.py）或 dict：

ts, window_sec, top_k, terms: list[(term, weight)]



4) CLI（
cli.py
）

参数建议：


--lang en-US|zh-CN（默认 en-US）
--update-interval 2.0（默认 2 秒）
--final-window 60（默认 60 秒）
--partial-window 10（默认 10 秒）
--top-k 60
--print-transcript（默认开启：打印 partial/final 文本）
--jsonl（默认开启：输出 TopTerms JSON Lines）
--verbose



DoD（Definition of Done）

在 macOS 上执行：

make setup
make run
允许权限后，对着麦克风说话：

终端持续输出转写文本（partial/final 均可）
每 2 秒输出一行 TopTerms JSON（terms 非空且随语音变化）
Ctrl+C 可退出，能调用 backend.stop() 做资源释放
README 中清楚写出：

环境要求
权限开启方式（系统设置路径）
常见错误与排查（无权限/无输入设备/识别不可用）



里程碑（可选，MVP 之后）

M1: --dry-run 支持从 examples/sample.wav 读入音频（回归测试）
M2: 输出一个 wordcloud.html（本地打开自动刷新），通过 SSE/WebSocket 或文件轮询
M3: 替换中文分词（jieba / PKU 分词等）
M4: 可插拔后端（Whisper / faster-whisper）保持同一事件接口
