from __future__ import annotations

import argparse
import json
import time
import webbrowser
from pathlib import Path

from realtime_asr.context.manager import ContextManager
from realtime_asr.events import TranscriptEvent
from realtime_asr.lm import LocalLLMReranker
from realtime_asr.web import TopTermsWebServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate live ASR transcript stream from text file")
    parser.add_argument("--script-path", default="examples/sample_script.txt")
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--partial-chunk-words", type=int, default=4)
    parser.add_argument("--word-interval", type=float, default=0.10)
    parser.add_argument("--line-pause", type=float, default=0.45)

    parser.add_argument("--update-interval", type=float, default=2.0)
    parser.add_argument("--final-window", type=int, default=60)
    parser.add_argument("--full-session", action="store_true", help="Use all FINAL transcript from session (no final window pruning).")
    parser.add_argument("--partial-window", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=60)

    parser.add_argument("--print-transcript", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--jsonl", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--realtime", action=argparse.BooleanOptionalAction, default=True)

    parser.add_argument("--serve-ui", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--ui-host", default="127.0.0.1")
    parser.add_argument("--ui-port", type=int, default=8765)

    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-interval", type=float, default=12.0)
    parser.add_argument("--llm-weight", type=float, default=2.0)
    parser.add_argument("--llm-top-k", type=int, default=30)
    parser.add_argument("--llm-ctx", type=int, default=2048)
    parser.add_argument("--llm-max-tokens", type=int, default=420)
    parser.add_argument("--llm-primary", action=argparse.BooleanOptionalAction, default=True)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    path = Path(args.script_path)
    if not path.exists():
        raise SystemExit(f"Script file not found: {path}")

    llm_reranker = None
    if args.llm_model:
        llm_reranker = LocalLLMReranker(
            model_path=args.llm_model,
            n_ctx=args.llm_ctx,
            max_tokens=args.llm_max_tokens,
            temperature=0.0,
            chat_format="chatml",
        )

    final_window_sec = 0 if args.full_session else args.final_window

    manager = ContextManager(
        final_window_sec=final_window_sec,
        partial_window_sec=args.partial_window,
        top_k=args.top_k,
        llm_reranker=llm_reranker,
        llm_interval_sec=args.llm_interval,
        llm_weight=args.llm_weight,
        llm_top_k=args.llm_top_k,
        llm_primary=(args.llm_primary and llm_reranker is not None),
    )

    web_server: TopTermsWebServer | None = None
    if args.serve_ui:
        web_server = TopTermsWebServer(host=args.ui_host, port=args.ui_port)
        web_server.start()
        print(f"[SIM] Word cloud UI: {web_server.url()}")
        if args.open_browser:
            webbrowser.open(web_server.url(), new=1, autoraise=True)

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    next_update = time.time() + args.update_interval
    full_transcript = ""

    def maybe_emit_top_terms(force: bool = False) -> None:
        nonlocal next_update
        now = time.time()
        if not force and now < next_update:
            return
        top_terms = manager.compute_top_terms(now)
        payload = {
            "ts": top_terms.ts,
            "window_sec": top_terms.window_sec,
            "top_k": top_terms.top_k,
            "terms": top_terms.terms,
        }
        if web_server is not None:
            web_server.update(payload)
        if args.jsonl:
            print(json.dumps(payload, ensure_ascii=False))
        next_update = now + args.update_interval

    try:
        for line in lines:
            words = line.split()
            buffer: list[str] = []
            for word in words:
                buffer.append(word)
                if len(buffer) % args.partial_chunk_words != 0:
                    continue
                partial_tail = " ".join(buffer)
                partial_full = (full_transcript + " " + partial_tail).strip()
                event = TranscriptEvent(
                    text=partial_full,
                    is_final=False,
                    ts=time.time(),
                    lang=args.lang,
                    source="simulated_stream",
                )
                manager.on_event(event)
                if args.print_transcript:
                    print(f"[PARTIAL] {partial_full}")
                maybe_emit_top_terms()
                if args.realtime:
                    time.sleep(args.word_interval)

            final_full = (full_transcript + " " + line).strip()
            event = TranscriptEvent(
                text=final_full,
                is_final=True,
                ts=time.time(),
                lang=args.lang,
                source="simulated_stream",
            )
            manager.on_event(event)
            if args.print_transcript:
                print(f"[FINAL] {final_full}")
            maybe_emit_top_terms(force=True)

            full_transcript = final_full
            if args.realtime:
                time.sleep(args.line_pause)

        maybe_emit_top_terms(force=True)
    finally:
        if web_server is not None:
            web_server.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
