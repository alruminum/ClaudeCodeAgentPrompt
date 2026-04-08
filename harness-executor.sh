#!/bin/bash
# ~/.claude/harness-executor.sh
# 결정론적 워크플로우 라우터 — LLM 에이전트 대체
#
# 호출 형식:
#   bash .claude/harness-executor.sh <mode> \
#     --impl <path> --issue <N> [--prefix <p>] [--bug <desc>] [--context <ctx>]
#
# 4가지 mode:
#   impl   — architect → validator → PLAN_VALIDATION_PASS → engineer 루프 (plan_validation_passed 시 architect+validator 스킵)
#   design — designer → design-critic → DESIGN_DONE
#   bugfix — qa 라우팅 기반 4-way 분기 (engineer_direct/architect_full/design/backlog)
#   plan   — product-planner → architect Mode A → PLAN_DONE

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness-utils.sh"
source "${HOME}/.claude/harness-bugfix.sh"

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
# (SIGKILL 제외 — kill -9는 어쩔 수 없음, TTL이 120s 후 자동 해제)
trap 'kill "$HB_PID" 2>/dev/null; rm -f "$LOCK_FILE" "/tmp/${PREFIX}_harness_kill"; write_run_end' EXIT

# router가 O_EXCL로 빈 파일 생성 → JSON 내용 채우기
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

# ── 공통: harness-loop.sh 경로 결정 (글로벌 우선 — 인프라는 글로벌 전용) ──
LOOP_SCRIPT="${HOME}/.claude/harness-loop.sh"
[[ ! -f "$LOOP_SCRIPT" ]] && LOOP_SCRIPT=".claude/harness-loop.sh"

# ══════════════════════════════════════════════════════════════════════
# mode: impl (Phase 0.5 → 0.7 → 0.8 → PLAN_VALIDATION_PASS)
# ══════════════════════════════════════════════════════════════════════
run_impl() {
  # ── 재진입 상태 감지 ──
  # plan_validation_passed 플래그 + impl 파일 있으면 → engineer 루프로 바로 진입
  if [[ -f "/tmp/${PREFIX}_plan_validation_passed" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: plan_validation_passed + impl 존재 → engineer 루프 직접 진입"
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    bash "$LOOP_SCRIPT" impl --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --depth "$DEPTH" --branch-type "$BRANCH_TYPE"
    return
  fi

  # Phase 0.5 — UI 키워드 감지
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    ui_kw=$(grep -iE "화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이" "$IMPL_FILE" || true)
    if [[ -n "$ui_kw" && ! -f "/tmp/${PREFIX}_design_critic_passed" ]]; then
      export HARNESS_RESULT="UI_DESIGN_REQUIRED"
      echo "UI_DESIGN_REQUIRED"
      echo "impl: $IMPL_FILE"
      echo "이유: $ui_kw"
      echo "필요 조치: mode:design 완료 후 mode:impl 재호출"
      exit 0
    fi
  fi

  # run_bugfix → run_impl 이중 로테이션 방지: RUN_LOG 이미 설정돼있으면 스킵
  [[ -z "$RUN_LOG" ]] && rotate_harness_logs "$PREFIX" "impl"

  # Phase 0.7 — impl 파일 없으면 architect 호출
  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] Phase 0.7 — architect Mode B 호출 중"
    _agent_call "architect" 900 \
      "Module Plan(Mode B) — issue #${ISSUE_NUM} impl 계획 작성. context: ${CONTEXT}" \
      "/tmp/${PREFIX}_arch_out.txt"
    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""
    echo "[HARNESS] Phase 0.7 — architect 완료 / impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # Phase 0.8 — validator Plan Validation (Mode C)
  echo "[HARNESS] Phase 0.8 — validator Plan Validation 호출 중"
  _agent_call "validator" 300 \
    "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_val_pv_out.txt"
  val_result=$(grep -oEm1 '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out.txt") || val_result="UNKNOWN"
  echo "[HARNESS] Phase 0.8 — Plan Validation 결과: $val_result"

  if [[ "$val_result" == "PASS" ]]; then
    touch "/tmp/${PREFIX}_plan_validation_passed"
    echo "$IMPL_FILE" > "/tmp/${PREFIX}_impl_path"
    export HARNESS_RESULT="PLAN_VALIDATION_PASS"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "필요 조치: 계획 확인 후 mode:impl 로 재호출"
    exit 0
  fi

  # FAIL → architect 재보강 1회 → 재검증
  echo "[HARNESS] Phase 0.8 — FAIL → architect 재보강 중"
  fail_feedback=$(tail -20 "/tmp/${PREFIX}_val_pv_out.txt")
  _agent_call "architect" 900 \
    "SPEC_GAP(Mode C) — Plan Validation FAIL 피드백 반영. impl: $IMPL_FILE feedback: ${fail_feedback}" \
    "/tmp/${PREFIX}_arch_fix_out.txt"
  echo "[HARNESS] Phase 0.8 — architect 재보강 완료, 재검증 중"

  _agent_call "validator" 300 \
    "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_val_pv_out2.txt"
  val_result2=$(grep -oEm1 '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out2.txt") || val_result2="UNKNOWN"
  echo "[HARNESS] Phase 0.8 — 재검증 결과: $val_result2"

  if [[ "$val_result2" == "PASS" ]]; then
    touch "/tmp/${PREFIX}_plan_validation_passed"
    echo "$IMPL_FILE" > "/tmp/${PREFIX}_impl_path"
    export HARNESS_RESULT="PLAN_VALIDATION_PASS"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "필요 조치: 계획 확인 후 mode:impl 로 재호출"
    exit 0
  fi

  export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
  echo "PLAN_VALIDATION_ESCALATE"
  tail -20 "/tmp/${PREFIX}_val_pv_out2.txt"
  exit 1
}

# ══════════════════════════════════════════════════════════════════════
# mode: design (Phase D1 → D2 → DESIGN_DONE)
# ══════════════════════════════════════════════════════════════════════
run_design() {
  rotate_harness_logs "$PREFIX" "design"
  attempt=0; MAX=3
  while [[ $attempt -lt $MAX ]]; do
    echo "[HARNESS] Phase D1 attempt $((attempt+1))/$MAX — designer 호출 중"
    _agent_call "designer" 300 \
      "issue: #$ISSUE_NUM context: $CONTEXT" \
      "/tmp/${PREFIX}_des_out.txt"

    echo "[HARNESS] Phase D2 attempt $((attempt+1))/$MAX — design-critic 호출 중"
    des_out=$(cat "/tmp/${PREFIX}_des_out.txt")
    _agent_call "design-critic" 300 \
      "$des_out" \
      "/tmp/${PREFIX}_dc_out.txt"
    dc_result=$(grep -oEm1 '\bPICK\b|\bITERATE\b|\bESCALATE\b' "/tmp/${PREFIX}_dc_out.txt") || dc_result="UNKNOWN"

    case "$dc_result" in
      PICK)
        touch "/tmp/${PREFIX}_design_critic_passed"
        export HARNESS_RESULT="DESIGN_DONE"
        echo "DESIGN_DONE"
        echo "issue: #$ISSUE_NUM"
        echo "필요 조치: 시안 확인 후 mode:impl 로 재호출"
        exit 0
        ;;
      ITERATE) attempt=$((attempt+1)); continue ;;
      *)
        export HARNESS_RESULT="DESIGN_ESCALATE"
        echo "DESIGN_ESCALATE: design-critic 판정 불명확"
        cat "/tmp/${PREFIX}_dc_out.txt"
        exit 1
        ;;
    esac
  done
  export HARNESS_RESULT="DESIGN_ESCALATE"
  echo "DESIGN_ESCALATE: 3회 모두 PICK 없음"
  exit 1
}

# ══════════════════════════════════════════════════════════════════════
# mode: bugfix (Phase B1 → qa 라우팅 기반 4-way 분기)
# 핵심 로직은 harness-bugfix.sh에 분리됨
# ══════════════════════════════════════════════════════════════════════
run_bugfix() {
  rotate_harness_logs "$PREFIX" "bugfix"

  # ── 필수 파라미터 검증: bugfix는 --bug 또는 --issue 필요 ──
  if [[ -z "$BUG_DESC" && ( -z "$ISSUE_NUM" || "$ISSUE_NUM" == "N" ) ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] 오류: bugfix 모드는 --bug 또는 --issue가 필요합니다"
    echo "사용법: harness-executor.sh bugfix --bug <설명> --issue <번호>"
    exit 1
  fi

  # ── 재진입 상태 감지 (역순 체크) ──

  # 1. impl 파일 있으면 → QA + architect 스킵, engineer 직접
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: impl 존재 ($IMPL_FILE) → engineer 직접"
    echo "[재진입 — impl 파일 기반. QA 스킵]" > "/tmp/${PREFIX}_qa_out.txt"
    _bugfix_direct "/tmp/${PREFIX}_qa_out.txt"
    return
  fi

  # 2. GitHub issue에 QA 리포트 있으면 → QA 스킵, bugfix_run으로 라우팅
  if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
    local issue_body
    issue_body=$(gh issue view "$ISSUE_NUM" --json body -q .body 2>/dev/null || echo "")
    if echo "$issue_body" | grep -q 'QA_REPORT\|QA_SUMMARY\|FUNCTIONAL_BUG\|SPEC_ISSUE\|DESIGN_ISSUE'; then
      echo "[HARNESS] 재진입: GitHub issue #${ISSUE_NUM}에 QA 리포트 존재 → QA 스킵"
      echo "$issue_body" > "/tmp/${PREFIX}_qa_out.txt"
      bugfix_run  # QA_SUMMARY 파싱 + 폴백 라우팅
      return
    fi
  fi

  # 3. 신규 — QA부터 시작

  # ── Phase B1: qa 분석 ──
  echo "[HARNESS] Phase B1 — qa 호출 중"
  _agent_call "qa" 300 \
    "bug: $BUG_DESC issue: #$ISSUE_NUM
탐색 범위: 이슈에 직접 관련된 파일만 분석하라. 전체 코드베이스 스캔 금지.
- 이슈 설명에서 언급된 파일/컴포넌트부터 시작
- 연관 파일은 import 체인 1단계까지만
- Glob 최대 2회, Read 최대 10회
분석 완료 후 반드시 mcp__github__create_issue로 이슈를 등록하라.
- FUNCTIONAL_BUG → Bugs 마일스톤 (라벨: bug)
- SPEC_ISSUE (PRD 명세 있음) → Feature 마일스톤 (해당 epic 라벨, 본문에 epic 경로 명시)
- SPEC_ISSUE (PRD 명세 없음) → Feature 마일스톤
- DESIGN_ISSUE → Feature 마일스톤" \
    "/tmp/${PREFIX}_qa_out.txt"

  bugfix_run  # harness-bugfix.sh 함수
}

# ══════════════════════════════════════════════════════════════════════
# mode: plan (Phase P1 → P2 → PLAN_DONE)
# ══════════════════════════════════════════════════════════════════════
run_plan() {
  rotate_harness_logs "$PREFIX" "plan"
  echo "[HARNESS] Phase P1 — product-planner 호출 중"
  _agent_call "product-planner" 300 \
    "context: $CONTEXT issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_pp_out.txt"
  pp_out=$(cat "/tmp/${PREFIX}_pp_out.txt")

  echo "[HARNESS] Phase P2 — architect Mode A 호출 중"
  _agent_call "architect" 900 \
    "System Design(Mode A) — ${pp_out} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_out.txt"

  export HARNESS_RESULT="PLAN_DONE"
  echo "PLAN_DONE"
  echo "issue: #$ISSUE_NUM"
  echo "필요 조치: UI 변경 있으면 mode:design, 없으면 mode:impl"
  exit 0
}

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
