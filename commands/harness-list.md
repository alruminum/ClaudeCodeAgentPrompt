---
name: harness-list
description: 하네스 화이트리스트에 등록된 프로젝트 목록 + 현재 cwd의 활성 여부를 출력한다.
---

# /harness-list

`~/.claude/harness-projects.json` 목록 출력 + 현재 cwd 활성 여부 확인.

Bash 도구로 아래 스크립트 실행.

```bash
python3 << 'PY'
import json, os
from pathlib import Path

wl = Path.home() / ".claude" / "harness-projects.json"
here = os.path.realpath(os.getcwd())

if not wl.exists():
    print("[harness-list] 화이트리스트 파일 없음 → 모든 프로젝트 disabled")
    print("")
    print(f"현재 cwd: {here}")
    print("상태: ❌ disabled")
    print("활성화: /harness-enable")
else:
    try:
        data = json.loads(wl.read_text())
    except Exception:
        print("[harness-list] JSON 파싱 실패")
        raise SystemExit(1)

    projects = data.get("projects", [])
    print(f"[harness-list] 등록 프로젝트 {len(projects)}개:")
    active = False
    matched = None
    for p in projects:
        root = os.path.realpath(os.path.expanduser(p))
        mark = ""
        if here == root:
            mark = "  ← 현재 (정확 일치)"
            active = True
            matched = root
        elif here.startswith(root + os.sep):
            mark = "  ← 현재 (상위 경로)"
            active = True
            matched = root
        print(f"  • {root}{mark}")

    print("")
    print(f"현재 cwd: {here}")
    if active:
        print(f"상태: ✅ enabled (매칭: {matched})")
    else:
        print("상태: ❌ disabled")
        print("활성화: /harness-enable")
PY
```

실행 후 출력을 유저에게 그대로 보여준다.
