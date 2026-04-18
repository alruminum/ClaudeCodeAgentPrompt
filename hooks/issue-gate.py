#!/usr/bin/env python3
"""
issue-gate.py — PreToolUse(mcp__github__create_issue, mcp__github__update_issue) 글로벌 훅
메인 Claude가 GitHub 이슈를 직접 생성/수정하는 것을 차단한다.

orchestration/policies.md 정책 3:
"메인 Claude — GitHub 이슈 직접 생성/수정 금지.
 이슈 생성/수정은 qa/designer 에이전트가 내부에서 처리한다."

예외: ISSUE_CREATORS 에이전트(qa, designer)가 활성 상태이면 허용.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import time
from harness_common import get_prefix, deny, flag_path, FLAGS, ISSUE_CREATORS

PREFIX = get_prefix()

# 폴백 플래그 TTL — 크래시/Ctrl+C로 남은 잔재 플래그 무효화 (15분)
FALLBACK_FLAG_TTL_SEC = 15 * 60


def _is_issue_creator_active():
    """ISSUE_CREATORS 에이전트 중 하나라도 활성 상태인지 확인.
    우선순위: env var(HARNESS_AGENT_NAME) → 플래그 파일({prefix}_{agent}_active, TTL 15분).
    env var는 harness/core.py subprocess 경로, 플래그는 Agent 툴 경로 폴백.
    플래그 cleanup은 post-agent-flags.py가 PostToolUse(Agent)에서 처리하며,
    크래시 잔재는 mtime TTL로 무시한다."""
    agent = os.environ.get("HARNESS_AGENT_NAME")
    if agent in ISSUE_CREATORS:
        return True
    now = time.time()
    for a in ISSUE_CREATORS:
        p = flag_path(PREFIX, f"{a}_active")
        if not os.path.exists(p):
            continue
        if (now - os.path.getmtime(p)) < FALLBACK_FLAG_TTL_SEC:
            return True
    return False


def main():
    try:
        json.load(sys.stdin)  # consume stdin
    except Exception:
        pass

    # ISSUE_CREATORS 에이전트(qa, designer) 활성이면 허용
    if _is_issue_creator_active():
        sys.exit(0)

    # 그 외 — 메인 Claude 직접 호출 차단 (harness_active 여부 무관)
    deny(
        "❌ 메인 Claude의 이슈 생성/수정 직접 호출 금지 (orchestration/policies.md 정책 3).\n"
        "이슈 생성/수정은 QA/designer 에이전트가 처리합니다.\n"
        "버그: /qa 스킬 → QA 에이전트가 분석·이슈 생성/수정 → python3 executor.py impl --issue <N>\n"
        "구현: python3 executor.py impl --impl <path> 으로 진입하면 architect가 이슈를 생성합니다."
    )


if __name__ == "__main__":
    main()
