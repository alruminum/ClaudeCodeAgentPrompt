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
from harness_common import get_prefix, deny, flag_path, FLAGS, ISSUE_CREATORS, is_harness_enabled
import session_state as ss

PREFIX = get_prefix()


def _is_issue_creator_active(stdin_data=None):
    """Phase 3: live.json 단일 소스로 판정.
    훅 stdin에서 session_id 파싱 → live.json.agent 읽기.
    ISSUE_CREATORS에 속하면 True.
    """
    agent = ss.active_agent(stdin_data=stdin_data)
    return agent in ISSUE_CREATORS


def main():
    # 화이트리스트 가드 — `~/.claude/harness-projects.json` 등록된 프로젝트에서만 동작.
    if not is_harness_enabled():
        sys.exit(0)

    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}

    # ISSUE_CREATORS 에이전트(qa, designer) 활성이면 허용
    if _is_issue_creator_active(d):
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
