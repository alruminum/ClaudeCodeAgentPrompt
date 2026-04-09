#!/bin/bash
# ~/.claude/harness/utils.sh
# 하네스 공용 유틸 — harness/executor.sh + harness/impl-process.sh에서 source

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
  echo "[HARNESS] 실시간 확인: tail -f \"$RUN_LOG\""
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
  # branch_name: 제어문자/탭/개행 제거 (git status 출력 혼입 방지)
  local branch_name="${HARNESS_BRANCH:-}"
  branch_name=$(printf '%s' "$branch_name" | tr -d '\t\n\r' | head -c 100)
  printf '{"event":"run_end","t":%d,"elapsed":%d,"result":"%s","branch":"%s"}\n' \
    "$t_end" "$((t_end - _HARNESS_RUN_START))" "$result" "$branch_name" >> "$RUN_LOG"
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
  if [[ -f "/tmp/${PREFIX}_harness_kill" ]]; then
    rm -f "/tmp/${PREFIX}_harness_active" "/tmp/${PREFIX}_harness_kill"
    export HARNESS_RESULT="HARNESS_KILLED"
    echo "HARNESS_KILLED: 사용자 요청으로 중단됨"
    exit 0
  fi
}

# ── 에이전트 출력에서 마커 파싱 ───────────────────────────────────────
# 사용법: parse_marker <out_file> <marker_list>
#   marker_list: "PASS|FAIL" 또는 "LGTM|CHANGES_REQUESTED" 등
# 반환: 매칭된 마커 (없으면 "UNKNOWN")
parse_marker() {
  local out_file="$1" marker_list="$2"
  local result=""
  result=$(grep -oEm1 "\\b(${marker_list})\\b" "$out_file" 2>/dev/null) || result=""
  if [[ -z "$result" ]]; then
    echo "UNKNOWN"
  else
    echo "$result"
  fi
}

# ── Plan Validation 공통 로직 ─────────────────────────────────────────
# 사용법: run_plan_validation <impl_file> <issue_num> <prefix> [max_rework]
# 반환: 0=PASS, 1=ESCALATE
# 부수효과: plan_validation_passed 플래그 생성 (PASS 시)
run_plan_validation() {
  local impl_file="$1" issue_num="$2" prefix="$3" max_rework="${4:-1}"
  local val_out_file="/tmp/${prefix}_val_pv_out.txt"

  echo "[HARNESS] validator Plan Validation 호출 중"
  _agent_call "validator" 300 \
    "Mode C — Plan Validation — impl: $impl_file issue: #$issue_num" \
    "$val_out_file"
  local val_result
  val_result=$(parse_marker "$val_out_file" "PASS|FAIL")
  echo "[HARNESS] Plan Validation 결과: $val_result"

  if [[ "$val_result" == "PASS" ]]; then
    touch "/tmp/${prefix}_plan_validation_passed"
    return 0
  fi

  # FAIL → architect 재보강 (max_rework회)
  local rework=0
  while [[ $rework -lt $max_rework ]]; do
    rework=$((rework + 1))
    echo "[HARNESS] Plan Validation FAIL → architect 재보강 ($rework/$max_rework)"
    local fail_feedback
    fail_feedback=$(tail -20 "$val_out_file")
    _agent_call "architect" 900 \
      "SPEC_GAP(Mode C) — Plan Validation FAIL 피드백 반영. impl: $impl_file feedback: ${fail_feedback}" \
      "/tmp/${prefix}_arch_fix_out.txt"

    local val_out_file2="/tmp/${prefix}_val_pv_out${rework}.txt"
    _agent_call "validator" 300 \
      "Mode C — Plan Validation — impl: $impl_file issue: #$issue_num" \
      "$val_out_file2"
    val_result=$(parse_marker "$val_out_file2" "PASS|FAIL")
    echo "[HARNESS] Plan Validation 재검증 결과: $val_result"

    if [[ "$val_result" == "PASS" ]]; then
      touch "/tmp/${prefix}_plan_validation_passed"
      return 0
    fi
  done

  # 재보강 후에도 FAIL → ESCALATE
  return 1
}

# ── Design Validation 공통 로직 ───────────────────────────────────────
# 사용법: run_design_validation <design_doc> <issue_num> <prefix> [max_rework]
# 반환: 0=PASS, 1=ESCALATE
run_design_validation() {
  local design_doc="$1" issue_num="$2" prefix="$3" max_rework="${4:-1}"
  local val_out_file="/tmp/${prefix}_val_dv_out.txt"

  echo "[HARNESS] validator Design Validation 호출 중"
  _agent_call "validator" 300 \
    "Mode A — Design Validation — design_doc: $design_doc issue: #$issue_num" \
    "$val_out_file"
  local val_result
  val_result=$(parse_marker "$val_out_file" "PASS|FAIL")
  echo "[HARNESS] Design Validation 결과: $val_result"

  if [[ "$val_result" == "PASS" ]]; then
    return 0
  fi

  # FAIL → architect 재설계 (max_rework회)
  local rework=0
  while [[ $rework -lt $max_rework ]]; do
    rework=$((rework + 1))
    echo "[HARNESS] Design Validation FAIL → architect 재설계 ($rework/$max_rework)"
    local fail_feedback
    fail_feedback=$(tail -20 "$val_out_file")
    _agent_call "architect" 900 \
      "System Design 재설계 — Design Validation FAIL 피드백 반영. design_doc: $design_doc feedback: ${fail_feedback}" \
      "/tmp/${prefix}_arch_dv_fix_out.txt"

    local val_out_file2="/tmp/${prefix}_val_dv_out${rework}.txt"
    _agent_call "validator" 300 \
      "Mode A — Design Validation — design_doc: $design_doc issue: #$issue_num" \
      "$val_out_file2"
    val_result=$(parse_marker "$val_out_file2" "PASS|FAIL")
    echo "[HARNESS] Design Validation 재검증 결과: $val_result"

    if [[ "$val_result" == "PASS" ]]; then
      return 0
    fi
  done

  return 1
}

# ── 소스 파일 경로 추출 (impl 또는 error trace에서) ───────────────────
# impl 파일에서 참조된 src/ 경로를 추출
extract_src_refs() {
  local file="$1"
  grep -oE 'src/[^ `"'"'"']+\.(ts|tsx|js|jsx)' "$file" 2>/dev/null | sort -u | head -5 || true
}

# error trace에서 src/ 경로 역추적
extract_files_from_error() {
  echo "$1" | grep -oE 'src/[^ :()]+\.(ts|tsx|js|jsx)' | sort -u | head -5 || true
}

# ── 스마트 컨텍스트 구성 ──────────────────────────────────────────────
# 파일 통째가 아닌 관련 청크만 선별 포함 (30KB 캡)
# 사용법: build_smart_context <impl_or_doc> <attempt_n> [error_trace]
#   attempt_n=0: impl 내용 + 참조 소스 (각 3KB 캡)
#   attempt_n>0: error trace 관련 파일만
build_smart_context() {
  local impl="$1" attempt_n="$2" err_trace="${3:-}"
  local ctx=""

  if [[ $attempt_n -eq 0 ]]; then
    ctx=$(cat "$impl")
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      [[ -f "$f" ]] && ctx="${ctx}
=== ${f} ===
$(head -c 3000 "$f")"
    done < <(extract_src_refs "$impl")
  else
    # retry 시에도 impl 포함 — engineer(N)이 impl 파일 재읽기하는 낭비 방지
    ctx=$(head -c 6000 "$impl")
    local failed_files
    failed_files=$(extract_files_from_error "$err_trace")
    if [[ -n "$failed_files" ]]; then
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        [[ -f "$f" ]] && ctx="${ctx}
=== ${f} ===
$(cat "$f")"
      done <<< "$failed_files"
    fi
  fi

  echo "$ctx" | head -c 30000
}

# ── validator용 변경 diff 컨텍스트 ────────────────────────────────────
# validator에게 impl + 변경된 파일 diff를 함께 전달해 Read 호출 절약
# 사용법: build_validator_context <impl_file>
build_validator_context() {
  local impl_file="$1"
  local ctx=""
  # impl 내용
  [[ -f "$impl_file" ]] && ctx=$(head -c 10000 "$impl_file")
  # 변경된 파일의 diff (staged + unstaged)
  local diff_out
  diff_out=$(git diff HEAD 2>/dev/null | head -c 15000 || true)
  if [[ -n "$diff_out" ]]; then
    ctx="${ctx}

=== git diff (changed files) ===
${diff_out}"
  fi
  echo "$ctx" | head -c 20000
}

# ── Feature branch 생성 ──────────────────────────────────────────────
# 사용법: create_feature_branch <type> <issue_num>
# 반환: 브랜치 이름 (stdout)
create_feature_branch() {
  local type="$1" issue_num="$2"

  # milestone: harness.config.json에서 읽기
  local milestone=""
  local config_file; config_file="$(pwd)/.claude/harness.config.json"
  if [[ -f "$config_file" ]]; then
    milestone=$(python3 -c '
import json, sys
try: print(json.load(open(sys.argv[1])).get("milestone",""))
except: pass
' "$config_file" 2>/dev/null || true)
  fi

  # slug: gh issue title → 영문/숫자만, 30자 캡
  local slug=""
  if command -v gh &>/dev/null; then
    local raw_title=""
    raw_title=$(gh issue view "$issue_num" --json title -q .title 2>/dev/null || true)
    if [[ -n "$raw_title" ]]; then
      slug=$(printf '%s' "$raw_title" \
        | tr '[:upper:]' '[:lower:]' \
        | sed 's/[^a-z0-9 -]//g' | sed 's/  */ /g' \
        | tr ' ' '-' | sed 's/--*/-/g; s/^-//; s/-$//' \
        | cut -c1-30)
    fi
  fi

  # 브랜치명 조립 (# 없이 숫자만)
  local branch_name="${type}/"
  [[ -n "$milestone" ]] && branch_name="${branch_name}${milestone}-"
  branch_name="${branch_name}${issue_num}"
  [[ -n "$slug" ]] && branch_name="${branch_name}-${slug}"

  # default branch 감지
  local default_branch
  default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
    | sed 's@^refs/remotes/origin/@@' || echo "main")

  # 이미 동일 브랜치 존재 → 체크아웃만 (재진입)
  if git show-ref --verify --quiet "refs/heads/${branch_name}" 2>/dev/null; then
    git checkout "$branch_name"
    echo "$branch_name"
    return 0
  fi

  git checkout -b "$branch_name" "$default_branch"
  echo "$branch_name"
}

# ── Feature branch → main 머지 ───────────────────────────────────────
# 사용법: merge_to_main <branch_name> <issue_num> <depth> <prefix>
# 반환: 0=성공, 1=실패
merge_to_main() {
  local branch_name="$1" issue_num="$2" depth="$3" prefix="$4"

  local default_branch
  default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
    | sed 's@^refs/remotes/origin/@@' || echo "main")

  # 머지 전 게이트 (depth별 3-way 분기)
  if [[ "$depth" == "deep" ]]; then
    if [[ ! -f "/tmp/${prefix}_pr_reviewer_lgtm" ]]; then
      echo "[HARNESS] merge 거부: pr_reviewer_lgtm 없음 (deep)"
      return 1
    fi
    if [[ ! -f "/tmp/${prefix}_security_review_passed" ]]; then
      echo "[HARNESS] merge 거부: security_review_passed 없음 (deep)"
      return 1
    fi
  elif [[ "$depth" == "std" || "$depth" == "bugfix" ]]; then
    if [[ ! -f "/tmp/${prefix}_validator_b_passed" ]]; then
      echo "[HARNESS] merge 거부: validator_b_passed 없음 ($depth)"
      return 1
    fi
  fi
  # fast: 게이트 없음 — engineer 커밋만으로 머지

  git checkout "$default_branch"

  local merge_msg
  merge_msg=$(printf 'merge: %s (#%s)' "$branch_name" "$issue_num")

  if ! git merge --no-ff -m "$merge_msg" "$branch_name" 2>/dev/null; then
    git merge --abort 2>/dev/null || true
    git checkout "$branch_name" 2>/dev/null || true
    echo "MERGE_CONFLICT_ESCALATE"
    return 1
  fi

  git branch -d "$branch_name" 2>/dev/null || true
  return 0
}

# ── 커밋 메시지 생성 ─────────────────────────────────────────────────
# IMPL_FILE, ISSUE_NUM 전역변수 의존 (harness/impl-process.sh, harness/executor.sh에서 설정)
generate_commit_msg() {
  local impl_name
  if [[ -n "$IMPL_FILE" ]]; then
    impl_name=$(basename "$IMPL_FILE" .md)
  else
    impl_name="bugfix-${ISSUE_NUM:-unknown}"
  fi
  local changed; changed=$(git diff --cached --name-only 2>/dev/null | head -5 | tr '\n' ' ' || echo "(파일 목록 없음)")
  cat <<MSGEOF
feat: implement ${impl_name} (#${ISSUE_NUM})

[왜] Issue #${ISSUE_NUM} 구현
[변경]
- ${changed}

Closes #${ISSUE_NUM}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
MSGEOF
}

# ── 변경된 파일 수집 ──────────────────────────────────────────────────
# 사용법: collect_changed_files
# stdout: 변경된 파일 목록 (개행 구분)
# 반환: 0=변경 있음, 1=변경 없음
collect_changed_files() {
  local files
  files=$(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}')
  if [[ -z "$files" ]]; then
    return 1
  fi
  echo "$files"
  return 0
}

# ── 커밋 + 머지 + HARNESS_DONE 일괄 처리 ─────────────────────────────
# 사용법: harness_commit_and_merge <branch> <issue> <depth> <prefix> [suffix]
# suffix: 커밋 메시지 접미사 (예: "[fast-mode]", "[bugfix-std]")
# 반환: 0=성공(HARNESS_DONE), 1=머지 실패(MERGE_CONFLICT_ESCALATE)
# 부수효과: HARNESS_RESULT 설정, exit 수행하지 않음 (호출자가 exit)
harness_commit_and_merge() {
  local branch="$1" issue="$2" depth="$3" prefix="$4" suffix="${5:-}"

  # 미커밋 변경이 있으면 커밋
  local commit_files_arr=()
  while IFS= read -r _f; do
    [[ -n "$_f" ]] && commit_files_arr+=("$_f")
  done < <(collect_changed_files)

  if [[ ${#commit_files_arr[@]} -gt 0 ]]; then
    git add -- "${commit_files_arr[@]}"
    local msg
    msg=$(generate_commit_msg)
    [[ -n "$suffix" ]] && msg="${msg} ${suffix}"
    git commit -m "$msg"
  fi

  # merge to main (engineer가 이미 커밋했을 수 있으므로 항상 시도)
  if ! merge_to_main "$branch" "$issue" "$depth" "$prefix"; then
    export HARNESS_RESULT="MERGE_CONFLICT_ESCALATE"
    echo "MERGE_CONFLICT_ESCALATE"
    echo "branch: $branch"
    return 1
  fi

  return 0
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
  # 도구 제한 — Agent 도구는 메인 Claude 전용, 모든 서브에이전트에서 기본 금지
  local _disallow_flags="--disallowedTools Agent"

  HARNESS_INTERNAL=1 HARNESS_PREFIX="$_prefix_for_flag" timeout "$timeout_secs" claude --agent "$agent" --print --verbose \
    --output-format stream-json --include-partial-messages \
    --max-budget-usd 2.00 \
    --permission-mode bypassPermissions \
    $_disallow_flags \
    --fallback-model haiku \
    -p "$prompt" 2>&1 \
    | tee -a "${RUN_LOG:-/dev/null}" \
    | python3 -c '
import sys, json

result = ""
cost = 0.0
in_tok = 0
out_tok = 0
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
            usage = o.get("usage", {})
            if usage:
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)

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

            elif et == "message_delta":
                u = e.get("usage", {})
                if u and in_tok == 0:
                    in_tok += u.get("input_tokens", 0)
                    out_tok += u.get("output_tokens", 0)
    except Exception:
        pass

for f in [
    (cost_file, lambda fh: fh.write(str(cost))),
    (out_file, lambda fh: fh.write(result)),
    (stats_file, lambda fh: json.dump({"tools": tools, "files_read": files_read[:50], "in_tok": in_tok, "out_tok": out_tok}, fh)),
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
