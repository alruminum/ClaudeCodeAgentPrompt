"""
plan_loop.py -- 기획-UX 루프.
planner -> ux-architect -> validator(UX) -> 리턴.
설계 루프(architect SD + designer)는 메인 Claude 오케스트레이션으로 분리됨.
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
        build_loop_context, run_ux_validation,
        generate_handoff, write_handoff,
    )
except ImportError:
    from config import HarnessConfig
    from core import (
        RunLogger, StateDir, HUD,
        agent_call, parse_marker, kill_check,
        build_loop_context, run_ux_validation,
        generate_handoff, write_handoff,
    )


def run_plan(
    issue_num: str | int,
    prefix: str,
    context: str = "",
    config: Optional[HarnessConfig] = None,
    state_dir: Optional[StateDir] = None,
    run_logger: Optional[RunLogger] = None,
) -> str:
    """기획-UX 루프 실행. planner -> ux-architect -> validator(UX) -> plan-reviewer -> 리턴.

    Returns:
        결과 마커 문자열:
        - "UX_REVIEW_PASS": 기획-UX 완료 + plan-reviewer PASS (유저 승인 1 대기)
        - "UX_SKIP": UI 없는 기능 + plan-reviewer PASS (설계 루프 직행)
        - "PLAN_REVIEW_CHANGES_REQUESTED": plan-reviewer 판단 FAIL (유저 결정 대기)
        - "CLARITY_INSUFFICIENT": 유저 답변 필요
        - "UX_FLOW_ESCALATE": ux-architect 에스컬레이션
        - "UX_REVIEW_ESCALATE": UX 검증 에스컬레이션
        - 기타 에스컬레이션 마커
    """
    issue_num = str(issue_num)

    if config is None:
        try:
            from .config import load_config
        except ImportError:
            from config import load_config
        config = load_config()
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix, issue_num=issue_num)
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

    # -- HUD 초기화 (기획-UX 루프만) --
    hud = HUD("plan", prefix, issue_num, 1, config.max_total_cost, state_dir)

    # -- 체크포인트: 이전 런 산출물 재사용 --
    _meta_file = state_dir.path / f"{prefix}_plan_metadata.json"
    _prev_meta = {}
    if _meta_file.exists():
        try:
            import json as _json
            _prev_meta = _json.loads(_meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    # ================================================================
    # 1. product-planner
    # ================================================================
    # 체크포인트 우선순위:
    #   1) {prefix}_plan_metadata.json의 prd_path (직전 런의 정확한 경로)
    #   2) 루트 prd.md — **metadata.json 자체가 없을 때만** 폴백 (기존 프로젝트 첫 리뷰 진입)
    #      metadata.json이 존재하면서 prd_path 키가 비어있는 건 "reviewer 피드백 반영 위한
    #      명시적 리셋"이므로 폴백 금지 — planner가 재실행되어야 함.
    _skip_pp = False
    _prev_prd = _prev_meta.get("prd_path", "")
    if not (_prev_prd and Path(_prev_prd).exists()) and not _meta_file.exists() and Path("prd.md").exists():
        _prev_prd = "prd.md"
        print(f"[HARNESS] 체크포인트 폴백: 루트 prd.md 사용 (metadata.json 없음 — 기존 프로젝트 첫 리뷰)")
    if _prev_prd and Path(_prev_prd).exists():
        print(f"[HARNESS] 체크포인트: prd 파일 존재 ({_prev_prd}) -- product-planner 스킵")
        hud.agent_skip("product-planner", f"checkpoint: {_prev_prd}")
        _skip_pp = True
        pp_out = f"PRODUCT_PLAN_READY\nplan_doc: {_prev_prd}"
        prd_path = _prev_prd
    else:
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

    if _skip_pp:
        pp_marker = "PRODUCT_PLAN_READY"
    else:
        pp_marker = parse_marker(pp_out_file, "PRODUCT_PLAN_READY|PRODUCT_PLAN_UPDATED|CLARITY_INSUFFICIENT")

    if pp_marker == "CLARITY_INSUFFICIENT":
        os.environ["HARNESS_RESULT"] = "CLARITY_INSUFFICIENT"
        print(f"[HARNESS] product-planner -> CLARITY_INSUFFICIENT (유저 답변 필요)")
        print(pp_out)
        run_logger.write_run_end("CLARITY_INSUFFICIENT", "", issue_num)
        return "CLARITY_INSUFFICIENT"

    if pp_marker not in ("PRODUCT_PLAN_READY", "PRODUCT_PLAN_UPDATED"):
        os.environ["HARNESS_RESULT"] = "CLARITY_INSUFFICIENT"
        print(f"[HARNESS] product-planner -> 마커 감지 실패 ({pp_marker}) -- CLARITY_INSUFFICIENT 처리")
        print(pp_out)
        run_logger.write_run_end("CLARITY_INSUFFICIENT", "", issue_num)
        return "CLARITY_INSUFFICIENT"

    hud.log(f"product-planner -> {pp_marker}")
    print(f"[HARNESS] product-planner -> {pp_marker}")

    # prd.md 경로 추출
    if not _skip_pp:
        prd_path = ""
        prd_m = re.search(r"(prd[^ ]*\.md)", pp_out)
        if prd_m:
            prd_path = prd_m.group(1)
        if not prd_path or not Path(prd_path).exists():
            if Path("prd.md").exists():
                prd_path = "prd.md"
    print(f"[HARNESS] prd_path: {prd_path or 'N/A'}")

    # ================================================================
    # 2. UI 여부 판단 -> ux-architect 호출 or 스킵
    # ================================================================
    _skip_uxa = False
    ux_flow_doc = ""

    # 체크포인트: ux-flow.md 이미 존재
    # metadata.json의 ux_flow_doc 키가 우선. 파일 존재 기반 폴백은 metadata.json 자체가
    # 없을 때(기존 프로젝트 첫 리뷰)만. metadata.json 있는데 ux_flow_doc 키가 비어있으면
    # 명시적 리셋이므로 ux-architect 재실행 허용.
    _prev_ux = _prev_meta.get("ux_flow_doc", "")
    if _prev_ux and Path(_prev_ux).exists():
        print(f"[HARNESS] 체크포인트: ux-flow.md 존재 ({_prev_ux}) -- ux-architect 스킵")
        hud.agent_skip("ux-architect", f"checkpoint: {_prev_ux}")
        _skip_uxa = True
        ux_flow_doc = _prev_ux
    elif not _meta_file.exists() and Path("docs/ux-flow.md").exists():
        print("[HARNESS] 체크포인트 폴백: docs/ux-flow.md 존재 -- ux-architect 스킵 (metadata.json 없음)")
        hud.agent_skip("ux-architect", "checkpoint: docs/ux-flow.md (fallback)")
        _skip_uxa = True
        ux_flow_doc = "docs/ux-flow.md"
    else:
        # PRD 화면 인벤토리 비어있는지 확인 -> UI 없는 기능이면 스킵
        _has_ui = True
        if prd_path and Path(prd_path).exists():
            try:
                prd_text = Path(prd_path).read_text(encoding="utf-8", errors="replace")
                # 화면 인벤토리 섹션이 비어있거나 모든 기능에 (UI 없음) 표시
                inv_m = re.search(r"##\s*화면 인벤토리(.*?)(?=\n##|\Z)", prd_text, re.DOTALL)
                if inv_m:
                    inv_body = inv_m.group(1).strip()
                    # 테이블 행이 없거나 모든 행에 "UI 없음" 포함
                    rows = [l for l in inv_body.splitlines() if l.strip().startswith("|") and not l.strip().startswith("| 화면") and not l.strip().startswith("|--")]
                    if not rows or all("UI 없음" in r or "(UI 없음)" in r for r in rows):
                        _has_ui = False
                else:
                    # 화면 인벤토리 섹션 자체가 없으면 대략적 플로우로 판단
                    flow_m = re.search(r"##\s*대략적 플로우(.*?)(?=\n##|\Z)", prd_text, re.DOTALL)
                    if not flow_m or not flow_m.group(1).strip():
                        _has_ui = False
            except OSError:
                pass

        if not _has_ui:
            print("[HARNESS] PRD 화면 인벤토리 비어있음 -- ux-architect 스킵 (UI 없는 기능)")
            hud.agent_skip("ux-architect", "no UI screens in PRD")
            hud.agent_skip("ux-validation", "no UI screens in PRD")
            _skip_uxa = True

    # ================================================================
    # 3. ux-architect 호출
    # ================================================================
    if not _skip_uxa:
        # UX_SYNC 모드 분기: src/ 존재 + ux-flow.md 없음
        _uxa_mode = "UX_FLOW"
        if Path("src").exists() and not Path("docs/ux-flow.md").exists():
            _uxa_mode = "UX_SYNC"
            print(f"[HARNESS] src/ 존재 + ux-flow.md 없음 -> UX_SYNC 모드")

        print(f"[HARNESS] ux-architect {_uxa_mode}")
        _uxa_t0 = time.time()
        hud.agent_start("ux-architect")
        uxa_out_file = str(state_dir.path / f"{prefix}_uxa_out.txt")

        if _uxa_mode == "UX_SYNC":
            _uxa_exit = agent_call(
                "ux-architect", 600,
                f"@MODE:UX_ARCHITECT:UX_SYNC\nprd_path: {prd_path}\nsrc_dir: src/\nissue: #{issue_num}",
                uxa_out_file, run_logger, config,
            )
        else:
            _uxa_exit = agent_call(
                "ux-architect", 600,
                f"@MODE:UX_ARCHITECT:UX_FLOW\nprd_path: {prd_path}\nissue: #{issue_num}",
                uxa_out_file, run_logger, config,
            )

        # 타임아웃 감지 (exit 124/142)
        if _uxa_exit in (124, 142):
            print(f"[HARNESS] ux-architect 타임아웃 (exit {_uxa_exit})")

        _uxa_cost = 0.0
        try:
            _uxa_cost_file = Path(str(uxa_out_file).replace(".txt", "_cost.txt"))
            _uxa_cost = float(_uxa_cost_file.read_text() or "0") if _uxa_cost_file.exists() else 0.0
        except (ValueError, OSError):
            pass
        kill_check(state_dir)

        uxa_marker = parse_marker(uxa_out_file, "UX_FLOW_READY|UX_FLOW_ESCALATE")

        if uxa_marker == "UX_FLOW_ESCALATE":
            hud.agent_done("ux-architect", int(time.time() - _uxa_t0), _uxa_cost, "fail")
            os.environ["HARNESS_RESULT"] = "UX_FLOW_ESCALATE"
            print("[HARNESS] ux-architect -> UX_FLOW_ESCALATE")
            uxa_content = Path(uxa_out_file).read_text(encoding="utf-8", errors="replace") if Path(uxa_out_file).exists() else ""
            print(uxa_content[-500:] if len(uxa_content) > 500 else uxa_content)
            run_logger.write_run_end("UX_FLOW_ESCALATE", "", issue_num)
            return "UX_FLOW_ESCALATE"

        if uxa_marker != "UX_FLOW_READY":
            hud.agent_done("ux-architect", int(time.time() - _uxa_t0), _uxa_cost, "fail")
            os.environ["HARNESS_RESULT"] = "UX_FLOW_ESCALATE"
            print(f"[HARNESS] ux-architect -> 마커 감지 실패 ({uxa_marker}) -- UX_FLOW_ESCALATE 처리")
            run_logger.write_run_end("UX_FLOW_ESCALATE", "", issue_num)
            return "UX_FLOW_ESCALATE"

        hud.agent_done("ux-architect", int(time.time() - _uxa_t0), _uxa_cost)
        hud.log(f"ux-architect -> {uxa_marker}")
        print(f"[HARNESS] ux-architect -> {uxa_marker}")

        # ux-flow.md 경로 추출
        try:
            uxa_content = Path(uxa_out_file).read_text(encoding="utf-8", errors="replace")
            m = re.search(r"(docs/ux-flow\.md|ux-flow\.md)", uxa_content)
            if m:
                ux_flow_doc = m.group(1)
        except OSError:
            pass
        if not ux_flow_doc or not Path(ux_flow_doc).exists():
            if Path("docs/ux-flow.md").exists():
                ux_flow_doc = "docs/ux-flow.md"
        print(f"[HARNESS] ux_flow_doc: {ux_flow_doc or 'N/A'}")

        # ================================================================
        # 3.5. handoff: ux-architect -> validator(UX)
        # ================================================================
        try:
            uxa_content = Path(uxa_out_file).read_text(encoding="utf-8", errors="replace") if Path(uxa_out_file).exists() else ""
            handoff_content = generate_handoff(
                "ux-architect", "validator",
                uxa_content[-2000:],
                ux_flow_doc or "N/A", 0, issue_num,
            )
            write_handoff(state_dir, prefix, 0, "ux-architect", "validator", handoff_content)
        except Exception:
            pass  # handoff 실패해도 루프 중단하지 않음

        # ================================================================
        # 4. validator UX Validation
        # ================================================================
        if ux_flow_doc and Path(ux_flow_doc).exists():
            print(f"[HARNESS] UX Validation (ux_flow_doc: {ux_flow_doc})")
            _uxv_t0 = time.time()
            hud.agent_start("ux-validation")
            if not run_ux_validation(ux_flow_doc, prd_path, issue_num, prefix, 1, state_dir, run_logger, config):
                hud.agent_done("ux-validation", int(time.time() - _uxv_t0), 0.0, "fail")
                os.environ["HARNESS_RESULT"] = "UX_REVIEW_ESCALATE"
                print("[HARNESS] ux-validation -> UX_REVIEW_ESCALATE")
                print(f"ux_flow_doc: {ux_flow_doc}")
                run_logger.write_run_end("UX_REVIEW_ESCALATE", "", issue_num)
                return "UX_REVIEW_ESCALATE"
            hud.agent_done("ux-validation", int(time.time() - _uxv_t0), 0.0)
            print("[HARNESS] ux-validation -> PASS")
        else:
            hud.agent_skip("ux-validation", "ux_flow_doc 미감지")
            print("[HARNESS] ux-validation 스킵 (ux_flow_doc 경로 미감지)")
        kill_check(state_dir)

    # ================================================================
    # 5. plan-reviewer (판단 게이트) -- 현실성·MVP 균형·UX 저니·숨은 가정
    # ================================================================
    # 유저가 이전 턴에 "override"를 선택했으면 리뷰어 스킵
    _override_flag = state_dir.path / f"{prefix}_plan_review_override"
    if _override_flag.exists():
        hud.agent_skip("plan-reviewer", "user override 선택")
        print("[HARNESS] plan-reviewer 스킵 (유저 override 플래그)")
        try:
            _override_flag.unlink()  # 1회성 — 다음 런에는 다시 리뷰
        except OSError:
            pass
    else:
        print("[HARNESS] plan-reviewer 판단 게이트")
        _pr_t0 = time.time()
        hud.agent_start("plan-reviewer")
        pr_out_file = str(state_dir.path / f"{prefix}_plan_reviewer_out.txt")
        _pr_params = f'prd_path: {prd_path}\nissue: #{issue_num}'
        if ux_flow_doc:
            _pr_params += f'\nux_flow_doc: {ux_flow_doc}'
        agent_call(
            "plan-reviewer", 600,
            f"@MODE:REVIEWER:PLAN_REVIEW\n{_pr_params}",
            pr_out_file, run_logger, config,
        )
        _pr_cost = 0.0
        try:
            _pr_cost_file = Path(str(pr_out_file).replace(".txt", "_cost.txt"))
            _pr_cost = float(_pr_cost_file.read_text() or "0") if _pr_cost_file.exists() else 0.0
        except (ValueError, OSError):
            pass
        kill_check(state_dir)

        pr_marker = parse_marker(pr_out_file, "PLAN_REVIEW_PASS|PLAN_REVIEW_CHANGES_REQUESTED")

        if pr_marker == "PLAN_REVIEW_CHANGES_REQUESTED":
            hud.agent_done("plan-reviewer", int(time.time() - _pr_t0), _pr_cost, "fail")
            os.environ["HARNESS_RESULT"] = "PLAN_REVIEW_CHANGES_REQUESTED"
            pr_content = Path(pr_out_file).read_text(encoding="utf-8", errors="replace") if Path(pr_out_file).exists() else ""
            print("[HARNESS] plan-reviewer -> PLAN_REVIEW_CHANGES_REQUESTED")
            print(f"  prd_path: {prd_path or 'N/A'}")
            print(f"  ux_flow_doc: {ux_flow_doc or 'N/A'}")
            print("  -> 메인 Claude: 아래 리포트 전문을 유저에게 전달 후 결정 수집")
            print("=" * 60)
            print(pr_content)
            print("=" * 60)
            run_logger.write_run_end("PLAN_REVIEW_CHANGES_REQUESTED", "", issue_num)
            # 메타데이터 저장 — 재호출 시 체크포인트 재사용
            import json as _json
            _plan_meta = {
                "prd_path": prd_path,
                "ux_flow_doc": ux_flow_doc,
                "issue_num": issue_num,
            }
            try:
                (state_dir.path / f"{prefix}_plan_metadata.json").write_text(
                    _json.dumps(_plan_meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return "PLAN_REVIEW_CHANGES_REQUESTED"

        if pr_marker != "PLAN_REVIEW_PASS":
            # 마커 미감지 — fail-safe: CHANGES_REQUESTED 처리
            hud.agent_done("plan-reviewer", int(time.time() - _pr_t0), _pr_cost, "fail")
            os.environ["HARNESS_RESULT"] = "PLAN_REVIEW_CHANGES_REQUESTED"
            print(f"[HARNESS] plan-reviewer -> 마커 감지 실패 ({pr_marker}) -- CHANGES_REQUESTED 처리")
            pr_content = Path(pr_out_file).read_text(encoding="utf-8", errors="replace") if Path(pr_out_file).exists() else ""
            print(pr_content[-1000:] if len(pr_content) > 1000 else pr_content)
            run_logger.write_run_end("PLAN_REVIEW_CHANGES_REQUESTED", "", issue_num)
            return "PLAN_REVIEW_CHANGES_REQUESTED"

        hud.agent_done("plan-reviewer", int(time.time() - _pr_t0), _pr_cost)
        hud.log("plan-reviewer -> PLAN_REVIEW_PASS")
        print("[HARNESS] plan-reviewer -> PLAN_REVIEW_PASS")

    # ================================================================
    # 완료 -- 메타데이터 저장
    # ================================================================
    import json as _json
    _plan_meta = {
        "prd_path": prd_path,
        "ux_flow_doc": ux_flow_doc,
        "issue_num": issue_num,
    }
    try:
        (state_dir.path / f"{prefix}_plan_metadata.json").write_text(
            _json.dumps(_plan_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

    # UI 없는 기능이면 UX_SKIP 반환
    if _skip_uxa and not ux_flow_doc:
        os.environ["HARNESS_RESULT"] = "UX_SKIP"
        hud.log("UX_SKIP (UI 없는 기능)")
        print("[HARNESS] UX_SKIP -- UI 없는 기능, 설계 루프 직행")
        print(f"  prd_path: {prd_path or 'N/A'}")
        print(f"  issue: #{issue_num}")
        run_logger.write_run_end("UX_SKIP", "", issue_num)
        return "UX_SKIP"

    os.environ["HARNESS_RESULT"] = "UX_REVIEW_PASS"
    hud.log("UX_REVIEW_PASS")
    print("[HARNESS] UX_REVIEW_PASS")
    print(f"  prd_path: {prd_path or 'N/A'}")
    print(f"  ux_flow_doc: {ux_flow_doc or 'N/A'}")
    print(f"  issue: #{issue_num}")
    print("  -> 유저 승인 1 대기 (PRD + UX Flow)")
    run_logger.write_run_end("UX_REVIEW_PASS", "", issue_num)
    return "UX_REVIEW_PASS"
