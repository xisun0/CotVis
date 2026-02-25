from __future__ import annotations

import argparse
import json
import sys
import time

from realtime_asr.asr_backend import MacSpeechBackend
from realtime_asr.context.manager import ContextManager
from realtime_asr.events import TranscriptEvent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Realtime ASR MVP CLI")
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--update-interval", type=float, default=2.0)
    parser.add_argument("--final-window", type=int, default=60)
    parser.add_argument("--partial-window", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=60)
    parser.add_argument(
        "--print-transcript",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--jsonl",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    manager = ContextManager(
        final_window_sec=args.final_window,
        partial_window_sec=args.partial_window,
        top_k=args.top_k,
    )

    backend = MacSpeechBackend(lang=args.lang)

    def on_event(event: TranscriptEvent) -> None:
        manager.on_event(event)
        if args.print_transcript:
            tag = "FINAL" if event.is_final else "PARTIAL"
            print(f"[{tag}] {event.text}")

    try:
        backend.start(on_event)
    except NotImplementedError as exc:
        print(f"Backend not ready: {exc}", file=sys.stderr)
        return 1

    try:
        while True:
            time.sleep(args.update_interval)
            top_terms = manager.compute_top_terms()
            if args.jsonl:
                print(
                    json.dumps(
                        {
                            "ts": top_terms.ts,
                            "window_sec": top_terms.window_sec,
                            "top_k": top_terms.top_k,
                            "terms": top_terms.terms,
                        },
                        ensure_ascii=False,
                    )
                )
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
