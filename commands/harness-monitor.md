---
description: 현재 프로젝트의 하네스 루프 실행 로그를 실시간 모니터링한다. /harness-monitor 실행 시 PREFIX를 자동 감지해 tail -f로 디버그 로그를 스트리밍한다.
argument-hint: ""
---

# /harness-monitor

별도 Claude Code 세션에서 실행하여 하네스 진행 상태를 실시간 모니터링한다.

## 사용법

```
터미널 1: claude → 하네스 실행 중 (executor.py 포어그라운드)
터미널 2: claude → /harness-monitor (이 스킬)
```

## 실행

아래 스크립트를 Bash로 실행한다:

```bash
# PREFIX 자동 감지
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

HUD_DIR=".claude/harness-state"
HUD_FILE="${HUD_DIR}/${PREFIX}_hud.json"

echo "📡 하네스 HUD 모니터 (PREFIX=${PREFIX})"
echo "   HUD 파일: ${HUD_FILE}"
echo "   종료: Ctrl+C"
echo ""

if [ ! -f "$HUD_FILE" ]; then
  echo "⏳ 하네스가 아직 시작되지 않았습니다. HUD 파일 대기 중..."
  echo ""
fi

# 1초마다 HUD JSON을 읽어 시각적으로 렌더링
python3 -c "
import json, time, sys
from pathlib import Path

hud_file = Path('${HUD_FILE}')
prev = ''

while True:
    try:
        if not hud_file.exists():
            time.sleep(1)
            continue

        raw = hud_file.read_text()
        if raw == prev:
            time.sleep(1)
            continue
        prev = raw

        d = json.loads(raw)
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

        # 클리어 + 렌더
        print('\033[2J\033[H', end='')  # 화면 클리어
        print(f'━━━ 📊 depth={depth} | attempt {attempt}/{max_att} | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s | {pct}% ━━━')
        print()
        for i, ag in enumerate(agents, 1):
            name = ag.get('name', '?')
            status = ag.get('status', 'pending')
            ag_elapsed = ag.get('elapsed', 0)
            ag_cost = ag.get('cost', 0)

            if status == 'done':
                bar = '▓' * 20 + ' ✅'
                detail = f' {ag_elapsed}s \${ag_cost:.2f}'
            elif status == 'fail':
                bar = '▓' * 20 + ' ❌'
                detail = f' {ag_elapsed}s'
            elif status == 'skip':
                bar = '░' * 20 + ' ⏭'
                detail = f' {ag.get(\"reason\", \"\")}'
            elif status == 'running':
                bar = '▓' * 10 + '░' * 10 + ' ⏳'
                detail = f' {ag_elapsed}s...'
            else:
                bar = '░' * 20 + '   '
                detail = ''

            print(f' [{i}/{total}] {name:<20s} {bar}{detail}')

        print()
        print('━' * 60)
        time.sleep(1)

    except KeyboardInterrupt:
        print('\n모니터링 종료.')
        break
    except Exception:
        time.sleep(1)
"
```

## 유저에게 안내

위 스크립트 실행 결과가 대화창에 실시간으로 표시된다.

하네스가 실행 중이 아니면 "HUD 파일 대기 중..." 메시지를 보여주고, 하네스가 시작되면 자동으로 모니터링이 시작된다.

하네스가 완료되면 HUD 파일이 삭제되므로 모니터링이 자동 종료된다.
