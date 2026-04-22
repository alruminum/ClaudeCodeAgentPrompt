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

# 화이트리스트 가드 import
import os as _os_hg
_sys_path = _os_hg.path.dirname(_os_hg.path.abspath(__file__))
if _sys_path not in __import__('sys').path:
    __import__('sys').path.insert(0, _sys_path)
from harness_common import is_harness_enabled
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

def _active_skill():
    """Phase 4: 활성 스킬 dict 또는 None. session_state 미가용 시 None 폴백."""
    try:
        import sys as _sys
        import os as _os
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import session_state as _ss  # type: ignore
        return _ss.active_skill()
    except Exception:
        return None


def main():
    if not is_harness_enabled():
        sys.exit(0)
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
            # Phase 4: 활성 스킬이 있으면 경고 톤을 그 맥락에 맞게 다듬어 노이즈 감소.
            # 스킬(/ux, /qa 등)이 정당한 흐름으로 시스템 파일을 손대는 경우가 흔하다.
            sk = _active_skill()
            sk_ctx = f" (스킬 '{sk.get('name')}' 진행 중)" if sk else ""
            fname = os.path.basename(fp)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        f"⚠️ [orch_rules_first] {fname} 수정 중{sk_ctx} — "
                        "orchestration-rules.md 선행 업데이트는 권장이지만 강제는 아닙니다. "
                        "규칙 수준의 변경이면 먼저 orchestration-rules.md를 고치고, "
                        "버그픽스·구현 디테일이면 이 메시지를 무시해도 됩니다."
                    )
                }
            }))
            sys.exit(0)

    # 그 외 파일 → 통과
    sys.exit(0)

if __name__ == "__main__":
    main()
