#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.stage1_2_orchestrator import Stage1_2Orchestrator
from src.core.factory import build_stage2_text_executor, validate_llm_provider_config
from src.storage.json_storage import JSONStorage


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DreamyDraw Stage 1-2 MVP text flow.")
    parser.add_argument("request", nargs="?", default=None, help="Raw text request.")
    parser.add_argument("--count", type=int, default=None, help="Requested approved text count.")
    parser.add_argument("--session", default=None, help="Existing session id to resume.")
    parser.add_argument("--resume", default=None, help="Clarification response for an existing session.")
    parser.add_argument("--output-dir", default=os.environ.get("DREAMYDRAW_STAGE1_2_OUTPUT_DIR", "output/stage1_2_mvp"))
    parser.add_argument("--executor", choices=("mock", "llm"), default="mock", help="Stage 2 text executor.")
    parser.add_argument("--provider", default=None, help="LLM provider for --executor llm. Defaults to LLM_PROVIDER.")
    parser.add_argument("--model", default=None, help="LLM model for --executor llm. Defaults to LLM_MODEL.")
    parser.add_argument("--debug-llm", action="store_true", help="Write raw LLM prompt/response debug artifacts.")
    args = parser.parse_args()
    debug_llm = args.debug_llm or _env_flag("DREAMYDRAW_LLM_DEBUG")

    if args.executor == "llm":
        try:
            validate_llm_provider_config(args.provider)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    text_executor = build_stage2_text_executor(
        executor_type=args.executor,
        provider_name=args.provider,
        model_name=args.model,
    )
    storage = JSONStorage(args.output_dir)
    orchestrator = Stage1_2Orchestrator(
        storage=storage,
        text_executor=text_executor,
        prompts_root=Path(__file__).resolve().parents[1] / "prompts",
        candidate_count=3,
    )

    if args.session:
        session_id = args.session
        resume_value = {"freeform_text": args.resume} if args.resume is not None else None
    else:
        if args.request is None:
            parser.error("request text or --session is required")
        config = {"count": args.count} if args.count is not None else {}
        session = orchestrator.start_session(args.request, current_config=config)
        session_id = session.session_id
        resume_value = None

    if debug_llm and hasattr(text_executor, "set_debug_artifacts"):
        debug_dir = Path(args.output_dir) / session_id / "debug" / "llm"
        text_executor.set_debug_artifacts(debug_dir, to_stderr=True)
        print(f"debug_llm_dir: {debug_dir}", file=sys.stderr)

    result = orchestrator.run_pipeline(session_id, resume_value=resume_value)
    _print_result(result)
    return 0


def _print_result(result) -> None:
    session = result.session
    print(f"session_id: {session.session_id}")
    print(f"completion_status: {session.completion_status.value}")
    print(f"current_node: {session.current_node}")

    if result.is_waiting_user:
        interrupt = result.interrupt or {}
        print("waiting_user: true")
        print(f"interrupt_type: {result.interrupt_type}")
        print(f"interrupt_node: {interrupt.get('node', '')}")
        print(f"interrupt_reason: {_interrupt_reason(interrupt)}")
        print(f"freeform_allowed: {str(bool(interrupt.get('freeform_allowed', True))).lower()}")
        options = interrupt.get("options") or []
        for option in options:
            print(f"option: {option.get('id')} | {option.get('label')}")
        return

    if session.approved_texts:
        print(f"approved_count: {len(session.approved_texts)}")
        print("approved_texts:")
        for index, item in enumerate(session.approved_texts, start=1):
            print(f"{index}. theme: {item.theme}")
            print(f"   text: {item.text}")
            if item.questions:
                print(f"   questions: {'; '.join(item.questions)}")

    if session.shortage.status != "not_started":
        print(f"shortage_status: {session.shortage.status}")
        print(f"shortage_approved: {session.shortage.approved}/{session.shortage.requested}")

    if not result.is_done and not result.is_waiting_user:
        print(f"diagnostic_current_node: {session.current_node}")
    if session.completion_status.value in {"failed", "stopped_unresolved_request", "stopped_by_user"}:
        print(f"diagnostic: {session.interpretation_state.stop_reason or session.shortage.failure_details}")


def _interrupt_reason(interrupt: dict[str, Any]) -> str:
    reason = interrupt.get("reason") or interrupt.get("message") or ""
    if isinstance(reason, list):
        return "; ".join(str(item) for item in reason)
    return str(reason)


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().casefold() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
