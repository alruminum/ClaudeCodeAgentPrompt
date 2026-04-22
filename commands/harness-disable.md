---
name: harness-disable
description: 현재 프로젝트(cwd)를 하네스 화이트리스트에서 제거해 전역 훅 적용을 중단한다.
---

# /harness-disable

현재 Claude Code cwd를 `~/.claude/harness-projects.json`에서 제거한다. 이후 이 프로젝트에서는 전역 하네스 훅이 no-op이다.

Bash 도구로 아래 스크립트 실행.

```bash
python3 << 'PY'
import json, os, sys
from pathlib import Path

wl = Path.home() / ".claude" / "harness-projects.json"
here = os.path.realpath(os.getcwd())

if not wl.exists():
    print("[harness-disable] 화이트리스트 파일 없음 — 아무 동작 안 함")
    sys.exit(0)

try:
    data = json.loads(wl.read_text())
except Exception:
    print("[harness-disable] 화이트리스트 JSON 파싱 실패 — 중단")
    sys.exit(1)

before = data.get("projects", [])
# here 그 자체를 제거. 상위 경로 등록분은 유지.
after = [p for p in before if os.path.realpath(os.path.expanduser(p)) != here]

if len(before) == len(after):
    print(f"[harness-disable] 정확 일치 없음 — 제거 대상 없음: {here}")
    # 상위 경로로 매칭되는 경우 안내
    for p in before:
        root = os.path.realpath(os.path.expanduser(p))
        if here.startswith(root + os.sep):
            print(f"  ⚠️ 상위 경로가 등록됨: {root}")
            print(f"     여기에서는 그 등록을 해제해야 cwd도 비활성화된다")
    sys.exit(0)

data["projects"] = after
wl.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print(f"[harness-disable] 제거 완료: {here}")
print(f"  남은 활성 프로젝트 수: {len(after)}")
PY
```

실행 후 결과 메시지를 유저에게 그대로 보여준다.
