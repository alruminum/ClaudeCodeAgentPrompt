#!/bin/bash
# ~/.claude/setup-harness.sh
# 신규 프로젝트 루트에서 실행: bash ~/.claude/setup-harness.sh
# .claude/settings.json 에 Harness Engineering PreToolUse/PostToolUse 훅 세트를 설치한다.
#
# UserPromptSubmit / SessionStart 는 ~/.claude/settings.json(전역)에서 관리.
# 이 스크립트는 프로젝트별 게이트 훅만 생성한다.
#
# 설치되는 훅 (모두 글로벌 ~/.claude/hooks/*.py 참조 — 업데이트 시 전 프로젝트 즉시 반영):
#   PreToolUse(Read)       — agent-boundary.py (하네스 인프라 Read 차단)
#   PreToolUse(Edit/Write) — file-ownership-gate.py + agent-boundary.py
#   PreToolUse(Bash)       — commit-gate.py + harness-drift-check.py
#   PreToolUse(Agent)      — agent-gate.py
#   PostToolUse(Bash)      — post-commit-cleanup.py
#   PostToolUse(Agent)     — post-agent-flags.py
#
# prefix 전달: env.HARNESS_PREFIX → 각 훅에서 os.environ.get("HARNESS_PREFIX")로 읽음
#
# 주의: harness-loop.sh / harness-executor.sh는 글로벌(~/.claude/) 전용.
#       프로젝트에 복사하지 않으며, 기존 낡은 복사본은 자동 삭제.

set -e

# 선택적 인수
# --doc-name <name>  : 핵심 설계 문서 이름 (docs/<name>.md), Mode C 신선도 체크에 사용 (기본값: domain-logic)
# --repo <owner/repo>: GitHub repo — milestone 생성 시 setup-agents.sh에 전달용 (이 스크립트에서 직접 사용하지 않음)
DOC_NAME="domain-logic"
REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --doc-name) DOC_NAME="$2"; shift 2 ;;
    --repo)     REPO="$2";     shift 2 ;;
    *) shift ;;
  esac
done

SETTINGS_FILE=".claude/settings.json"
CONFIG_FILE=".claude/harness.config.json"
mkdir -p .claude

# 프로젝트 prefix 유도: 디렉토리명 → 소문자 → 영숫자만 → 최대 6자
RAW=$(basename "$PWD")
PREFIX=$(echo "$RAW" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9' | cut -c1-6)
if [ -z "$PREFIX" ]; then
  PREFIX="proj"
fi

echo "📌 프로젝트 prefix: ${PREFIX}_"
echo "📄 설정 파일: $SETTINGS_FILE"
echo "📋 핵심 설계 문서: docs/${DOC_NAME}.md"

# harness.config.json 생성 (없으면)
if [ ! -f "$CONFIG_FILE" ]; then
  echo "{\"prefix\": \"${PREFIX}\"}" > "$CONFIG_FILE"
  echo "📄 $CONFIG_FILE 생성 완료"
else
  echo "ℹ️  $CONFIG_FILE 이미 존재 — 유지"
fi

# 기존 settings.json 에서 allowedTools 보존
EXISTING_ALLOWED="[]"
if [ -f "$SETTINGS_FILE" ]; then
  EXISTING_ALLOWED=$(python3 -c "
import json, sys
with open('$SETTINGS_FILE') as f:
    d = json.load(f)
print(json.dumps(d.get('allowedTools', [])))
" 2>/dev/null || echo "[]")
  echo "⚠️  기존 settings.json 감지 — allowedTools 보존, hooks 덮어씀"
fi

# Python으로 settings.json 생성
python3 << PYEOF
import json

prefix = "${PREFIX}"
p = prefix
doc_name = "${DOC_NAME}"

hooks = {
    "PreToolUse": [
        # ── Read: 하네스 인프라 파일 읽기 차단 (에이전트 활성 시) ─────────
        {
            "matcher": "Read",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/agent-boundary.py 2>/dev/null || true"},
            ]
        },
        # ── Edit: 파일 소유권 + 에이전트 경계 (글로벌 훅 참조) ────────────
        {
            "matcher": "Edit",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/file-ownership-gate.py 2>/dev/null || true"},
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/agent-boundary.py 2>/dev/null || true"},
            ]
        },
        # ── Write: Edit와 동일 보호 ───────────────────────────────────────
        {
            "matcher": "Write",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/file-ownership-gate.py 2>/dev/null || true"},
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/agent-boundary.py 2>/dev/null || true"},
            ]
        },
        # ── Bash: 커밋 게이트 + 드리프트 감지 (글로벌 훅 참조) ────────────
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/commit-gate.py 2>/dev/null || true"},
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/harness-drift-check.py 2>/dev/null || true"},
            ]
        },
        # ── Agent: 에이전트 순서 게이트 (글로벌 훅 참조) ──────────────────
        {
            "matcher": "Agent",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/agent-gate.py 2>/dev/null || true"},
            ]
        }
    ],
    "PostToolUse": [
        # ── Bash: commit 성공 후 플래그 정리 (글로벌 훅 참조) ────────────
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/post-commit-cleanup.py 2>/dev/null || true"},
            ]
        },
        # ── Agent: 플래그 생성/삭제 + 경고 (글로벌 훅 참조) ──────────────
        {
            "matcher": "Agent",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": "python3 ~/.claude/hooks/post-agent-flags.py 2>/dev/null || true"},
            ]
        }
    ]
}

import os
settings_path = "$SETTINGS_FILE"
existing_allowed = ${EXISTING_ALLOWED}

# env 섹션에 HARNESS_PREFIX와 HARNESS_DOC_NAME 주입
output = {
    "env": {
        "HARNESS_PREFIX": prefix,
        "HARNESS_DOC_NAME": doc_name,
    },
    "allowedTools": existing_allowed,
    "hooks": hooks
}

with open(settings_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"✅ {settings_path} 생성 완료 (prefix: {prefix}_)")
PYEOF

# harness-loop.sh / harness-executor.sh — 글로벌 전용 (프로젝트에 복사하지 않음)
# 실행 인프라는 ~/.claude/ 에서만 관리. 프로젝트엔 설정(harness.config.json)만 둔다.
# 기존 프로젝트에 낡은 복사본이 있으면 삭제
for old_file in ".claude/harness-loop.sh" ".claude/harness-executor.sh"; do
  if [ -f "$old_file" ]; then
    rm -f "$old_file"
    echo "  🗑 낡은 $old_file 삭제 (글로벌 전용으로 전환)"
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Harness 훅 설치 완료"
echo ""
echo "  플래그 prefix : /tmp/${PREFIX}_*"
echo "  설정 파일     : $SETTINGS_FILE"
echo "  config 파일   : $CONFIG_FILE"
echo ""
echo "설치된 훅 (글로벌 ~/.claude/hooks/*.py 참조):"
echo "  PreToolUse(Edit/Write)  — file-ownership-gate.py + agent-boundary.py"
echo "  PreToolUse(Bash)        — commit-gate.py + harness-drift-check.py"
echo "  PreToolUse(Agent)       — agent-gate.py"
echo "  PostToolUse(Bash)       — post-commit-cleanup.py"
echo "  PostToolUse(Agent)      — post-agent-flags.py"
echo ""
echo "전역 훅(UserPromptSubmit/SessionStart)은 ~/.claude/settings.json에서 자동 적용됨."
echo ""
echo "다음 단계:"
echo "  1. /init-agents  — 에이전트 파일(.claude/agents/) 초기화"
echo "  2. 각 에이전트 '프로젝트 특화 지침' 섹션 채우기"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
