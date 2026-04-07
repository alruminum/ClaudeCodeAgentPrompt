#!/bin/bash
# ~/.claude/harness-utils.sh
# 하네스 공용 유틸 — harness-executor.sh + harness-loop.sh에서 source

HARNESS_LOG_DIR="${HOME}/.claude/harness-logs"
RUN_LOG=""          # rotate_harness_logs() 호출 후 설정
_HARNESS_RUN_START=0  # write_run_end에서 elapsed 계산용

# ── FIFO 로테이션: prefix별 최신 10개 유지 ──────────────────────────────
# mapfile 제거 → bash 3.2(macOS 기본) 호환
rotate_harness_logs() {
  local prefix="$1" mode="${2:-unknown}"
  local dir="${HARNESS_LOG_DIR}/${prefix}"
  mkdir -p "$dir"

  # 10번째 이후(오래된 것)를 삭제 → 새 파일 추가 후 최대 10개 유지
  # glob 미사용: zsh 소싱 시 "no matches found" 에러 방지
  ls -t "$dir" 2>/dev/null \
    | grep '^run_.*\.jsonl$' \
    | tail -n +10 \
    | xargs -I{} rm -f "$dir/{}" 2>/dev/null || true

  _HARNESS_RUN_START=$(date +%s)
  local ts; ts=$(date +%Y%m%d_%H%M%S)
  RUN_LOG="${dir}/run_${ts}.jsonl"

  printf '{"event":"run_start","prefix":"%s","mode":"%s","t":%d}\n' \
    "$prefix" "$mode" "$_HARNESS_RUN_START" > "$RUN_LOG"

  echo "[HARNESS] 실행 로그: $RUN_LOG"
  echo "[HARNESS] 실시간 확인: tail -f $RUN_LOG"
}

# ── run_end 이벤트 기록 ───────────────────────────────────────────────
write_run_end() {
  [[ -z "$RUN_LOG" || ! -f "$RUN_LOG" ]] && return
  local t_end; t_end=$(date +%s)
  printf '{"event":"run_end","t":%d,"elapsed":%d}\n' \
    "$t_end" "$((t_end - _HARNESS_RUN_START))" >> "$RUN_LOG"
}

# ── 에이전트 호출 래퍼 ────────────────────────────────────────────────
# 사용법: _agent_call <agent> <timeout_secs> <prompt> <out_file>
# stream-json → tee to RUN_LOG(아카이브+실시간) → python3으로 result 텍스트 추출 → out_file
_agent_call() {
  local agent="$1" timeout_secs="$2" prompt="$3" out_file="$4"
  local cost_file="${out_file%.txt}_cost.txt"
  local t_start; t_start=$(date +%s)
  local _call_exit=0

  echo "0" > "$cost_file"
  : > "$out_file"  # 파이프라인 실패 시에도 파일 존재 보장
  [[ -n "$RUN_LOG" ]] && printf '{"event":"agent_start","agent":"%s","t":%d}\n' \
    "$agent" "$t_start" >> "$RUN_LOG"

  echo "[HARNESS] ${agent} 호출 중..."

  # stream-json → tee to RUN_LOG(아카이브+실시간) → python3으로 result + cost 추출 → out_file
  # HARNESS_INTERNAL=1: 이 claude 호출이 UserPromptSubmit 훅을 재트리거하지 않도록 방지
  # NOTE: python3이 result를 out_file에 직접 쓴다 (stdout redirect 대신 파일 직접 쓰기).
  #       macOS에서 파이프라인 SIGPIPE/signal로 stdout flush가 안 되는 문제 방지.
  HARNESS_INTERNAL=1 timeout "$timeout_secs" claude --agent "$agent" --print --verbose \
    --output-format stream-json --include-partial-messages \
    --max-budget-usd 2.00 \
    -p "$prompt" 2>&1 \
    | tee -a "${RUN_LOG:-/dev/null}" \
    | python3 -c '
import sys, json
result = ""
cost = 0.0
cost_file = sys.argv[1] if len(sys.argv) > 1 else "/dev/null"
out_file = sys.argv[2] if len(sys.argv) > 2 else "/dev/null"
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        o = json.loads(line)
        if o.get("type") == "result":
            result = o.get("result", "")
            cost = float(o.get("total_cost_usd", 0) or 0)
    except Exception:
        pass
try:
    with open(cost_file, "w") as f:
        f.write(str(cost))
except Exception:
    pass
try:
    with open(out_file, "w") as f:
        f.write(result)
except Exception:
    pass
' "$cost_file" "$out_file" 2>/dev/null || _call_exit=$?

  local t_end; t_end=$(date +%s)
  local agent_cost; agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
  [[ -n "$RUN_LOG" ]] && printf '{"event":"agent_end","agent":"%s","t":%d,"elapsed":%d,"exit":%d,"cost_usd":%s}\n' \
    "$agent" "$t_end" "$((t_end - t_start))" "$_call_exit" "$agent_cost" >> "$RUN_LOG"

  echo "[HARNESS] ${agent} 완료 ($((t_end - t_start))s, exit=${_call_exit})"

  # 에이전트 결과 요약을 harness output log에 출력 (tail -f로 실시간 확인용)
  if [[ -s "$out_file" ]]; then
    local total_lines; total_lines=$(wc -l < "$out_file" | tr -d ' ')
    echo "┌── ${agent} 출력 (${total_lines}줄) ──"
    head -30 "$out_file"
    [[ "$total_lines" -gt 30 ]] && echo "  ... (나머지 $((total_lines - 30))줄 생략)"
    echo "└──────────────────────────────────"
  fi
  return $_call_exit
}
