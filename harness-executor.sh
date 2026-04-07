#!/bin/bash
# ~/.claude/harness-executor.sh
# 결정론적 워크플로우 라우터 — LLM 에이전트 대체
#
# 호출 형식:
#   bash .claude/harness-executor.sh <mode> \
#     --impl <path> --issue <N> [--prefix <p>] [--bug <desc>] [--context <ctx>]
#
# 5가지 mode:
#   impl   — architect → validator Plan Validation → PLAN_VALIDATION_PASS (유저 게이트)
#   impl2  — harness-loop.sh 위임 (engineer~pr-reviewer 루프)
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

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"; CONSTRAINTS=""

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
  # plan_validation_passed 플래그 + impl 파일 있으면 → impl2로 바로 전환
  if [[ -f "/tmp/${PREFIX}_plan_validation_passed" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: plan_validation_passed + impl 존재 → impl2 전환"
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    bash "$LOOP_SCRIPT" impl2 --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --depth "$DEPTH"
    return
  fi

  # Phase 0.5 — UI 키워드 감지
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    ui_kw=$(grep -iE "화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이" "$IMPL_FILE" || true)
    if [[ -n "$ui_kw" && ! -f "/tmp/${PREFIX}_design_critic_passed" ]]; then
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
    IMPL_FILE=$(grep -oE 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt" | head -1 || echo "")
    echo "[HARNESS] Phase 0.7 — architect 완료 / impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # Phase 0.8 — validator Plan Validation (Mode C)
  echo "[HARNESS] Phase 0.8 — validator Plan Validation 호출 중"
  _agent_call "validator" 300 \
    "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_val_pv_out.txt"
  val_result=$(grep -oE '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out.txt" | head -1 || echo "UNKNOWN")
  echo "[HARNESS] Phase 0.8 — Plan Validation 결과: $val_result"

  if [[ "$val_result" == "PASS" ]]; then
    touch "/tmp/${PREFIX}_plan_validation_passed"
    echo "$IMPL_FILE" > "/tmp/${PREFIX}_impl_path"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "필요 조치: 계획 확인 후 mode:impl2 로 재호출"
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
  val_result2=$(grep -oE '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out2.txt" | head -1 || echo "UNKNOWN")
  echo "[HARNESS] Phase 0.8 — 재검증 결과: $val_result2"

  if [[ "$val_result2" == "PASS" ]]; then
    touch "/tmp/${PREFIX}_plan_validation_passed"
    echo "$IMPL_FILE" > "/tmp/${PREFIX}_impl_path"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "필요 조치: 계획 확인 후 mode:impl2 로 재호출"
    exit 0
  fi

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
    dc_result=$(grep -oE '\bPICK\b|\bITERATE\b|\bESCALATE\b' "/tmp/${PREFIX}_dc_out.txt" | head -1 || echo "UNKNOWN")

    case "$dc_result" in
      PICK)
        touch "/tmp/${PREFIX}_design_critic_passed"
        echo "DESIGN_DONE"
        echo "issue: #$ISSUE_NUM"
        echo "필요 조치: 시안 확인 후 mode:impl 로 재호출"
        exit 0
        ;;
      ITERATE) attempt=$((attempt+1)); continue ;;
      *)
        echo "DESIGN_ESCALATE: design-critic 판정 불명확"
        cat "/tmp/${PREFIX}_dc_out.txt"
        exit 1
        ;;
    esac
  done
  echo "DESIGN_ESCALATE: 3회 모두 PICK 없음"
  exit 1
}

# ══════════════════════════════════════════════════════════════════════
# mode: bugfix (Phase B1 → qa 라우팅 기반 4-way 분기)
# ══════════════════════════════════════════════════════════════════════
run_bugfix() {
  rotate_harness_logs "$PREFIX" "bugfix"

  # ── 재진입 상태 감지 (역순 체크) ──

  # 1. impl 파일 있으면 → QA + architect 스킵, engineer 직접
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: impl 존재 ($IMPL_FILE) → engineer 직접"
    qa_out="[재진입 — impl 파일 기반. QA 스킵]"
    _run_bugfix_direct
    return
  fi

  # 2. GitHub issue에 QA 리포트 있으면 → QA 스킵, architect부터
  if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
    local issue_body
    issue_body=$(gh issue view "$ISSUE_NUM" --json body -q .body 2>/dev/null || echo "")
    if echo "$issue_body" | grep -q 'QA_REPORT\|FUNCTIONAL_BUG\|SPEC_ISSUE\|DESIGN_ISSUE'; then
      echo "[HARNESS] 재진입: GitHub issue #$ISSUE_NUM에 QA 리포트 존재 → QA 스킵"
      qa_out="$issue_body"

      # 타입 기반 라우팅
      local routing="architect"
      if echo "$qa_out" | grep -q 'FUNCTIONAL_BUG'; then
        routing="engineer_direct"
      elif echo "$qa_out" | grep -q 'DESIGN_ISSUE'; then
        routing="design"
      fi
      echo "[HARNESS] 재진입 routing: $routing"

      case "$routing" in
        engineer_direct) _run_bugfix_direct ;;
        design) run_design ;;
        *) _run_bugfix_full ;;
      esac
      return
    fi
  fi

  # 3. 신규 — QA부터 시작

  # ── Phase B1: qa 분석 ──
  echo "[HARNESS] Phase B1 — qa 호출 중"
  _agent_call "qa" 300 \
    "bug: $BUG_DESC issue: #$ISSUE_NUM
분석 완료 후 반드시 mcp__github__create_issue로 이슈를 등록하라.
- FUNCTIONAL_BUG → Bugs 마일스톤 (라벨: bug)
- SPEC_ISSUE (PRD 명세 있음) → Feature 마일스톤 (해당 epic 라벨, 본문에 epic 경로 명시)
- SPEC_ISSUE (PRD 명세 없음) → Feature 마일스톤
- DESIGN_ISSUE → Feature 마일스톤" \
    "/tmp/${PREFIX}_qa_out.txt"
  qa_out=$(cat "/tmp/${PREFIX}_qa_out.txt")

  # ── qa 라우팅 파싱 (타입 기준, 심각도 무관) ──
  local routing="architect"  # 기본값 (안전 — SPEC_ISSUE)
  if echo "$qa_out" | grep -q 'FUNCTIONAL_BUG'; then
    routing="engineer_direct"
  elif echo "$qa_out" | grep -q 'DESIGN_ISSUE'; then
    routing="design"
  elif echo "$qa_out" | grep -q 'SPEC_ISSUE'; then
    routing="architect"
  fi
  echo "[HARNESS] qa routing: $routing"

  case "$routing" in
    engineer_direct)
      _run_bugfix_direct
      ;;
    design)
      echo "[HARNESS] DESIGN_ISSUE → 루프 B 전환"
      run_design
      ;;
    *)
      _run_bugfix_full
      ;;
  esac
}

# ── engineer 직접 경로: architect Mode F → engineer → vitest → validator Mode D → commit ──
_run_bugfix_direct() {
  # impl 파일이 이미 있으면 architect 스킵
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] impl 존재 ($IMPL_FILE) → architect 스킵"
  else
    echo "[HARNESS] Phase B2 — architect Bugfix Plan(Mode F) 호출 중"
    _agent_call "architect" 300 \
      "Bugfix Plan(Mode F) — ${qa_out} issue: #$ISSUE_NUM" \
      "/tmp/${PREFIX}_arch_out.txt"
    IMPL_FILE=$(grep -oE 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt" | head -1 || echo "")

    if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
      echo "[HARNESS] Mode F impl 생성 실패 → full 경로로 폴백"
      _run_bugfix_full
      return
    fi
  fi

  local attempt=0
  local MAX_HOTFIX=3
  while [[ $attempt -lt $MAX_HOTFIX ]]; do
    attempt=$((attempt + 1))
    kill_check
    echo "[HARNESS] engineer 직접 (attempt $attempt/$MAX_HOTFIX)"

    local context
    context=$(cat "$IMPL_FILE" 2>/dev/null | head -c 30000)
    local AGENT_EXIT=0
    _agent_call "engineer" 900 \
      "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: Bugfix Plan의 버그 수정 이행
context:
$context
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?

    if [[ $AGENT_EXIT -eq 124 ]]; then
      echo "[HARNESS] engineer timeout — 재시도"
      continue
    fi

    # vitest 직접 실행 (test-engineer 스킵)
    echo "[HARNESS] vitest run (ground truth)"
    local vitest_exit=0
    npx vitest run --reporter=verbose 2>&1 | tail -100 > "/tmp/${PREFIX}_vitest_out.txt" || vitest_exit=$?

    if [[ $vitest_exit -eq 0 ]]; then
      # validator Mode D (Bugfix Validation)
      echo "[HARNESS] validator Bugfix Validation(Mode D) 호출 중"
      _agent_call "validator" 300 \
        "Mode D — Bugfix Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM vitest: PASS" \
        "/tmp/${PREFIX}_val_bf_out.txt"
      local bf_result
      bf_result=$(grep -oE 'BUGFIX_PASS|BUGFIX_FAIL' "/tmp/${PREFIX}_val_bf_out.txt" | head -1 || echo "UNKNOWN")

      if [[ "$bf_result" == "BUGFIX_PASS" ]]; then
        commit_files=()
        while IFS= read -r _f; do [[ -n "$_f" ]] && commit_files+=("$_f"); done \
          < <(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}')
        if [[ ${#commit_files[@]} -gt 0 ]]; then
          git add -- "${commit_files[@]}"
          git commit -m "$(generate_commit_msg) [bugfix-direct]"
          local commit_hash
          commit_hash=$(git rev-parse --short HEAD)
          export HARNESS_RESULT="HARNESS_DONE"
          echo "HARNESS_DONE (engineer_direct)"
          echo "impl: $IMPL_FILE"
          echo "issue: #$ISSUE_NUM"
          echo "commit: $commit_hash"
          exit 0
        else
          echo "[HARNESS] 변경사항 없음"
          exit 0
        fi
      fi
      echo "[HARNESS] validator BUGFIX_FAIL — engineer 재시도"
    else
      echo "[HARNESS] vitest 실패 (exit=$vitest_exit) — engineer 재시도"
    fi
  done

  rm -f "/tmp/${PREFIX}_plan_validation_passed"
  export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
  echo "IMPLEMENTATION_ESCALATE (engineer_direct ${MAX_HOTFIX}회 실패)"
  exit 1
}

# ── 기존 full 경로: architect Mode B → validator Mode C → 루프 C ──
_run_bugfix_full() {
  echo "[HARNESS] Phase B2 — architect bugfix Mode B (full) 호출 중"
  _agent_call "architect" 900 \
    "버그픽스 — Module Plan(Mode B) — ${qa_out} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_out.txt"
  IMPL_FILE=$(grep -oE 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt" | head -1 || echo "")

  # Phase 0.8 재사용 (IMPL_FILE이 이미 설정됨)
  run_impl
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
  impl2)
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    bash "$LOOP_SCRIPT" impl2 --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --depth "$DEPTH"
    ;;
  design)  run_design ;;
  bugfix)  run_bugfix ;;
  plan)    run_plan ;;
  *)       echo "[HARNESS] 알 수 없는 mode: $MODE"; exit 1 ;;
esac
