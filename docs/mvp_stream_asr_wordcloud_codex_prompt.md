你是我的仓库开发助手。请在当前 git repo 中实现一个 MVP：
macOS Speech Framework 流式 ASR -> 事件式 Context Management（基于稳定片段累加）-> 每2秒输出 TopTerms（JSON Lines）。
要求可在 macOS 上本地运行，从麦克风实时识别。

# 目标（必须达成）
- 命令：make setup && make run
- 运行后：请求麦克风与语音识别权限；对着麦克风说话，终端持续打印转写文本（partial/final均可）
- 每 2 秒输出一行 TopTerms 的 JSON Lines（terms 会随着说话变化）
- Ctrl+C 优雅退出并释放资源

# 技术约束
- 使用 macOS 原生 Speech Framework（通过 pyobjc 调用系统 Framework）
- 不使用任何云端 ASR API
- Python 3.11+
- 依赖用 pyproject.toml 管理（建议用 hatch/uv/poetry 任意一种，但要清晰、可安装）
- 代码要有合理的错误处理：无权限、不可用、无输入设备时要给出可读提示

# 目录结构（请按此创建/修改）
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
  docs/
    mvp_stream_asr_wordcloud_spec.md
  Makefile
  README.md
  pyproject.toml

# 模块与接口要求
1) events.py
- 定义 dataclass: TranscriptEvent
  - text: str
  - is_final: bool
  - ts: float
  - lang: str | None
  - source: str
- 定义 dataclass: TopTermsEvent（或用dict也可，但推荐 dataclass）
  - ts: float
  - window_sec: int
  - top_k: int
  - terms: list[tuple[str, float]]

2) asr_backend/base.py
- 定义抽象类 ASRBackend
  - start(callback: Callable[[TranscriptEvent], None]) -> None
  - stop() -> None
  - is_running() -> bool

3) asr_backend/mac_speech.py
- 用 pyobjc 调用 macOS Speech framework 实现 ASRBackend
- 需要：
  - 请求权限（Speech recognition + microphone）
  - 从默认麦克风持续采集
  - 识别回调中不断产生 TranscriptEvent 并调用 callback
  - partial/final 状态正确设置 is_final
- 注意：Speech Framework 的 bestTranscription 可能是“全量文本”，请明确选择输出策略：
  - 推荐：每次回调输出“当前 bestTranscription.formattedString 的全量文本”并带 is_final
  - 然后由 context manager 做差分与稳定化（避免重复计数）

4) context/tokenizer.py
- 实现最小 tokenize:
  - 英文：re.findall(r"[a-zA-Z']+", lower_text)
  - 中文：re.findall(r"[\u4e00-\u9fff]+", text) 作为粗 token（MVP）
- 提供 stopwords（最小集合）与 normalize（小写、去标点）
- 对长度为1的英文 token 可以过滤（例如 "a" "i" 可按 stopwords 处理）

5) context/manager.py
实现“事件式 B 策略”的 ContextManager：
- 接收 TranscriptEvent
- 维护：
  - stable_segments: deque[(ts, text)] 仅 final
  - ephemeral_text: str 与 ephemeral_ts: float（最近 partial）
  - last_full_text: str（用于从全量 findBestTranscription 中做增量差分/截断）
- 规则：
  - 当收到 partial：更新 ephemeral_text（用于临时层）
  - 当收到 final：提取本次 final 的“新增稳定片段”写入 stable_segments，并清空/更新 ephemeral
- 统计：
  - final_window_sec 默认 60s：统计 stable_segments within window
  - partial_window_sec 默认 10s：统计 ephemeral（或最近partial）并乘 partial_weight=0.3
  - final_weight=1.0
- 输出：
  - 提供 compute_top_terms(now_ts) -> TopTermsEvent
  - terms 为 top_k（默认60）的 (term, weight)
  - weight 可以用 raw freq 或 sqrt/log 缩放（任选其一，但要稳定，不要极端）

6) cli.py
- argparse 参数：
  --lang (default en-US)
  --update-interval (default 2.0)
  --final-window (default 60)
  --partial-window (default 10)
  --top-k (default 60)
  --print-transcript (default true)
  --jsonl (default true)
  --verbose
- 运行流程：
  - 初始化 ContextManager
  - 启动 MacSpeechBackend，将事件喂给 ContextManager.on_event(...)
  - 主线程每 update-interval 秒 compute_top_terms 并 print JSON line
  - 同时可选择打印 transcript（partial/final）
  - 捕获 KeyboardInterrupt，调用 backend.stop() 并退出

7) Makefile
- make setup: 安装依赖
- make run: 运行 CLI（带合理默认参数）

8) README.md
写清：
- 环境要求（macOS + Python版本）
- 安装：make setup
- 运行：make run
- 权限开启路径与常见错误排查（无权限、识别不可用）
- 输出示例（转写与 TopTerms JSONL）

9) docs/mvp_stream_asr_wordcloud_spec.md
把 MVP 需求与 DoD 写成开发文档（可参考你实现的行为），确保与代码一致。

# 质量要求
- 代码可读、模块清晰、注释适度
- 错误信息友好
- 不要引入不必要依赖（除 pyobjc 和基础工具库）
- 运行后能真实从麦克风获得识别结果并持续输出

# 最后请你做的事情
- 创建/修改以上文件并填充内容
- 确保 make setup && make run 可用
- 在 README 里给出一个“快速验证步骤”
- 给出我应该如何在 macOS 系统设置里打开权限的说明

开始实现。完成后给我一个简短的变更摘要（哪些文件新增/修改）和运行命令。
