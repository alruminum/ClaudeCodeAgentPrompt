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
        RunLogger, StateDir, HUD,
        agent_call, parse_marker, kill_check,
        build_loop_context, run_design_validation, run_plan_validation,
    )
except ImportError:
    from config import HarnessConfig
    from core import (
        RunLogger, StateDir, HUD,
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

    # ── HUD 초기화 ──
    hud = HUD("plan", prefix, issue_num, 1, config.max_total_cost, state_dir)

    # ── product-planner ──
    print("[HARNESS] product-planner 기획")
    _pp_t0 = time.time()
    hud.agent_start("product-planner")
    pp_out_file = str(state_dir.path / f"{prefix}_pp_out.txt")
    agent_call(
        "product-planner", 600,
        f"@MODE:PLANNER:PRODUCT_PLAN\ncontext: {context} issue: #{issue_num}",
        pp_out_file, run_logger, config,
    )
    pp_out = Path(pp_out_file).read_text(encoding="utf-8", errors="replace")
    _pp_cost = 0.0
    try:
        _pp_cost_file = Path(str(pp_out_file).replace(".txt", "_cost.txt"))
        _pp_cost = float(_pp_cost_file.read_text() or "0") if _pp_cost_file.exists() else 0.0
    except (ValueError, OSError):
        pass
    hud.agent_done("product-planner", int(time.time() - _pp_t0), _pp_cost)
    kill_check(state_dir)

    pp_marker = parse_marker(pp_out_file, "PRODUCT_PLAN_READY|PRODUCT_PLAN_UPDATED|CLARITY_INSUFFICIENT")

    if pp_marker == "CLARITY_INSUFFICIENT":
        os.environ["HARNESS_RESULT"] = "CLARITY_INSUFFICIENT"
        print(f"[HARNESS] product-planner → CLARITY_INSUFFICIENT (유저 답변 필요)")
        print(pp_out)
        run_logger.write_run_end("CLARITY_INSUFFICIENT", "", issue_num)
        return "CLARITY_INSUFFICIENT"

    if pp_marker not in ("PRODUCT_PLAN_READY", "PRODUCT_PLAN_UPDATED"):
        os.environ["HARNESS_RESULT"] = "CLARITY_INSUFFICIENT"
        print(f"[HARNESS] product-planner → 마커 감지 실패 ({pp_marker}) — CLARITY_INSUFFICIENT 처리")
        print(pp_out)
        run_logger.write_run_end("CLARITY_INSUFFICIENT", "", issue_num)
        return "CLARITY_INSUFFICIENT"

    hud.log(f"product-planner → {pp_marker}")
    print(f"[HARNESS] product-planner → {pp_marker}")

    # prd.md 경로 추출 (product-planner가 저장한 파일)
    prd_path = ""
    prd_m = re.search(r"(prd[^ ]*\.md)", pp_out)
    if prd_m:
        prd_path = prd_m.group(1)
    if not prd_path or not Path(prd_path).exists():
        if Path("prd.md").exists():
            prd_path = "prd.md"
    print(f"[HARNESS] prd_path: {prd_path or 'N/A'}")

    # ── architect System Design ──
    print("[HARNESS] architect System Design 작성")
    _asd_t0 = time.time()
    hud.agent_start("architect-sd")
    arch_sd_out = str(state_dir.path / f"{prefix}_arch_sd_out.txt")
    # pp_out 전문이 아닌 prd.md 경로만 전달 — architect가 직접 Read
    agent_call(
        "architect", 600,
        f"@MODE:ARCHITECT:SYSTEM_DESIGN\nplan_doc: {prd_path}\nissue: #{issue_num}",
        arch_sd_out, run_logger, config,
    )
    _asd_cost = 0.0
    try:
        _asd_cost_file = Path(str(arch_sd_out).replace(".txt", "_cost.txt"))
        _asd_cost = float(_asd_cost_file.read_text() or "0") if _asd_cost_file.exists() else 0.0
    except (ValueError, OSError):
        pass
    kill_check(state_dir)

    arch_sd_marker = parse_marker(arch_sd_out, "SYSTEM_DESIGN_READY|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")
    if arch_sd_marker == "PRODUCT_PLANNER_ESCALATION_NEEDED":
        hud.agent_done("architect-sd", int(time.time() - _asd_t0), _asd_cost, "fail")
        os.environ["HARNESS_RESULT"] = "PRODUCT_PLANNER_ESCALATION_NEEDED"
        print("[HARNESS] architect-sd → PRODUCT_PLANNER_ESCALATION_NEEDED")
        run_logger.write_run_end("PRODUCT_PLANNER_ESCALATION_NEEDED", "", issue_num)
        return "PRODUCT_PLANNER_ESCALATION_NEEDED"
    if arch_sd_marker not in ("SYSTEM_DESIGN_READY",):
        hud.agent_done("architect-sd", int(time.time() - _asd_t0), _asd_cost, "fail")
        os.environ["HARNESS_RESULT"] = "SPEC_GAP_ESCALATE"
        print(f"[HARNESS] architect-sd → 마커 감지 실패 ({arch_sd_marker}) — SPEC_GAP_ESCALATE")
        arch_sd_content = Path(arch_sd_out).read_text(encoding="utf-8", errors="replace") if Path(arch_sd_out).exists() else ""
        print(arch_sd_content[-500:] if len(arch_sd_content) > 500 else arch_sd_content)
        run_logger.write_run_end("SPEC_GAP_ESCALATE", "", issue_num)
        return "SPEC_GAP_ESCALATE"
    hud.agent_done("architect-sd", int(time.time() - _asd_t0), _asd_cost)
    hud.log(f"architect-sd → {arch_sd_marker}")
    print(f"[HARNESS] architect-sd → {arch_sd_marker}")

    # design_doc 경로 추출 (architecture*.md 우선, 보조 문서 오탐 방지)
    design_doc = ""
    stories_doc = ""
    try:
        content = Path(arch_sd_out).read_text(encoding="utf-8", errors="replace")
        # 1차: architecture*.md 우선 매칭
        m = re.search(r"docs/(?:milestones/[^ ]*)?architecture[^ ]*\.md", content)
        if m and Path(m.group(0)).exists():
            design_doc = m.group(0)
        else:
            # 2차: docs/*.md 중 sdk/db-schema 제외
            for match in re.finditer(r"docs/[^ ]+\.md", content):
                p = match.group(0)
                if not re.search(r"(sdk|db-schema|test-plan|ait-reference)", p) and Path(p).exists():
                    design_doc = p
                    break
        # stories.md 경로 추출
        m_stories = re.search(r"docs/[^ ]*stories\.md", content)
        if m_stories and Path(m_stories.group(0)).exists():
            stories_doc = m_stories.group(0)
    except OSError:
        pass
    print(f"[HARNESS] design_doc: {design_doc or 'N/A'}")
    print(f"[HARNESS] stories_doc: {stories_doc or 'N/A'}")

    # ── Design Validation ──
    if design_doc and Path(design_doc).exists():
        print(f"[HARNESS] Design Validation (design_doc: {design_doc})")
        _dv_t0 = time.time()
        hud.agent_start("design-validation")
        if not run_design_validation(design_doc, issue_num, prefix, 1, state_dir, run_logger, config):
            hud.agent_done("design-validation", int(time.time() - _dv_t0), 0.0, "fail")
            os.environ["HARNESS_RESULT"] = "DESIGN_REVIEW_ESCALATE"
            print(f"[HARNESS] design-validation → DESIGN_REVIEW_ESCALATE")
            print(f"design_doc: {design_doc}")
            run_logger.write_run_end("DESIGN_REVIEW_ESCALATE", "", issue_num)
            return "DESIGN_REVIEW_ESCALATE"
        hud.agent_done("design-validation", int(time.time() - _dv_t0), 0.0)
        print("[HARNESS] design-validation → PASS")
    else:
        hud.agent_skip("design-validation", "design_doc 미감지")
        print("[HARNESS] design-validation 스킵 (design_doc 경로 미감지)")
    kill_check(state_dir)

    # ── architect Module Plan / Task Decompose ──
    # stories.md에서 모듈 수 파악 → 3개 이상이면 TASK_DECOMPOSE
    _arch_mp_mode = "MODULE_PLAN"
    _module_hint = ""
    if stories_doc and Path(stories_doc).exists():
        try:
            stories_text = Path(stories_doc).read_text(encoding="utf-8", errors="replace")
            # impl 항목 카운트 (| NN | 모듈명 | 패턴)
            impl_lines = re.findall(r"\|\s*\d+\s*\|", stories_text)
            if len(impl_lines) >= 3:
                _arch_mp_mode = "TASK_DECOMPOSE"
            else:
                # 첫 번째 모듈명 추출
                m_mod = re.search(r"\|\s*\d+\s*\|\s*([^|]+)", stories_text)
                if m_mod:
                    _module_hint = m_mod.group(1).strip()
        except OSError:
            pass

    _amp_t0 = time.time()
    hud.agent_start("architect-mp")
    arch_mp_out = str(state_dir.path / f"{prefix}_arch_mp_out.txt")

    if _arch_mp_mode == "TASK_DECOMPOSE":
        print(f"[HARNESS] architect TASK_DECOMPOSE (stories: {stories_doc})")
        hud.log(f"TASK_DECOMPOSE ({stories_doc})")
        agent_call(
            "architect", 600,
            f"@MODE:ARCHITECT:TASK_DECOMPOSE\n"
            f"stories_doc: {stories_doc}\n"
            f"design_doc: {design_doc or 'N/A'}\n"
            f"issue: #{issue_num}",
            arch_mp_out, run_logger, config,
        )
    else:
        print(f"[HARNESS] architect MODULE_PLAN (module: {_module_hint or 'auto'}, design_doc: {design_doc})")
        hud.log(f"MODULE_PLAN ({_module_hint or 'auto'})")
        agent_call(
            "architect", 600,
            f"@MODE:ARCHITECT:MODULE_PLAN\n"
            f"design_doc: {design_doc or 'N/A'}\n"
            f"module: {_module_hint or 'design_doc 참조하여 첫 번째 모듈 계획'}\n"
            f"issue: #{issue_num}",
            arch_mp_out, run_logger, config,
        )
    _amp_cost = 0.0
    try:
        _amp_cost_file = Path(str(arch_mp_out).replace(".txt", "_cost.txt"))
        _amp_cost = float(_amp_cost_file.read_text() or "0") if _amp_cost_file.exists() else 0.0
    except (ValueError, OSError):
        pass
    kill_check(state_dir)

    arch_mp_marker = parse_marker(arch_mp_out, "READY_FOR_IMPL|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")
    if arch_mp_marker == "PRODUCT_PLANNER_ESCALATION_NEEDED":
        hud.agent_done("architect-mp", int(time.time() - _amp_t0), _amp_cost, "fail")
        os.environ["HARNESS_RESULT"] = "PRODUCT_PLANNER_ESCALATION_NEEDED"
        print("[HARNESS] architect-mp → PRODUCT_PLANNER_ESCALATION_NEEDED")
        run_logger.write_run_end("PRODUCT_PLANNER_ESCALATION_NEEDED", "", issue_num)
        return "PRODUCT_PLANNER_ESCALATION_NEEDED"
    if arch_mp_marker not in ("READY_FOR_IMPL",):
        hud.agent_done("architect-mp", int(time.time() - _amp_t0), _amp_cost, "fail")
        os.environ["HARNESS_RESULT"] = "SPEC_GAP_ESCALATE"
        print(f"[HARNESS] architect-mp → 마커 감지 실패 ({arch_mp_marker}) — SPEC_GAP_ESCALATE")
        run_logger.write_run_end("SPEC_GAP_ESCALATE", "", issue_num)
        return "SPEC_GAP_ESCALATE"
    hud.agent_done("architect-mp", int(time.time() - _amp_t0), _amp_cost)
    hud.log(f"architect-mp → {arch_mp_marker}")
    print(f"[HARNESS] architect-mp → {arch_mp_marker}")

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
    print(f"[HARNESS] Plan Validation (impl: {impl_file})")
    _pv_t0 = time.time()
    hud.agent_start("plan-validation")
    if not run_plan_validation(impl_file, issue_num, prefix, 1, state_dir, run_logger, config):
        hud.agent_done("plan-validation", int(time.time() - _pv_t0), 0.0, "fail")
        os.environ["HARNESS_RESULT"] = "PLAN_VALIDATION_ESCALATE"
        print(f"[HARNESS] plan-validation → FAIL — PLAN_VALIDATION_ESCALATE")
        print(f"impl: {impl_file}")
        run_logger.write_run_end("PLAN_VALIDATION_ESCALATE", "", issue_num)
        return "PLAN_VALIDATION_ESCALATE"
    hud.agent_done("plan-validation", int(time.time() - _pv_t0), 0.0)

    # ── 완료 ──
    (state_dir.path / f"{prefix}_impl_path").write_text(impl_file, encoding="utf-8")
    os.environ["HARNESS_RESULT"] = "PLAN_VALIDATION_PASS"
    hud.log("PLAN_VALIDATION_PASS")
    print(f"[HARNESS] ✅ PLAN_VALIDATION_PASS")
    print(f"  impl: {impl_file}")
    print(f"  design_doc: {design_doc or 'N/A'}")
    print(f"  issue: #{issue_num}")
    print("  → 계획 확인 후 mode:impl 로 재호출")
    run_logger.write_run_end("PLAN_VALIDATION_PASS", "", issue_num)
    return "PLAN_VALIDATION_PASS"
