#!/usr/bin/env python3
"""
PostToolUse(Bash) hook: HARNESS_DONE / IMPLEMENTATION_ESCALATE / HARNESS_CRASH 감지
→ /tmp/harness_review_trigger.json 저장 → Stop hook이 /harness-review 자동 주입.
"""
import sys
import os
import json
import glob

MARKERS = ("HARNESS_DONE", "IMPLEMENTATION_ESCALATE", "HARNESS_CRASH", "KNOWN_ISSUE",
           "PLAN_VALIDATION_PASS", "PLAN_VALIDATION_ESCALATE")


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    resp = str(d.get("tool_response", ""))

    matched = next((m for m in MARKERS if m in resp), None)
    if not matched:
        sys.exit(0)

    # 이미 트리거 파일 있으면 중복 방지
    if os.path.exists("/tmp/harness_review_trigger.json"):
        sys.exit(0)

    # 가장 최신 JSONL 로그 탐색 (harness-logs 하위 전체)
    search_dirs = [
        os.path.expanduser("~/.claude/harness-logs"),
    ]
    # CWD .claude/harness-logs도 탐색
    cwd_logs = os.path.join(os.getcwd(), ".claude", "harness-logs")
    if os.path.isdir(cwd_logs):
        search_dirs.append(cwd_logs)

    all_jsonl = []
    for base in search_dirs:
        all_jsonl.extend(glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True))

    latest = max(all_jsonl, key=os.path.getmtime) if all_jsonl else None

    trigger = {
        "marker": matched,
        "jsonl": latest,
    }
    with open("/tmp/harness_review_trigger.json", "w") as f:
        json.dump(trigger, f, ensure_ascii=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
