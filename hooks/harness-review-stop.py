#!/usr/bin/env python3
"""
Stop hook: /tmp/harness_review_trigger.json 존재 시
→ {"continue": true, "prompt": "/harness-review"} 반환
→ 메인 Claude가 /harness-review 스킬을 자동 실행 (리포트 항상 출력)
"""
import sys

# 화이트리스트 가드 import
import os as _os_hg
_sys_path = _os_hg.path.dirname(_os_hg.path.abspath(__file__))
if _sys_path not in __import__('sys').path:
    __import__('sys').path.insert(0, _sys_path)
from harness_common import is_harness_enabled
import os
import json

TRIGGER = "/tmp/harness_review_trigger.json"


def main():
    if not is_harness_enabled():
        sys.exit(0)
    if not os.path.exists(TRIGGER):
        sys.exit(0)

    try:
        trigger = json.loads(open(TRIGGER).read())
    except Exception:
        try:
            os.remove(TRIGGER)
        except Exception:
            pass
        sys.exit(0)

    os.remove(TRIGGER)

    jsonl = trigger.get("jsonl", "")
    if jsonl and os.path.exists(jsonl):
        # 절대 경로 → harness-logs/ 기준 상대경로로 변환
        base = os.path.expanduser("~/.claude/harness-logs/")
        if jsonl.startswith(base):
            arg = jsonl[len(base):]  # e.g. "mb/run_20260409_223459.jsonl"
        else:
            arg = jsonl
        prompt = f"/harness-review {arg}"
    else:
        prompt = "/harness-review"

    print(json.dumps({"continue": True, "prompt": prompt}))


if __name__ == "__main__":
    main()
