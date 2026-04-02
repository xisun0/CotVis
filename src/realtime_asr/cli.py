from __future__ import annotations

import argparse
from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.runtime.session import ReviewSession
from realtime_asr.runtime.state_machine import SessionState
from realtime_asr.voice.tts import ConsoleTextToSpeech, NullTextToSpeech, SystemTextToSpeech


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Voice-first manuscript review CLI for Markdown documents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser(
        "review",
        help="Open a document review session.",
    )
    review.add_argument("path", help="Path to a Markdown document.")
    review.add_argument(
        "--start-paragraph",
        type=int,
        default=1,
        help="1-based paragraph index to start from.",
    )
    review.add_argument(
        "--match",
        default=None,
        help="Optional text fragment used to locate a starting paragraph.",
    )
    review.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved session target without starting voice features.",
    )
    review.add_argument(
        "--read-demo",
        action="store_true",
        help="Run a sentence-by-sentence reading demo.",
    )
    review.add_argument(
        "--interactive-demo",
        action="store_true",
        help="Run an interactive terminal demo for reading controls.",
    )
    review.add_argument(
        "--max-sentences",
        type=int,
        default=5,
        help="Maximum number of sentences to read in demo mode.",
    )
    review.add_argument(
        "--tts",
        choices=("console", "none", "system"),
        default="console",
        help="TTS backend for read-demo mode.",
    )

    subparsers.add_parser(
        "plan",
        help="Print the current development plan path.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "plan":
        print("docs/voice_review_cli_development_plan.md")
        return 0

    path = Path(args.path).expanduser().resolve()
    document = load_document(path)
    session = ReviewSession.start(
        document=document,
        start_paragraph=max(1, int(args.start_paragraph)),
        match_text=args.match,
    )

    if args.dry_run:
        _print_dry_run_preview(document=document, session=session, args=args)
        return 0

    if args.read_demo:
        _run_read_demo(session=session, args=args)
        return 0

    if args.interactive_demo:
        _run_interactive_demo(session=session, args=args)
        return 0

    print(f"[session] document={document.path}")
    print(f"[session] paragraphs={len(document.paragraphs)}")
    print(f"[session] readable_paragraphs={len(document.readable_paragraphs)}")
    print(f"[session] state={session.state.value}")
    print(f"[session] current_paragraph={session.current_paragraph.index}")
    print(f"[session] current_paragraph_id={session.anchor.paragraph_id}")
    print(f"[session] current_sentence_id={session.anchor.sentence_id}")
    print(f"[session] anchor_fallback={session.anchor.fallback_direction}")
    print("[todo] Phase 0 skeleton is ready.")
    print("[todo] Reading, voice commands, and review flow start in Phase 1+.")
    return 0


def _print_dry_run_preview(document, session, args) -> None:
    kind_counts = document.kind_counts()
    print("[document]")
    print(f"path={document.path}")
    print(f"paragraphs={len(document.paragraphs)}")
    print(f"readable_paragraphs={len(document.readable_paragraphs)}")
    print(f"primary_paragraphs={len(document.primary_paragraphs)}")
    print(f"secondary_paragraphs={len(document.secondary_paragraphs)}")
    print(f"kind_counts={kind_counts}")
    print("")

    print("[start]")
    if args.match:
        reason = f'matched readable paragraph containing "{args.match}"'
    elif int(args.start_paragraph) > 1:
        reason = f"selected preferred paragraph #{int(args.start_paragraph)}"
    else:
        reason = "first primary paragraph after skipped or secondary front matter"
    print(f"reason={reason}")
    print(f"paragraph_id={session.anchor.paragraph_id}")
    print(f"sentence_id={session.anchor.sentence_id}")
    print(f"anchor_fallback={session.anchor.fallback_direction}")
    print("")

    print("[current]")
    print(f"index={session.current_paragraph.index}")
    print(f"id={session.current_paragraph.id}")
    print(f"kind={session.current_paragraph.kind}")
    print(f"readable={session.current_paragraph.readable}")
    print(f"reading_priority={session.current_paragraph.reading_priority}")
    print(f"sentences={len(session.current_paragraph.sentences)}")
    print(f"anchor_paragraph_index={session.anchor.last_known_paragraph_index}")
    print(f"anchor_sentence_index={session.anchor.last_known_sentence_index}")
    print("")

    for sentence in session.current_paragraph.sentences[:3]:
        print(f"[sentence {sentence.index}]")
        print(f"id={sentence.id}")
        print(sentence.text)
        print("")

    previous_paragraph = _neighbor_paragraph(document, session.current_paragraph.index, -1)
    next_paragraph = _neighbor_paragraph(document, session.current_paragraph.index, 1)
    if previous_paragraph is not None:
        print("[previous]")
        print(f"index={previous_paragraph.index}")
        print(f"id={previous_paragraph.id}")
        print(f"kind={previous_paragraph.kind}")
        print(f"readable={previous_paragraph.readable}")
        print(f"reading_priority={previous_paragraph.reading_priority}")
        if previous_paragraph.skip_reason:
            print(f"skip_reason={previous_paragraph.skip_reason}")
        print("")
    if next_paragraph is not None:
        print("[next]")
        print(f"index={next_paragraph.index}")
        print(f"id={next_paragraph.id}")
        print(f"kind={next_paragraph.kind}")
        print(f"readable={next_paragraph.readable}")
        print(f"reading_priority={next_paragraph.reading_priority}")
        if next_paragraph.skip_reason:
            print(f"skip_reason={next_paragraph.skip_reason}")
        print("")


def _neighbor_paragraph(document, current_index: int, offset: int):
    target = current_index + offset
    if target < 1 or target > len(document.paragraphs):
        return None
    return document.paragraphs[target - 1]


def _run_read_demo(session, args) -> None:
    tts = _build_tts_backend(args.tts)
    first_sentence = session.begin_reading()

    print("[read-demo]")
    print(f"state={session.state.value}")
    print(f"max_sentences={args.max_sentences}")
    print(f"tts={args.tts}")
    print("")

    if first_sentence is None:
        print("[read-demo] no readable sentence found")
        return

    sentence = first_sentence
    steps = 0
    while sentence is not None and steps < max(1, int(args.max_sentences)):
        _emit_sentence(session, sentence, tts)
        steps += 1
        sentence = session.advance()

    print("")
    print(f"[read-demo] final_state={session.state.value}")
    print(f"[read-demo] final_paragraph_id={session.anchor.paragraph_id}")
    print(f"[read-demo] final_sentence_id={session.anchor.sentence_id}")
    print(f"[read-demo] steps={steps}")


def _run_interactive_demo(session, args) -> None:
    tts = _build_tts_backend(args.tts)
    sentence = session.begin_reading()

    print("[interactive-demo]")
    print("commands=pause,resume,next,previous,again,paragraph,next paragraph,previous paragraph,next subsection,previous subsection,next section,previous section,status,jump paragraph N,jump match TEXT,help,quit")
    print(f"tts={args.tts}")
    print("")

    if sentence is None:
        print("[interactive-demo] no readable sentence found")
        return

    _emit_sentence(session, sentence, tts)

    while True:
        try:
            raw = input("voice-review> ").strip().lower()
        except EOFError:
            print("")
            break

        command = raw or "next"
        if command == "help":
            print("[help] pause resume next previous again paragraph next paragraph previous paragraph next subsection previous subsection next section previous section status jump paragraph N jump match TEXT quit")
            continue
        if command == "status":
            _print_status(session)
            continue
        if command.startswith("jump paragraph "):
            value = command.removeprefix("jump paragraph ").strip()
            if not value.isdigit():
                print(f"[error] invalid_jump_paragraph={value}")
                continue
            try:
                sentence = session.jump_to_paragraph(int(value))
            except ValueError as exc:
                print(f"[error] {exc}")
                continue
            if sentence is None:
                print("[error] jump_target_has_no_sentence")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command.startswith("jump match "):
            value = raw[len("jump match ") :].strip()
            if not value:
                print("[error] empty_jump_match")
                continue
            try:
                sentence = session.jump_to_match(value)
            except ValueError as exc:
                print(f"[error] {exc}")
                continue
            if sentence is None:
                print("[error] jump_target_has_no_sentence")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "pause":
            session.pause()
            print(f"[status] state={session.state.value}")
            continue
        if command == "resume":
            sentence = session.resume()
            print(f"[status] state={session.state.value}")
            if sentence is not None:
                _emit_sentence(session, sentence, tts)
            continue
        if command == "previous":
            sentence = session.repeat_previous()
            if sentence is not None:
                print(f"[status] state={session.state.value}")
                _emit_sentence(session, sentence, tts)
            continue
        if command == "again":
            sentence = session.replay_current()
            if sentence is not None:
                print(f"[status] state={session.state.value}")
                _emit_sentence(session, sentence, tts)
            continue
        if command == "paragraph":
            sentences = session.replay_paragraph()
            print(f"[status] state={session.state.value}")
            if not sentences:
                print("[error] current_paragraph_has_no_sentences")
                continue
            for sentence in sentences:
                _emit_paragraph_replay_sentence(session, sentence, tts)
            continue
        if command == "next paragraph":
            sentence = session.next_paragraph()
            if sentence is None:
                print("[error] no_next_paragraph")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "previous paragraph":
            sentence = session.previous_paragraph()
            if sentence is None:
                print("[error] no_previous_paragraph")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "next subsection":
            sentence = session.next_subsection()
            if sentence is None:
                print("[error] no_next_subsection")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "previous subsection":
            sentence = session.previous_subsection()
            if sentence is None:
                print("[error] no_previous_subsection")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "next section":
            sentence = session.next_section()
            if sentence is None:
                print("[error] no_next_section")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "previous section":
            sentence = session.previous_section()
            if sentence is None:
                print("[error] no_previous_section")
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "next":
            if session.state is SessionState.PAUSED:
                print("[status] state=paused command_ignored=next")
                continue
            sentence = session.advance()
            if sentence is None:
                print(f"[status] state={session.state.value}")
                if session.state is SessionState.COMPLETED:
                    print("[interactive-demo] reached end of readable content")
                    break
                continue
            _emit_sentence(session, sentence, tts)
            continue
        if command == "quit":
            print("[interactive-demo] quitting")
            break
        print(f"[error] unknown_command={command}")


def _emit_sentence(session, sentence, tts) -> None:
    for announcement in session.consume_announcements():
        print(f"[section] {announcement}")
        tts.speak(announcement)
    print(
        f"[reading] state={session.state.value} "
        f"paragraph={session.current_paragraph.id} sentence={sentence.id} index={sentence.index}"
    )
    print(sentence.text)
    tts.speak(sentence.text)


def _emit_paragraph_replay_sentence(session, sentence, tts) -> None:
    print(
        f"[paragraph] paragraph={session.current_paragraph.id} "
        f"sentence={sentence.id} index={sentence.index}"
    )
    print(sentence.text)
    tts.speak(sentence.text)


def _print_status(session) -> None:
    print(
        f"[status] state={session.state.value} "
        f"paragraph_id={session.anchor.paragraph_id} "
        f"sentence_id={session.anchor.sentence_id} "
        f"paragraph_index={session.anchor.last_known_paragraph_index} "
        f"sentence_index={session.anchor.last_known_sentence_index}"
    )


def _build_tts_backend(name: str):
    if name == "none":
        return NullTextToSpeech()
    if name == "system":
        return SystemTextToSpeech()
    return ConsoleTextToSpeech()


if __name__ == "__main__":
    raise SystemExit(main())
