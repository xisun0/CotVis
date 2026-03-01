from __future__ import annotations

import argparse
import json
from pathlib import Path

from realtime_asr.lm.llm_reranker import LocalLLMReranker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test local LLM term extraction")
    p.add_argument(
        "--model",
        default="/Users/sxi/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        help="Path to local GGUF model",
    )
    p.add_argument(
        "--text",
        default=None,
        help="Direct input text. If omitted, --text-file is used.",
    )
    p.add_argument(
        "--text-file",
        default="examples/sample_script.txt",
        help="Path to text file if --text is not provided",
    )
    p.add_argument("--top-k", type=int, default=20)
    p.add_argument("--n-ctx", type=int, default=512)
    p.add_argument("--max-tokens", type=int, default=420)
    p.add_argument("--chat-format", default="chatml")
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.text:
        source_text = args.text.strip()
    else:
        source_text = Path(args.text_file).read_text(encoding="utf-8").strip()

    reranker = LocalLLMReranker(
        model_path=args.model,
        n_ctx=args.n_ctx,
        max_tokens=args.max_tokens,
        temperature=0.0,
        chat_format=args.chat_format,
    )

    scores = reranker.suggest_scores([source_text], {}, top_k=args.top_k)
    payload = [
        {"term": term, "score": score}
        for term, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
