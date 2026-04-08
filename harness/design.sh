#!/bin/bash
# ~/.claude/harness/design.sh
# design 모드: designer → design-critic → DESIGN_DONE
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

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
