#!/bin/bash
# ~/.claude/harness-watch.sh
# 하네스 로그 실시간 감시 — terminal 이벤트 감지 시 자동 종료
#
# 사용법: bash ~/.claude/harness-watch.sh <log_file> [timeout_secs=600]
#
# 종료 트리거:
#   HARNESS_DONE, IMPLEMENTATION_ESCALATE, PLAN_VALIDATION_PASS,
#   PLAN_VALIDATION_ESCALATE, DESIGN_DONE, DESIGN_LOOP_ESCALATE,
#   UI_DESIGN_REQUIRED, SPEC_GAP_ESCALATE, HARNESS_KILLED,
#   HARNESS_BUDGET_EXCEEDED, MERGE_CONFLICT_ESCALATE

LOG="$1"
TIMEOUT="${2:-600}"

# macOS timeout 호환
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

if [[ -z "$LOG" ]]; then
  echo "[WATCH] 사용법: harness-watch.sh <log_file> [timeout_secs]"
  exit 1
fi

# 로그 파일 생성 대기 (하네스 시작 직후라 약간 지연될 수 있음)
for i in $(seq 1 20); do
  [[ -f "$LOG" ]] && break
  sleep 0.5
done

if [[ ! -f "$LOG" ]]; then
  echo "[WATCH] 타임아웃: 로그 파일이 생성되지 않음: $LOG"
  exit 1
fi

TERMINAL_RE="HARNESS_DONE|IMPLEMENTATION_ESCALATE|PLAN_VALIDATION_PASS|PLAN_VALIDATION_ESCALATE|DESIGN_DONE|DESIGN_LOOP_ESCALATE|UI_DESIGN_REQUIRED|SPEC_GAP_ESCALATE|HARNESS_KILLED|HARNESS_BUDGET_EXCEEDED|MERGE_CONFLICT_ESCALATE"

echo "[WATCH] 로그 감시 시작: $LOG"
echo "[WATCH] 종료 트리거: HARNESS_DONE / ESCALATE / PASS 등"
echo "────────────────────────────────────────"

# timeout으로 무한 대기 방지, tail -f | while 로 줄별 감시
timeout "$TIMEOUT" tail -f "$LOG" 2>/dev/null | while IFS= read -r line; do
  echo "$line"
  if echo "$line" | grep -qE "$TERMINAL_RE"; then
    break
  fi
done

echo "────────────────────────────────────────"
echo "[WATCH] 하네스 종료 감지 — 감시 완료"
