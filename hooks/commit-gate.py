#!/usr/bin/env python3
"""
commit-gate.py — PreToolUse(Bash) 글로벌 훅
git commit 전 pr-reviewer LGTM 확인.
프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import subprocess
from harness_common import get_prefix, get_state_dir, deny

PREFIX = get_prefix()


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = d.get("tool_input", {}).get("command", "")

    # ── Gate 1: gh issue create 직접 호출 차단 ────────────────────────
    # QA 에이전트만 이슈를 생성할 수 있다. 메인 Claude 직접 생성 금지.
    _IS_GH_ISSUE_CREATE = (
        re.search(r"gh\s+issue\s+create", cmd)
        or re.search(r"gh\s+api\s+.*issues.*--method\s+POST", cmd)
        or re.search(r"gh\s+api\s+.*issues.*-X\s+POST", cmd)
    )
    if _IS_GH_ISSUE_CREATE and os.environ.get("HARNESS_INTERNAL") != "1":
        deny(
            "❌ gh issue create 직접 호출 금지.\n"
            "버그 이슈는 QA 에이전트가 생성한다.\n"
            f"올바른 흐름: bash [executor.sh] bugfix --prefix {PREFIX} → QA가 분석·이슈 생성·라우팅"
        )

    # ── Gate 2: BUG 컨텍스트에서 executor.sh impl 직접 호출 차단 ───────
    # is_bug 플래그는 harness-router.py가 버그 감지 시 설정.
    # executor.sh bugfix 호출 시 클리어됨.
    _is_bug_flag = f"{get_state_dir()}/{PREFIX}_is_bug"
    _IS_EXECUTOR_IMPL = re.search(r"executor\.sh\s+impl\b", cmd)
    _IS_EXECUTOR_BUGFIX = re.search(r"executor\.sh\s+bugfix\b", cmd)

    if _IS_EXECUTOR_BUGFIX and os.path.exists(_is_bug_flag):
        # 올바른 경로 — bugfix 호출, 플래그 클리어
        try:
            os.remove(_is_bug_flag)
        except OSError:
            pass

    if _IS_EXECUTOR_IMPL and os.path.exists(_is_bug_flag) and os.environ.get("HARNESS_INTERNAL") != "1":
        deny(
            "❌ BUG 컨텍스트에서 executor.sh impl 직접 호출 금지.\n"
            "버그는 반드시 bugfix 루프를 거쳐야 한다 (QA → 4-way 분기).\n"
            f"올바른 명령: bash [executor.sh] bugfix --prefix {PREFIX}"
        )

    # ── Gate 3: 인터뷰 진행 중 executor.sh 호출 차단 ───────────────────
    # harness-router.py가 AMBIGUOUS 분류 시 interview_state.json을 생성.
    # 인터뷰 완료(DONE) 전까지 구현 루프 진입 금지.
    _interview_path = f"{get_state_dir()}/{PREFIX}_interview_state.json"
    _IS_EXECUTOR_ANY = re.search(r"executor\.sh\s+(impl|bugfix|design|plan)\b", cmd)
    if _IS_EXECUTOR_ANY and os.path.exists(_interview_path) and os.environ.get("HARNESS_INTERNAL") != "1":
        deny(
            "❌ 인터뷰 진행 중 — executor.sh 호출 불가.\n"
            "요구사항 명확화 인터뷰를 먼저 완료하세요.\n"
            "현재 질문에 답변하면 다음 단계로 진행됩니다."
        )

    # git commit 명령이 아니면 통과
    if not re.search(r"git\s+commit", cmd):
        sys.exit(0)

    # staged 파일에 src/ 가 있는지 확인
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=5
        )
        staged = result.stdout
    except Exception:
        sys.exit(0)

    has_src = bool(re.search(r"^src/", staged, re.MULTILINE))
    if not has_src:
        sys.exit(0)

    # feature branch → LGTM 불필요, 자유 커밋
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        current_branch = branch_result.stdout.strip()
    except Exception:
        current_branch = ""

    if current_branch and current_branch not in ("main", "master"):
        sys.exit(0)

    # src 변경이 있으면 LGTM 필요
    if not os.path.exists(f"{get_state_dir()}/{PREFIX}_pr_reviewer_lgtm"):
        deny(f"❌ git commit 전 pr-reviewer LGTM 필요. {get_state_dir()}/{PREFIX}_pr_reviewer_lgtm 없음.")

    sys.exit(0)


if __name__ == "__main__":
    main()
