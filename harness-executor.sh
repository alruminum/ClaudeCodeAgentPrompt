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
#   bugfix — qa → architect bugfix → Plan Validation
#   plan   — product-planner → architect Mode A → PLAN_DONE

set -euo pipefail

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"

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

# ── 공통: harness-loop.sh 경로 결정 ─────────────────────────────────
LOOP_SCRIPT=".claude/harness-loop.sh"
[[ ! -f "$LOOP_SCRIPT" ]] && LOOP_SCRIPT="${HOME}/.claude/harness-loop.sh"

# ══════════════════════════════════════════════════════════════════════
# mode: impl (Phase 0.5 → 0.7 → 0.8 → PLAN_VALIDATION_PASS)
# ══════════════════════════════════════════════════════════════════════
run_impl() {
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

  # Phase 0.7 — impl 파일 없으면 architect 호출
  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] Phase 0.7 — architect Mode B 호출 중"
    claude --agent architect --print \
      -p "Module Plan(Mode B) — issue #${ISSUE_NUM} impl 계획 작성. context: ${CONTEXT}" \
      > "/tmp/${PREFIX}_arch_out.txt" 2>&1 || true
    IMPL_FILE=$(grep -oE 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt" | head -1 || echo "")
    echo "[HARNESS] Phase 0.7 — architect 완료 / impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # Phase 0.8 — validator Plan Validation (Mode C)
  echo "[HARNESS] Phase 0.8 — validator Plan Validation 호출 중"
  claude --agent validator --print \
    -p "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_val_pv_out.txt" 2>&1 || true
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
  claude --agent architect --print \
    -p "SPEC_GAP(Mode C) — Plan Validation FAIL 피드백 반영. impl: $IMPL_FILE feedback: ${fail_feedback}" \
    > "/tmp/${PREFIX}_arch_fix_out.txt" 2>&1 || true
  echo "[HARNESS] Phase 0.8 — architect 재보강 완료, 재검증 중"

  claude --agent validator --print \
    -p "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_val_pv_out2.txt" 2>&1 || true
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
  attempt=0; MAX=3
  while [[ $attempt -lt $MAX ]]; do
    echo "[HARNESS] Phase D1 attempt $((attempt+1))/$MAX — designer 호출 중"
    claude --agent designer --print \
      -p "issue: #$ISSUE_NUM context: $CONTEXT" \
      > "/tmp/${PREFIX}_des_out.txt" 2>&1 || true

    echo "[HARNESS] Phase D2 attempt $((attempt+1))/$MAX — design-critic 호출 중"
    des_out=$(cat "/tmp/${PREFIX}_des_out.txt")
    claude --agent design-critic --print \
      -p "$des_out" \
      > "/tmp/${PREFIX}_dc_out.txt" 2>&1 || true
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
# mode: bugfix (Phase B1 → B2 → Plan Validation)
# ══════════════════════════════════════════════════════════════════════
run_bugfix() {
  echo "[HARNESS] Phase B1 — qa 호출 중"
  claude --agent qa --print \
    -p "bug: $BUG_DESC issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_qa_out.txt" 2>&1 || true
  qa_out=$(cat "/tmp/${PREFIX}_qa_out.txt")

  echo "[HARNESS] Phase B2 — architect bugfix Mode B 호출 중"
  claude --agent architect --print \
    -p "버그픽스 — Module Plan(Mode B) — ${qa_out} issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_arch_out.txt" 2>&1 || true
  IMPL_FILE=$(grep -oE 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt" | head -1 || echo "")

  # Phase 0.8 재사용 (IMPL_FILE이 이미 설정됨)
  run_impl
}

# ══════════════════════════════════════════════════════════════════════
# mode: plan (Phase P1 → P2 → PLAN_DONE)
# ══════════════════════════════════════════════════════════════════════
run_plan() {
  echo "[HARNESS] Phase P1 — product-planner 호출 중"
  claude --agent product-planner --print \
    -p "context: $CONTEXT issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_pp_out.txt" 2>&1 || true
  pp_out=$(cat "/tmp/${PREFIX}_pp_out.txt")

  echo "[HARNESS] Phase P2 — architect Mode A 호출 중"
  claude --agent architect --print \
    -p "System Design(Mode A) — ${pp_out} issue: #$ISSUE_NUM" \
    > "/tmp/${PREFIX}_arch_out.txt" 2>&1 || true

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
