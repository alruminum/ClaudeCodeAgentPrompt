---
description: 현재 프로젝트의 하네스 HUD를 실시간 모니터링하는 전용 세션. 한 번 띄우면 무한 대기하며 하네스 루프가 시작/종료될 때마다 자동으로 표시한다.
argument-hint: ""
---

# /harness-monitor

별도 Claude Code 세션에서 실행하는 **전용 모니터링 세션**. 한 번 띄우면 무한 대기하며, 하네스 루프가 시작될 때마다 HUD를 표시하고 종료되면 대기 상태로 돌아간다.

## 사용법

```
터미널 1: claude → 하네스 실행 (반복 사용)
터미널 2: claude → /harness-monitor (한 번만 실행, 계속 떠 있음)
```

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

HUD_DIR="$(pwd)/.claude/harness-state"
HUD_FILE="${HUD_DIR}/.${PREFIX}_hud"

echo "📡 하네스 HUD 모니터 (PREFIX=${PREFIX})"
echo "   HUD 파일: ${HUD_FILE}"
echo "   모드: 전용 세션 (무한 대기, Ctrl+C로 종료)"
echo ""

python3 -c "
import json, time, sys, os
from pathlib import Path
from datetime import datetime

hud_file = Path('${HUD_FILE}')
prev = ''
run_count = 0
was_active = False

def render_hud(d):
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

    lines = []
    lines.append(f'━━━ 📊 depth={depth} | attempt {attempt}/{max_att} | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s | {pct}% ━━━')
    lines.append('')
    for i, ag in enumerate(agents, 1):
        name = ag.get('name', '?')
        status = ag.get('status', 'pending')
        ag_elapsed = ag.get('elapsed', 0)
        ag_cost = ag.get('cost', 0)

        if status == 'done':
            bar = '\u2593' * 20 + ' \u2705'
            detail = f' {ag_elapsed}s \${ag_cost:.2f}'
        elif status == 'fail':
            bar = '\u2593' * 20 + ' \u274c'
            detail = f' {ag_elapsed}s'
        elif status == 'skip':
            bar = '\u2591' * 20 + ' \u23ed'
            detail = f' {ag.get(\"reason\", \"\")}'
        elif status == 'running':
            bar = '\u2593' * 10 + '\u2591' * 10 + ' \u23f3'
            detail = f' {ag_elapsed}s...'
        else:
            bar = '\u2591' * 20 + '   '
            detail = ''
        lines.append(f' [{i}/{total}] {name:<20s} {bar}{detail}')

    # 로그 라인 표시
    log = d.get('log', [])
    if log:
        lines.append('')
        for l in log[-5:]:
            lines.append(f'  > {l}')

    lines.append('')
    return '\n'.join(lines)

print('\u23f3 하네스 대기 중... (하네스가 시작되면 자동으로 HUD 표시)')
print('')

while True:
    try:
        if hud_file.exists():
            raw = hud_file.read_text()
            if raw != prev:
                if not was_active:
                    run_count += 1
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f'')
                    print(f'╔══════════════════════════════════════════════════════╗')
                    print(f'║  🚀 하네스 루프 #{run_count} 시작 ({ts})                  ║')
                    print(f'╚══════════════════════════════════════════════════════╝')
                    print('')
                    was_active = True

                prev = raw
                try:
                    d = json.loads(raw)
                    print(render_hud(d))
                except json.JSONDecodeError:
                    pass
        else:
            if was_active:
                ts = datetime.now().strftime('%H:%M:%S')
                print(f'✅ 하네스 루프 #{run_count} 종료 ({ts})')
                print(f'')
                print(f'\u23f3 다음 하네스 대기 중...')
                print('')
                was_active = False
                prev = ''

        time.sleep(1)

    except KeyboardInterrupt:
        print(f'\n모니터링 종료. (총 {run_count}회 관찰)')
        break
    except Exception:
        time.sleep(1)
"
```

## 유저에게 안내

이 스킬은 **전용 모니터링 세션**이다.
- 한 번 실행하면 Ctrl+C로 종료할 때까지 계속 떠 있는다
- 하네스 루프가 시작되면 자동으로 HUD를 표시한다
- 하네스 루프가 끝나면 "다음 하네스 대기 중..."으로 돌아간다
- 여러 루프를 연속으로 관찰할 수 있다 (루프 #1, #2, #3...)
