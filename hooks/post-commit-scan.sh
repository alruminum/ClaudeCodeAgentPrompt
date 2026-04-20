#!/bin/bash
# post-commit-scan.sh — 커밋 후 간단한 정적 분석
# PostToolUse(Bash) 훅에서 git commit 성공 후 호출되거나,
# git post-commit 훅으로 직접 사용 가능.
#
# 결과를 STATE_DIR/{PREFIX}_scan_report.txt에 저장.
# 다음 세션에서 harness-router.py가 참고할 수 있음.

set -euo pipefail

# STATE_DIR 설정 (프로젝트 .claude/harness-state/ 우선)
if [[ -d ".claude/harness-state" ]]; then
  STATE_DIR=".claude/harness-state"
elif [[ -d ".claude" ]]; then
  STATE_DIR=".claude/harness-state"
  mkdir -p "$STATE_DIR"
else
  STATE_DIR="/tmp"
fi

# prefix 유도
CONFIG=".claude/harness.config.json"
if [[ -f "$CONFIG" ]]; then
  PREFIX=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('prefix','proj'))" 2>/dev/null || echo "proj")
else
  PREFIX=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9' | cut -c1-6)
  [[ -z "$PREFIX" ]] && PREFIX="proj"
fi

REPORT="${STATE_DIR}/${PREFIX}_scan_report.txt"
echo "=== Post-Commit Scan $(date +%Y-%m-%d\ %H:%M:%S) ===" > "$REPORT"

# 변경된 파일만 대상
CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -E '\.(ts|tsx|js|jsx)$' || echo "")
if [[ -z "$CHANGED" ]]; then
  echo "No source files changed." >> "$REPORT"
  exit 0
fi

ISSUES=0

# 1. console.log 잔류 체크
CL_COUNT=0
for f in $CHANGED; do
  [[ -f "$f" ]] || continue
  c=$(grep -c 'console\.log' "$f" 2>/dev/null || echo 0)
  if [[ $c -gt 0 ]]; then
    echo "[WARN] console.log 잔류: $f ($c건)" >> "$REPORT"
    CL_COUNT=$((CL_COUNT + c))
  fi
done
[[ $CL_COUNT -gt 0 ]] && ISSUES=$((ISSUES + 1))

# 2. any 타입 사용 체크
ANY_COUNT=0
for f in $CHANGED; do
  [[ -f "$f" ]] || continue
  c=$(grep -cE ': any\b|as any\b|<any>' "$f" 2>/dev/null || echo 0)
  if [[ $c -gt 0 ]]; then
    echo "[WARN] any 타입 사용: $f ($c건)" >> "$REPORT"
    ANY_COUNT=$((ANY_COUNT + c))
  fi
done
[[ $ANY_COUNT -gt 0 ]] && ISSUES=$((ISSUES + 1))

# 3. TODO/FIXME/HACK 잔류 체크
TODO_COUNT=0
for f in $CHANGED; do
  [[ -f "$f" ]] || continue
  c=$(grep -cE 'TODO|FIXME|HACK' "$f" 2>/dev/null || echo 0)
  if [[ $c -gt 0 ]]; then
    echo "[INFO] TODO/FIXME/HACK: $f ($c건)" >> "$REPORT"
    TODO_COUNT=$((TODO_COUNT + c))
  fi
done

# 4. UX 영향 파일 변경 감지 → ux-flow.md 드리프트 플래그
#    대상: *Screen.tsx, *Page.tsx, routes/**, screens/**, 라우터 설정
#    ux-flow.md 가 존재하는 프로젝트에서만 동작 (없으면 스킵).
UX_CHANGED=""
if [[ -f "docs/ux-flow.md" ]]; then
  UX_CHANGED=$(echo "$CHANGED" | tr ' ' '\n' | grep -E '(Screen\.(tsx|jsx)$|Page\.(tsx|jsx)$|/routes/|/screens/|router\.(ts|tsx|js|jsx)$)' || echo "")
  if [[ -n "$UX_CHANGED" ]]; then
    UX_COUNT=$(echo "$UX_CHANGED" | grep -c . || echo 0)
    # cross-session 전역 플래그 — STATE_DIR 최상위에 둠.
    # `.flags/` 서브디렉토리는 session-start 의 migrate_legacy_flags 가 비우기 때문에
    # 세션 시작마다 사라진다. 최상위 + session-start.py cleanup 예외로 보존.
    FLAG_FILE="${STATE_DIR}/${PREFIX}_ux_flow_drift"
    # 플래그 파일에 변경 파일 목록 저장 (SessionStart 알림 + /ux-sync 스킬에서 사용)
    {
      echo "# UX drift detected at $(date +%Y-%m-%dT%H:%M:%S)"
      echo "# Consumed by: harness-session-start.py (notify), /ux-sync (read changed files)"
      echo "$UX_CHANGED"
    } > "$FLAG_FILE"
    echo "" >> "$REPORT"
    echo "[UX-DRIFT] $UX_COUNT UX-impacting file(s) changed. Flag: $FLAG_FILE" >> "$REPORT"
    echo "$UX_CHANGED" | sed 's/^/  - /' >> "$REPORT"
  fi
fi

# 요약
echo "" >> "$REPORT"
echo "--- Summary ---" >> "$REPORT"
echo "Files scanned: $(echo "$CHANGED" | wc -w | tr -d ' ')" >> "$REPORT"
echo "console.log: $CL_COUNT" >> "$REPORT"
echo "any type: $ANY_COUNT" >> "$REPORT"
echo "TODO/FIXME/HACK: $TODO_COUNT" >> "$REPORT"
echo "Issues: $ISSUES" >> "$REPORT"

if [[ $ISSUES -gt 0 ]]; then
  echo "[POST-COMMIT-SCAN] $ISSUES issue(s) found. See $REPORT"
fi
