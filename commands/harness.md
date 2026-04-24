---
name: harness
description: 하네스 관리 통합 진입점. 인자 없으면 현재 상태 + 사용 가능 동작 안내. 인자로 `on/off/ls/watch/review/kill` 서브동작 실행. 외우기 싫을 때 이거 하나만 치면 된다.
---

# /harness

하네스 관리 단일 진입점. args에 따라 분기한다.

## 동작 분기

args에서 첫 단어를 추출해 아래처럼 라우팅한다.

| args | 동작 | 내부 실행 |
|---|---|---|
| `on` / `enable` | 현재 cwd 화이트리스트 등록 | `/harness-enable` 스킬 호출 |
| `off` / `disable` | 현재 cwd 화이트리스트 제거 | `/harness-disable` 스킬 호출 |
| `ls` / `list` | 화이트리스트 목록 + 현재 cwd 활성 여부 | `/harness-list` 스킬 호출 |
| `watch` / `monitor` | 이벤트 로그 실시간 스트림 | `/harness-monitor` 스킬 호출 |
| `review` | 최근 JSONL 로그 분석 | `/harness-review` 스킬 호출 |
| `kill` / `stop` | 실행 중 하네스 강제 중단 | `/harness-kill` 스킬 호출 |
| (없음) | 현재 상태 출력 + 동작 안내 | 아래 파이썬 블록 |

## 인자 없을 때 (기본)

Bash 도구로 아래 스크립트를 실행해서 현재 상태 + 사용 가능 동작을 한 번에 보여준다.

```bash
python3 << 'PY'
import json, os
from pathlib import Path

wl = Path.home() / ".claude" / "harness-projects.json"
here = os.path.realpath(os.getcwd())

# 화이트리스트 상태
if not wl.exists():
    enabled = False
    matched = None
    projects = []
else:
    try:
        data = json.loads(wl.read_text())
    except Exception:
        data = {"projects": []}
    projects = data.get("projects", [])
    enabled = False
    matched = None
    for p in projects:
        root = os.path.realpath(os.path.expanduser(p))
        if here == root or here.startswith(root + os.sep):
            enabled = True
            matched = root
            break

# 활성 하네스 세션 (가볍게)
sessions_root = Path.home() / ".claude" / "harness-state" / ".sessions"
active_sessions = []
if sessions_root.is_dir():
    active_sessions = sorted(d.name[:8] for d in sessions_root.iterdir() if d.is_dir())

print(f"현재 cwd: {here}")
print(f"하네스 활성: {'✅ enabled' if enabled else '❌ disabled'}"
      + (f"  (매칭: {matched})" if matched else ""))
print(f"등록 프로젝트 {len(projects)}개:")
for p in projects:
    root = os.path.realpath(os.path.expanduser(p))
    mark = "  ← 현재" if matched == root else ""
    print(f"  • {root}{mark}")
if active_sessions:
    print(f"활성 세션: {', '.join(active_sessions)}")
print("")
print("사용 가능 동작 (`/harness <동작>`):")
print("  on / off       — 활성화 / 비활성화")
print("  ls             — 화이트리스트 목록")
print("  watch          — 실시간 이벤트 스트림")
print("  review         — 최근 run 로그 분석")
print("  kill           — 실행 중 하네스 중단")
PY
```

## 처리 방식

1. `args` 변수에서 첫 단어 추출 (공백·탭 기준)
2. 위 표에서 매칭되는 동작 찾아 해당 스킬을 Skill 도구로 호출
3. 매칭 안 되는 args면 "알 수 없는 동작: <args>" + 표 출력
4. args 없으면 파이썬 블록 실행
