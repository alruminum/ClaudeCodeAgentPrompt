# 하네스 중단

현재 실행 중인 하네스 루프를 즉시 중단합니다. (전역 신호 — 모든 세션에 전파)

Bash 도구로 실행:
```bash
python3 -c "
import sys; sys.path.insert(0, '$HOME/.claude/hooks')
import session_state as ss
ss.set_global_signal(harness_kill=True)
print('킬 스위치 활성화. 다음 에이전트 호출 전에 루프가 중단됩니다.')
"
```
