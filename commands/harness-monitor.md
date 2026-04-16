---
description: 하네스 HUD 실시간 모니터. `/loop 5s /harness-monitor`로 반복 실행하면 대시보드처럼 동작한다.
argument-hint: ""
---

# /harness-monitor

하네스 HUD 스냅샷을 한 번 출력한다. `/loop 5s /harness-monitor`로 반복 실행하면 실시간 모니터링 대시보드가 된다.

## 실행

아래 스크립트를 Bash로 실행한다:

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

HUD_FILE="$(pwd)/.claude/harness-state/.${PREFIX}_hud"

python3 -c "
import json, sys
from pathlib import Path

hud_file = Path('${HUD_FILE}')
if not hud_file.exists():
    print('⏳ 하네스 미실행 (HUD 파일 없음)')
    sys.exit(0)

try:
    d = json.loads(hud_file.read_text())
except (json.JSONDecodeError, OSError):
    print('⚠️ HUD 파일 읽기 실패')
    sys.exit(0)

depth = d.get('depth', '?')
attempt = d.get('attempt', 0) + 1
max_att = d.get('max_attempts', 3)
cost = d.get('cost', 0)
budget = d.get('budget', 20)
elapsed = d.get('elapsed', 0)
m, s = divmod(elapsed, 60)
agents = d.get('agents', [])
total = len(agents)
done = sum(1 for a in agents if a.get('status') in ('done', 'skip'))
pct = int(done / total * 100) if total else 0
status = d.get('status', '')

if status == 'done':
    tag = ' ✅ 완료'
else:
    tag = ''

print(f'━━━ 📊 depth={depth} | attempt {attempt}/{max_att} | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s | {pct}%{tag} ━━━')
print()
for i, ag in enumerate(agents, 1):
    name = ag.get('name', '?')
    st = ag.get('status', 'pending')
    ag_elapsed = ag.get('elapsed', 0)
    ag_cost = ag.get('cost', 0)

    if st == 'done':
        bar = '\u2593' * 20 + ' \u2705'
        detail = f' {ag_elapsed}s \${ag_cost:.2f}'
    elif st == 'fail':
        bar = '\u2593' * 20 + ' \u274c'
        detail = f' {ag_elapsed}s'
    elif st == 'skip':
        bar = '\u2591' * 20 + ' \u23ed'
        detail = f' {ag.get(\"reason\", \"\")}'
    elif st == 'running':
        bar = '\u2593' * 10 + '\u2591' * 10 + ' \u23f3'
        detail = f' {ag_elapsed}s...'
    else:
        bar = '\u2591' * 20 + '   '
        detail = ''
    print(f' [{i}/{total}] {name:<20s} {bar}{detail}')

log = d.get('log', [])
if log:
    print()
    for l in log[-5:]:
        print(f'  > {l}')
"
```

## 사용법

```
/harness-monitor          # 원샷 스냅샷
/loop 5s /harness-monitor # 5초마다 반복 → 실시간 대시보드
```
