#!/usr/bin/env python3
"""
orch-rules-first.py — PreToolUse(Edit/Write) 전역 훅 (경고형)
단일 소스 원칙 유도: 하네스 인프라 파일 수정 시 orchestration-rules.md 선행
수정을 권장한다. 차단은 하지 않고 경고만 주입한다(버그픽스·구현 디테일까지
규칙 파일에 억지로 밀어 넣는 것을 방지).

대상 파일 (하네스 인프라):
  - harness/*.py, harness/*.sh, setup-{harness,agents}.sh, hooks/*.py
  - agents/*.md

동작:
  - orchestration-rules.md 수정 감지 → /tmp/_orch_rules_touched 플래그 생성
  - 하네스 인프라 파일 수정 시 플래그 없으면 → additionalContext 경고 주입 (통과)
  - orchestration-rules.md 자체 수정은 항상 통과 (플래그 설정만)
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
    # harness Python 모듈
    r'harness/executor\.py',
    r'harness/core\.py',
    r'harness/config\.py',
    r'harness/impl_router\.py',
    r'harness/impl_loop\.py',
    r'harness/helpers\.py',
    r'harness/plan_loop\.py',
    r'harness/review_agent\.py',
    # harness/*.sh 래퍼/레거시
    r'harness/executor\.sh',
    r'harness/design\.sh',
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

    # 하네스 인프라 또는 에이전트 정의 파일 수정 → 플래그 없으면 경고만 주입
    if is_harness_infra(fp) or is_agent_def(fp):
        if not flag_is_fresh():
            fname = os.path.basename(fp)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        f"⚠️ [orch_rules_first] {fname} 수정 중 — orchestration-rules.md "
                        "선행 업데이트는 권장이지만 강제는 아닙니다. 규칙 수준의 변경이면 "
                        "먼저 orchestration-rules.md를 고치고, 버그픽스·구현 디테일이면 "
                        "이 메시지를 무시해도 됩니다."
                    )
                }
            }))
            sys.exit(0)

    # 그 외 파일 → 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
