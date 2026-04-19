#!/usr/bin/env python3
"""session-agent-cleanup.py — UserPromptSubmit 훅.

Agent tool reject(유저 tool-use 거부), PreToolUse deny, 예외 종료 등으로 live.json.agent 필드가 고아로 남은 경우를 청소한다.

원인 체인:
  1. agent-gate.py(PreToolUse Agent)가 live.json.agent="qa" 등으로 기록.
  2. 유저가 Agent tool use reject → 실제 Agent 서브프로세스는 실행 안 됨.
  3. post-agent-flags.py(PostToolUse Agent)는 PreToolUse에서 막혔으므로 실행 안 됨.
  4. live.json.agent 필드가 영원히 남음.
  5. 이후 모든 Read/Write가 agent-boundary.py에서 stale agent로 판정돼 엉뚱한 제한 적용.

새 유저 프롬프트가 들어오는 시점엔 이전 Agent tool은 성공/실패/reject 중 하나로 종료된 상태이므로 agent 필드를 무조건 해제한다 (Agent는 동기 실행이라 턴 건너서 지속되지 않음).

settings.json UserPromptSubmit 체인 맨 앞에 등록되어야 한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json

try:
    import session_state as ss
except ImportError:
    sys.exit(0)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    sid = ss.session_id_from_stdin(d)
    if not sid:
        sid = ss.current_session_id()
    if not sid:
        sys.exit(0)

    try:
        ss.clear_live_field(sid, "agent")
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
