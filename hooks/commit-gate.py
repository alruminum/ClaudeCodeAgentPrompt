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
import glob
import time
from harness_common import get_prefix, get_state_dir, deny, FLAGS, ISSUE_CREATORS

PREFIX = get_prefix()


def _is_issue_creator_active():
    """ISSUE_CREATORS 에이전트 중 하나라도 활성 상태인지 확인."""
    state_dir = get_state_dir()
    now = time.time()
    for agent in ISSUE_CREATORS:
        flag_file = os.path.join(state_dir, f"{PREFIX}_{agent}_active")
        if os.path.exists(flag_file):
            return True
        for f in glob.glob(os.path.join(state_dir, f"*_{agent}_active")):
            try:
                if now - os.path.getmtime(f) < 900:
                    return True
            except Exception:
                pass
    return False


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = d.get("tool_input", {}).get("command", "")

    # ── Gate 1: gh issue create 직접 호출 차단 ────────────────────────
    # QA/designer 에이전트만 이슈를 생성할 수 있다. 메인 Claude 직접 생성 금지.
    _IS_GH_ISSUE_CREATE = (
        re.search(r"gh\s+issue\s+create", cmd)
        or re.search(r"gh\s+api\s+.*issues.*--method\s+POST", cmd)
        or re.search(r"gh\s+api\s+.*issues.*-X\s+POST", cmd)
    )
    if _IS_GH_ISSUE_CREATE and os.environ.get("HARNESS_INTERNAL") != "1" and not _is_issue_creator_active():
        deny(
            "❌ gh issue create 직접 호출 금지.\n"
            "버그 이슈는 QA 에이전트가, 디자인 이슈는 designer 에이전트가 생성한다.\n"
            f"올바른 흐름: /qa 스킬 → QA 에이전트 분석·이슈 생성 → python3 executor.py impl --issue <N> --prefix {PREFIX}"
        )

    # ── Gate 2: (removed in v6 — bugfix 모드 제거에 따라 is_bug 게이트 삭제)

    # ── Gate 3: 인터뷰 진행 중 executor.sh 호출 차단 ───────────────────
    # harness-router.py가 AMBIGUOUS 분류 시 interview_state.json을 생성.
    # 인터뷰 완료(DONE) 전까지 구현 루프 진입 금지.
    _interview_path = f"{get_state_dir()}/{PREFIX}_interview_state.json"
    _IS_EXECUTOR_ANY = re.search(r"executor\.(sh|py)\s+(impl|bugfix|design|plan)\b", cmd)
    if _IS_EXECUTOR_ANY and os.path.exists(_interview_path) and os.environ.get("HARNESS_INTERNAL") != "1":
        deny(
            "❌ 인터뷰 진행 중 — executor.py 호출 불가.\n"
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
    if not os.path.exists(f"{get_state_dir()}/{PREFIX}_{FLAGS.PR_REVIEWER_LGTM}"):
        deny(f"❌ git commit 전 pr-reviewer LGTM 필요. {get_state_dir()}/{PREFIX}_{FLAGS.PR_REVIEWER_LGTM} 없음.")

    sys.exit(0)


if __name__ == "__main__":
    main()
