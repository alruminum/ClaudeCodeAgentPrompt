#!/usr/bin/env python3
"""
file-ownership-gate.py — PreToolUse(Edit/Write) 글로벌 훅
에이전트 소유 파일 보호: docs/* (architect), src/* (engineer).
프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
"""
import sys
import json
import os
import re

PREFIX = os.environ.get("HARNESS_PREFIX", "mb")

# 설계 문서 패턴 (architect/designer/product-planner 소유)
DOCS_PATTERN = re.compile(
    r"(docs/(architecture|game-logic|db-schema|sdk|ui-spec|domain-logic|reference)[^/]*[.]md"
    r"|(^|/)prd[.]md"
    r"|(^|/)trd[.]md)"
)


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

    fp = d.get("tool_input", {}).get("file_path", "")
    if not fp:
        sys.exit(0)

    # docs/* 설계 문서 차단 — architect_active 플래그 시 통과
    if DOCS_PATTERN.search(fp):
        if not os.path.exists(f"/tmp/{PREFIX}_architect_active"):
            deny(f"❌ {fp} 는 에이전트 소유 파일. 직접 수정 금지 → architect/designer/product-planner 에이전트 호출.")

    # src/** 소스 차단 — src/__tests__/ 제외, harness_active 시 통과
    is_src = bool(re.search(r"(^|/)src/", fp))
    is_test = bool(re.search(r"(^|/)src/__tests__/", fp))
    if is_src and not is_test:
        if not os.path.exists(f"/tmp/{PREFIX}_harness_active"):
            deny("❌ src/** 는 engineer 에이전트 소유. 직접 수정 금지 → "
                 "architect Mode B → validator Mode A PASS → engineer 순서로 진행.")

    sys.exit(0)


if __name__ == "__main__":
    main()
