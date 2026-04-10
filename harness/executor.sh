#!/bin/bash
# ~/.claude/harness/executor.sh
# 결정론적 워크플로우 라우터 — 순수 라우터 + 공유 인프라
#
# 호출 형식:
#   bash .claude/harness/executor.sh <mode> \
#     --impl <path> --issue <N> [--prefix <p>] [--bug <desc>] [--context <ctx>]
#     [--choice]  ← design 모드 전용(DEPRECATED): 3 variant + design-critic PASS/REJECT
#
# mode 목록:
#   impl   — harness/impl.sh (계획 + dispatcher) → impl_fast/std/deep.sh (실행)
#   direct — harness/impl_direct.sh (impl 파일 없이 engineer 직행, qa 스킬 / ux 스킬 경유)
#   plan   — harness/plan.sh (product-planner → architect → validator)
#
# ⚠️  design 모드: DEPRECATED (v4)
#   designer는 ux 스킬에서 Agent 도구로 직접 호출 (하네스 루프 밖).
#   'executor.sh design' 은 레거시 호환용으로만 유지.
#   신규 UX 요청은 ux 스킬 → designer 에이전트 직접 호출 사용.
#
# ⚠️  bugfix 모드: DEPRECATED (v5)
#   버그 보고는 qa 스킬이 QA 에이전트를 직접 호출해 분류 후 executor.sh direct로 라우팅.
#   'executor.sh bugfix' 는 레거시 호환용으로만 유지.

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/utils.sh"
source "${HOME}/.claude/harness/impl.sh"
source "${HOME}/.claude/harness/design.sh"
source "${HOME}/.claude/harness/impl_direct.sh"
source "${HOME}/.claude/harness/bugfix.sh"
source "${HOME}/.claude/harness/plan.sh"

export HARNESS_RESULT="unknown"

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"; CONSTRAINTS=""
BRANCH_TYPE="feat"  # bugfix 경로에서 "fix"로 변경
export DESIGN_MODE="default"  # design 모드 기본값: default (1 variant, 크리틱 없음)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)    IMPL_FILE="$2";  shift 2 ;;
    --issue)   ISSUE_NUM="$2";  shift 2 ;;
    --prefix)  PREFIX="$2";     shift 2 ;;
    --bug)     BUG_DESC="$2";   shift 2 ;;
    --context) CONTEXT="$2";    shift 2 ;;
    --depth)   DEPTH="$2";      shift 2 ;;
    --choice)  DESIGN_MODE="choice"; shift ;;
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
trap 'kill "$HB_PID" 2>/dev/null; rm -f "$LOCK_FILE" "/tmp/${PREFIX}_harness_kill"; rm -f /tmp/${PREFIX}_*_active 2>/dev/null; write_run_end' EXIT

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

# ── impl 서브 스크립트 기본 경로 (impl.sh dispatcher가 참조) ──
IMPL_SCRIPT_DIR="${HOME}/.claude/harness"

# ══════════════════════════════════════════════════════════════════════
# 모드 라우터
# ══════════════════════════════════════════════════════════════════════
case "$MODE" in
  impl)    run_impl ;;
  direct)  run_direct ;;
  design)  run_design ;;
  bugfix)
    echo "[HARNESS] ⚠️  bugfix 모드는 deprecated입니다. qa 스킬을 사용하세요."
    echo "[HARNESS] 하위 호환성을 위해 실행합니다."
    run_bugfix
    ;;
  plan)    run_plan ;;
  *)       export HARNESS_RESULT="HARNESS_CRASH"; echo "[HARNESS] 알 수 없는 mode: $MODE"; exit 1 ;;
esac
