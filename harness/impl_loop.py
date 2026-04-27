"""
impl_loop.py — impl_simple/std/deep.sh 대체.
AgentStep 체인 구조 + run_simple/run_std/run_deep 구현.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from .config import HarnessConfig, load_config
    from .core import (
        Flag, Marker, RunLogger, StateDir, HUD, WorktreeManager,
        agent_call, parse_marker,
        create_feature_branch, merge_to_main, push_and_ensure_pr, generate_commit_msg,
        collect_changed_files,
        build_smart_context, build_validator_context, explore_instruction,
        generate_handoff, write_handoff,
        prune_history, kill_check, detect_depth,
        record_escalate,
    )
    from .helpers import (
        load_constraints, append_failure, append_success,
        rollback_attempt, check_agent_output, run_automated_checks,
        budget_check, generate_pr_body, save_impl_meta,
        setup_hlog, log_decision, log_phase,
        extract_acceptance_criteria, extract_polish_items,
    )
    from .providers import run_review_batch
except ImportError:
    from config import HarnessConfig, load_config
    from core import (
        Flag, Marker, RunLogger, StateDir, HUD, WorktreeManager,
        agent_call, parse_marker,
        create_feature_branch, merge_to_main, push_and_ensure_pr, generate_commit_msg,
        collect_changed_files,
        build_smart_context, build_validator_context, explore_instruction,
        generate_handoff, write_handoff,
        prune_history, kill_check, detect_depth,
        record_escalate,
    )
    from helpers import (
        load_constraints, append_failure, append_success,
        rollback_attempt, check_agent_output, run_automated_checks,
        budget_check, generate_pr_body, save_impl_meta,
        setup_hlog, log_decision, log_phase,
        extract_acceptance_criteria, extract_polish_items,
    )
    from providers import run_review_batch


# ═══════════════════════════════════════════════════════════════════════
# 0. Circuit Breaker — 시간 윈도우 기반 동일 실패 감지
# ═══════════════════════════════════════════════════════════════════════

CIRCUIT_BREAKER_WINDOW = 1800  # 초 (120→1800: jajang attempt 평균 436s × 3 = 1308s 커버)
CIRCUIT_BREAKER_THRESHOLD = 2  # 동일 타입 N회


def _circuit_breaker_check(
    fail_type: str,
    fail_timestamps: Dict[str, List[float]],
    hlog_fn: Callable,
    run_logger: Optional[RunLogger] = None,
) -> bool:
    """동일 fail_type이 CIRCUIT_BREAKER_WINDOW초 내 CIRCUIT_BREAKER_THRESHOLD회 반복 → True.

    True이면 즉시 IMPLEMENTATION_ESCALATE해야 함.
    """
    now = time.time()
    if fail_type not in fail_timestamps:
        fail_timestamps[fail_type] = []
    fail_timestamps[fail_type].append(now)

    # window 바깥 타임스탬프 제거
    cutoff = now - CIRCUIT_BREAKER_WINDOW
    fail_timestamps[fail_type] = [t for t in fail_timestamps[fail_type] if t >= cutoff]

    count = len(fail_timestamps[fail_type])
    if count >= CIRCUIT_BREAKER_THRESHOLD:
        hlog_fn(f"CIRCUIT BREAKER: {fail_type} {count}회/{CIRCUIT_BREAKER_WINDOW}s → 조기 에스컬레이션")
        print(f"[HARNESS] CIRCUIT BREAKER: {fail_type}이 {CIRCUIT_BREAKER_WINDOW}초 내 {count}회 반복 — 조기 에스컬레이션")
        if run_logger:
            run_logger.log_event({
                "event": "circuit_breaker",
                "fail_type": fail_type,
                "count": count,
                "window_s": CIRCUIT_BREAKER_WINDOW,
                "t": int(now),
            })
        return True
    return False


def _extract_must_fix_from_pr_log(pr_log_path: Path) -> str:
    """이전 attempt의 pr.log에서 ### MUST FIX 섹션만 추출.

    pr-reviewer는 기본적으로 이번 attempt의 diff만 보므로, 이전 attempt에서
    지적한 MUST FIX 항목이 engineer에 의해 처리되지 않고 남아 있어도 시야
    밖이라 놓친다 (run_20260419_201311 재현: #8b8b90 하드코딩이 attempt-1
    에서 MUST FIX 지적됐으나 attempt-2 engineer가 놓쳤고 attempt-2 pr-reviewer
    가 이번 diff에 해당 문자열이 없어 LGTM 처리).

    이 함수는 직전 attempt의 MUST FIX 본문을 추출해 pr-reviewer 프롬프트에
    "이번 diff 에서 처리됐는지 확인" 체크리스트로 주입하기 위한 헬퍼.
    """
    if not pr_log_path.exists():
        return ""
    try:
        content = pr_log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # "### MUST FIX" 시작부터 다음 "### " 섹션 또는 "---MARKER" / 파일 끝까지
    m = re.search(
        r"###\s*MUST\s*FIX(.*?)(?=\n###\s|\n---MARKER|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""
    body = m.group(1).strip()
    return body[:1500]  # 과도한 길이 방지


def _prev_must_fix_hint(loop_out_dir: Path, attempt: int) -> str:
    """pr-reviewer 호출부에 끼워 넣을 이전 MUST FIX 체크리스트 문자열."""
    if attempt <= 0:
        return ""
    prev_log = loop_out_dir / f"attempt-{attempt - 1}" / "pr.log"
    must = _extract_must_fix_from_pr_log(prev_log)
    if not must:
        return ""
    return (
        f"\n\n[이전 attempt-{attempt - 1} MUST FIX — 이번 diff·PR 전체 기준으로 처리됐는지 확인]\n"
        f"```\n{must}\n```\n"
        "위 항목이 이번 변경뿐 아니라 PR 누적 상태에서 **여전히 남아 있다면** "
        "이번 diff 가 아무리 작아도 반드시 CHANGES_REQUESTED를 내야 한다. "
        "처리됐다면 어떤 커밋에서 해결됐는지 명시한 뒤 LGTM."
    )


def _extract_generic_fail_hint(prev_dir: Path, limit: int = 2000) -> str:
    """fail_type이 task_map에 없을 때 prev_dir의 최신 .log 마지막 N바이트를 인라인.

    Why: explore_instruction만 주면 engineer가 Read를 생략하고 같은 실수를
    반복하는 버그가 반복 관찰됨 (pr_fail은 이미 인라인 처리 — 같은 원리).
    validator/test/autocheck 외 새로 생길 수 있는 fail_type 전반을 커버.
    """
    if not prev_dir.is_dir():
        return ""
    try:
        logs = sorted(
            prev_dir.glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""
    for p in logs:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if txt.strip():
            return f"[이전 실패 로그: {p.name}]\n```\n{txt[-limit:]}\n```"
    return ""


# ═══════════════════════════════════════════════════════════════════════
# 1. AgentStep dataclass
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AgentStep:
    agent: str
    timeout: int
    prompt_builder: Callable  # (context_dict) -> str
    success_markers: str      # "PASS|LGTM" etc.
    fail_type: str            # "engineer_fail" etc.


def _bind_cwd(work_cwd: Optional[str]):
    """work_cwd가 있으면 agent_call에 cwd를 자동 주입하는 래퍼 반환."""
    if not work_cwd:
        return agent_call
    from functools import partial
    return partial(agent_call, cwd=work_cwd)


# ═══════════════════════════════════════════════════════════════════════
# 2. run_simple — impl_simple.sh 전체 흐름
# ═══════════════════════════════════════════════════════════════════════

def run_simple(
    impl_file: str,
    issue_num: str | int,
    config: HarnessConfig,
    state_dir: StateDir,
    prefix: str,
    branch_type: str = "feat",
    run_logger: Optional[RunLogger] = None,
    hud: Optional[HUD] = None,
) -> str:
    """simple depth 구현 루프. impl_simple.sh와 동일한 흐름.

    Returns:
        결과 문자열 (HARNESS_DONE, IMPLEMENTATION_ESCALATE, etc.)
    """
    issue_num = str(issue_num)
    depth = "simple"

    if not Path(impl_file).exists():
        print(f"[HARNESS] 오류: impl 파일을 찾을 수 없음: {impl_file}")
        return "ERROR"

    # Phase 0: setup
    constraints = load_constraints(config)
    hlog_fn = setup_hlog(state_dir, prefix)

    # harness_active 플래그
    state_dir.flag_touch(Flag.HARNESS_ACTIVE)
    # simple은 plan_validation 스킵
    if not state_dir.flag_exists(Flag.PLAN_VALIDATION_PASSED):
        state_dir.flag_touch(Flag.PLAN_VALIDATION_PASSED)

    # 로그 초기화
    if run_logger is None:
        run_logger = RunLogger(prefix, "impl", issue_num)

    # feature branch (worktree 격리 지원)
    use_wt = bool(config and config.isolation == "worktree")
    wt_mgr = WorktreeManager(state_dir.project_root, prefix) if use_wt else None
    feature_branch, wt_path = create_feature_branch(branch_type, issue_num, wt_mgr)
    work_cwd = str(wt_path) if wt_path else None
    agent_call = _bind_cwd(work_cwd)  # noqa: F841 — worktree cwd 자동 주입
    _orig_cwd = os.getcwd()
    if work_cwd:
        os.chdir(work_cwd)
        import atexit
        atexit.register(lambda oc=_orig_cwd: os.path.isdir(oc) and os.chdir(oc))
    os.environ["HARNESS_BRANCH"] = feature_branch
    hlog_fn(f"feature branch: {feature_branch}" + (f" (worktree: {wt_path})" if wt_path else ""))
    run_logger.log_event({
        "event": "branch_create",
        "branch": feature_branch,
        "worktree": str(wt_path) if wt_path else "",
        "t": int(time.time()),
    })

    MAX = 3
    MAX_SPEC_GAP = 2
    attempt = 0
    spec_gap_count = 0
    error_trace = ""
    fail_type = ""
    _fail_timestamps: Dict[str, List[float]] = {}

    hlog_fn(f"=== 하네스 루프 시작 (depth=simple, max_retries={MAX}) ===")

    # HUD 초기화 (외부 전달 시 set_depth로 확장, 없으면 자체 생성)
    if hud is not None:
        hud.set_depth(depth)
    else:
        hud = HUD(depth, prefix, issue_num, MAX, config.max_total_cost, state_dir)

    # 히스토리 디렉토리
    hist_dir = state_dir.path / f"{prefix}_history"
    run_ts = os.environ.get("HARNESS_RUN_TS", time.strftime("%Y%m%d_%H%M%S"))
    loop_out_dir = hist_dir / "impl" / f"run_{run_ts}"
    loop_out_dir.mkdir(parents=True, exist_ok=True)

    # config 이벤트
    run_logger.log_event({
        "event": "config",
        "impl_file": impl_file,
        "issue": issue_num,
        "depth": "simple",
        "max_retries": MAX,
        "constraints_chars": len(constraints),
    })

    while attempt < MAX:
        hlog_fn.set_attempt(attempt)
        kill_check(state_dir)

        # Circuit Breaker: 이전 루프에서 실패한 fail_type이 있으면 시간 윈도우 검사
        if fail_type and _circuit_breaker_check(fail_type, _fail_timestamps, hlog_fn, run_logger):
            state_dir.flag_rm(Flag.PLAN_VALIDATION_PASSED)
            os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
            hlog_fn("=== circuit breaker → IMPLEMENTATION_ESCALATE ===")
            print("IMPLEMENTATION_ESCALATE (circuit_breaker)")
            print(f"branch: {feature_branch}")
            record_escalate(state_dir, impl_file, fail_type)
            run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
            return "IMPLEMENTATION_ESCALATE"

        attempt_dir = loop_out_dir / f"attempt-{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        os.environ["HARNESS_HIST_DIR"] = str(attempt_dir)
        prune_history(str(loop_out_dir))

        # 컨텍스트 구성
        context = build_smart_context(impl_file, 0)
        if attempt == 0:
            task = "impl 파일의 구현 명세 전체 이행"
        else:
            prev_dir = loop_out_dir / f"attempt-{attempt - 1}"
            wt_prefix = (
                "[주의] 이전 attempt의 변경이 working tree에 남아있음. "
                "추가 수정으로 해결하라 (stash/reset 금지).\n"
            )
            if fail_type == "pr_fail":
                _pr_log = prev_dir / "pr.log"
                _pr_hint = ""
                if _pr_log.exists():
                    _pr_hint = _pr_log.read_text(encoding="utf-8")[:2000]
                task = (
                    f"[코드 품질] 시도 {attempt}회.\n"
                    f"이전 pr-reviewer 피드백:\n```\n{_pr_hint}\n```\n"
                    f"{explore_instruction(str(loop_out_dir))}\n"
                    "MUST FIX 항목만 수정하라. 기능 변경 금지."
                )
            elif fail_type == "autocheck_fail":
                _ac_log = prev_dir / "autocheck.log"
                _ac_hint = ""
                if _ac_log.exists():
                    _ac_hint = _ac_log.read_text(encoding="utf-8")[:1000]
                task = (
                    f"[자동 체크 실패] 시도 {attempt}회.\n"
                    f"이전 실패 원인:\n```\n{_ac_hint}\n```\n"
                    f"{explore_instruction(str(loop_out_dir))}\n"
                    "위 에러를 수정하라. 기능 변경 금지."
                )
            else:
                _fh = _extract_generic_fail_hint(prev_dir)
                task = (
                    f"[재시도] 시도 {attempt}회. fail_type={fail_type}\n"
                    + (f"{_fh}\n" if _fh else "")
                    + f"{explore_instruction(str(loop_out_dir))}"
                )
            task = wt_prefix + task

        run_logger.log_event({
            "event": "context",
            "chars": len(context),
            "attempt": attempt,
        })

        # ── validator → engineer 핸드오프 확인 ──────────────────
        _val_handoff_hint = ""
        if attempt == 0:
            _val_handoff_file = state_dir.path / f"{prefix}_handoffs" / "attempt-0" / "validator-to-engineer.md"
            if _val_handoff_file.exists():
                _val_handoff_hint = f"\n인수인계 문서: {_val_handoff_file}"

        # ── 워커 1: engineer ─────────────────────────────────────
        log_phase("engineer", run_logger, attempt)
        hlog_fn(f"engineer 시작 (depth=simple, timeout=900s)")
        kill_check(state_dir)
        hud.set_attempt(attempt)
        hud.agent_start("engineer")

        eng_out = str(state_dir.path / f"{prefix}_eng_out.txt")
        _eng_t0 = time.time()
        agent_exit = agent_call(
            "engineer", 900,
            f"impl: {impl_file}\nissue: #{issue_num}\ntask:\n{task}\n"
            f"context:\n{context}\nconstraints:\n{constraints}{_val_handoff_hint}",
            eng_out, run_logger, config, str(attempt_dir),
        )
        _eng_cost = float(Path(f"{eng_out[:-4]}_cost.txt").read_text() or "0") if Path(f"{eng_out[:-4]}_cost.txt").exists() else 0.0
        hud.agent_done("engineer", int(time.time() - _eng_t0), _eng_cost, "done" if agent_exit == 0 else "fail")
        hlog_fn(f"engineer 종료 (exit={agent_exit})")
        if agent_exit == 124:
            hlog_fn("engineer timeout")
        total_cost = budget_check("engineer", eng_out, 0, config.max_total_cost, state_dir, prefix, config=config)

        # engineer 출력 보존
        try:
            shutil.copy2(eng_out, str(attempt_dir / "engineer.log"))
        except OSError:
            pass

        if not check_agent_output("engineer", eng_out):
            fail_type = "autocheck_fail"
            error_trace = f"engineer agent produced no output (exit={agent_exit})"
            append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, fail_type, "engineer 출력 없음")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        # ── SPEC_GAP 감지 + depth 재판정 ────────────────────────
        eng_content = Path(eng_out).read_text(encoding="utf-8", errors="replace")
        if "SPEC_GAP_FOUND" in eng_content:
            spec_gap_count += 1
            hlog_fn(f"SPEC_GAP_FOUND (spec_gap_count={spec_gap_count}/{MAX_SPEC_GAP})")
            log_decision("spec_gap", str(spec_gap_count), "SPEC_GAP_FOUND in engineer output", run_logger, attempt)

            if spec_gap_count > MAX_SPEC_GAP:
                hlog_fn("SPEC_GAP 동결 초과 → IMPLEMENTATION_ESCALATE")
                os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
                print(f"IMPLEMENTATION_ESCALATE (spec_gap_count {spec_gap_count} > {MAX_SPEC_GAP})")
                print(f"branch: {feature_branch}")
                record_escalate(state_dir, impl_file, fail_type or "spec_gap_exceeded")
                run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
                return "IMPLEMENTATION_ESCALATE"

            # handoff: engineer → architect (SPEC_GAP)
            _sg_handoff = generate_handoff(
                "engineer", "architect", eng_content,
                impl_file, attempt, issue_num,
            )
            _sg_handoff_path = write_handoff(state_dir, prefix, attempt, "engineer", "architect-specgap", _sg_handoff)
            run_logger.log_event({
                "event": "handoff", "from": "engineer", "to": "architect-specgap",
                "t": int(time.time()),
            })

            # architect SPEC_GAP 처리
            log_phase("architect-spec-gap", run_logger, attempt)
            print("[HARNESS] SPEC_GAP → architect (depth 재판정 포함)")
            # SPEC_GAP_FOUND 마커 이후 ~ 끝까지 추출 (기존 50줄 하드캡 대신)
            _sg_idx = eng_content.find("SPEC_GAP_FOUND")
            if _sg_idx >= 0:
                spec_gap_context = eng_content[_sg_idx:][:3000]  # 3KB 캡
            else:
                spec_gap_context = "\n".join(eng_content.splitlines()[-50:])
            arch_out = str(state_dir.path / f"{prefix}_arch_sg_out.txt")
            agent_call(
                "architect", 900,
                f"@MODE:ARCHITECT:SPEC_GAP\n"
                f"engineer가 SPEC_GAP_FOUND 보고. impl: {impl_file} issue: #{issue_num}\n"
                f"인수인계 문서: {_sg_handoff_path}\n"
                f"현재 depth: simple\nengineer 보고:\n{spec_gap_context}\n"
                f"[지시] SPEC_GAP 해결 후 depth 재판정. frontmatter depth: 필드를 재선언하라. "
                f"상향만 허용(simple→std→deep).",
                arch_out, run_logger, config,
            )
            budget_check("architect", arch_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)

            sg_result = parse_marker(arch_out, "SPEC_GAP_RESOLVED|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")

            if sg_result == "SPEC_GAP_RESOLVED":
                new_depth = detect_depth(impl_file)
                if new_depth != "simple" and new_depth in ("std", "deep"):
                    hlog_fn(f"depth 상향: simple → {new_depth}. Python 함수로 직접 전환")
                    runner = run_std if new_depth == "std" else run_deep
                    return runner(impl_file, issue_num, config, state_dir, prefix, branch_type, run_logger, hud)
                hlog_fn("SPEC_GAP_RESOLVED → engineer 재시도 (depth=simple 유지, attempt 동결)")
                error_trace = ""
                fail_type = ""
                continue

            elif sg_result == "PRODUCT_PLANNER_ESCALATION_NEEDED":
                os.environ["HARNESS_RESULT"] = "PRODUCT_PLANNER_ESCALATION_NEEDED"
                print("PRODUCT_PLANNER_ESCALATION_NEEDED")
                print(f"branch: {feature_branch}")
                run_logger.write_run_end("PRODUCT_PLANNER_ESCALATION_NEEDED", feature_branch, issue_num)
                return "PRODUCT_PLANNER_ESCALATION_NEEDED"

            elif sg_result == "TECH_CONSTRAINT_CONFLICT":
                os.environ["HARNESS_RESULT"] = "TECH_CONSTRAINT_CONFLICT"
                print("TECH_CONSTRAINT_CONFLICT")
                print(f"branch: {feature_branch}")
                run_logger.write_run_end("TECH_CONSTRAINT_CONFLICT", feature_branch, issue_num)
                return "TECH_CONSTRAINT_CONFLICT"

            else:
                hlog_fn(f"architect SPEC_GAP 결과 불명확: {sg_result} → engineer 재시도")
                error_trace = ""
                fail_type = ""
                continue

        # ── automated_checks ──────────────────────────────────────
        # simple depth는 test-engineer/TDD GREEN 단계가 없으므로 회귀 테스트를 여기서 실행
        check_ok, check_err = run_automated_checks(
            impl_file, config, state_dir, prefix, cwd=work_cwd, run_tests=True,
        )
        if not check_ok:
            error_trace = check_err or "automated_checks FAIL"
            fail_type = "autocheck_fail"
            log_decision("fail_type", fail_type, "automated_checks failed", run_logger, attempt)
            append_failure(impl_file, "autocheck_fail", error_trace, state_dir, prefix)
            try:
                shutil.copy2(
                    str(state_dir.path / f"{prefix}_autocheck_fail.txt"),
                    str(attempt_dir / "autocheck.log"),
                )
            except OSError:
                pass
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, "autocheck_fail",
                           f"{attempt_dir}/autocheck.log 참조")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue
        print("[HARNESS] automated_checks PASS")

        # ── 즉시 커밋 ────────────────────────────────────────────
        changed = collect_changed_files(work_cwd)
        if changed:
            subprocess.run(["git", "add", "--"] + changed, capture_output=True, timeout=10)
            commit_suffix = ""
            if attempt > 0:
                commit_suffix = f" [attempt-{attempt}-fix]"
            msg = generate_commit_msg(impl_file, issue_num) + commit_suffix
            subprocess.run(["git", "commit", "-m", msg], capture_output=True, timeout=10)
            push_and_ensure_pr(feature_branch, issue_num, impl_file, "simple", state_dir, prefix, cwd=work_cwd)

            r = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            early_commit = r.stdout.strip() if r.returncode == 0 else "unknown"
            run_logger.log_event({
                "event": "commit",
                "hash": early_commit,
                "attempt": attempt + 1,
                "t": int(time.time()),
            })
            hlog_fn(f"early commit: {early_commit} (attempt={attempt + 1})")

        # ── Handoff: engineer → pr-reviewer ─────────────────────
        _eng_handoff_hint = ""
        try:
            _eng_content_for_ho = Path(eng_out).read_text(encoding="utf-8", errors="replace")
            _eng_ho = generate_handoff(
                "engineer", "pr-reviewer", _eng_content_for_ho,
                impl_file, attempt, issue_num,
                changed_files=changed if changed else None,
            )
            _eng_ho_path = write_handoff(state_dir, prefix, attempt, "engineer", "pr-reviewer", _eng_ho)
            _eng_handoff_hint = f"\n인수인계 문서: {_eng_ho_path}"
            run_logger.log_event({
                "event": "handoff", "from": "engineer", "to": "pr-reviewer",
                "t": int(time.time()),
            })
        except OSError:
            pass

        # ── 워커 2: pr-reviewer + second reviewer (병렬) ─────────
        log_phase("pr-reviewer", run_logger, attempt)
        hlog_fn("pr-reviewer 시작 (depth=simple, timeout=360s)")
        kill_check(state_dir)
        hud.agent_start("pr-reviewer")

        # diff 생성
        r = subprocess.run(
            ["git", "diff", "HEAD~1"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            r = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
        diff_out = "\n".join(r.stdout.splitlines()[:300])

        # src_files
        r_names = subprocess.run(
            ["git", "diff", "HEAD~1", "--name-only"],
            capture_output=True, text=True, timeout=5,
        )
        src_files = " ".join(r_names.stdout.strip().splitlines()) if r_names.returncode == 0 else ""

        # second reviewer v3: 파일별 분할 + threading 병렬
        import threading as _threading
        _second_result = [""]
        _second_thread = None
        if config.second_reviewer:
            _changed_for_2nd = [
                line.strip() for line in r_names.stdout.strip().splitlines()
                if line.strip()
            ] if r_names.returncode == 0 else []
            if _changed_for_2nd:
                def _bg_review():
                    _second_result[0] = run_review_batch(
                        _changed_for_2nd, config.second_reviewer, config.second_reviewer_model,
                    )
                _second_thread = _threading.Thread(target=_bg_review, daemon=True)
                _second_thread.start()
                hlog_fn(f"second reviewer v3 ({config.second_reviewer}) 파일별 병렬 시작 ({len(_changed_for_2nd)}개)")

        pr_out = str(state_dir.path / f"{prefix}_pr_out.txt")
        _pr_t0 = time.time()
        _prev_must_hint = _prev_must_fix_hint(loop_out_dir, attempt)
        agent_exit = agent_call(
            "pr-reviewer", 360,
            f'@MODE:PR_REVIEWER:REVIEW\n'
            f'@PARAMS: {{ "impl_path": "{impl_file}", "src_files": "{src_files}" }}\n'
            f"변경 diff:\n{diff_out}{_eng_handoff_hint}{_prev_must_hint}",
            pr_out, run_logger, config, str(attempt_dir),
        )
        _pr_cost = float(Path(f"{pr_out[:-4]}_cost.txt").read_text() or "0") if Path(f"{pr_out[:-4]}_cost.txt").exists() else 0.0
        hud.agent_done("pr-reviewer", int(time.time() - _pr_t0), _pr_cost, "done" if agent_exit == 0 else "fail")
        hlog_fn(f"pr-reviewer 종료 (exit={agent_exit})")
        if agent_exit == 124:
            hlog_fn("pr-reviewer timeout")
        total_cost = budget_check("pr-reviewer", pr_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)

        try:
            shutil.copy2(pr_out, str(attempt_dir / "pr.log"))
        except OSError:
            pass

        if not check_agent_output("pr-reviewer", pr_out):
            fail_type = "pr_fail"
            error_trace = f"pr-reviewer agent produced no output (exit={agent_exit})"
            append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        pr_result = parse_marker(pr_out, "LGTM|CHANGES_REQUESTED")
        hud.log(f"pr-reviewer → {pr_result or 'UNKNOWN'}")
        print(f"[HARNESS] pr-reviewer 결과: {pr_result}")

        if pr_result != "LGTM":
            fail_type = "pr_fail"
            log_decision("fail_type", fail_type, f"pr-reviewer result={pr_result}", run_logger, attempt)
            append_failure(impl_file, "pr_fail",
                           f"pr-reviewer CHANGES_REQUESTED (see {attempt_dir}/pr.log)",
                           state_dir, prefix)
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, "pr_fail",
                           f"{attempt_dir}/pr.log 의 MUST FIX 항목만 수정")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        # LGTM
        state_dir.flag_touch(Flag.PR_REVIEWER_LGTM)
        print("[HARNESS] LGTM")

        # second reviewer v3 결과 수집
        _second_findings = ""
        if _second_thread:
            _second_thread.join(timeout=300)
            _second_findings = _second_result[0]
            if _second_findings:
                hlog_fn(f"second reviewer v3 findings: {len(_second_findings)} chars")
                if run_logger:
                    run_logger.log_event({
                        "event": "second_review",
                        "reviewer": config.second_reviewer,
                        "findings_chars": len(_second_findings),
                        "t": int(time.time()),
                    })

        # ── POLISH: 코드 다듬기 (LGTM 후, merge 전) ──────────────
        polish_items = extract_polish_items(pr_out)
        if _second_findings:
            polish_items = (polish_items + f"\n\n[{config.second_reviewer} 리뷰]\n{_second_findings}").strip()
        if polish_items:
            hlog_fn("POLISH 항목 감지 — engineer POLISH 모드 실행")
            print("[HARNESS] POLISH: 코드 다듬기")
            _polish_out = str(state_dir.path / f"{prefix}_polish_out.txt")
            _pre_polish_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            agent_call(
                "engineer", 180,
                f"@MODE:ENGINEER:POLISH\n정리 항목:\n{polish_items}",
                _polish_out, run_logger, config,
            )
            # regression check (하네스 직접 실행, 에이전트 X)
            _reg_ok = True
            if config.lint_command:
                _polish_files = collect_changed_files(work_cwd)
                _lintable = [f for f in _polish_files if any(f.endswith(e) for e in ('.ts','.tsx','.js','.jsx','.mjs','.cjs'))]
                _lint_cmd = f"{config.lint_command} {' '.join(_lintable)}" if _lintable else config.lint_command
                _lint_r = subprocess.run(
                    _lint_cmd, shell=True, capture_output=True, timeout=60,
                )
                if _lint_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: lint ({_lint_cmd})")
            if _reg_ok and config.build_command:
                _build_r = subprocess.run(
                    config.build_command, shell=True, capture_output=True, timeout=120,
                )
                if _build_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: build ({config.build_command})")
            if _reg_ok and config.test_command:
                _test_r = subprocess.run(
                    config.test_command, shell=True, capture_output=True, timeout=300,
                )
                if _test_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: test ({config.test_command})")
            if not _reg_ok:
                hlog_fn("POLISH revert — 변경 파일만 선택적 복원")
                print("[HARNESS] POLISH regression 실패 — 변경 파일만 복원")
                _polish_changed = collect_changed_files(work_cwd)
                if _polish_changed:
                    subprocess.run(
                        ["git", "checkout", _pre_polish_hash, "--"] + _polish_changed,
                        capture_output=True, timeout=10,
                    )
                    subprocess.run(["git", "add", "--"] + _polish_changed, capture_output=True, timeout=10)
                    subprocess.run(
                        ["git", "commit", "-m", f"revert: polish regression (#{issue_num})"],
                        capture_output=True, timeout=10,
                    )
                    hlog_fn(f"POLISH revert 커밋 ({len(_polish_changed)} files)")
                    push_and_ensure_pr(feature_branch, issue_num, impl_file, "simple", state_dir, prefix, cwd=work_cwd)
            else:
                # polish 변경 커밋
                _changed = collect_changed_files(work_cwd)
                if _changed:
                    subprocess.run(["git", "add", "--"] + _changed, capture_output=True, timeout=10)
                    subprocess.run(
                        ["git", "commit", "-m", f"polish: code cleanup (#{issue_num})"],
                        capture_output=True, timeout=10,
                    )
                    hlog_fn("POLISH 커밋 완료")
                    push_and_ensure_pr(feature_branch, issue_num, impl_file, "simple", state_dir, prefix, cwd=work_cwd)
                print("[HARNESS] POLISH 완료")
        else:
            hlog_fn("POLISH 항목 없음 — 스킵")

        # simple: test-engineer, validator, security-reviewer 스킵
        state_dir.flag_touch(Flag.TEST_ENGINEER_PASSED)
        state_dir.flag_touch(Flag.VALIDATOR_B_PASSED)
        state_dir.flag_touch(Flag.SECURITY_REVIEW_PASSED)
        hlog_fn("test-engineer, validator, security-reviewer 스킵 (depth=simple)")

        # ── merge to main ─────────────────────────────────────────
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        impl_commit = r.stdout.strip() if r.returncode == 0 else "unknown"

        # merge는 메인 repo에서 실행해야 함 — worktree cwd 복원
        if work_cwd:
            os.chdir(_orig_cwd)
        if not merge_to_main(feature_branch, issue_num, "simple", prefix, state_dir, wt_mgr):
            os.environ["HARNESS_RESULT"] = "MERGE_CONFLICT_ESCALATE"
            print("MERGE_CONFLICT_ESCALATE")
            print(f"branch: {feature_branch}")
            print(f"impl_commit: {impl_commit}")
            hlog_fn("=== merge conflict ===")
            run_logger.write_run_end("MERGE_CONFLICT_ESCALATE", feature_branch, issue_num)
            return "MERGE_CONFLICT_ESCALATE"

        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        merge_commit = r.stdout.strip() if r.returncode == 0 else "unknown"
        run_logger.log_event({
            "event": "branch_merge",
            "branch": feature_branch,
            "impl_commit": impl_commit,
            "merge_commit": merge_commit,
            "t": int(time.time()),
        })

        # PR body, success, meta
        pr_body_file = state_dir.path / f"{prefix}_pr_body.txt"
        try:
            pr_body_file.write_text(
                generate_pr_body(impl_file, issue_num, attempt + 1, MAX, state_dir, prefix),
                encoding="utf-8",
            )
        except OSError:
            pass

        append_success(impl_file, attempt + 1, eng_out=eng_out, attempt_dir=str(attempt_dir))
        save_impl_meta(attempt_dir, attempt, "PASS", depth, hints="구현 완료")
        (state_dir.path / f"{prefix}_last_issue").write_text(issue_num, encoding="utf-8")

        hud.agent_done("merge", 0, 0.0, "done")
        hud.log(f"HARNESS_DONE (attempt {attempt + 1})")
        hud.cleanup()
        os.environ["HARNESS_RESULT"] = "HARNESS_DONE"
        hlog_fn(f"=== 루프 종료 (HARNESS_DONE, attempt={attempt + 1}) ===")
        print("HARNESS_DONE")
        print(f"impl: {impl_file}")
        print(f"issue: #{issue_num}")
        print(f"attempts: {attempt + 1}")
        print(f"commit: {merge_commit}")
        print(f"pr_body: {pr_body_file}")

        # memory candidate 출력
        candidate_file = state_dir.path / f"{prefix}_memory_candidate.md"
        if candidate_file.exists():
            print()
            print("[HARNESS MEMORY] 이번 루프에서 실패 패턴이 감지됐습니다.")
            print(f"   파일: {candidate_file}")
            print(candidate_file.read_text(encoding="utf-8"))
            print()
            print(f"memory_candidate: {candidate_file}")

        run_logger.write_run_end("HARNESS_DONE", feature_branch, issue_num)
        return "HARNESS_DONE"

    # ── MAX 초과 → ESCALATE ─────────────────────────────────────
    state_dir.flag_rm(Flag.PLAN_VALIDATION_PASSED)
    os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
    hlog_fn(f"=== 루프 종료 (IMPLEMENTATION_ESCALATE, attempt={MAX}) ===")
    print("IMPLEMENTATION_ESCALATE")
    print(f"attempts: {MAX}")
    print(f"spec_gap_count: {spec_gap_count}")
    print(f"branch: {feature_branch}")
    print("마지막 에러:")
    if error_trace:
        for line in error_trace.splitlines()[:20]:
            print(line)

    record_escalate(state_dir, impl_file, fail_type or "max_attempts")
    run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
    return "IMPLEMENTATION_ESCALATE"


# ═══════════════════════════════════════════════════════════════════════
# 3. _run_std_deep — std/deep 공통 내부 함수
# ═══════════════════════════════════════════════════════════════════════

def _run_std_deep(
    impl_file: str,
    issue_num: str | int,
    config: HarnessConfig,
    state_dir: StateDir,
    prefix: str,
    depth: str,  # "std" or "deep"
    branch_type: str = "feat",
    run_logger: Optional[RunLogger] = None,
    hud: Optional[HUD] = None,
) -> str:
    """std/deep depth 공통 구현 루프.

    std와 deep의 차이:
    - deep: pr-reviewer LGTM 후 security-reviewer 추가
    - std: SPEC_GAP에서 deep으로 상향 가능
    - deep: SPEC_GAP에서 상향 없음 (최고 depth)
    """
    issue_num = str(issue_num)

    if not Path(impl_file).exists():
        print(f"[HARNESS] 오류: impl 파일을 찾을 수 없음: {impl_file}")
        return "ERROR"

    constraints = load_constraints(config)
    hlog_fn = setup_hlog(state_dir, prefix)

    state_dir.flag_touch(Flag.HARNESS_ACTIVE)
    if not state_dir.flag_exists(Flag.PLAN_VALIDATION_PASSED):
        state_dir.flag_touch(Flag.PLAN_VALIDATION_PASSED)

    if run_logger is None:
        run_logger = RunLogger(prefix, "impl", issue_num)

    use_wt = bool(config and config.isolation == "worktree")
    wt_mgr = WorktreeManager(state_dir.project_root, prefix) if use_wt else None
    feature_branch, wt_path = create_feature_branch(branch_type, issue_num, wt_mgr)
    work_cwd = str(wt_path) if wt_path else None
    agent_call = _bind_cwd(work_cwd)  # noqa: F841 — worktree cwd 자동 주입
    _orig_cwd = os.getcwd()
    if work_cwd:
        os.chdir(work_cwd)
        import atexit
        atexit.register(lambda oc=_orig_cwd: os.path.isdir(oc) and os.chdir(oc))
    os.environ["HARNESS_BRANCH"] = feature_branch
    hlog_fn(f"feature branch: {feature_branch}" + (f" (worktree: {wt_path})" if wt_path else ""))
    run_logger.log_event({"event": "branch_create", "branch": feature_branch, "worktree": str(wt_path) if wt_path else "", "t": int(time.time())})

    MAX = 3
    MAX_SPEC_GAP = 2
    attempt = 0
    spec_gap_count = 0
    error_trace = ""
    fail_type = ""
    _fail_timestamps: Dict[str, List[float]] = {}

    total_cost = 0.0
    hlog_fn(f"=== 하네스 루프 시작 (depth={depth}, max_retries={MAX}) ===")

    # HUD 초기화 (외부 전달 시 set_depth로 확장, 없으면 자체 생성)
    if hud is not None:
        hud.set_depth(depth)
    else:
        hud = HUD(depth, prefix, issue_num, MAX, config.max_total_cost, state_dir)

    hist_dir = state_dir.path / f"{prefix}_history"
    run_ts = os.environ.get("HARNESS_RUN_TS", time.strftime("%Y%m%d_%H%M%S"))
    loop_out_dir = hist_dir / "impl" / f"run_{run_ts}"
    loop_out_dir.mkdir(parents=True, exist_ok=True)

    run_logger.log_event({
        "event": "config", "impl_file": impl_file, "issue": issue_num,
        "depth": depth, "max_retries": MAX, "constraints_chars": len(constraints),
    })

    _tdd_test_files = ""  # TDD 테스트 파일 경로 (attempt 0에서 설정, 이후 유지)

    while attempt < MAX:
        hlog_fn.set_attempt(attempt)
        kill_check(state_dir)

        # Circuit Breaker: 이전 루프에서 실패한 fail_type이 있으면 시간 윈도우 검사
        if fail_type and _circuit_breaker_check(fail_type, _fail_timestamps, hlog_fn, run_logger):
            state_dir.flag_rm(Flag.PLAN_VALIDATION_PASSED)
            os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
            hlog_fn("=== circuit breaker → IMPLEMENTATION_ESCALATE ===")
            print("IMPLEMENTATION_ESCALATE (circuit_breaker)")
            print(f"branch: {feature_branch}")
            record_escalate(state_dir, impl_file, fail_type)
            run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
            return "IMPLEMENTATION_ESCALATE"

        attempt_dir = loop_out_dir / f"attempt-{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        os.environ["HARNESS_HIST_DIR"] = str(attempt_dir)
        prune_history(str(loop_out_dir))

        # ── TDD Phase: test-engineer 선행 (attempt 0 + test_command + std/deep) ──
        _tdd_active = (attempt == 0 and bool(config.test_command) and depth in ("std", "deep"))
        if _tdd_active:
            log_phase("test-engineer-tdd", run_logger, attempt)
            hlog_fn(f"test-engineer TDD 시작 (attempt=0, depth={depth})")
            hud.agent_start("test-engineer")
            kill_check(state_dir)

            te_tdd_out = str(state_dir.path / f"{prefix}_te_tdd_out.txt")
            te_tdd_prompt = (
                f"@MODE:TEST_ENGINEER:TDD\n"
                f'@PARAMS: {{ "impl_path": "{impl_file}" }}\n\n'
                f"[지시] impl의 인터페이스 정의 + 수용 기준(TEST)에서 테스트 작성. 코드 없이 impl만 참조.\n"
                f"issue: #{issue_num}"
            )
            _te_tdd_t0 = time.time()
            te_tdd_exit = agent_call("test-engineer", 900, te_tdd_prompt, te_tdd_out, run_logger, config, str(attempt_dir))
            _te_tdd_cost = 0.0
            try:
                _te_cost_file = Path(str(te_tdd_out).replace(".txt", "_cost.txt"))
                _te_tdd_cost = float(_te_cost_file.read_text() or "0") if _te_cost_file.exists() else 0.0
            except (ValueError, OSError):
                pass
            hud.agent_done("test-engineer", int(time.time() - _te_tdd_t0), _te_tdd_cost)
            hlog_fn(f"test-engineer TDD 종료 (exit={te_tdd_exit})")
            total_cost = budget_check("test-engineer", te_tdd_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)

            te_tdd_marker = parse_marker(te_tdd_out, "TESTS_WRITTEN")
            if te_tdd_marker == "TESTS_WRITTEN":
                hlog_fn("TESTS_WRITTEN 확인")
                print("[HARNESS] test-engineer TDD -> TESTS_WRITTEN")
                try:
                    _te_content = Path(te_tdd_out).read_text(encoding="utf-8", errors="replace")
                    _tdd_test_files = " ".join(
                        m.group(0) for m in re.finditer(r"src/[^ ]+\.(?:test|spec)\.[jt]sx?", _te_content)
                    )
                except OSError:
                    pass
            else:
                hlog_fn(f"test-engineer TDD 마커 없음 ({te_tdd_marker}) -- 테스트 없이 진행")
                print(f"[HARNESS] test-engineer TDD -> {te_tdd_marker} (TESTS_WRITTEN 아님)")

            # RED 확인 (정보성, attempt 미소진)
            if _tdd_test_files and config.test_command:
                import shlex as _shlex_red
                try:
                    red_result = subprocess.run(
                        _shlex_red.split(config.test_command),
                        capture_output=True, text=True, timeout=120,
                    )
                    if red_result.returncode == 0:
                        print("[HARNESS] 경고: 테스트가 코드 없이 통과 -- trivially true 의심")
                        hlog_fn("RED: trivially true")
                    else:
                        print(f"[HARNESS] RED 확인 OK (exit={red_result.returncode})")
                        hlog_fn(f"RED OK (exit={red_result.returncode})")
                except (subprocess.TimeoutExpired, OSError) as e:
                    hlog_fn(f"RED 확인 실패: {e}")

            # handoff: test-engineer -> engineer
            try:
                _te_output = Path(te_tdd_out).read_text(encoding="utf-8", errors="replace") if Path(te_tdd_out).exists() else ""
                _te_ho = generate_handoff(
                    "test-engineer", "engineer", _te_output,
                    impl_file, attempt, issue_num,
                )
                write_handoff(state_dir, prefix, attempt, "test-engineer", "engineer", _te_ho)
                run_logger.log_event({"event": "handoff", "from": "test-engineer", "to": "engineer", "t": int(time.time())})
            except Exception:
                pass
        elif attempt > 0 and depth in ("std", "deep"):
            hud.agent_skip("test-engineer", f"attempt {attempt} -- 테스트 이미 작성됨")
            hlog_fn(f"test-engineer 스킵 (attempt {attempt})")

        context = build_smart_context(impl_file, 0)
        if attempt == 0:
            _tdd_hint = ""
            if _tdd_test_files:
                _tdd_hint = f"\n\n[TDD] 테스트 파일: {_tdd_test_files}\n이 테스트를 통과시켜라. commit 전 Bash로 테스트 실행해서 통과 확인하라."
            task = f"impl 파일의 구현 명세 전체 이행{_tdd_hint}"
        else:
            prev_dir = loop_out_dir / f"attempt-{attempt - 1}"
            wt_prefix = (
                "[주의] 이전 attempt의 변경이 working tree에 남아있음. "
                "추가 수정으로 해결하라 (stash/reset 금지).\n"
            )
            # 이전 pr-reviewer 피드백을 프롬프트에 인라인 주입 (경로만 알려주면
            # engineer가 Read로 직접 가져와야 하는데 실제 런에서 자주 놓치고 동일
            # 수정을 복붙하는 버그 관찰 — run_20260419_201311 재현).
            _pr_log = prev_dir / "pr.log"
            _pr_hint = _pr_log.read_text(encoding="utf-8")[:2000] if _pr_log.exists() else ""

            task_map = {
                "autocheck_fail": (
                    f"[사전 검사 실패] 시도 {attempt}회.\n"
                    f"{explore_instruction(str(loop_out_dir), str(prev_dir / 'autocheck.log'))}\n"
                    "위 문제를 해결한 뒤 다시 구현하라."
                ),
                "test_fail": (
                    f"[테스트 실패] 시도 {attempt}회.\n"
                    f"{explore_instruction(str(loop_out_dir), str(prev_dir / 'test-results.log'))}\n"
                    f"{'테스트 파일: ' + _tdd_test_files + chr(10) if _tdd_test_files else ''}"
                    "구현 코드를 수정하라. 테스트 코드 자체는 수정 금지. commit 전 자체 vitest 실행."
                ),
                "validator_fail": (
                    f"[스펙 불일치] 시도 {attempt}회.\n"
                    f"{explore_instruction(str(loop_out_dir), str(prev_dir / 'validator.log'))}\n"
                    "impl 파일의 해당 항목을 다시 확인하고 누락된 부분을 구현하라."
                ),
                "pr_fail": (
                    f"[코드 품질] 시도 {attempt}회.\n"
                    f"이전 pr-reviewer 피드백:\n```\n{_pr_hint}\n```\n"
                    f"{explore_instruction(str(loop_out_dir))}\n"
                    "MUST FIX 항목만 수정하라. 기능 변경 금지."
                ),
            }
            _fh_generic = _extract_generic_fail_hint(prev_dir)
            _default_task = (
                f"[재시도] 시도 {attempt}회. fail_type={fail_type}\n"
                + (f"{_fh_generic}\n" if _fh_generic else "")
                + f"{explore_instruction(str(loop_out_dir))}"
            )
            task = task_map.get(fail_type, _default_task)
            task = wt_prefix + task

        run_logger.log_event({"event": "context", "chars": len(context), "attempt": attempt})

        # ── 워커 1: engineer ────────────────────────────────────────
        log_phase("engineer", run_logger, attempt)
        hlog_fn(f"engineer 시작 (depth={depth}, timeout=900s)")
        kill_check(state_dir)
        hud.set_attempt(attempt)
        hud.agent_start("engineer")

        eng_out = str(state_dir.path / f"{prefix}_eng_out.txt")
        _eng_t0 = time.time()
        agent_exit = agent_call(
            "engineer", 900,
            f"impl: {impl_file}\nissue: #{issue_num}\ntask:\n{task}\n"
            f"context:\n{context}\nconstraints:\n{constraints}",
            eng_out, run_logger, config, str(attempt_dir),
        )
        _eng_cost = float(Path(f"{eng_out[:-4]}_cost.txt").read_text() or "0") if Path(f"{eng_out[:-4]}_cost.txt").exists() else 0.0
        hud.agent_done("engineer", int(time.time() - _eng_t0), _eng_cost, "done" if agent_exit == 0 else "fail")
        hlog_fn(f"engineer 종료 (exit={agent_exit})")
        if agent_exit == 124:
            hlog_fn("engineer timeout")
        total_cost = budget_check("engineer", eng_out, 0, config.max_total_cost, state_dir, prefix, config=config)
        try:
            shutil.copy2(eng_out, str(attempt_dir / "engineer.log"))
        except OSError:
            pass

        if not check_agent_output("engineer", eng_out):
            fail_type = "autocheck_fail"
            error_trace = f"engineer agent produced no output (exit={agent_exit})"
            append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, fail_type, "engineer 출력 없음")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        # ── SPEC_GAP 감지 ──────────────────────────────────────────
        eng_content = Path(eng_out).read_text(encoding="utf-8", errors="replace")
        if "SPEC_GAP_FOUND" in eng_content:
            spec_gap_count += 1
            hlog_fn(f"SPEC_GAP_FOUND (spec_gap_count={spec_gap_count}/{MAX_SPEC_GAP})")
            log_decision("spec_gap", str(spec_gap_count), "SPEC_GAP_FOUND in engineer output", run_logger, attempt)

            if spec_gap_count > MAX_SPEC_GAP:
                hlog_fn("SPEC_GAP 동결 초과 → IMPLEMENTATION_ESCALATE")
                os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
                print(f"IMPLEMENTATION_ESCALATE (spec_gap_count {spec_gap_count} > {MAX_SPEC_GAP})")
                print(f"branch: {feature_branch}")
                record_escalate(state_dir, impl_file, fail_type or "spec_gap_exceeded")
                run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
                return "IMPLEMENTATION_ESCALATE"

            # handoff: engineer → architect (SPEC_GAP) — std/deep
            _sg_handoff2 = generate_handoff(
                "engineer", "architect", eng_content,
                impl_file, attempt, issue_num,
            )
            _sg_handoff_path2 = write_handoff(state_dir, prefix, attempt, "engineer", "architect-specgap", _sg_handoff2)

            log_phase("architect-spec-gap", run_logger, attempt)
            print("[HARNESS] SPEC_GAP → architect (depth 재판정 포함)")
            _sg_idx2 = eng_content.find("SPEC_GAP_FOUND")
            if _sg_idx2 >= 0:
                spec_gap_ctx = eng_content[_sg_idx2:][:3000]
            else:
                spec_gap_ctx = "\n".join(eng_content.splitlines()[-50:])

            if depth == "deep":
                sg_prompt = (
                    f"@MODE:ARCHITECT:SPEC_GAP\n"
                    f"engineer가 SPEC_GAP_FOUND 보고. impl: {impl_file} issue: #{issue_num}\n"
                    f"인수인계 문서: {_sg_handoff_path2}\n"
                    f"현재 depth: deep (최고 depth — 하향 없음)\n"
                    f"engineer 보고:\n{spec_gap_ctx}\n"
                    f"[지시] SPEC_GAP 해결. depth는 이미 deep이므로 재판정 불필요."
                )
            else:
                sg_prompt = (
                    f"@MODE:ARCHITECT:SPEC_GAP\n"
                    f"engineer가 SPEC_GAP_FOUND 보고. impl: {impl_file} issue: #{issue_num}\n"
                    f"현재 depth: {depth}\nengineer 보고:\n{spec_gap_ctx}\n"
                    f"[지시] SPEC_GAP 해결 후 depth 재판정. frontmatter depth: 필드를 재선언하라. "
                    f"상향만 허용(simple→std→deep)."
                )

            arch_out = str(state_dir.path / f"{prefix}_arch_sg_out.txt")
            agent_call("architect", 900, sg_prompt, arch_out, run_logger, config)
            budget_check("architect", arch_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)

            sg_result = parse_marker(arch_out, "SPEC_GAP_RESOLVED|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")

            if sg_result == "SPEC_GAP_RESOLVED":
                if depth == "std":
                    new_depth = detect_depth(impl_file)
                    if new_depth == "deep":
                        hlog_fn("depth 상향: std → deep. Python 함수로 직접 전환")
                        return run_deep(impl_file, issue_num, config, state_dir, prefix, branch_type, run_logger)
                hlog_fn(f"SPEC_GAP_RESOLVED → engineer 재시도 (depth={depth} 유지, attempt 동결)")
                error_trace = ""
                fail_type = ""
                continue
            elif sg_result == "PRODUCT_PLANNER_ESCALATION_NEEDED":
                os.environ["HARNESS_RESULT"] = "PRODUCT_PLANNER_ESCALATION_NEEDED"
                print("PRODUCT_PLANNER_ESCALATION_NEEDED")
                print(f"branch: {feature_branch}")
                run_logger.write_run_end("PRODUCT_PLANNER_ESCALATION_NEEDED", feature_branch, issue_num)
                return "PRODUCT_PLANNER_ESCALATION_NEEDED"
            elif sg_result == "TECH_CONSTRAINT_CONFLICT":
                os.environ["HARNESS_RESULT"] = "TECH_CONSTRAINT_CONFLICT"
                print("TECH_CONSTRAINT_CONFLICT")
                print(f"branch: {feature_branch}")
                run_logger.write_run_end("TECH_CONSTRAINT_CONFLICT", feature_branch, issue_num)
                return "TECH_CONSTRAINT_CONFLICT"
            else:
                hlog_fn(f"architect SPEC_GAP 결과 불명확: {sg_result} → engineer 재시도")
                error_trace = ""
                fail_type = ""
                continue

        # ── automated_checks ──────────────────────────────────────
        check_ok, check_err = run_automated_checks(impl_file, config, state_dir, prefix, cwd=work_cwd)
        if not check_ok:
            error_trace = check_err or "automated_checks FAIL"
            fail_type = "autocheck_fail"
            log_decision("fail_type", fail_type, "automated_checks failed", run_logger, attempt)
            append_failure(impl_file, "autocheck_fail", error_trace, state_dir, prefix)
            try:
                shutil.copy2(str(state_dir.path / f"{prefix}_autocheck_fail.txt"), str(attempt_dir / "autocheck.log"))
            except OSError:
                pass
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, "autocheck_fail", f"{attempt_dir}/autocheck.log 참조")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue
        print("[HARNESS] automated_checks PASS")

        # ── 즉시 커밋 ────────────────────────────────────────────
        changed = collect_changed_files(work_cwd)
        if changed:
            subprocess.run(["git", "add", "--"] + changed, capture_output=True, timeout=10)
            commit_suffix = ""
            if attempt > 0:
                commit_suffix = f" [attempt-{attempt}-fix]"
            msg = generate_commit_msg(impl_file, issue_num) + commit_suffix
            subprocess.run(["git", "commit", "-m", msg], capture_output=True, timeout=10)
            push_and_ensure_pr(feature_branch, issue_num, impl_file, depth, state_dir, prefix, cwd=work_cwd)
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
            early_commit = r.stdout.strip() if r.returncode == 0 else "unknown"
            run_logger.log_event({"event": "commit", "hash": early_commit, "attempt": attempt + 1, "t": int(time.time())})
            hlog_fn(f"early commit: {early_commit} (attempt={attempt + 1})")

        # ── TDD 여부에 따라 test-engineer 처리 분기 ─────────────────
        if _tdd_active or (attempt > 0 and depth in ("std", "deep")):
            # TDD: test-engineer 이미 완료 (attempt 0) 또는 스킵 (attempt 1+)
            # → 바로 vitest GREEN 확인으로 진행
            hlog_fn("test-engineer 스킵 (TDD: 이미 완료 or attempt 1+)")
        elif not config.test_command:
            # test_command 미설정 시 기존 순서 폴백 (engineer → test-engineer)
            _eng_output = ""
            try:
                _eng_output = Path(str(state_dir.path / f"{prefix}_eng_out.txt")).read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            _handoff_content = generate_handoff(
                "engineer", "test-engineer", _eng_output,
                impl_file, attempt, issue_num,
                acceptance_criteria=extract_acceptance_criteria(impl_file),
            )
            _handoff_path = write_handoff(state_dir, prefix, attempt, "engineer", "test-engineer", _handoff_content)
            run_logger.log_event({
                "event": "handoff", "from": "engineer", "to": "test-engineer",
                "t": int(time.time()),
            })

            r_changed = subprocess.run(["git", "diff", "HEAD~1", "--name-only"], capture_output=True, text=True, timeout=5)
            if r_changed.returncode != 0:
                r_changed = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5)
                changed_files_str = " ".join(
                    line.split(None, 1)[1] for line in r_changed.stdout.splitlines()
                    if re.match(r"^ M|^M |^A ", line)
                )
            else:
                changed_files_str = " ".join(r_changed.stdout.strip().splitlines())

            log_phase("test-engineer", run_logger, attempt)
            hlog_fn(f"test-engineer 시작 (depth={depth}, timeout=900s)")
            kill_check(state_dir)
            hud.agent_start("test-engineer")

            _te_handoff_hint = f"\n인수인계 문서: {_handoff_path}" if _handoff_path else ""
            # test_command 없는 폴백: TDD 모드로 호출하되 실행 금지 지시
            te_prompt = (
                f"@MODE:TEST_ENGINEER:TDD\n"
                f'@PARAMS: {{ "impl_path": "{impl_file}" }}\n\n'
                f"[지시] impl + 구현 코드 기반으로 테스트 작성. 테스트 실행은 하지 마라 (test_command 미설정).\n"
                f"수정된 파일: {changed_files_str}\n"
                f"issue: #{issue_num}"
                f"{_te_handoff_hint}"
            )

            # fallback: test-engineer 호출 (test_command 없을 때)
            te_out = str(state_dir.path / f"{prefix}_te_out.txt")
            agent_exit = agent_call("test-engineer", 900, te_prompt, te_out, run_logger, config, str(attempt_dir))
            hlog_fn(f"test-engineer 종료 (exit={agent_exit})")
            total_cost = budget_check("test-engineer", te_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)

            if not check_agent_output("test-engineer", te_out):
                fail_type = "test_fail"
                error_trace = f"test-engineer agent produced no output (exit={agent_exit})"
                append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
                rollback_attempt(attempt, run_logger)
                attempt += 1
                continue

            # test_command 없으므로 마커 기반 판정
            te_marker = parse_marker(te_out, "TESTS_PASS|TESTS_FAIL|TESTS_WRITTEN")
            if te_marker == "TESTS_FAIL":
                fail_type = "test_fail"
                te_content = Path(te_out).read_text(encoding="utf-8", errors="replace")
                log_decision("fail_type", fail_type, "test-engineer reported TESTS_FAIL", run_logger, attempt)
                append_failure(impl_file, "test_fail", te_content, state_dir, prefix)
                rollback_attempt(attempt, run_logger)
                attempt += 1
                continue
            state_dir.flag_touch(Flag.TEST_ENGINEER_PASSED)
            hud.agent_done("test-engineer", 0, 0.0)
            print("[HARNESS] test-engineer PASS (fallback)")

        # ── GREEN 확인 (vitest run) ───────────────────────────────
        import shlex as _shlex
        if config.test_command:
            test_cmd_parts = _shlex.split(config.test_command)
            print(f"[HARNESS] GREEN 테스트: {config.test_command} (attempt {attempt + 1}/{MAX})")
            hlog_fn(f"GREEN 테스트 시작: {config.test_command}")
            kill_check(state_dir)
            test_result = subprocess.run(
                test_cmd_parts,
                capture_output=True, text=True, timeout=300,
            )
            test_out_file = state_dir.path / f"{prefix}_test_out.txt"
            test_out_file.write_text(test_result.stdout + test_result.stderr, encoding="utf-8")
            hlog_fn(f"GREEN 테스트 종료 (exit={test_result.returncode})")

            if test_result.returncode != 0:
                print("[HARNESS] TESTS_FAIL (GREEN)")
                error_trace = test_out_file.read_text(encoding="utf-8")
                fail_type = "test_fail"
                log_decision("fail_type", fail_type, f"test exit={test_result.returncode}", run_logger, attempt)
                append_failure(impl_file, "test_fail", error_trace, state_dir, prefix)
                try:
                    shutil.copy2(str(test_out_file), str(attempt_dir / "test-results.log"))
                except OSError:
                    pass
                save_impl_meta(attempt_dir, attempt, "FAIL", depth, "test_fail",
                               f"{attempt_dir}/test-results.log 의 실패 케이스 확인")
                rollback_attempt(attempt, run_logger)
                attempt += 1
                continue
            state_dir.flag_touch(Flag.TEST_ENGINEER_PASSED)
            print("[HARNESS] GREEN PASS")

        # ── 워커 3: validator ─────────────────────────────────────
        log_phase("validator", run_logger, attempt)
        hlog_fn(f"validator 시작 (depth={depth}, timeout=300s)")
        hud.agent_start("validator")
        kill_check(state_dir)
        val_context = build_validator_context(impl_file)
        # engineer → validator handoff
        _eng_val_hint = ""
        try:
            _ev_content = Path(eng_out).read_text(encoding="utf-8", errors="replace")
            _ev_ho = generate_handoff("engineer", "validator", _ev_content, impl_file, attempt, issue_num)
            _ev_ho_path = write_handoff(state_dir, prefix, attempt, "engineer", "validator", _ev_ho)
            _eng_val_hint = f"\n인수인계 문서: {_ev_ho_path}"
            run_logger.log_event({"event": "handoff", "from": "engineer", "to": "validator", "t": int(time.time())})
        except OSError:
            pass

        val_out = str(state_dir.path / f"{prefix}_val_out.txt")
        agent_exit = agent_call(
            "validator", 300,
            f"@MODE:VALIDATOR:CODE_VALIDATION\nimpl: {impl_file}\ncontext:\n{val_context}{_eng_val_hint}",
            val_out, run_logger, config, str(attempt_dir),
        )
        hlog_fn(f"validator 종료 (exit={agent_exit})")
        if agent_exit == 124:
            hlog_fn("validator timeout")
        total_cost = budget_check("validator", val_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)
        try:
            shutil.copy2(val_out, str(attempt_dir / "validator.log"))
        except OSError:
            pass

        if not check_agent_output("validator", val_out):
            fail_type = "validator_fail"
            error_trace = f"validator agent produced no output (exit={agent_exit})"
            append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        val_result = parse_marker(val_out, "PASS|FAIL|SPEC_MISSING")
        print(f"[HARNESS] validator 결과: {val_result}")

        if val_result == "SPEC_MISSING":
            hlog_fn("SPEC_MISSING → architect MODULE_PLAN 복구")
            arch_sm_out = str(state_dir.path / f"{prefix}_arch_sm_out.txt")
            agent_call(
                "architect", 900,
                f"@MODE:ARCHITECT:MODULE_PLAN\nSPEC_MISSING 복구. impl: {impl_file} issue: #{issue_num}",
                arch_sm_out, run_logger, config,
            )
            budget_check("architect", arch_sm_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)
            fail_type = "validator_fail"
            error_trace = "SPEC_MISSING: impl 파일 복구 후 재시도"
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        if val_result != "PASS":
            fail_type = "validator_fail"
            log_decision("fail_type", fail_type, f"validator result={val_result}", run_logger, attempt)
            append_failure(impl_file, "validator_fail", f"validator FAIL (see {attempt_dir}/validator.log)", state_dir, prefix)
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, "validator_fail",
                           f"{attempt_dir}/validator.log 의 FAIL 항목 확인")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue
        state_dir.flag_touch(Flag.VALIDATOR_B_PASSED)

        # ── Handoff: engineer → pr-reviewer (std/deep) ─────────
        _eng_handoff_hint_sd = ""
        try:
            _eng_content_sd = Path(eng_out).read_text(encoding="utf-8", errors="replace")
            _eng_ho_sd = generate_handoff(
                "engineer", "pr-reviewer", _eng_content_sd,
                impl_file, attempt, issue_num,
                changed_files=changed if changed else None,
            )
            _eng_ho_path_sd = write_handoff(state_dir, prefix, attempt, "engineer", "pr-reviewer", _eng_ho_sd)
            _eng_handoff_hint_sd = f"\n인수인계 문서: {_eng_ho_path_sd}"
            run_logger.log_event({"event": "handoff", "from": "engineer", "to": "pr-reviewer", "t": int(time.time())})
        except OSError:
            pass

        # ── 워커 4: pr-reviewer + second reviewer (병렬) ─────────
        log_phase("pr-reviewer", run_logger, attempt)
        hlog_fn(f"pr-reviewer 시작 (depth={depth}, timeout=360s)")
        hud.agent_start("pr-reviewer")
        kill_check(state_dir)

        r = subprocess.run(["git", "diff", "HEAD~1"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            r = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, timeout=10)
        diff_out = "\n".join(r.stdout.splitlines()[:300])
        r_names = subprocess.run(["git", "diff", "HEAD~1", "--name-only"], capture_output=True, text=True, timeout=5)
        src_files = " ".join(r_names.stdout.strip().splitlines()) if r_names.returncode == 0 else ""

        # second reviewer v3: 파일별 분할 + threading 병렬
        import threading as _threading
        _second_result = [""]
        _second_thread = None
        if config.second_reviewer:
            _changed_for_2nd = [
                line.strip() for line in r_names.stdout.strip().splitlines()
                if line.strip()
            ] if r_names.returncode == 0 else []
            if _changed_for_2nd:
                def _bg_review():
                    _second_result[0] = run_review_batch(
                        _changed_for_2nd, config.second_reviewer, config.second_reviewer_model,
                    )
                _second_thread = _threading.Thread(target=_bg_review, daemon=True)
                _second_thread.start()
                hlog_fn(f"second reviewer v3 ({config.second_reviewer}) 파일별 병렬 시작 ({len(_changed_for_2nd)}개)")

        pr_out = str(state_dir.path / f"{prefix}_pr_out.txt")
        _prev_must_hint_sd = _prev_must_fix_hint(loop_out_dir, attempt)
        agent_exit = agent_call(
            "pr-reviewer", 360,
            f'@MODE:PR_REVIEWER:REVIEW\n'
            f'@PARAMS: {{ "impl_path": "{impl_file}", "src_files": "{src_files}" }}\n'
            f"변경 diff:\n{diff_out}{_eng_handoff_hint_sd}{_prev_must_hint_sd}",
            pr_out, run_logger, config, str(attempt_dir),
        )
        hlog_fn(f"pr-reviewer 종료 (exit={agent_exit})")
        if agent_exit == 124:
            hlog_fn("pr-reviewer timeout")
        total_cost = budget_check("pr-reviewer", pr_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)
        try:
            shutil.copy2(pr_out, str(attempt_dir / "pr.log"))
        except OSError:
            pass

        if not check_agent_output("pr-reviewer", pr_out):
            fail_type = "pr_fail"
            error_trace = f"pr-reviewer agent produced no output (exit={agent_exit})"
            append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue

        pr_result = parse_marker(pr_out, "LGTM|CHANGES_REQUESTED")
        print(f"[HARNESS] pr-reviewer 결과: {pr_result}")
        if pr_result != "LGTM":
            fail_type = "pr_fail"
            log_decision("fail_type", fail_type, f"pr-reviewer result={pr_result}", run_logger, attempt)
            append_failure(impl_file, "pr_fail", f"pr-reviewer CHANGES_REQUESTED (see {attempt_dir}/pr.log)", state_dir, prefix)
            save_impl_meta(attempt_dir, attempt, "FAIL", depth, "pr_fail",
                           f"{attempt_dir}/pr.log 의 MUST FIX 항목만 수정")
            rollback_attempt(attempt, run_logger)
            attempt += 1
            continue
        state_dir.flag_touch(Flag.PR_REVIEWER_LGTM)
        print("[HARNESS] LGTM")

        # second reviewer v3 결과 수집
        _second_findings = ""
        if _second_thread:
            _second_thread.join(timeout=300)
            _second_findings = _second_result[0]
            if _second_findings:
                hlog_fn(f"second reviewer v3 findings: {len(_second_findings)} chars")
                if run_logger:
                    run_logger.log_event({
                        "event": "second_review",
                        "reviewer": config.second_reviewer,
                        "findings_chars": len(_second_findings),
                        "t": int(time.time()),
                    })

        # ── POLISH: 코드 다듬기 (LGTM 후, security/merge 전) ─────
        polish_items = extract_polish_items(str(state_dir.path / f"{prefix}_pr_out.txt"))
        if _second_findings:
            polish_items = (polish_items + f"\n\n[{config.second_reviewer} 리뷰]\n{_second_findings}").strip()
        if polish_items:
            hlog_fn("POLISH 항목 감지 — engineer POLISH 모드 실행")
            print("[HARNESS] POLISH: 코드 다듬기")
            _polish_out = str(state_dir.path / f"{prefix}_polish_out.txt")
            _pre_polish_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            agent_call(
                "engineer", 180,
                f"@MODE:ENGINEER:POLISH\n정리 항목:\n{polish_items}",
                _polish_out, run_logger, config,
            )
            _reg_ok = True
            if config.lint_command:
                _polish_files = collect_changed_files(work_cwd)
                _lintable = [f for f in _polish_files if any(f.endswith(e) for e in ('.ts','.tsx','.js','.jsx','.mjs','.cjs'))]
                _lint_cmd = f"{config.lint_command} {' '.join(_lintable)}" if _lintable else config.lint_command
                _lint_r = subprocess.run(_lint_cmd, shell=True, capture_output=True, timeout=60)
                if _lint_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: lint ({_lint_cmd})")
            if _reg_ok and config.build_command:
                _build_r = subprocess.run(config.build_command, shell=True, capture_output=True, timeout=120)
                if _build_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: build ({config.build_command})")
            if _reg_ok and config.test_command:
                _test_r = subprocess.run(config.test_command, shell=True, capture_output=True, timeout=300)
                if _test_r.returncode != 0:
                    _reg_ok = False
                    hlog_fn(f"POLISH regression FAIL: test ({config.test_command})")
            if not _reg_ok:
                hlog_fn("POLISH revert — 변경 파일만 선택적 복원")
                print("[HARNESS] POLISH regression 실패 — 변경 파일만 복원")
                _polish_changed = collect_changed_files(work_cwd)
                if _polish_changed:
                    subprocess.run(
                        ["git", "checkout", _pre_polish_hash, "--"] + _polish_changed,
                        capture_output=True, timeout=10,
                    )
                    subprocess.run(["git", "add", "--"] + _polish_changed, capture_output=True, timeout=10)
                    subprocess.run(
                        ["git", "commit", "-m", f"revert: polish regression (#{issue_num})"],
                        capture_output=True, timeout=10,
                    )
                    hlog_fn(f"POLISH revert 커밋 ({len(_polish_changed)} files)")
                    push_and_ensure_pr(feature_branch, issue_num, impl_file, depth, state_dir, prefix, cwd=work_cwd)
            else:
                _changed = collect_changed_files(work_cwd)
                if _changed:
                    subprocess.run(["git", "add", "--"] + _changed, capture_output=True, timeout=10)
                    subprocess.run(
                        ["git", "commit", "-m", f"polish: code cleanup (#{issue_num})"],
                        capture_output=True, timeout=10,
                    )
                    hlog_fn("POLISH 커밋 완료")
                    push_and_ensure_pr(feature_branch, issue_num, impl_file, depth, state_dir, prefix, cwd=work_cwd)
                print("[HARNESS] POLISH 완료")
        else:
            hlog_fn("POLISH 항목 없음 — 스킵")

        # ── 워커 5: security-reviewer (deep only) ─────────────────
        if depth == "deep":
            log_phase("security-reviewer", run_logger, attempt)
            hlog_fn("security-reviewer 시작 (deep only, timeout=180s)")
            hud.agent_start("security-reviewer")
            kill_check(state_dir)

            r_src = subprocess.run(["git", "diff", "HEAD~1", "--name-only"], capture_output=True, text=True, timeout=5)
            changed_src = " ".join(
                l for l in r_src.stdout.splitlines()
                if re.search(r"\.(ts|tsx|js|jsx)$", l)
            )[:10] if r_src.returncode == 0 else ""

            r_diff = subprocess.run(["git", "diff", "HEAD~1"], capture_output=True, text=True, timeout=10)
            if r_diff.returncode != 0:
                r_diff = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, timeout=10)
            sec_diff = "\n".join(r_diff.stdout.splitlines()[:500])

            sec_out = str(state_dir.path / f"{prefix}_sec_out.txt")
            agent_exit = agent_call(
                "security-reviewer", 180,
                f"보안 리뷰 대상 파일:\n{changed_src}\n\n변경 diff:\n{sec_diff}",
                sec_out, run_logger, config, str(attempt_dir),
            )
            hlog_fn(f"security-reviewer 종료 (exit={agent_exit})")
            if agent_exit == 124:
                hlog_fn("security-reviewer timeout")
            total_cost = budget_check("security-reviewer", sec_out, total_cost, config.max_total_cost, state_dir, prefix, config=config)
            try:
                shutil.copy2(sec_out, str(attempt_dir / "security.log"))
            except OSError:
                pass

            if not check_agent_output("security-reviewer", sec_out):
                fail_type = "security_fail"
                error_trace = f"security-reviewer agent produced no output (exit={agent_exit})"
                append_failure(impl_file, fail_type, error_trace, state_dir, prefix)
                rollback_attempt(attempt, run_logger)
                attempt += 1
                continue

            sec_result = parse_marker(sec_out, "SECURE|VULNERABILITIES_FOUND")
            print(f"[HARNESS] security-reviewer 결과: {sec_result}")
            if sec_result != "SECURE":
                fail_type = "security_fail"
                log_decision("fail_type", fail_type, f"security result={sec_result}", run_logger, attempt)
                append_failure(impl_file, "security_fail",
                               f"security VULNERABILITIES_FOUND (see {attempt_dir}/security.log)",
                               state_dir, prefix)
                save_impl_meta(attempt_dir, attempt, "FAIL", depth, "security_fail",
                               f"{attempt_dir}/security.log 의 HIGH/MEDIUM 취약점 수정")
                rollback_attempt(attempt, run_logger)
                attempt += 1
                continue
            state_dir.flag_touch(Flag.SECURITY_REVIEW_PASSED)
            print("[HARNESS] SECURE")
        else:
            # std: security-reviewer 스킵
            state_dir.flag_touch(Flag.SECURITY_REVIEW_PASSED)
            hlog_fn("security-reviewer 스킵 (depth=std)")
            hud.agent_skip("security-reviewer", "depth=std")

        # ── merge to main ─────────────────────────────────────────
        hud.agent_start("merge")
        # 미커밋 변경 커밋 (테스트 파일 등)
        changed2 = collect_changed_files(work_cwd)
        if changed2:
            subprocess.run(["git", "add", "--"] + changed2, capture_output=True, timeout=10)
            subprocess.run(
                ["git", "commit", "-m", generate_commit_msg(impl_file, issue_num) + " [test-files]"],
                capture_output=True, timeout=10,
            )
            hlog_fn("test 파일 추가 커밋 완료")
            push_and_ensure_pr(feature_branch, issue_num, impl_file, depth, state_dir, prefix, cwd=work_cwd)

        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        impl_commit = r.stdout.strip() if r.returncode == 0 else "unknown"

        # merge는 메인 repo에서 실행해야 함 — worktree cwd 복원
        if work_cwd:
            os.chdir(_orig_cwd)
        if not merge_to_main(feature_branch, issue_num, depth, prefix, state_dir, wt_mgr):
            os.environ["HARNESS_RESULT"] = "MERGE_CONFLICT_ESCALATE"
            print("MERGE_CONFLICT_ESCALATE")
            print(f"branch: {feature_branch}")
            print(f"impl_commit: {impl_commit}")
            hlog_fn("=== merge conflict ===")
            run_logger.write_run_end("MERGE_CONFLICT_ESCALATE", feature_branch, issue_num)
            return "MERGE_CONFLICT_ESCALATE"

        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        merge_commit = r.stdout.strip() if r.returncode == 0 else "unknown"
        run_logger.log_event({
            "event": "branch_merge", "branch": feature_branch,
            "impl_commit": impl_commit, "merge_commit": merge_commit, "t": int(time.time()),
        })

        pr_body_file = state_dir.path / f"{prefix}_pr_body.txt"
        try:
            pr_body_file.write_text(
                generate_pr_body(impl_file, issue_num, attempt + 1, MAX, state_dir, prefix),
                encoding="utf-8",
            )
        except OSError:
            pass

        append_success(impl_file, attempt + 1, eng_out=eng_out, attempt_dir=str(attempt_dir))
        save_impl_meta(attempt_dir, attempt, "PASS", depth, hints="구현 완료")
        (state_dir.path / f"{prefix}_last_issue").write_text(issue_num, encoding="utf-8")

        hud.agent_done("merge", 0, 0.0, "done")
        hud.log(f"HARNESS_DONE (attempt {attempt + 1})")
        hud.cleanup()
        os.environ["HARNESS_RESULT"] = "HARNESS_DONE"
        hlog_fn(f"=== 루프 종료 (HARNESS_DONE, attempt={attempt + 1}) ===")
        print("HARNESS_DONE")
        print(f"impl: {impl_file}")
        print(f"issue: #{issue_num}")
        print(f"attempts: {attempt + 1}")
        print(f"commit: {merge_commit}")
        print(f"pr_body: {pr_body_file}")

        candidate_file = state_dir.path / f"{prefix}_memory_candidate.md"
        if candidate_file.exists():
            print()
            print("[HARNESS MEMORY] 이번 루프에서 실패 패턴이 감지됐습니다.")
            print(f"   파일: {candidate_file}")
            print(candidate_file.read_text(encoding="utf-8"))
            print()
            print(f"memory_candidate: {candidate_file}")

        run_logger.write_run_end("HARNESS_DONE", feature_branch, issue_num)
        return "HARNESS_DONE"

    # ── MAX 초과 → ESCALATE ─────────────────────────────────────
    state_dir.flag_rm(Flag.PLAN_VALIDATION_PASSED)
    os.environ["HARNESS_RESULT"] = "IMPLEMENTATION_ESCALATE"
    hlog_fn(f"=== 루프 종료 (IMPLEMENTATION_ESCALATE, attempt={MAX}) ===")
    print("IMPLEMENTATION_ESCALATE")
    print(f"attempts: {MAX}")
    print(f"spec_gap_count: {spec_gap_count}")
    print(f"branch: {feature_branch}")
    print("마지막 에러:")
    if error_trace:
        for line in error_trace.splitlines()[:20]:
            print(line)
    record_escalate(state_dir, impl_file, fail_type or "max_attempts")
    run_logger.write_run_end("IMPLEMENTATION_ESCALATE", feature_branch, issue_num)
    return "IMPLEMENTATION_ESCALATE"


# ═══════════════════════════════════════════════════════════════════════
# 4. run_std / run_deep — thin wrappers
# ═══════════════════════════════════════════════════════════════════════

def run_std(
    impl_file: str, issue_num: str | int, config: HarnessConfig,
    state_dir: StateDir, prefix: str, branch_type: str = "feat",
    run_logger: Optional[RunLogger] = None, hud: Optional[HUD] = None,
) -> str:
    """std depth 구현 루프. impl_std.sh 대체."""
    return _run_std_deep(impl_file, issue_num, config, state_dir, prefix, "std", branch_type, run_logger, hud)


def run_deep(
    impl_file: str, issue_num: str | int, config: HarnessConfig,
    state_dir: StateDir, prefix: str, branch_type: str = "feat",
    run_logger: Optional[RunLogger] = None, hud: Optional[HUD] = None,
) -> str:
    """deep depth 구현 루프. impl_deep.sh 대체."""
    return _run_std_deep(impl_file, issue_num, config, state_dir, prefix, "deep", branch_type, run_logger, hud)


# ═══════════════════════════════════════════════════════════════════════
# 5. DEPTH_CHAINS — depth별 에이전트 체인 정의 (참조용)
# ═══════════════════════════════════════════════════════════════════════

DEPTH_CHAINS = {
    "simple": ["engineer", "pr-reviewer"],
    "std": ["test-engineer", "engineer", "validator", "pr-reviewer"],
    "deep": ["test-engineer", "engineer", "validator", "pr-reviewer", "security-reviewer"],
}
