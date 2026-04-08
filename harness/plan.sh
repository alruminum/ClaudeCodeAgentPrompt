#!/bin/bash
# ~/.claude/harness/plan.sh
# plan 모드: product-planner → architect Mode A → PLAN_DONE
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

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
