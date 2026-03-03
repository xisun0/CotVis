from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import webbrowser

from realtime_asr.asr_backend import MacSpeechBackend
from realtime_asr.asr_backend.mac_speech import MacSpeechBackendError
from realtime_asr.context.manager import ContextManager
from realtime_asr.events import TranscriptEvent
from realtime_asr.lm import LocalLLMReranker
from realtime_asr.web import TopTermsWebServer

try:
    import CoreFoundation
except Exception:  # pragma: no cover
    CoreFoundation = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Realtime ASR MVP CLI")
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--update-interval", type=float, default=2.0)
    parser.add_argument("--final-window", type=int, default=60)
    parser.add_argument("--full-session", action="store_true", help="Use all FINAL transcript from session (no final window pruning).")
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
    parser.add_argument("--serve-ui", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--ui-host", default="127.0.0.1")
    parser.add_argument("--ui-port", type=int, default=8765)
    parser.add_argument(
        "--canvas-top-n",
        type=int,
        default=15,
        help="Active concept cap per snapshot used for lane assignment and canvas nodes.",
    )
    parser.add_argument("--llm-model", default=None, help="Local GGUF model path for optional LLM reranking.")
    parser.add_argument("--llm-interval", type=float, default=12.0)
    parser.add_argument("--llm-weight", type=float, default=2.0)
    parser.add_argument("--llm-top-k", type=int, default=30)
    parser.add_argument("--llm-ctx", type=int, default=2048)
    parser.add_argument("--llm-max-tokens", type=int, default=420)
    parser.add_argument("--llm-primary", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--llm-only", action=argparse.BooleanOptionalAction, default=False)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    llm_reranker = None
    if args.llm_model:
        try:
            llm_reranker = LocalLLMReranker(
                model_path=args.llm_model,
                n_ctx=args.llm_ctx,
                max_tokens=args.llm_max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            print(f"Failed to initialize local LLM reranker: {exc}", file=sys.stderr)
            return 1
    if args.llm_only and llm_reranker is None:
        print("--llm-only requires --llm-model to be set.", file=sys.stderr)
        return 1

    final_window_sec = 0 if args.full_session else args.final_window

    manager = ContextManager(
        final_window_sec=final_window_sec,
        partial_window_sec=args.partial_window,
        top_k=args.top_k,
        llm_reranker=llm_reranker,
        llm_interval_sec=args.llm_interval,
        llm_weight=args.llm_weight,
        llm_top_k=args.llm_top_k,
        llm_only=args.llm_only,
        llm_primary=(args.llm_primary and llm_reranker is not None),
        canvas_top_n=args.canvas_top_n,
    )

    backend = MacSpeechBackend(lang=args.lang, verbose=args.verbose)
    web_server: TopTermsWebServer | None = None

    if args.serve_ui:
        web_server = TopTermsWebServer(
            host=args.ui_host,
            port=args.ui_port,
            canvas_top_n=args.canvas_top_n,
        )
        try:
            web_server.start()
        except OSError as exc:
            print(
                f"Failed to start web UI server on {args.ui_host}:{args.ui_port}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(f"[CLI] Word cloud UI: {web_server.url()}")
        if args.open_browser:
            webbrowser.open(web_server.url(), new=1, autoraise=True)
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
            if args.llm_model:
                print(f"[CLI] Local LLM rerank enabled: {args.llm_model}")
            if args.llm_only:
                print("[CLI] LLM-only mode enabled: base term scoring is disabled.")

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
            payload = {
                "ts": top_terms.ts,
                "window_sec": top_terms.window_sec,
                "top_k": top_terms.top_k,
                "terms": top_terms.terms,
            }
            if web_server is not None:
                web_server.update(
                    top_terms,
                    lane_assigner=manager.lane_assigner,
                    registry=manager.concept_registry,
                )
            if args.jsonl:
                print(json.dumps(payload, ensure_ascii=False))
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()
        if web_server is not None:
            web_server.stop()

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
