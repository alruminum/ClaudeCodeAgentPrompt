---
description: 현재 프로젝트의 harness 훅 상태와 워크플로우 플래그를 확인한다.
argument-hint: ""
---

# /harness-status

현재 harness 상태를 점검한다. (Phase 3: session-isolated 상태 덤프 포함)

## 실행

아래 명령어를 실행하고 결과를 유저에게 출력한다:

```bash
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/.claude/hooks')
import session_state as ss
snap = ss.diagnostic_snapshot()
print(json.dumps(snap, indent=2, ensure_ascii=False))
"
```

추가로 세션/이슈 lock 현황:

```bash
python3 -c "
import sys, os, json
from pathlib import Path
sys.path.insert(0, '$HOME/.claude/hooks')
import session_state as ss
root = ss.state_root()
sessions = sorted(d.name for d in (root/'.sessions').iterdir() if d.is_dir()) if (root/'.sessions').is_dir() else []
issues = []
if (root/'.issues').is_dir():
    for d in (root/'.issues').iterdir():
        lock = d/'lock'
        if lock.exists():
            data = ss.read_json(lock) or {}
            issues.append({'issue': d.name, 'holder': data.get('session_id','')[:8], 'pid': data.get('pid'), 'mode': data.get('mode')})
print('sessions:', sessions)
print('issue_locks:', json.dumps(issues, indent=2))
print('global:', json.dumps(ss.get_global_signal(), indent=2))
"
```

## 출력 형식

```
[Harness Status]
current_session: <sid>
active_agent: <agent or none>
harness_active: <true/false>
sessions: [sid1, sid2, ...]
issue_locks: [...]
global_signal: {...}
```
