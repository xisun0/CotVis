"""Fixed-text, full-file TTS comparison; Audio8 source stays outside this repo."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np
import psutil
import soundfile as sf

SAMPLES = [
    "你好，测试已经完成。",
    "代码已修改，相关检查全部通过。下一步可以查看差异。",
    "请在 GitHub 上查看这个 issue，然后运行 Python 脚本。",
    "我们使用固定效应回归，并按照公司层面聚类标准误。",
    "样本包含三千一百五十七家公司，覆盖二零一零年至二零二三年。",
    "增长率从 3.5% 上升到 12.8%，增加了 9.3 个百分点。",
    "预算是 1250.50 美元，截止日期为 2026 年 9 月 6 日。",
    "The tests passed. Please review the changes before merging this branch.",
    "运行 pytest 后，检查 README.md 中的安装步骤是否准确。",
    "结果显示，政策发布后，高相关性公司的累计异常收益更高。但这个结果还不能证明具体的信息传递机制。",
    "我已经完成数据核对。原始面板与回归样本的区别主要来自缺失值和筛选条件。请先确认样本定义，再比较两张表中的系数。",
    "这次修改包含三个部分。首先，统一输入文件的日期格式。其次，保留原始记录并标记缺失值。最后，重新生成描述统计表。检查结果表明，行数保持一致，但仍有两条记录需要人工核对。",
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["audio8", "openai"], default="audio8")
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--threads", type=int, default=5)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    process = psutil.Process()
    start = time.perf_counter()
    if a.backend == "audio8":
        sys.path.insert(0, str(a.runtime))
        from arktts_runtime.runtime import ArkTtsRuntime
        engine = ArkTtsRuntime(a.runtime / "model", a.runtime / "voices", threads=a.threads)
    else:
        from openai import OpenAI
        engine = OpenAI(timeout=90, max_retries=0)
    meta = {"backend": a.backend, "load_seconds": time.perf_counter()-start,
            "rss_after_load_bytes": process.memory_info().rss, "threads": a.threads,
            "max_new_tokens": 1024, "seed": 42,
            "openai_model": "gpt-4o-mini-tts", "openai_voice": "alloy", "openai_speed": 1.2}
    (a.output / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta), flush=True)
    with (a.output / "results.jsonl").open("w") as out:
        for i, text in enumerate(SAMPLES[:a.limit]):
            start = time.perf_counter()
            result = {"id": i+1, "text": text}
            try:
                path = a.output / f"{i+1:02d}.wav"
                if a.backend == "audio8":
                    audio, codes = engine.synthesize(text=text, voice="default", max_new_tokens=1024, seed=42)
                    sr = int(engine.manifest["sample_rate"])
                    sf.write(path, audio, sr)
                    result.update(frames=int(codes.shape[1]), hit_token_limit=codes.shape[1] == 1024)
                else:
                    path = path.with_suffix(".mp3")
                    with engine.audio.speech.with_streaming_response.create(model="gpt-4o-mini-tts", voice="alloy", input=text, response_format="mp3", speed=1.2) as response:
                        response.stream_to_file(path)
                    audio, sr = sf.read(path)
                elapsed = time.perf_counter()-start
                duration = len(audio)/sr
                result.update(seconds=elapsed, duration_seconds=duration, rtf=elapsed/duration,
                              finite=bool(np.isfinite(audio).all()), peak=float(np.max(np.abs(audio))),
                              rms=float(np.sqrt(np.mean(np.square(audio)))), file=path.name,
                              peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            except Exception as exc:
                result.update(error=str(exc), seconds=time.perf_counter()-start)
            out.write(json.dumps(result, ensure_ascii=False)+"\n")
            out.flush()
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if "error" in result:
                break

if __name__ == "__main__":
    main()
