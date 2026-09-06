# Audio8 本机评估（Issue #12）

结论：本轮暂缓接入默认播报。CPU 路径可用，但完整文件等待明显长于现有 TTS，数字与中英混读出现待试听核对的异常。未改动生产代码或项目依赖，未实现后端切换或打断集成。音色自然度仍待人工试听。

## 环境与口径

- Apple M3 Pro，18 GiB RAM，arm64；Python 3.11.14，ONNX Runtime 1.23.2，CPUExecutionProvider。
- 上游代码：`Edge0-AI/Audio8_TTS`，commit `07e40f5d0b03fc473635ef378654bfb581027ac3`，目录 `onnx_runtime_0_1b_int8`。
- 模型：`Audio8/audio8-TTS-0.1B-ONNX-INT8`，revision `317c12d4e0da83847b594fcf8bd74bf2c76615ec`。
- 模型文件约 443 MB（磁盘约 422 MiB）；不下载 registration encoder。文件校验见 `model-files.json`，依赖见 `requirements-resolved.txt`。
- 使用模型自带 reference codes 注册 default 音色；seed 42、temperature 0.7、top_p 0.9、top_k 50、max_new_tokens 1024。主测试 5 线程。
- 对照沿用项目配置：gpt-4o-mini-tts、alloy、speed 1.2、MP3。Audio8 输出 WAV、默认语速；两者音色与语速未严格匹配。
- 12 条预先固定的场景文本，每条每后端测一次。未调用口播改写，也未读取真实私人会话。记录从提交文字到文件可用的时间，未启动扬声器，不是端到端首声实测。
- 探索性测试，未控制后台负载、网络波动和热状态；不能作为稳定 p95 或模型质量排名。客户端导入、模型加载分别记录，API 网络时间计入对照。

## 结果

| 指标 | Audio8，5 线程 | 现有 OpenAI TTS |
|---|---:|---:|
| 成功生成文件 | 12/12 | 12/12 |
| 文件可用耗时中位数 | 7.63 秒 | 2.26 秒 |
| 耗时范围 | 3.46–20.81 秒 | 1.24–3.37 秒 |
| 耗时/音频时长中位数（RTF） | 1.15 | 0.27 |
| 本机进程峰值 RSS | 2.55 GiB | 0.11 GiB，仅客户端 |

Audio8 runtime 初始化约 1.41 秒，加载后 RSS 约 1.27 GiB。额外首次 CLI smoke 从进程启动到退出约 7.26 秒；这不是清空系统缓存后的冷启动测量，`time -l` 的额外系统统计被 sandbox 拒绝，但音频生成成功。

12 条音频均非空、数值有限，生成器均在 token 上限前结束；这不能证明完整准确朗读。最长文本生成 443 帧，音频 20.57 秒、生成 20.81 秒。

前三条相同文本复测：1 线程耗时 6.22/13.90/13.24 秒，3 线程 3.86/7.85/7.45 秒，均未优于 5 线程的 3.46/7.04/6.76 秒。未穷举线程设置。

额外原生 streaming 探针：第二条文本在约 1.98 秒后产生首个 0.51 秒音频块。仅消费首块后关闭生成器，未测试整段持续流、扬声器播放或取消请求；不能据此宣称流式播报已可用。

## 自动转写核对

两组均用 whisper-1 转写，无参考提示。转写仅作问题定位，不作为听感评分或准确率标签。完整记录见各目录 `transcripts.jsonl`。

- Audio8 第 6 条输入 `3.5%`，转写成 `10%`；第 7 条 `1250.50 美元` 转写成 `250-50年`。
- 第 3 条 issue / 脚本转写为“异书 / 九本”，第 9 条 README.md 转写为“Readme Boombay”。
- 对照组上述数字与术语基本保留；两组均将“标准误”转写为“标准物”，因此不能把所有转写差异归因于 TTS。
- 中文长句整体内容在转写中保留。建议人工重点听第 3、6、7、9 条，再决定是否继续做数字预处理或更换参考音色。

许可证资料存在差异：固定 ONNX 模型卡标为 Apache-2.0，而原始 0.1B 模型页面标为 Audio8 Community License v1.0。这里只记录来源差异，未据此确认商用授权。

## 复现

将本仓库评估分支检出到任意目录；将上游下载到独立目录，例如 `/private/tmp/audio8-upstream`：

```bash
git clone https://github.com/Edge0-AI/Audio8_TTS.git /private/tmp/audio8-upstream
git -C /private/tmp/audio8-upstream checkout 07e40f5d0b03fc473635ef378654bfb581027ac3
cd /private/tmp/audio8-upstream/onnx_runtime_0_1b_int8
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r /path/to/codex-speak/experiments/audio8/requirements-resolved.txt
.venv/bin/python -c 'from huggingface_hub import snapshot_download; snapshot_download("Audio8/audio8-TTS-0.1B-ONNX-INT8", revision="317c12d4e0da83847b594fcf8bd74bf2c76615ec", local_dir="model", ignore_patterns=["registration/*","*.jpeg",".gitattributes"])'
.venv/bin/python scripts/register_default_voice.py
cd /path/to/codex-speak
/private/tmp/audio8-upstream/onnx_runtime_0_1b_int8/.venv/bin/python experiments/audio8/benchmark.py --runtime /private/tmp/audio8-upstream/onnx_runtime_0_1b_int8 --output experiments/audio8/local
```

使用 `--threads 1 --limit 3 --output experiments/audio8/threads1` 可复测线程设置。`--backend openai --output experiments/audio8/openai` 调用收费 API，需要 OPENAI_API_KEY。`transcribe.py <结果目录>` 也调用收费转写 API，限本次合成样本核对，不属于产品 ASR 依赖。

JSON 指标、转写和脚本入库；模型、环境与音频不入 Git。当前音频位于本 worktree 的 `experiments/audio8/local/` 和 `openai/`。临时目录可能被系统清理，音频可由固定脚本重新生成，云端生成不保证逐位一致。
