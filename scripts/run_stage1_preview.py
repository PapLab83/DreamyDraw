#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stage1_runner import Stage1Runner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standalone Stage 1 preview checkpoint.")
    parser.add_argument("request", nargs="?", default=None, help="Raw user request for a new Stage 1 session.")
    parser.add_argument("--session", dest="session_id", help="Resume an existing Stage 1 session id.")
    parser.add_argument("--resume-option", help="Selected clarification option id.")
    parser.add_argument("--resume-text", help="Freeform clarification text.")
    parser.add_argument(
        "--storage-dir",
        default="test_output/stage1_preview",
        help="JSONStorage directory for standalone Stage 1 sessions.",
    )
    args = parser.parse_args()

    runner = Stage1Runner(storage_dir=args.storage_dir, prompts_root=PROJECT_ROOT / "prompts")
    try:
        if args.session_id:
            result = runner.resume(args.session_id, _resume_payload(args))
        elif args.request is not None:
            result = runner.start(args.request)
        else:
            parser.error("Provide either a request text or --session for resume.")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _print_result(result, Path(args.storage_dir))
    return 0


def _resume_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "selected_option_id": args.resume_option,
        "freeform_text": args.resume_text,
    }


def _print_result(result, storage_dir: Path) -> None:
    session = result.session
    print(f"session_id: {session.session_id}")
    print(f"status: {_status(result)}")
    print(f"completion_status: {_status_value(session.completion_status)}")
    print(f"saved_state: {storage_dir / session.session_id / 'state.json'}")
    print("normalized_request:")
    print(f"  format: {session.normalized_request.content_format}")
    print(f"  truth_mode: {session.normalized_request.truth_mode}")
    print(f"  utility_mode: {session.normalized_request.utility_mode}")
    print(f"  utility_topic: {session.normalized_request.utility_topic}")
    print(f"  target_age: {session.normalized_request.target_age}")
    print(f"  main_subject: {session.normalized_request.main_subject}")

    if session.preview_state.preview_text:
        print(f"preview: {session.preview_state.preview_text}")
    if session.prompt_context.snapshot_hash:
        print(f"prompt_context_snapshot_hash: {session.prompt_context.snapshot_hash}")
    if result.is_waiting_user and session.pending_interrupt:
        _print_interrupt(session.pending_interrupt)


def _print_interrupt(interrupt: Any) -> None:
    payload = interrupt.payload
    print(f"interrupt_type: {interrupt.type}")
    print(f"reason: {payload.get('reason')}")
    print(f"message: {payload.get('message')}")
    print("options:")
    for option in payload.get("options", []):
        print(f"  {option.get('id')}: {option.get('label')}")
    print("resume_examples:")
    print("  python scripts/run_stage1_preview.py --session <session_id> --resume-option opt_1")
    print('  python scripts/run_stage1_preview.py --session <session_id> --resume-text "Сказка про лису для 5 лет"')


def _status(result: Any) -> str:
    if result.is_stage1_ready:
        return "stage1_ready"
    if result.is_waiting_user:
        return "waiting_user"
    return _status_value(result.session.completion_status)


def _status_value(status: Any) -> str:
    return getattr(status, "value", status)


if __name__ == "__main__":
    raise SystemExit(main())
