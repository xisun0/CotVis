from __future__ import annotations

import argparse
from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.patching.save import SaveConflictError, plan_save, save_document
from realtime_asr.review.engine import build_review_engine
from realtime_asr.runtime.session import ReviewSession
from realtime_asr.runtime.state_machine import SessionState
from realtime_asr.voice.asr import OpenAITurnAsr, TypedTurnAsr
from realtime_asr.voice.commands import ClassifiedUtterance, classify_utterance, normalize_review_decision
from realtime_asr.voice.tts import ConsoleTextToSpeech, NullTextToSpeech, SystemTextToSpeech
from realtime_asr.voice.turn_control import ExplicitTriggerTurnController


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
        "--voice-demo",
        action="store_true",
        help="Run an explicit-trigger voice command demo.",
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
    review.add_argument(
        "--asr",
        choices=("typed", "openai"),
        default="typed",
        help="ASR backend for voice-demo mode.",
    )
    review.add_argument(
        "--voice-listen-seconds",
        type=float,
        default=6.0,
        help="Maximum recording duration for each explicit-trigger voice turn.",
    )
    review.add_argument(
        "--voice-silence-seconds",
        type=float,
        default=0.8,
        help="Silence duration that ends the current spoken command turn.",
    )
    review.add_argument(
        "--voice-energy-threshold",
        type=float,
        default=0.005,
        help="Energy threshold used to detect speech start and end.",
    )
    review.add_argument(
        "--command-language",
        choices=("auto", "zh", "en"),
        default="auto",
        help="Preferred language for spoken command recognition.",
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

    if args.voice_demo:
        _run_voice_demo(session=session, args=args)
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
    review_engine = build_review_engine()
    session.ensure_document_overview(review_engine)
    sentence = session.begin_reading()

    print("[interactive-demo]")
    print("commands=pause/resume/next/... with English or Chinese aliases")
    print(f"tts={args.tts}")
    print("")

    if sentence is None:
        print("[interactive-demo] no readable sentence found")
        return

    _emit_sentence(session, sentence, tts)

    while True:
        try:
            raw = input("voice-review> ").strip()
        except EOFError:
            print("")
            break

        classified = _classify_for_current_mode(session, raw)
        if classified.kind == "request":
            _handle_review_request(session, review_engine, classified.text or "")
            continue
        if classified.kind != "control" or classified.command is None:
            print(f"[error] unknown_command={raw}")
            continue
        if _execute_control_command(
            session=session,
            tts=tts,
            command=classified.command.name,
            argument=classified.command.argument,
            mode_label="interactive-demo",
        ):
            print("[interactive-demo] quitting")
            break


def _run_voice_demo(session, args) -> None:
    tts = _build_tts_backend(args.tts)
    review_engine = build_review_engine()
    session.ensure_document_overview(review_engine)
    turn_controller = ExplicitTriggerTurnController()
    asr = _build_asr_backend(args)
    sentence = session.begin_reading()

    print("[voice-demo]")
    print("trigger=press Enter to capture one spoken command turn")
    print("special=:skip to keep reading, :quit to exit")
    print(f"tts={args.tts}")
    print(f"asr={args.asr}")
    print(f"command_language={args.command_language}")
    if args.asr == "openai":
        print(
            f"voice_turn=max {float(args.voice_listen_seconds):.1f}s, "
            f"silence_stop {float(args.voice_silence_seconds):.1f}s"
        )
    print("")

    if sentence is None:
        print("[voice-demo] no readable sentence found")
        return

    _emit_sentence(session, sentence, tts)

    while True:
        decision = turn_controller.wait_for_trigger()
        if decision.action == "quit":
            print("[voice-demo] quitting")
            break
        if decision.action == "unknown":
            print(f"[voice-demo] invalid_trigger={decision.raw}")
            continue
        if decision.action == "skip":
            if _execute_control_command(
                session=session,
                tts=tts,
                command="next",
                argument=None,
                mode_label="voice-demo",
            ):
                print("[voice-demo] quitting")
                break
            continue

        try:
            turn = asr.capture_turn()
        except RuntimeError as exc:
            print(f"[voice-demo] asr_error={exc}")
            continue
        if turn is None:
            print("[voice-demo] no speech detected")
            continue

        print(f"[transcript] {turn.transcript}")
        classified = _classify_for_current_mode(session, turn.transcript)
        if classified.kind == "request":
            _handle_review_request(session, review_engine, classified.text or "")
            continue
        if classified.kind != "control" or classified.command is None:
            print("[voice-demo] unsupported_spoken_command")
            continue
        print(f"[command] {classified.command.name}")
        if classified.command.argument is not None:
            print(f"[command-argument] {classified.command.argument}")

        if _execute_control_command(
            session=session,
            tts=tts,
            command=classified.command.name,
            argument=classified.command.argument,
            mode_label="voice-demo",
        ):
            print("[voice-demo] quitting")
            break


def _execute_control_command(session, tts, command: str, argument: str | None, mode_label: str) -> bool:
    if session.state is SessionState.AWAITING_DECISION and command not in {"help", "status", "quit", "accept", "discard"}:
        print(f"[{mode_label}] review_decision_required")
        print(f"[{mode_label}] say 用这个 or 放弃, or continue refining with another request")
        return False
    if command == "help":
        print("[help] pause resume next previous again paragraph next paragraph previous paragraph next subsection previous subsection next section previous section status jump paragraph N jump match TEXT quit")
        return False
    if command == "status":
        _print_status(session)
        return False
    if command == "accept":
        try:
            save_plan = plan_save(session.document)
        except SaveConflictError as exc:
            print(f"[save-error] {exc}")
            print(f"[review-state] {session.state.value}")
            return False
        applied = session.accept_review()
        if applied is None:
            print("[error] no_active_revision_to_accept")
            return False
        save_result = save_document(session.document, apply_result=applied, plan=save_plan)
        print("[review-decision] accepted")
        print(f"[apply] paragraph={applied.paragraph_id} sentence={applied.sentence_id}")
        print("[original]")
        print(applied.original_text)
        print("[updated]")
        current_sentence = session.current_sentence
        if current_sentence is not None:
            print(current_sentence.text)
        else:
            print(applied.updated_text)
        print(f"[save] mode={save_result.mode} path={save_result.path}")
        print(f"[review-state] {session.state.value}")
        return False
    if command == "discard":
        session.discard_review()
        print("[review-decision] discarded")
        print(f"[review-state] {session.state.value}")
        return False
    if command == "jump paragraph":
        value = (argument or "").strip()
        if not value.isdigit():
            print(f"[error] invalid_jump_paragraph={value}")
            return False
        try:
            sentence = session.jump_to_paragraph(int(value))
        except ValueError as exc:
            print(f"[error] {exc}")
            return False
        if sentence is None:
            print("[error] jump_target_has_no_sentence")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "jump match":
        value = (argument or "").strip()
        if not value:
            print("[error] empty_jump_match")
            return False
        try:
            sentence = session.jump_to_match(value)
        except ValueError as exc:
            print(f"[error] {exc}")
            return False
        if sentence is None:
            print("[error] jump_target_has_no_sentence")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "pause":
        session.pause()
        print(f"[status] state={session.state.value}")
        return False
    if command == "resume":
        sentence = session.resume()
        print(f"[status] state={session.state.value}")
        if sentence is not None:
            _emit_sentence(session, sentence, tts)
        return False
    if command == "previous":
        sentence = session.repeat_previous()
        if sentence is not None:
            print(f"[status] state={session.state.value}")
            _emit_sentence(session, sentence, tts)
        return False
    if command == "again":
        sentence = session.replay_current()
        if sentence is not None:
            print(f"[status] state={session.state.value}")
            _emit_sentence(session, sentence, tts)
        return False
    if command == "paragraph":
        sentences = session.replay_paragraph()
        print(f"[status] state={session.state.value}")
        if not sentences:
            print("[error] current_paragraph_has_no_sentences")
            return False
        for sentence in sentences:
            _emit_paragraph_replay_sentence(session, sentence, tts)
        return False
    if command == "next paragraph":
        sentence = session.next_paragraph()
        if sentence is None:
            print("[error] no_next_paragraph")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "previous paragraph":
        sentence = session.previous_paragraph()
        if sentence is None:
            print("[error] no_previous_paragraph")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "next subsection":
        sentence = session.next_subsection()
        if sentence is None:
            print("[error] no_next_subsection")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "previous subsection":
        sentence = session.previous_subsection()
        if sentence is None:
            print("[error] no_previous_subsection")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "next section":
        sentence = session.next_section()
        if sentence is None:
            print("[error] no_next_section")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "previous section":
        sentence = session.previous_section()
        if sentence is None:
            print("[error] no_previous_section")
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "next":
        if session.state is SessionState.PAUSED:
            print("[status] state=paused command_ignored=next")
            return False
        sentence = session.advance()
        if sentence is None:
            print(f"[status] state={session.state.value}")
            if session.state is SessionState.COMPLETED:
                print(f"[{mode_label}] reached end of readable content")
                return True
            return False
        _emit_sentence(session, sentence, tts)
        return False
    if command == "quit":
        return True
    print(f"[error] unhandled_command={command}")
    return False


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


def _handle_review_request(session, review_engine, request_text: str) -> None:
    cycle = session.start_review(request_text, review_engine)
    if cycle.instruction.request_type == "answer":
        print(f"[review-request] {cycle.request_text}")
        print(f"[review-intent] {cycle.instruction.intent}")
        print("[answer]")
        print(cycle.instruction.answer_text or "I do not have a grounded answer for that yet.")
        print(f"[review-state] {session.state.value}")
        return
    print(f"[review-target] type={cycle.target.target_type} paragraph_id={cycle.target.paragraph_id} sentence_id={cycle.target.sentence_id}")
    print(f"[review-request] {cycle.request_text}")
    print(f"[review-intent] {cycle.instruction.intent}")
    if cycle.instruction.constraints:
        print(f"[review-constraints] {', '.join(cycle.instruction.constraints)}")
    print("")
    print("[original]")
    print(cycle.target.source_text)
    print("")
    if cycle.candidates:
        candidate = cycle.candidates[0]
        print("[rationale]")
        print(candidate.rationale)
        print("")
        print("[revision]")
        print(candidate.text)
        print("")
    print("[review-state] awaiting_decision")


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


def _classify_for_current_mode(session, raw: str):
    if session.state is SessionState.AWAITING_DECISION:
        decision = normalize_review_decision(raw)
        if decision is not None:
            return ClassifiedUtterance(kind="control", command=decision, text=(raw or "").strip())
    return classify_utterance(raw)


def _build_tts_backend(name: str):
    if name == "none":
        return NullTextToSpeech()
    if name == "system":
        return SystemTextToSpeech()
    return ConsoleTextToSpeech()


def _build_asr_backend(args):
    if args.asr == "openai":
        language = None if args.command_language == "auto" else args.command_language
        return OpenAITurnAsr(
            max_record_seconds=float(args.voice_listen_seconds),
            silence_seconds_to_stop=float(args.voice_silence_seconds),
            energy_threshold=float(args.voice_energy_threshold),
            language=language,
        )
    return TypedTurnAsr()


if __name__ == "__main__":
    raise SystemExit(main())
