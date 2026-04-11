"""
impl_router.py — impl.sh 대체.
impl 파일 유무에 따라 architect 호출 → depth 감지 → depth별 루프 라우팅.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .config import HarnessConfig
from .core import (
    Flag, RunLogger, StateDir,
    agent_call, parse_marker, detect_depth,
    run_plan_validation,
)
from .impl_loop import run_simple, run_std, run_deep


def ensure_depth_frontmatter(
    impl_file: str,
    issue_num: str | int,
    prefix: str,
    state_dir: StateDir,
    run_logger: Optional[RunLogger] = None,
    config: Optional[HarnessConfig] = None,
) -> None:
    """depth frontmatter 강제 검증. 없으면 architect 마이크로 패치."""
    impl = Path(impl_file)
    if not impl.exists():
        return

    content = impl.read_text(encoding="utf-8", errors="replace")

    # frontmatter depth: 필드 존재 확인
    has_depth = False
    in_fm = False
    fence_count = 0
    for line in content.splitlines():
        if line.strip() == "---":
            fence_count += 1
            if fence_count == 1:
                in_fm = True
                continue
            elif fence_count == 2:
                break
        if in_fm and re.match(r"^depth:", line):
            has_depth = True
            break

    if has_depth:
        depth_line = next(
            (l for l in content.splitlines() if re.match(r"^depth:", l)),
            "",
        )
        print(f"[HARNESS] depth frontmatter 확인: {depth_line.strip()}")
        return

    # frontmatter 자체가 있는지 확인
    has_frontmatter = content.startswith("---")
    fm_status = "있음(depth만 누락)" if has_frontmatter else "없음"

    print("[HARNESS] ⚠️ impl 파일에 depth frontmatter 누락 — architect 마이크로 패치 호출")
    patch_out = str(state_dir.path / f"{prefix}_depth_patch_out.txt")
    agent_call(
        "architect", 60,
        f"@MODE:ARCHITECT:SPEC_GAP\n"
        f"이 impl 파일에 YAML frontmatter depth 필드가 누락됐다.\n"
        f"파일 첫 줄부터 --- 블록을 추가하고 depth: simple|std|deep 중 하나를 선언하라.\n"
        f"기준: behavior 불변(이름·텍스트·스타일·색상·애니메이션·설정값)=simple, "
        f"behavior 변경(로직·API·DB)=std, 보안 민감=deep.\n"
        f"impl: {impl_file}\nissue: #{issue_num}\n"
        f"기존 frontmatter 유무: {fm_status}\n"
        f"파일 내용 확인 후 depth만 추가하라. 다른 내용은 수정하지 마라.",
        patch_out, run_logger, config,
    )

    # 재확인
    content = impl.read_text(encoding="utf-8", errors="replace")
    has_depth = False
    fence_count = 0
    in_fm = False
    for line in content.splitlines():
        if line.strip() == "---":
            fence_count += 1
            if fence_count == 1:
                in_fm = True
                continue
            elif fence_count == 2:
                break
        if in_fm and re.match(r"^depth:", line):
            has_depth = True
            depth_line = line
            break

    if has_depth:
        print(f"[HARNESS] depth 패치 성공: {depth_line.strip()}")
    else:
        print("[HARNESS] ⚠️ depth 패치 실패 — std 폴백 적용 (architect 프롬프트 개선 필요)")
        if run_logger:
            run_logger.log_event({
                "event": "warn",
                "msg": "depth_frontmatter_missing_after_retry",
                "impl": impl_file,
                "t": int(time.time()),
            })


def run_impl(
    impl_file: str,
    issue_num: str | int,
    prefix: str,
    depth: str = "auto",
    context: str = "",
    branch_type: str = "feat",
    run_logger: Optional[RunLogger] = None,
    config: Optional[HarnessConfig] = None,
    state_dir: Optional[StateDir] = None,
) -> str:
    """impl.sh의 run_impl() 대체. depth별 루프 라우팅.

    Returns:
        결과 문자열 (HARNESS_DONE, IMPLEMENTATION_ESCALATE, etc.)
    """
    issue_num = str(issue_num)

    if config is None:
        from .config import load_config
        config = load_config()
    if state_dir is None:
        state_dir = StateDir(Path.cwd(), prefix)

    # ── 재진입 감지 ──
    if (state_dir.flag_exists(Flag.PLAN_VALIDATION_PASSED)
            and impl_file and Path(impl_file).exists()):
        print("[HARNESS] 재진입: plan_validation_passed + impl 존재 → engineer 루프 직접 진입")
        if depth == "auto":
            depth = detect_depth(impl_file)
        print(f"[HARNESS] depth: {depth}")
        return _dispatch_depth(depth, impl_file, issue_num, config, state_dir, prefix, branch_type, run_logger)

    # ── UI 키워드 감지 (design 루프 전환) ──
    skip_design_check = False
    issue_labels_cache = ""
    if issue_num and issue_num != "N":
        try:
            r = subprocess.run(
                ["gh", "issue", "view", issue_num, "--json", "labels", "-q",
                 '[.labels[].name] | join(",")'],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                issue_labels_cache = r.stdout.strip()
        except Exception:
            pass
        if re.search(r"bug|fix|hotfix", issue_labels_cache, re.IGNORECASE):
            skip_design_check = True

    if not skip_design_check and impl_file and Path(impl_file).exists():
        try:
            impl_text = Path(impl_file).read_text(encoding="utf-8")
            ui_kw = re.search(
                r"화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이",
                impl_text,
            )
            if ui_kw and not state_dir.flag_exists(Flag.DESIGN_CRITIC_PASSED):
                os.environ["HARNESS_RESULT"] = "UI_DESIGN_REQUIRED"
                print("UI_DESIGN_REQUIRED")
                print(f"impl: {impl_file}")
                print(f"이유: {ui_kw.group()}")
                print("필요 조치: mode:design 완료 후 mode:impl 재호출")
                return "UI_DESIGN_REQUIRED"
        except OSError:
            pass

    # 로그 초기화 (이중 로테이션 방지)
    if run_logger is None:
        run_logger = RunLogger(prefix, "impl", issue_num)

    # 히스토리 디렉토리
    run_ts = os.environ.get("HARNESS_RUN_TS", time.strftime("%Y%m%d_%H%M%S"))
    hist_dir = state_dir.path / f"{prefix}_history"
    impl_run_dir = hist_dir / "impl" / f"run_{run_ts}"
    impl_run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HARNESS_HIST_DIR"] = str(impl_run_dir)

    # ── impl 파일 없으면 architect 호출 ──
    if not impl_file or not Path(impl_file).exists():
        issue_labels = ""
        issue_summary = ""
        suspected_files = ""
        arch_mode = "MODULE_PLAN"

        if issue_num and issue_num != "N":
            try:
                r = subprocess.run(
                    ["gh", "issue", "view", issue_num, "--json", "labels", "-q",
                     '[.labels[].name] | join(",")'],
                    capture_output=True, text=True, timeout=10,
                )
                issue_labels = r.stdout.strip() if r.returncode == 0 else ""
            except Exception:
                pass

            try:
                r = subprocess.run(
                    ["gh", "issue", "view", issue_num, "--json", "title,body", "-q",
                     '"## " + .title + "\\n\\n" + .body'],
                    capture_output=True, text=True, timeout=10,
                )
                issue_summary = r.stdout.strip() if r.returncode == 0 else ""
            except Exception:
                pass

            # LIGHT_PLAN 분기 조건
            if (re.search(r"bug|design-fix|fix|hotfix|cleanup", issue_labels, re.IGNORECASE)
                    or "DESIGN_HANDOFF" in issue_summary):
                arch_mode = "LIGHT_PLAN"

                # suspected_files
                try:
                    r = subprocess.run(
                        ["gh", "issue", "view", issue_num, "--json", "title", "-q", ".title"],
                        capture_output=True, text=True, timeout=10,
                    )
                    issue_title = r.stdout.strip() if r.returncode == 0 else ""
                    if issue_title:
                        keywords = re.findall(r"[a-zA-Z가-힣]{2,}", issue_title)[:5]
                        if keywords:
                            kw_pattern = "|".join(re.escape(k) for k in keywords)
                            r = subprocess.run(
                                ["grep", "-rlE", kw_pattern, "src/"],
                                capture_output=True, text=True, timeout=10,
                            )
                            if r.returncode == 0:
                                suspected_files = ",".join(r.stdout.strip().splitlines()[:10])
                except Exception:
                    pass

        arch_out = str(state_dir.path / f"{prefix}_arch_out.txt")

        if arch_mode == "LIGHT_PLAN":
            # depth 힌트
            depth_hint = ""
            if depth != "auto":
                depth_hint = depth
            elif "DESIGN_HANDOFF" in issue_summary:
                depth_hint = "simple"
            elif re.search(r"bug|fix|hotfix|cleanup", issue_labels, re.IGNORECASE):
                depth_hint = "simple"

            depth_prompt = (
                f"스킬/하네스 추천: {depth_hint} (참고용 — architect가 이슈 내용 기반으로 최종 판단. 상향/하향 모두 가능)"
                if depth_hint else
                "추천 없음 — 이슈 내용 기반으로 architect가 직접 판단"
            )

            print(f"[HARNESS] architect LIGHT_PLAN 작성 (issue #{issue_num}, depth_hint={depth_hint or 'none'})")
            agent_call(
                "architect", 900,
                f"@MODE:ARCHITECT:LIGHT_PLAN\n"
                f"issue #{issue_num}\n"
                f"suspected_files: {suspected_files}\n"
                f"labels: {issue_labels}\n"
                f"issue_summary:\n{issue_summary}\n"
                f"context: {context}\n\n"
                f"[DEPTH 선택 — frontmatter depth: 필드 필수]\n"
                f"기준: 이 이슈의 구현이 기존 코드 구조 수정으로 완결되는가, 새 로직 구조를 신설해야 하는가?\n"
                f"- simple: 기존 구조 수정 — 값·조건·스타일·요소 변경, 코드 제거/정리\n"
                f"- std: 새 로직 구조 신설 — 새 함수·모듈·상태·API·데이터 흐름\n"
                f"- deep: 보안·결제·인증\n"
                f"{depth_prompt}",
                arch_out, run_logger, config,
            )
        else:
            print("[HARNESS] architect Module Plan 작성")
            agent_call(
                "architect", 900,
                f"@MODE:ARCHITECT:MODULE_PLAN\n"
                f"issue #{issue_num} impl 계획 작성. context: {context}",
                arch_out, run_logger, config,
            )

        # architect 결과 마커
        arch_marker = parse_marker(
            arch_out,
            "LIGHT_PLAN_READY|READY_FOR_IMPL|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT",
        )
        if arch_marker == "PRODUCT_PLANNER_ESCALATION_NEEDED":
            os.environ["HARNESS_RESULT"] = "PRODUCT_PLANNER_ESCALATION_NEEDED"
            print("PRODUCT_PLANNER_ESCALATION_NEEDED")
            return "PRODUCT_PLANNER_ESCALATION_NEEDED"
        if arch_marker == "TECH_CONSTRAINT_CONFLICT":
            os.environ["HARNESS_RESULT"] = "TECH_CONSTRAINT_CONFLICT"
            print("TECH_CONSTRAINT_CONFLICT")
            return "TECH_CONSTRAINT_CONFLICT"

        # impl 파일 경로 추출
        try:
            arch_content = Path(arch_out).read_text(encoding="utf-8", errors="replace")
            m = re.search(r"docs/[^ ]+\.md", arch_content)
            impl_file = m.group(0) if m else ""
        except OSError:
            impl_file = ""
        print(f"[HARNESS] impl: {impl_file}")

    if not impl_file or not Path(impl_file).exists():
        os.environ["HARNESS_RESULT"] = "SPEC_GAP_ESCALATE"
        print("SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다.")
        return "SPEC_GAP_ESCALATE"

    # ── depth frontmatter 강제 검증 ──
    ensure_depth_frontmatter(impl_file, issue_num, prefix, state_dir, run_logger, config)

    # ── Plan Validation ──
    print("[HARNESS] Plan Validation")
    if run_plan_validation(impl_file, issue_num, prefix, 1, state_dir, run_logger, config):
        (state_dir.path / f"{prefix}_impl_path").write_text(impl_file, encoding="utf-8")
        print("PLAN_VALIDATION_PASS")
        print(f"impl: {impl_file}")
        print(f"issue: #{issue_num}")

        if depth == "auto":
            depth = detect_depth(impl_file)
        print(f"[HARNESS] depth: {depth}")
        return _dispatch_depth(depth, impl_file, issue_num, config, state_dir, prefix, branch_type, run_logger)

    os.environ["HARNESS_RESULT"] = "PLAN_VALIDATION_ESCALATE"
    print("PLAN_VALIDATION_ESCALATE")
    return "PLAN_VALIDATION_ESCALATE"


def _dispatch_depth(
    depth: str,
    impl_file: str,
    issue_num: str,
    config: HarnessConfig,
    state_dir: StateDir,
    prefix: str,
    branch_type: str,
    run_logger: Optional[RunLogger],
) -> str:
    """depth별 루프 함수 디스패치."""
    runners = {
        "simple": run_simple,
        "std": run_std,
        "deep": run_deep,
    }
    runner = runners.get(depth, run_std)
    return runner(impl_file, issue_num, config, state_dir, prefix, branch_type, run_logger)
