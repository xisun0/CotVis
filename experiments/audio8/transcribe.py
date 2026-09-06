"""ASR proxy check of synthetic fixtures; not a human listening assessment."""
import argparse
import json
from pathlib import Path
from openai import OpenAI

p = argparse.ArgumentParser()
p.add_argument("directory", type=Path)
a = p.parse_args()
client = OpenAI(timeout=90, max_retries=0)
with (a.directory / "transcripts.jsonl").open("w") as out:
    for row in map(json.loads, (a.directory / "results.jsonl").read_text().splitlines()):
        with (a.directory / row["file"]).open("rb") as f:
            response = client.audio.transcriptions.create(model="whisper-1", file=f)
        result = {"id": row["id"], "expected": row["text"], "transcript": response.text}
        out.write(json.dumps(result, ensure_ascii=False) + "\n")
        out.flush()
        print(json.dumps(result, ensure_ascii=False), flush=True)
