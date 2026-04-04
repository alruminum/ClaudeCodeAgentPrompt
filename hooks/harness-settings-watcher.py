#!/usr/bin/env python3
"""
Global PostToolUse hook: .claude/settings.json hooks 섹션 변경 감지
→ ~/.claude/setup-harness.sh 동기화 리마인드
"""
import sys
import json
import re

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

fp = d.get("tool_input", {}).get("file_path", "")
if not re.search(r"\.claude/settings\.json$", fp):
    sys.exit(0)

old = d.get("tool_input", {}).get("old_string", "")
new = d.get("tool_input", {}).get("new_string", "")
combined = old + new

hooks_changed = any(k in combined for k in [
    '"hooks"', "PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart"
])

if hooks_changed:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "⚠️ [GLOBAL HARNESS] settings.json hooks 섹션 변경됨\n"
                "→ PreToolUse/PostToolUse 훅을 추가/수정했다면 ~/.claude/setup-harness.sh에도 반영 필요\n"
                "→ allowedTools / permissions / enabledPlugins 변경은 해당 없음"
            )
        }
    }))
