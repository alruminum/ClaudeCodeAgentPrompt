"""
plan_loop.py — plan.sh 대체.
product-planner → architect → validator → PLAN_COMPLETE.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

try:
    from .config import HarnessConfig
    from .core import (
        RunLogger, StateDir,
        agent_call, parse_marker, kill_check,
        build_loop_context, run_design_validation, run_plan_validation,
    )
except ImportError:
    from config import HarnessConfig
    from core import (
        RunLogger, StateDir,
        agent_call, parse_marker, kill_check,
        build_loop_context, run_design_validation, run_plan_validation,
    )


def run_plan(
    issue_num: str | int,
    prefix: str,
    context: str = "",
    config: Optional[HarnessConfig] = None,
    state_dir: Optional[StateDir] = None,
    run_logger: Optional[RunLogger] = None,
) -> str:
    """plan 모드 실행. plan.sh의 run_plan() 대체."""
    issue_num = str(issue_num)

    if config is None:
        try:
            from .config import load_config
        except ImportError:
            from config import load_config
        config = load_config()
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix)
    if run_logger is None:
        run_logger = RunLogger(prefix, "plan", issue_num)

    # 히스토리 디렉토리
    run_ts = os.environ.get("HARNESS_RUN_TS", time.strftime("%Y%m%d_%H%M%S"))
    hist_dir = state_dir.path / f"{prefix}_history"
    plan_run_dir = hist_dir / "plan" / f"run_{run_ts}"
    plan_run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HARNESS_HIST_DIR"] = str(plan_run_dir)

    # 루프 컨텍스트 prepend
    lc = build_loop_context("plan")
    if lc:
        context = f"{lc}\n{context}"

    # ── product-planner ──
    print("[HARNESS] product-planner 기획")
    pp_out_file = str(state_dir.path / f"{prefix}_pp_out.txt")
    agent_call(
        "product-planner", 300,
        f"@MODE:PLANNER:PRODUCT_PLAN\ncontext: {context} issue: #{issue_num}",
        pp_out_file, run_logger, config,
    )
    pp_out = Path(pp_out_file).read_text(encoding="utf-8", errors="replace")
    kill_check(state_dir)

    pp_marker = parse_marker(pp_out_file, "PRODUCT_PLAN_READY|PRODUCT_PLAN_UPDATED")

    # ── architect System Design ──
    print("[HARNESS] architect System Design 작성")
    arch_sd_out = str(state_dir.path / f"{prefix}_arch_sd_out.txt")
    agent_call(
        "architect", 900,
        f"@MODE:ARCHITECT:SYSTEM_DESIGN\n{pp_out} issue: #{issue_num}",
        arch_sd_out, run_logger, config,
    )
    kill_check(state_dir)

    # design_doc 경로 추출
    design_doc = ""
    try:
        content = Path(arch_sd_out).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"docs/[^ ]+\.md", content)
        if m:
            design_doc = m.group(0)
    except OSError:
        pass

    # ── Design Validation ──
    if design_doc and Path(design_doc).exists():
        print("[HARNESS] Design Validation")
        if not run_design_validation(design_doc, issue_num, prefix, 1, state_dir, run_logger, config):
            os.environ["HARNESS_RESULT"] = "DESIGN_REVIEW_ESCALATE"
            print("DESIGN_REVIEW_ESCALATE")
            print(f"issue: #{issue_num}")
            print(f"design_doc: {design_doc}")
            run_logger.write_run_end("DESIGN_REVIEW_ESCALATE", "", issue_num)
            return "DESIGN_REVIEW_ESCALATE"
        print("[HARNESS] Design Validation PASS")
    else:
        print("[HARNESS] design_doc 경로 미감지 — Design Validation 스킵")
    kill_check(state_dir)

    # ── architect Module Plan ──
    print("[HARNESS] architect Module Plan 작성")
    arch_mp_out = str(state_dir.path / f"{prefix}_arch_mp_out.txt")
    agent_call(
        "architect", 900,
        f"@MODE:ARCHITECT:MODULE_PLAN\ndesign_doc: {design_doc or 'N/A'} issue: #{issue_num}",
        arch_mp_out, run_logger, config,
    )
    kill_check(state_dir)

    impl_file = ""
    try:
        content = Path(arch_mp_out).read_text(encoding="utf-8", errors="replace")
        m = re.search(r"docs/[^ ]+\.md", content)
        if m:
            impl_file = m.group(0)
    except OSError:
        pass

    if not impl_file or not Path(impl_file).exists():
        os.environ["HARNESS_RESULT"] = "SPEC_GAP_ESCALATE"
        print("SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다.")
        print(f"issue: #{issue_num}")
        run_logger.write_run_end("SPEC_GAP_ESCALATE", "", issue_num)
        return "SPEC_GAP_ESCALATE"

    # ── Plan Validation ──
    print("[HARNESS] Plan Validation")
    if not run_plan_validation(impl_file, issue_num, prefix, 1, state_dir, run_logger, config):
        os.environ["HARNESS_RESULT"] = "PLAN_VALIDATION_ESCALATE"
        print("PLAN_VALIDATION_ESCALATE")
        print(f"impl: {impl_file}")
        print(f"issue: #{issue_num}")
        run_logger.write_run_end("PLAN_VALIDATION_ESCALATE", "", issue_num)
        return "PLAN_VALIDATION_ESCALATE"

    # ── 완료 ──
    (state_dir.path / f"{prefix}_impl_path").write_text(impl_file, encoding="utf-8")
    os.environ["HARNESS_RESULT"] = "PLAN_VALIDATION_PASS"
    print("PLAN_VALIDATION_PASS")
    print(f"impl: {impl_file}")
    print(f"design_doc: {design_doc or 'N/A'}")
    print(f"issue: #{issue_num}")
    print("필요 조치: 계획 확인 후 mode:impl 로 재호출")
    run_logger.write_run_end("PLAN_VALIDATION_PASS", "", issue_num)
    return "PLAN_VALIDATION_PASS"
