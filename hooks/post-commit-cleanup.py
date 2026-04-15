#!/usr/bin/env python3
"""
post-commit-cleanup.py — PostToolUse(Bash) 글로벌 훅
git commit 성공 후 플래그 정리.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
from harness_common import get_prefix, get_state_dir, FLAGS

PREFIX = get_prefix()


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = d.get("tool_input", {}).get("command", "")
    resp = str(d.get("tool_response", ""))

    if not re.search(r"git\s+commit", cmd):
        sys.exit(0)

    # 성공 판정
    if "error" in resp.lower() or "failed" in resp.lower():
        sys.exit(0)

    # commit 성공 → 1회성 플래그 삭제
    for name in [FLAGS.PR_REVIEWER_LGTM, FLAGS.TEST_ENGINEER_PASSED]:
        p = os.path.join(get_state_dir(), f"{PREFIX}_{name}")
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    # orch-rules-first 플래그 리셋 — 커밋 단위로 강제
    # orchestration-rules.md 수정 → 스크립트 수정 → 커밋 = 하나의 단위
    # 다음 기능은 orchestration-rules.md를 다시 먼저 수정해야 함
    orch_flag = "/tmp/_orch_rules_touched"
    if os.path.exists(orch_flag):
        try:
            os.remove(orch_flag)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
