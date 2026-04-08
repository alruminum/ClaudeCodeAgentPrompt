#!/bin/bash
# ~/.claude/setup-harness.sh
# 신규 프로젝트 루트에서 실행: bash ~/.claude/setup-harness.sh
# 프로젝트별 .claude/settings.json + harness.config.json을 초기화한다.
#
# ⚠️ 훅은 프로젝트 settings.json에 쓰지 않는다.
#    모든 훅은 ~/.claude/settings.json(전역)에서만 관리.
#    프로젝트 settings.json에는 env + allowedTools만 작성.
#
# 전역 훅 (모두 ~/.claude/hooks/*.py 참조):
#   PreToolUse(Edit/Write) — orch-rules-first.py + agent-boundary.py
#   PreToolUse(Read)       — agent-boundary.py
#   PreToolUse(Bash)       — harness-drift-check.py + commit-gate.py
#   PreToolUse(Agent)      — agent-gate.py
#   PostToolUse(Edit)      — harness-settings-watcher.py
#   PostToolUse(Bash)      — post-commit-cleanup.py
#   PostToolUse(Agent)     — post-agent-flags.py
#
# prefix 결정: 각 훅이 harness_common.get_prefix()로 harness.config.json → dirname → "proj" 폴백
#
# 주의: harness-*.sh (executor, impl-plan, impl-process, design, bugfix, plan, utils)는 글로벌(~/.claude/) 전용.
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

import os
settings_path = "$SETTINGS_FILE"
existing_allowed = ${EXISTING_ALLOWED}

# ⚠️ 훅은 프로젝트 settings.json에 쓰지 않는다.
#    모든 훅은 ~/.claude/settings.json(전역)에서 관리.
#    프로젝트에는 env + allowedTools만 작성.
output = {
    "env": {
        "HARNESS_DOC_NAME": doc_name,
    },
    "allowedTools": existing_allowed,
}

# 기존 settings.json에 hooks 섹션이 있으면 제거 (마이그레이션)
if os.path.exists(settings_path):
    try:
        with open(settings_path) as f:
            old = json.load(f)
        if "hooks" in old:
            print("⚠️  기존 프로젝트 hooks 섹션 발견 — 제거 (전역으로 이관)")
    except Exception:
        pass

with open(settings_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"✅ {settings_path} 생성 완료 (prefix: {prefix}_)")
PYEOF

# harness-*.sh — 글로벌 전용 (프로젝트에 복사하지 않음)
# 실행 인프라는 ~/.claude/ 에서만 관리. 프로젝트엔 설정(harness.config.json)만 둔다.
# 기존 프로젝트에 낡은 복사본이 있으면 삭제
for old_file in ".claude/harness-loop.sh" ".claude/harness/executor.sh" ".claude/harness/impl-process.sh"; do
  if [ -f "$old_file" ]; then
    rm -f "$old_file"
    echo "  🗑 낡은 $old_file 삭제 (글로벌 전용으로 전환)"
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Harness 프로젝트 설정 완료"
echo ""
echo "  플래그 prefix : /tmp/${PREFIX}_*"
echo "  설정 파일     : $SETTINGS_FILE (env + allowedTools만)"
echo "  config 파일   : $CONFIG_FILE"
echo ""
echo "⚠️  훅은 전역 ~/.claude/settings.json에서만 관리."
echo "    프로젝트 settings.json에 hooks 섹션 추가 금지."
echo ""
echo "다음 단계:"
echo "  1. /init-agents  — 에이전트 파일(.claude/agents/) 초기화"
echo "  2. 각 에이전트 '프로젝트 특화 지침' 섹션 채우기"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
