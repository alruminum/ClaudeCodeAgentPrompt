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
  local result="${HARNESS_RESULT:-unknown}"
  # 미설정(unknown) = 크래시/unhandled exit → HARNESS_CRASH로 마킹
  if [[ "$result" == "unknown" ]]; then
    result="HARNESS_CRASH"
  fi
  local t_end; t_end=$(date +%s)
  printf '{"event":"run_end","t":%d,"elapsed":%d,"result":"%s"}\n' \
    "$t_end" "$((t_end - _HARNESS_RUN_START))" "$result" >> "$RUN_LOG"
  # 크래시/실패 시 자동 리뷰 트리거 (백그라운드 — 하네스 종료를 블로킹하지 않음)
  if [[ "$result" == "HARNESS_CRASH" || "$result" == "IMPLEMENTATION_ESCALATE" ]]; then
    local review_script="${HOME}/.claude/scripts/harness-review.py"
    if [[ -f "$review_script" ]]; then
      python3 "$review_script" "$RUN_LOG" > "${RUN_LOG%.jsonl}_review.txt" 2>&1 &
    fi
  fi
}

# ── 킬 스위치 체크 (executor + loop 양쪽에서 사용) ────────────────────
kill_check() {
  if [ -f "/tmp/${PREFIX}_harness_kill" ]; then
    rm -f "/tmp/${PREFIX}_harness_active" "/tmp/${PREFIX}_harness_kill"
    export HARNESS_RESULT="HARNESS_KILLED"
    echo "HARNESS_KILLED: 사용자 요청으로 중단됨"
    exit 0
  fi
}

# ── 에이전트 호출 래퍼 ────────────────────────────────────────────────
# 사용법: _agent_call <agent> <timeout_secs> <prompt> <out_file>
# stream-json → tee to RUN_LOG(아카이브+실시간) → python3으로 result 텍스트 추출 → out_file
_agent_call() {
  local agent="$1" timeout_secs="$2" prompt="$3" out_file="$4"
  local cost_file="${out_file%.txt}_cost.txt"
  local stats_file="${out_file%.txt}_stats.json"
  local t_start; t_start=$(date +%s)
  local _call_exit=0

  echo "0" > "$cost_file"
  echo "{}" > "$stats_file"
  : > "$out_file"  # 파이프라인 실패 시에도 파일 존재 보장
  [[ -n "$RUN_LOG" ]] && printf '{"event":"agent_start","agent":"%s","t":%d,"prompt_chars":%d}\n' \
    "$agent" "$t_start" "${#prompt}" >> "$RUN_LOG"

  # 에이전트별 active 플래그 — agent-boundary.py가 이 플래그로 경로 제한 적용
  local _prefix_for_flag=""
  _prefix_for_flag=$(python3 -c '
import json, os, re
cp = os.path.join(os.getcwd(), ".claude", "harness.config.json")
if os.path.exists(cp):
    try:
        print(json.load(open(cp)).get("prefix","proj"))
    except: print("proj")
else:
    raw = os.path.basename(os.getcwd()).lower()
    print(re.sub(r"[^a-z0-9]","",raw)[:8] or "proj")
' 2>/dev/null || echo "proj")
  touch "/tmp/${_prefix_for_flag}_${agent}_active"

  echo "[HARNESS] ${agent} 호출 중..."

  # 공통 스코프 제한 — 하네스 인프라 탐색 방지
  local _scope_prefix="[SCOPE] 프로젝트 소스(src/, docs/, 루트 설정)만 분석 대상. .claude/, hooks/, harness-*.sh, orchestration-rules.md 등 하네스 인프라 파일은 읽지도 수정하지도 마라."
  prompt="${_scope_prefix}
${prompt}"

  # stream-json → tee to RUN_LOG(아카이브+실시간) → python3으로 result + cost + stats 추출
  # HARNESS_INTERNAL=1: 이 claude 호출이 UserPromptSubmit 훅을 재트리거하지 않도록 방지
  # NOTE: python3이 result를 out_file에 직접 쓴다 (stdout redirect 대신 파일 직접 쓰기).
  #       macOS에서 파이프라인 SIGPIPE/signal로 stdout flush가 안 되는 문제 방지.
  HARNESS_INTERNAL=1 timeout "$timeout_secs" claude --agent "$agent" --print --verbose \
    --output-format stream-json --include-partial-messages \
    --max-budget-usd 2.00 \
    --fallback-model haiku \
    -p "$prompt" 2>&1 \
    | tee -a "${RUN_LOG:-/dev/null}" \
    | python3 -c '
import sys, json

result = ""
cost = 0.0
cost_file = sys.argv[1] if len(sys.argv) > 1 else "/dev/null"
out_file = sys.argv[2] if len(sys.argv) > 2 else "/dev/null"
stats_file = sys.argv[3] if len(sys.argv) > 3 else "/dev/null"

# Tool usage tracking
tools = {}
files_read = []
cur_tool = ""
cur_input = ""

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        o = json.loads(line)
        t = o.get("type", "")

        if t == "result":
            result = o.get("result", "")
            cost = float(o.get("total_cost_usd", 0) or 0)

        elif t == "stream_event":
            e = o.get("event", {})
            et = e.get("type", "")

            if et == "content_block_start":
                cb = e.get("content_block", {})
                if cb.get("type") == "tool_use":
                    name = cb.get("name", "unknown")
                    tools[name] = tools.get(name, 0) + 1
                    cur_tool = name
                    cur_input = ""

            elif et == "content_block_delta":
                d = e.get("delta", {})
                if d.get("type") == "input_json_delta" and cur_tool in ("Read", "Glob", "Grep"):
                    cur_input += d.get("partial_json", "")

            elif et == "content_block_stop":
                if cur_tool in ("Read", "Glob") and cur_input:
                    try:
                        inp = json.loads(cur_input)
                        fp = inp.get("file_path", "") or inp.get("pattern", "")
                        if fp:
                            files_read.append(fp)
                    except Exception:
                        pass
                cur_tool = ""
                cur_input = ""
    except Exception:
        pass

for f in [
    (cost_file, lambda fh: fh.write(str(cost))),
    (out_file, lambda fh: fh.write(result)),
    (stats_file, lambda fh: json.dump({"tools": tools, "files_read": files_read[:50]}, fh)),
]:
    try:
        with open(f[0], "w") as fh:
            f[1](fh)
    except Exception:
        pass
' "$cost_file" "$out_file" "$stats_file" 2>/dev/null || _call_exit=$?

  local t_end; t_end=$(date +%s)
  local agent_cost; agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
  [[ -n "$RUN_LOG" ]] && printf '{"event":"agent_end","agent":"%s","t":%d,"elapsed":%d,"exit":%d,"cost_usd":%s,"prompt_chars":%d}\n' \
    "$agent" "$t_end" "$((t_end - t_start))" "$_call_exit" "$agent_cost" "${#prompt}" >> "$RUN_LOG"

  # agent_stats: 도구 사용 요약 + Read한 파일 목록 (별도 이벤트)
  if [[ -f "$stats_file" && -n "$RUN_LOG" ]]; then
    python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        s = json.load(f)
    s["event"] = "agent_stats"
    s["agent"] = sys.argv[2]
    print(json.dumps(s, ensure_ascii=False))
except Exception:
    pass
' "$stats_file" "$agent" >> "$RUN_LOG" 2>/dev/null
  fi

  # 에이전트 active 플래그 해제
  rm -f "/tmp/${_prefix_for_flag}_${agent}_active" 2>/dev/null

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
