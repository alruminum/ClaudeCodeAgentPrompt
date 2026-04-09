#!/bin/bash
# ~/.claude/harness/executor.sh
# 결정론적 워크플로우 라우터 — 순수 라우터 + 공유 인프라
#
# 호출 형식:
#   bash .claude/harness/executor.sh <mode> \
#     --impl <path> --issue <N> [--prefix <p>] [--bug <desc>] [--context <ctx>]
#
# 4가지 mode:
#   impl   — harness/impl.sh (계획) + harness/impl-process.sh (실행)
#   design — harness/design.sh (designer → design-critic)
#   bugfix — harness/bugfix.sh (qa → 5-way 분기: engineer_direct/architect/design/backlog/KNOWN_ISSUE)
#   plan   — harness/plan.sh (product-planner → architect → validator)

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/utils.sh"
source "${HOME}/.claude/harness/impl.sh"
source "${HOME}/.claude/harness/design.sh"
source "${HOME}/.claude/harness/bugfix.sh"
source "${HOME}/.claude/harness/plan.sh"

export HARNESS_RESULT="unknown"

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"; CONSTRAINTS=""
BRANCH_TYPE="feat"  # bugfix 경로에서 "fix"로 변경

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)    IMPL_FILE="$2";  shift 2 ;;
    --issue)   ISSUE_NUM="$2";  shift 2 ;;
    --prefix)  PREFIX="$2";     shift 2 ;;
    --bug)     BUG_DESC="$2";   shift 2 ;;
    --context) CONTEXT="$2";    shift 2 ;;
    --depth)   DEPTH="$2";      shift 2 ;;
    *) shift ;;
  esac
done

LOCK_FILE="/tmp/${PREFIX}_harness_active"
LOCK_STARTED=$(date +%s)

# ── 병렬 실행 가드: 같은 PREFIX로 동시 실행 방지 ─────────────────────
if [[ -f "$LOCK_FILE" ]]; then
  existing_pid=$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("pid", ""))
except: pass
' "$LOCK_FILE" 2>/dev/null || true)
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "[HARNESS] 오류: 같은 PREFIX($PREFIX)로 이미 실행 중 (PID=$existing_pid)"
    echo "동시 실행은 지원하지 않습니다. /harness-kill로 기존 실행을 중단하거나 완료를 기다리세요."
    exit 1
  fi
  # PID가 죽었으면 stale lock — 정리 후 진행
  rm -f "$LOCK_FILE"
fi

_write_lease() {
  printf '{"pid":%d,"mode":"%s","started":%d,"heartbeat":%d}\n' \
    $$ "$MODE" "$LOCK_STARTED" "$(date +%s)" > "${LOCK_FILE}" 2>/dev/null || true
}

# Heartbeat: 15초마다 JSON lease 갱신 → router TTL(120s) 기준 "나 살아있음" 신호
_harness_heartbeat() {
  while true; do
    sleep 15
    _write_lease
  done
}
_harness_heartbeat &
HB_PID=$!

# EXIT trap: 성공/실패/크래시/kill 모두 lock 해제
trap 'kill "$HB_PID" 2>/dev/null; rm -f "$LOCK_FILE" "/tmp/${PREFIX}_harness_kill"; write_run_end' EXIT

_write_lease

# ── depth 자동 감지 (--depth 미지정 또는 auto 시) ─────────────────────
detect_depth() {
  local impl="$1"
  if [[ -z "$impl" || ! -f "$impl" ]]; then
    echo "std"; return
  fi
  if grep -q "(BROWSER:DOM)" "$impl" 2>/dev/null; then
    echo "deep"
  elif grep -q "(MANUAL)" "$impl" 2>/dev/null && \
       ! grep -qE "\(TEST\)|\(BROWSER:DOM\)" "$impl" 2>/dev/null; then
    echo "fast"
  else
    echo "std"
  fi
}

# ── 공통: harness/impl-process.sh 경로 결정 (글로벌 우선) ──
PROCESS_SCRIPT="${HOME}/.claude/harness/impl-process.sh"
[[ ! -f "$PROCESS_SCRIPT" ]] && PROCESS_SCRIPT=".claude/harness/impl-process.sh"

# ══════════════════════════════════════════════════════════════════════
# 모드 라우터
# ══════════════════════════════════════════════════════════════════════
case "$MODE" in
  impl)    run_impl ;;
  design)  run_design ;;
  bugfix)  run_bugfix ;;
  plan)    run_plan ;;
  *)       export HARNESS_RESULT="HARNESS_CRASH"; echo "[HARNESS] 알 수 없는 mode: $MODE"; exit 1 ;;
esac
