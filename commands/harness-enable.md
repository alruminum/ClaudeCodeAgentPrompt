---
name: harness-enable
description: 현재 프로젝트(cwd)를 하네스 화이트리스트에 등록해 전역 훅을 활성화한다.
---

# /harness-enable

현재 Claude Code cwd를 `~/.claude/harness-projects.json`에 추가한다. 등록된 프로젝트에서만 전역 하네스 훅(`~/.claude/hooks/*.py`)이 동작한다. 등록 안 된 프로젝트는 훅이 조용히 no-op이라 일반 코드 작업 시 태클 없음.

Bash 도구로 아래 스크립트 실행.

```bash
python3 << 'PY'
import json, os, sys
from pathlib import Path

wl = Path.home() / ".claude" / "harness-projects.json"
here = os.path.realpath(os.getcwd())

data = {"projects": []}
if wl.exists():
    try:
        data = json.loads(wl.read_text())
    except Exception:
        pass
projects = data.get("projects", [])

# 이미 등록됐거나 상위 경로가 이미 등록됐으면 스킵
for p in projects:
    root = os.path.realpath(os.path.expanduser(p))
    if here == root or here.startswith(root + os.sep):
        print(f"[harness-enable] 이미 등록됨 (경로: {root})")
        sys.exit(0)

projects.append(here)
data["projects"] = sorted(set(projects))
wl.parent.mkdir(parents=True, exist_ok=True)
wl.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print(f"[harness-enable] 등록 완료: {here}")
print(f"  현재 활성 프로젝트 수: {len(data['projects'])}")
PY
```

실행 후 "등록 완료" 메시지를 유저에게 그대로 보여준다.
