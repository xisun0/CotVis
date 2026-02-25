from __future__ import annotations

import argparse
import json
import platform
import sys
import time

from realtime_asr.asr_backend import MacSpeechBackend
from realtime_asr.asr_backend.mac_speech import MacSpeechBackendError
from realtime_asr.context.manager import ContextManager
from realtime_asr.events import TranscriptEvent

try:
    import CoreFoundation
except Exception:  # pragma: no cover
    CoreFoundation = None


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

    backend = MacSpeechBackend(lang=args.lang, verbose=args.verbose)
    last_event_ts = time.time()

    def on_event(event: TranscriptEvent) -> None:
        nonlocal last_event_ts
        last_event_ts = event.ts
        manager.on_event(event)
        if args.print_transcript:
            tag = "FINAL" if event.is_final else "PARTIAL"
            print(f"[{tag}] {event.text}")

    try:
        backend.start(on_event)
    except MacSpeechBackendError as exc:
        print(f"Failed to start backend: {exc}", file=sys.stderr)
        return 1
    if args.verbose:
        print("[CLI] Backend started. Waiting for speech...")

    try:
        while True:
            _wait_interval(args.update_interval)
            if not backend.is_running():
                err = backend.get_last_error()
                if err:
                    print(f"Backend stopped: {err}", file=sys.stderr)
                else:
                    print("Backend stopped.", file=sys.stderr)
                return 1
            if args.verbose and (time.time() - last_event_ts) > 10.0:
                stats = backend.get_debug_stats()
                print(
                    "[CLI] No transcript in 10s. "
                    f"audio_buffers={int(stats['audio_buffer_count'])}, "
                    f"recognizer_callbacks={int(stats['result_callback_count'])}"
                )
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


def _wait_interval(seconds: float) -> None:
    if seconds <= 0:
        return
    if platform.system() != "Darwin" or CoreFoundation is None:
        time.sleep(seconds)
        return

    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        CoreFoundation.CFRunLoopRunInMode(
            CoreFoundation.kCFRunLoopDefaultMode,
            min(remaining, 0.2),
            False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
