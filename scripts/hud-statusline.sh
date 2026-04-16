#!/bin/bash
# HUD statusline — 화면 하단에 하네스 진행 상태 한 줄 표시
# settings.json의 statusLine.command로 등록하여 사용
# stdin: Claude Code 세션 JSON (사용 안 함)
# stdout: 한 줄 상태 텍스트

cat > /dev/null  # drain stdin

# prefix 결정
PREFIX=$(python3 -c "
import json
from pathlib import Path
cp = Path.cwd() / '.claude' / 'harness.config.json'
if cp.exists():
    print(json.load(open(cp)).get('prefix', ''))
else:
    import re
    raw = Path.cwd().name.lower()
    print(re.sub(r'[^a-z0-9]', '', raw)[:8])
" 2>/dev/null)

if [[ -z "$PREFIX" ]]; then
    exit 0
fi

HUD_FILE="$(pwd)/.claude/harness-state/.${PREFIX}_hud"

if [[ ! -f "$HUD_FILE" ]]; then
    exit 0
fi

python3 -c "
import json, sys
from pathlib import Path

try:
    d = json.loads(Path('${HUD_FILE}').read_text())
except:
    sys.exit(0)

depth = d.get('depth', '?')
cost = d.get('cost', 0)
budget = d.get('budget', 20)
elapsed = d.get('elapsed', 0)
m, s = divmod(elapsed, 60)
agents = d.get('agents', [])
total = len(agents)
done = sum(1 for a in agents if a.get('status') in ('done', 'skip'))
pct = int(done / total * 100) if total else 0
status = d.get('status', '')

# 현재 running 에이전트 찾기
running = next((a['name'] for a in agents if a.get('status') == 'running'), '')

if status == 'done':
    print(f'harness {depth} {pct}% done | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s')
elif running:
    print(f'harness {depth} {pct}% | {running} | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s')
else:
    print(f'harness {depth} {pct}% | \${cost:.2f}/\${budget:.0f} | {m}m{s:02d}s')
" 2>/dev/null
