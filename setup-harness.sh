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
#   PreToolUse(mcp__github__create_issue) — issue-gate.py
#   PostToolUse(Edit)      — harness-settings-watcher.py
#   PostToolUse(Bash)      — post-commit-cleanup.py + harness-review-trigger.py
#   PostToolUse(Agent)     — post-agent-flags.py
#   Stop                   — afplay Glass.aiff + harness-review-stop.py
#
# prefix 결정: 각 훅이 harness_common.get_prefix()로 harness.config.json → dirname → "proj" 폴백
#
# 주의: harness-*.sh (executor, impl, impl_simple, impl_std, impl_deep, design, plan, utils)는 글로벌(~/.claude/) 전용.
#       프로젝트에 복사하지 않으며, 기존 낡은 복사본은 자동 삭제.

set -e

# 선택적 인수
# --doc-name <name>  : 핵심 설계 문서 이름 (docs/<name>.md), Mode C 신선도 체크에 사용 (기본값: domain-logic)
# --repo <owner/repo>: GitHub repo — 마일스톤/레이블 자동 생성에 사용
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
for old_file in ".claude/harness-loop.sh" ".claude/harness/executor.sh"; do
  if [ -f "$old_file" ]; then
    rm -f "$old_file"
    echo "  🗑 낡은 $old_file 삭제 (글로벌 전용으로 전환)"
  fi
done

# ── 낡은 .claude/agents/ 복사본 정리 (마이그레이션) ─────────────────────
# 에이전트는 전역(~/.claude/agents/)에서 직접 로드. 프로젝트 복사본 불필요.
# 프로젝트별 컨텍스트는 .claude/agent-config/ 에 저장.
if [ -d ".claude/agents" ]; then
  AGENT_COUNT=$(ls .claude/agents/*.md 2>/dev/null | wc -l | tr -d ' ')
  if [ "$AGENT_COUNT" -gt 0 ]; then
    echo "⚠️  낡은 .claude/agents/ 감지 (${AGENT_COUNT}개 파일)"
    echo "    에이전트는 전역(~/.claude/agents/)에서 직접 로드됩니다."
    echo "    프로젝트별 지침은 .claude/agent-config/에 옮겨주세요."
    echo "    (자동 삭제하지 않음 — 수동 확인 후 삭제)"
  fi
fi

# ── .claude/agent-config/ 디렉토리 생성 ──────────────────────────────
mkdir -p .claude/agent-config
echo "📁 .claude/agent-config/ 준비 완료 (프로젝트별 에이전트 지침)"

# ── CLAUDE.md 베이스 복사 (없을 때만) ─────────────────────────────────
if [ ! -f "CLAUDE.md" ]; then
  if [ -f "${HOME}/.claude/templates/CLAUDE-base.md" ]; then
    cp "${HOME}/.claude/templates/CLAUDE-base.md" CLAUDE.md
    if [ -n "$REPO" ]; then
      sed -i '' "s|\[채우기: owner/repo\]|${REPO}|g" CLAUDE.md 2>/dev/null || true
    fi
    echo "📄 CLAUDE.md 생성 (베이스 템플릿에서 복사)"
  fi
else
  echo "ℹ️  CLAUDE.md 이미 존재 — 건너뜀"
fi

# ── GitHub 마일스톤/레이블 자동 생성 ──────────────────────────────────
if [ -n "$REPO" ]; then
  echo ""
  echo "🏷️  GitHub 마일스톤 생성 중 (${REPO})..."
  for M in "Story" "Bugs" "Epics" "Feature"; do
    RESULT=$(gh api "repos/${REPO}/milestones" -f title="$M" -f state="open" 2>&1)
    if echo "$RESULT" | grep -q '"number"'; then
      echo "  ✅ $M"
    elif echo "$RESULT" | grep -qF 'already_exists'; then
      echo "  ⚠️  $M (이미 존재)"
    else
      echo "  ❌ $M 실패 — gh auth login 확인 필요"
    fi
  done

  echo ""
  echo "🏷️  GitHub 레이블 생성 중..."
  for LABEL_INFO in "v01:0075ca" "bug:d73a4a" "feat:a2eeef"; do
    LABEL_NAME="${LABEL_INFO%%:*}"
    LABEL_COLOR="${LABEL_INFO##*:}"
    RESULT=$(gh api "repos/${REPO}/labels" -f name="$LABEL_NAME" -f color="$LABEL_COLOR" 2>&1)
    if echo "$RESULT" | grep -q '"name"'; then
      echo "  ✅ $LABEL_NAME"
    elif echo "$RESULT" | grep -qF 'already_exists'; then
      echo "  ⚠️  $LABEL_NAME (이미 존재)"
    else
      echo "  ❌ $LABEL_NAME 실패"
    fi
  done
fi

# ── 전역 settings.json 훅 관리 ──────────────────────────────────────
# _meta: "harness" 태그가 붙은 훅만 프레임워크가 관리.
# _meta가 없거나 "user"인 훅은 사용자 훅으로 보존.
# 새 프레임워크 훅 추가 시 이 스크립트에서 _meta: harness로 등록.
GLOBAL_SETTINGS="${HOME}/.claude/settings.json"
INJECT_HOOK_MARKER="harness-review-inject.py"

if [ -f "$GLOBAL_SETTINGS" ]; then
  if grep -qF "$INJECT_HOOK_MARKER" "$GLOBAL_SETTINGS" 2>/dev/null; then
    echo "ℹ️  harness-review-inject.py 훅 이미 등록됨 — 스킵"
  else
    python3 << 'INJECT_PYEOF'
import json, sys, os

settings_path = os.path.expanduser("~/.claude/settings.json")
hook_cmd = "python3 ~/.claude/hooks/harness-review-inject.py 2>/dev/null || true"

try:
    with open(settings_path) as f:
        cfg = json.load(f)
except Exception as e:
    print(f"❌ 전역 settings.json 읽기 실패: {e}", flush=True)
    sys.exit(0)

ups = cfg.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])

# 이미 등록됐는지 확인
already = any(
    any(h.get("command", "") == hook_cmd for h in block.get("hooks", []))
    for block in ups
)
if already:
    print("ℹ️  harness-review-inject.py 이미 등록됨", flush=True)
    sys.exit(0)

# 새 블록 추가 (_meta: harness 태그 포함)
ups.append({
    "_meta": "harness",
    "hooks": [
        {
            "type": "command",
            "command": hook_cmd,
            "timeout": 10
        }
    ]
})

with open(settings_path, "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)

print("✅ 전역 settings.json에 harness-review-inject.py 훅 등록 완료 (_meta: harness)", flush=True)
INJECT_PYEOF
  fi
else
  echo "⚠️  전역 settings.json 없음 — harness-review-inject.py 훅 수동 등록 필요"
fi

# ── rule-audit pre-commit hook 설치 ────────────────────────────────────
# harness 관련 파일 변경 시 rule-audit.bats를 자동 실행
# 이미 pre-commit hook이 있으면 append (덮어쓰기 금지)
PRECOMMIT_HOOK=".git/hooks/pre-commit"
RULE_AUDIT_MARKER="# rule-audit: harness consistency check"
GLOBAL_HARNESS_DIR="${HOME}/.claude/harness"

if [ -d ".git/hooks" ]; then
  if ! grep -qF "$RULE_AUDIT_MARKER" "$PRECOMMIT_HOOK" 2>/dev/null; then
    cat >> "$PRECOMMIT_HOOK" <<HOOKEOF

${RULE_AUDIT_MARKER}
_harness_changed=\$(git diff --cached --name-only 2>/dev/null | grep -E "(impl_simple\.sh|impl_std\.sh|impl_deep\.sh|impl_helpers\.sh|impl\.sh|utils\.sh|orchestration-rules\.md|RULE_INDEX\.md)" || true)
if [ -n "\$_harness_changed" ]; then
  echo "[pre-commit] harness 파일 변경 감지 — rule-audit.bats 실행 중..."
  if command -v bats &>/dev/null && [ -f "${GLOBAL_HARNESS_DIR}/tests/rule-audit.bats" ]; then
    bats "${GLOBAL_HARNESS_DIR}/tests/rule-audit.bats" || { echo "[pre-commit] rule-audit.bats 실패 — commit 중단"; exit 1; }
  else
    echo "[pre-commit] bats 미설치 또는 rule-audit.bats 없음 — 검사 스킵"
  fi
fi
HOOKEOF
    chmod +x "$PRECOMMIT_HOOK"
    echo "✅ pre-commit hook에 rule-audit 추가 완료: $PRECOMMIT_HOOK"
  else
    echo "ℹ️  pre-commit hook에 rule-audit 이미 등록됨 — 스킵"
  fi
else
  echo "ℹ️  .git/hooks 디렉토리 없음 — pre-commit hook 스킵 (git init 후 재실행)"
fi

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
echo "  1. CLAUDE.md의 [채우기] 항목을 프로젝트에 맞게 작성"
echo "  2. .claude/agent-config/ 에 프로젝트별 에이전트 지침 추가 (선택)"
echo "     예: .claude/agent-config/engineer.md — SDK 래퍼 패턴, 의존성 규칙 등"
echo "  3. product-planner와 PRD/TRD 작성 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
