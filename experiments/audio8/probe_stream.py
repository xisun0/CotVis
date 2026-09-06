"""Measure native runtime first chunk availability; no playback integration."""
import json
from pathlib import Path
import sys
import time
import threading

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from arktts_runtime.runtime import ArkTtsRuntime

runtime = ArkTtsRuntime(root / "model", root / "voices", threads=5)
stop = threading.Event()
start = time.perf_counter()
stream = runtime.stream(text="代码已修改，相关检查全部通过。下一步可以查看差异。", voice="default", stop_event=stop, max_new_tokens=1024)
first = next(stream)
print(json.dumps({"first_chunk_seconds": time.perf_counter()-start,
                  "chunk_audio_seconds": len(first["audio"])/44100}), flush=True)
stream.close()
