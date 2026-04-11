#!/bin/bash
# ~/.claude/harness/plan.sh
# plan 모드: product-planner → architect → validator → READY_FOR_IMPL
#
# 흐름 (plan.md 기반):
#   신규: product-planner → architect System Design → validator Design Validation
#         → (Epic 판단) architect Task Decompose 또는 Module Plan
#         → validator Plan Validation → READY_FOR_IMPL
#   변경: product-planner → (전체 구조 변경?) architect System Design 또는 Module Plan 직접
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

run_plan() {
  rotate_harness_logs "$PREFIX" "plan"
  # 루프 타입별 컨텍스트 prepend
  local _lc
  _lc=$(build_loop_context "plan" 2>/dev/null || true)
  if [[ -n "$_lc" ]]; then
    CONTEXT="${_lc}
${CONTEXT}"
  fi

  # ── product-planner ──
  echo "[HARNESS] product-planner 기획"
  _agent_call "product-planner" 300 \
    "@MODE:PLANNER:PRODUCT_PLAN
context: $CONTEXT issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_pp_out.txt"
  local pp_out
  pp_out=$(cat "/tmp/${PREFIX}_pp_out.txt")
  kill_check

  # product-planner 결과 마커 감지
  local pp_marker
  pp_marker=$(parse_marker "/tmp/${PREFIX}_pp_out.txt" "PRODUCT_PLAN_READY|PRODUCT_PLAN_UPDATED")

  # ── architect System Design ──
  echo "[HARNESS] architect System Design 작성"
  _agent_call "architect" 900 \
    "@MODE:ARCHITECT:SYSTEM_DESIGN
${pp_out} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_sd_out.txt"
  kill_check

  # design_doc 경로 추출
  local design_doc
  design_doc=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_sd_out.txt") || design_doc=""

  # ── Design Validation ──
  if [[ -n "$design_doc" && -f "$design_doc" ]]; then
    echo "[HARNESS] Design Validation"
    if ! run_design_validation "$design_doc" "$ISSUE_NUM" "$PREFIX" 1; then
      export HARNESS_RESULT="DESIGN_REVIEW_ESCALATE"
      echo "DESIGN_REVIEW_ESCALATE"
      echo "issue: #$ISSUE_NUM"
      echo "design_doc: $design_doc"
      exit 1
    fi
    echo "[HARNESS] Design Validation PASS"
  else
    echo "[HARNESS] design_doc 경로 미감지 — Design Validation 스킵"
  fi
  kill_check

  # ── architect Module Plan ──
  echo "[HARNESS] architect Module Plan 작성"
  _agent_call "architect" 900 \
    "@MODE:ARCHITECT:MODULE_PLAN
design_doc: ${design_doc:-N/A} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_mp_out.txt"
  kill_check

  local impl_file
  impl_file=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_mp_out.txt") || impl_file=""

  if [[ -z "$impl_file" || ! -f "$impl_file" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    echo "issue: #$ISSUE_NUM"
    exit 1
  fi

  # ── Plan Validation ──
  echo "[HARNESS] Plan Validation"
  if ! run_plan_validation "$impl_file" "$ISSUE_NUM" "$PREFIX" 1; then
    export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
    echo "PLAN_VALIDATION_ESCALATE"
    echo "impl: $impl_file"
    echo "issue: #$ISSUE_NUM"
    exit 1
  fi

  # ── 완료: PLAN_VALIDATION_PASS → 유저 게이트 ──
  echo "$impl_file" > "/tmp/${PREFIX}_impl_path"
  export HARNESS_RESULT="PLAN_VALIDATION_PASS"
  echo "PLAN_VALIDATION_PASS"
  echo "impl: $impl_file"
  echo "design_doc: ${design_doc:-N/A}"
  echo "issue: #$ISSUE_NUM"
  echo "필요 조치: 계획 확인 후 mode:impl 로 재호출"
  exit 0
}
