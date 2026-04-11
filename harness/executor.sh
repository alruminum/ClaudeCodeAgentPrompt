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
#   impl   — harness/impl.sh (계획 + dispatcher) → impl_simple/std/deep.sh (실행)
#   plan   — harness/plan.sh (product-planner → architect → validator)
#
# ⚠️  design 모드: DEPRECATED (v4)
#   designer는 ux 스킬에서 Agent 도구로 직접 호출 (하네스 루프 밖).
#   'executor.sh design' 은 레거시 호환용으로만 유지.
#   신규 UX 요청은 ux 스킬 → designer 에이전트 직접 호출 사용.
#
# ⚠️  bugfix/direct 모드: REMOVED (v6)
#   버그 보고는 qa 스킬이 QA 에이전트를 직접 호출해 분류 후 executor.sh impl --issue <N>으로 라우팅.
#   impl.sh가 issue labels로 BUGFIX_PLAN vs MODULE_PLAN을 분기한다.

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/utils.sh"
source "${HOME}/.claude/harness/impl.sh"
source "${HOME}/.claude/harness/design.sh"
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

# STATE_DIR 초기화: 프로젝트 .claude/harness-state/ 사용
init_state_dir "$(pwd)"

LOCK_FILE="${STATE_DIR}/${PREFIX}_harness_active"
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
trap 'kill "$HB_PID" 2>/dev/null; rm -f "$LOCK_FILE" "${STATE_DIR}/${PREFIX}_harness_kill"; rm -f ${STATE_DIR}/${PREFIX}_*_active 2>/dev/null; write_run_end' EXIT

_write_lease

# ── depth 자동 감지 (--depth 미지정 또는 auto 시) ─────────────────────
detect_depth() {
  local impl="$1"
  if [[ -z "$impl" || ! -f "$impl" ]]; then
    echo "std"; return
  fi
  # frontmatter depth: 필드 읽기 (YAML frontmatter --- ... --- 블록 내)
  local depth_val
  depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
  case "$depth_val" in
    simple|std|deep) echo "$depth_val" ;;
    *) echo "std" ;;  # frontmatter 없거나 유효하지 않으면 기본 std
  esac
}

# ── impl 서브 스크립트 기본 경로 (impl.sh dispatcher가 참조) ──
IMPL_SCRIPT_DIR="${HOME}/.claude/harness"

# ══════════════════════════════════════════════════════════════════════
# 모드 라우터
# ══════════════════════════════════════════════════════════════════════
case "$MODE" in
  impl)    run_impl ;;
  design)  run_design ;;
  direct)
    echo "[HARNESS] ⚠️  direct 모드는 제거됐습니다. executor.sh impl --issue <N>을 사용하세요."
    export HARNESS_RESULT="HARNESS_CRASH"; exit 1
    ;;
  bugfix)
    echo "[HARNESS] ⚠️  bugfix 모드는 제거됐습니다. qa 스킬 → executor.sh impl --issue <N>을 사용하세요."
    export HARNESS_RESULT="HARNESS_CRASH"; exit 1
    ;;
  plan)    run_plan ;;
  *)       export HARNESS_RESULT="HARNESS_CRASH"; echo "[HARNESS] 알 수 없는 mode: $MODE"; exit 1 ;;
esac
