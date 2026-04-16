---
description: 하네스 이벤트 로그를 실시간으로 표시. 별도 터미널에서 실행하면 에이전트 시작/완료가 주욱 나옴.
argument-hint: ""
---

# /harness-monitor

하네스 이벤트 로그를 `tail -f`로 스트리밍한다. 별도 터미널에서 실행:

```
! tail -f .claude/harness-state/.mb_events
```

또는 prefix 자동 감지:

```bash
PREFIX=$(python3 -c "
import json
from pathlib import Path
cp = Path.cwd() / '.claude' / 'harness.config.json'
if cp.exists():
    print(json.load(open(cp)).get('prefix', 'proj'))
else:
    import re
    raw = Path.cwd().name.lower()
    print(re.sub(r'[^a-z0-9]', '', raw)[:8] or 'proj')
" 2>/dev/null || echo "proj")

echo "📡 하네스 모니터 (PREFIX=${PREFIX})"
echo "   tail -f .claude/harness-state/.${PREFIX}_events"
echo ""
tail -f ".claude/harness-state/.${PREFIX}_events" 2>/dev/null || echo "⏳ 이벤트 파일 없음 — 하네스 시작 후 다시 실행"
```

출력 예시:
```
[10:23:15] architect 시작
[10:25:01] architect → LIGHT_PLAN_READY
[10:25:01] architect 완료 (97s, $0.30)
[10:25:02] Plan Validation → PASS
[10:25:02] depth: simple
[10:25:03] engineer 시작
[10:26:20] engineer 완료 (77s, $0.36)
[10:26:20] pr-reviewer → LGTM
[10:26:21] HARNESS_DONE (attempt 1)
```
