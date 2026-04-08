#!/usr/bin/env python3
"""
Global PostToolUse(Edit) hook: .claude/settings.json 변경 감시

1. 전역 settings.json hooks 변경 → setup-harness.sh 동기화 리마인드
2. 프로젝트 settings.json에 hooks 추가 감지 → 즉시 제거 경고
   (모든 훅은 전역에서만 관리 — 프로젝트에는 env + allowedTools만)
"""
import sys
import json
import os
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

# 전역 settings.json인지 프로젝트 settings.json인지 구분
global_settings = os.path.expanduser("~/.claude/settings.json")
is_global = os.path.abspath(fp) == os.path.abspath(global_settings)

if is_global and hooks_changed:
    # 전역 → 동기화 리마인드
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
elif not is_global and hooks_changed:
    # 프로젝트 → 즉시 제거 경고
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "🚫 [HARNESS] 프로젝트 settings.json에 hooks 섹션 추가 금지!\n"
                "모든 훅은 ~/.claude/settings.json(전역)에서만 관리한다.\n"
                "프로젝트 settings.json에는 env + allowedTools만 허용.\n"
                "→ 방금 추가한 hooks를 즉시 제거하라."
            )
        }
    }))
