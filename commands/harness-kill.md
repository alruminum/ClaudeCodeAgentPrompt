# 하네스 중단

현재 실행 중인 하네스 루프를 즉시 중단합니다. (전역 신호 — 모든 세션에 전파)

Bash 도구로 실행:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
import session_state as ss
ss.set_global_signal(harness_kill=True)
# Phase 4: 현 세션의 활성 스킬도 즉시 청소 (Stop 훅 재강화 루프 차단)
sid = ss.current_session_id()
cleared = ss.clear_active_skill(sid) if sid else False
msg = '킬 스위치 활성화. 다음 에이전트 호출 전에 루프가 중단됩니다.'
if cleared:
    msg += ' (활성 스킬도 청소됨)'
print(msg)
"
```
