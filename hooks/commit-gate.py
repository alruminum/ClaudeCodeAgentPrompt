#!/usr/bin/env python3
"""
commit-gate.py — PreToolUse(Bash) 글로벌 훅
git commit 전 pr-reviewer LGTM 확인.
프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
"""
import sys
import json
import os
import re
import subprocess

PREFIX = os.environ.get("HARNESS_PREFIX", "mb")


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = d.get("tool_input", {}).get("command", "")

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

    # src 변경이 있으면 LGTM 필요
    if not os.path.exists(f"/tmp/{PREFIX}_pr_reviewer_lgtm"):
        deny(f"❌ git commit 전 pr-reviewer LGTM 필요. /tmp/{PREFIX}_pr_reviewer_lgtm 없음.")

    sys.exit(0)


if __name__ == "__main__":
    main()
