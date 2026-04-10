#!/usr/bin/env python3
"""
issue-gate.py — PreToolUse(mcp__github__create_issue) 글로벌 훅
메인 Claude가 하네스 외부에서 GitHub 이슈를 직접 생성하는 것을 차단한다.

orchestration-rules.md 정책 1c:
"메인 Claude — 하네스 진입 전 GitHub 이슈 직접 생성 금지.
 이슈 생성은 하네스 내부에서 처리한다."
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from harness_common import get_prefix, deny, flag_exists

PREFIX = get_prefix()


def main():
    try:
        json.load(sys.stdin)  # consume stdin
    except Exception:
        pass

    if not flag_exists(PREFIX, "harness_active"):
        deny(
            f"❌ 메인 Claude의 create_issue 직접 호출 금지 (orchestration-rules.md 정책 1c).\n"
            f"이슈 생성은 하네스 내부에서 처리됩니다.\n"
            f"버그: executor.sh bugfix --bug '<설명>' 으로 진입하면 qa 에이전트가 이슈를 생성합니다.\n"
            f"구현: executor.sh impl --impl <path> 으로 진입하면 architect가 이슈를 생성합니다."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
