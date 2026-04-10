#!/bin/bash
# ~/.claude/harness/impl.sh
# 루프 C (구현 루프): plan_validation_passed → engineer process 위임
# planning fallback: impl 없으면 architect Module Plan → validator Plan Validation
#
# harness/executor.sh에서 source — 전역변수(PREFIX, IMPL_FILE, ISSUE_NUM 등) 사용

run_impl() {
  # ── 재진입 상태 감지 ──
  # plan_validation_passed 플래그 + impl 파일 있으면 → engineer 루프로 바로 진입
  if [[ -f "/tmp/${PREFIX}_plan_validation_passed" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: plan_validation_passed + impl 존재 → engineer 루프 직접 진입"
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    local sub_script="${IMPL_SCRIPT_DIR}/impl_${DEPTH}.sh"
    bash "$sub_script" --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --branch-type "$BRANCH_TYPE"
    return
  fi

  # UI 키워드 감지 (design 루프 전환 판단)
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    local ui_kw
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

  # impl 파일 없으면 architect Module Plan 호출
  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] architect Module Plan 작성"
    _agent_call "architect" 900 \
      "@MODE:ARCHITECT:MODULE_PLAN
issue #${ISSUE_NUM} impl 계획 작성. context: ${CONTEXT}" \
      "/tmp/${PREFIX}_arch_out.txt"
    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""
    echo "[HARNESS] impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # Plan Validation (구현 전 게이트)
  echo "[HARNESS] Plan Validation"
  if run_plan_validation "$IMPL_FILE" "$ISSUE_NUM" "$PREFIX" 1; then
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
  exit 1
}
