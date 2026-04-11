#!/usr/bin/env python3
"""
orch-rules-first.py — PreToolUse(Edit/Write) 전역 훅
단일 소스 원칙 강제: 하네스 인프라 파일 수정 시 orchestration-rules.md 선행 수정 확인.

대상 파일 (하네스 인프라):
  - harness/executor.sh, harness/impl.sh, harness/impl_{simple,std,deep}.sh, harness/design.sh
  - harness/plan.sh, setup-harness.sh, setup-agents.sh
  - hooks/harness-router.py, hooks/harness-session-start.py
  - agents/*.md (에이전트 정의 파일)

동작:
  - orchestration-rules.md 수정 감지 → /tmp/_orch_rules_touched 플래그 생성
  - 하네스 인프라 파일 수정 시 플래그 없으면 → deny + 안내 메시지
  - orchestration-rules.md 자체 수정은 항상 허용 (플래그 설정만)
"""
import sys
import json
import os
import re
import time

FLAG = "/tmp/_orch_rules_touched"
# 세션 타임아웃: 2시간 (플래그가 오래되면 무효)
SESSION_TIMEOUT = 7200

HARNESS_INFRA_PATTERNS = [
    # harness/*.sh 스크립트 (디렉토리 구조)
    r'harness/executor\.sh',
    r'harness/impl\.sh',
    r'harness/impl_simple\.sh',
    r'harness/impl_std\.sh',
    r'harness/impl_deep\.sh',
    r'harness/impl_helpers\.sh',
    r'harness/design\.sh',
    r'harness/plan\.sh',
    r'harness/utils\.sh',
    # 셋업 스크립트
    r'setup-harness\.sh',
    r'setup-agents\.sh',
    # 모든 훅 파이썬 파일
    r'hooks/[^/]+\.py$',
]

def is_orch_rules(fp):
    return bool(re.search(r'orchestration-rules\.md$', fp)) or \
           bool(re.search(r'orchestration/[^/]+\.md$', fp))

def is_harness_infra(fp):
    return any(re.search(p, fp) for p in HARNESS_INFRA_PATTERNS)

def is_agent_def(fp):
    return bool(re.search(r'[./]claude/agents/[^/]+\.md$', fp))

def flag_is_fresh():
    if not os.path.exists(FLAG):
        return False
    age = time.time() - os.path.getmtime(FLAG)
    return age < SESSION_TIMEOUT

def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    fp = d.get("tool_input", {}).get("file_path", "")
    if not fp:
        sys.exit(0)

    # orchestration-rules.md 수정 → 플래그 설정, 항상 허용
    if is_orch_rules(fp):
        open(FLAG, "w").close()
        sys.exit(0)

    # 하네스 인프라 또는 에이전트 정의 파일 수정 → 플래그 확인
    if is_harness_infra(fp) or is_agent_def(fp):
        if not flag_is_fresh():
            fname = os.path.basename(fp)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"❌ [orch_rules_first] {fname} 수정 전 orchestration-rules.md를 먼저 업데이트하세요.\n"
                        "단일 소스 원칙: orchestration-rules.md → 스크립트/에이전트 순서.\n"
                        "orchestration-rules.md를 먼저 수정하면 이 게이트가 자동 해제됩니다."
                    )
                }
            }))
            sys.exit(0)

    # 그 외 파일 → 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
