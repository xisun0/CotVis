from __future__ import annotations

import argparse
from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.runtime.session import ReviewSession


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


if __name__ == "__main__":
    raise SystemExit(main())
