#!/bin/bash
# Stop hook — 하네스 실행 중이면 종료 차단
# exit 0 = 종료 허용, exit 2 = 종료 차단

CONFIG=".claude/harness.config.json"
if [ ! -f "$CONFIG" ]; then
  exit 0
fi

PREFIX=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('prefix','proj'))" 2>/dev/null)
if [ -z "$PREFIX" ]; then
  exit 0
fi

# Kill switch → 즉시 종료 허용
if [ -f "/tmp/${PREFIX}_harness_kill" ]; then
  exit 0
fi

# 하네스 실행 중이면 차단
if [ -f "/tmp/${PREFIX}_harness_active" ]; then
  echo "[STOP GATE] 하네스 실행 중. 완료 전까지 종료 불가."
  echo "중단하려면: /harness-kill"
  exit 2
fi

exit 0
