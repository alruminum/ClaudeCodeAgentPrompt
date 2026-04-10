#!/bin/bash
# ~/.claude/harness/impl-process.sh
# impl 모드 engineer 루프 — LLM 루프 해석 방지
#
# 호출 형식:
#   bash .claude/harness/impl-process.sh impl \
#     --impl <impl_file_path> \
#     --issue <issue_number> \
#     [--prefix <prefix>]
#
# 출력:
#   HARNESS_DONE         — 성공 (commit 완료)
#   IMPLEMENTATION_ESCALATE — 3회 모두 실패

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/utils.sh"

export HARNESS_RESULT="unknown"

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; DEPTH="std"; BRANCH_TYPE="feat"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)        IMPL_FILE="$2";   shift 2 ;;
    --issue)       ISSUE_NUM="$2";   shift 2 ;;
    --prefix)      PREFIX="$2";      shift 2 ;;
    --depth)       DEPTH="$2";       shift 2 ;;
    --branch-type) BRANCH_TYPE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ── 필수 인자 검증 ─────────────────────────────────────────────────────
if [[ -z "$MODE" || -z "$IMPL_FILE" || -z "$ISSUE_NUM" ]]; then
  echo "사용법: bash harness/impl-process.sh impl --impl <path> --issue <N> [--prefix <prefix>]"
  exit 1
fi

if [[ ! -f "$IMPL_FILE" ]]; then
  echo "[HARNESS] 오류: impl 파일을 찾을 수 없음: $IMPL_FILE"
  exit 1
fi

# ── Phase 0: constraints 로드 (1회 — 재시도에도 고정) ──────────────────
MEM_GLOBAL="${HOME}/.claude/harness-memory.md"
MEM_LOCAL=".claude/harness-memory.md"

# harness-memory.md가 없으면 B-5 형식으로 생성, 있으면 필수 섹션 헤더 추가
if [[ ! -f "$MEM_LOCAL" ]]; then
  mkdir -p .claude
  printf "# Harness Memory\n\n## impl 패턴\n\n## design 패턴\n\n## bugfix 패턴\n\n## Auto-Promoted Rules\n\n## Known Failure Patterns\n\n## Success Patterns\n" > "$MEM_LOCAL"
else
  for sec in "impl 패턴" "design 패턴" "bugfix 패턴"; do
    grep -qF "## ${sec}" "$MEM_LOCAL" 2>/dev/null || printf "\n## %s\n" "$sec" >> "$MEM_LOCAL"
  done
fi

CONSTRAINTS=""
# Auto-Promoted Rules 우선 로드 (자동 프로모션된 규칙이 최우선)
for mf in "$MEM_GLOBAL" "$MEM_LOCAL"; do
  if [[ -f "$mf" ]]; then
    promoted=$(sed -n '/^## Auto-Promoted Rules/,/^##/p' "$mf" 2>/dev/null | grep "^- PROMOTED:" | head -10 || true)
    [[ -n "$promoted" ]] && CONSTRAINTS="${CONSTRAINTS}
[AUTO-PROMOTED RULES — 반복 실패 패턴, 반드시 회피]:
${promoted}"
  fi
done
[[ -f "$MEM_GLOBAL" ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_GLOBAL")"
[[ -f "$MEM_LOCAL"  ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_LOCAL")"
# CLAUDE.md: 관련 섹션만 추출 (전체 cat 대신 토큰 절약)
if [[ -f "CLAUDE.md" ]]; then
  CONSTRAINTS="${CONSTRAINTS}
$(sed -n '/^## 개발 명령어/,/^---/p; /^## 작업 순서/,/^---/p; /^## Git/,/^---/p' CLAUDE.md | head -c 10000)"
fi

# ── 헬퍼 함수 ──────────────────────────────────────────────────────────

# attempt 결과를 meta.json으로 기록
# 사용법: _save_impl_meta <attempt_dir> <attempt_num> <result> <fail_type> <next_hints>
_save_impl_meta() {
  local adir="$1" anum="$2" res="$3" ftype="${4:-}" hints="${5:-}"
  local chg; chg=$(git diff HEAD~1 --name-only 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//' || echo "")
  local ftests=""
  if [[ -f "${adir}/test-results.log" ]]; then
    ftests=$(grep -E "✗| FAIL |× " "${adir}/test-results.log" 2>/dev/null | head -3 | tr '\n' ',' | cut -c1-200 || echo "")
  fi
  local err1=""
  if [[ -f "${adir}/engineer.log" ]]; then
    err1=$(head -1 "${adir}/engineer.log" | cut -c1-150 || echo "")
  fi
  write_attempt_meta "${adir}/meta.json" "$anum" "impl" "$DEPTH" "$res" \
    "$ftype" "$ftests" "$chg" "engineer,test-engineer,validator,pr-reviewer" "$err1" "$hints"
}

append_failure() {
  local type="$1" err="$2"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  local err_1line; err_1line=$(echo "$err" | head -1 | cut -c1-100)

  # 원자적 쓰기: temp 파일에 기록 후 append (race condition 방지)
  local tmp_entry; tmp_entry=$(mktemp)
  printf -- "- %s | %s | %s | %s\n" \
    "$date_str" "$impl_name" "$type" "$err_1line" \
    > "$tmp_entry"
  cat "$tmp_entry" >> "$MEM_LOCAL"
  rm -f "$tmp_entry"

  # ── B2: 실패 패턴 자동 프로모션 (같은 impl+type 3회 → Auto-Promoted Rules) ──
  local pattern_key="${impl_name}|${type}"
  local count; count=$(grep -Fc "$pattern_key" "$MEM_LOCAL" 2>/dev/null) || count=0
  if [[ $count -ge 3 ]]; then
    # Auto-Promoted Rules 섹션이 없으면 생성
    if ! grep -Fq "## Auto-Promoted Rules" "$MEM_LOCAL" 2>/dev/null; then
      printf "\n## Auto-Promoted Rules\n\n" >> "$MEM_LOCAL"
    fi
    # 중복 프로모션 방지: 이미 프로모션된 패턴인지 확인
    if ! grep -Fq "PROMOTED: $pattern_key" "$MEM_LOCAL" 2>/dev/null; then
      local tmp_promo; tmp_promo=$(mktemp)
      printf -- "- PROMOTED: %s | %s회 반복 | %s | MUST NOT: %s\n" \
        "$pattern_key" "$count" "$date_str" "$err_1line" \
        > "$tmp_promo"
      cat "$tmp_promo" >> "$MEM_LOCAL"
      rm -f "$tmp_promo"
      echo "[HARNESS] 실패 패턴 자동 프로모션: ${pattern_key} (${count}회)"
    fi
  fi

  # ── P1: Memory 후보 파일 기록 (HARNESS_DONE 후 유저에게 제안) ─────────────
  local candidate_file="/tmp/${PREFIX}_memory_candidate.md"
  # 같은 루프 내 중복 기록 방지
  if ! grep -Fq "$pattern_key" "$candidate_file" 2>/dev/null; then
    cat >> "$candidate_file" <<CANDIDATE
---
date: $date_str
impl: $impl_name
type: $type
pattern: $err_1line
suggestion: "impl 파일에 관련 제약 추가 또는 에이전트 지시 보강 검토"
CANDIDATE
  fi
}

rollback_attempt() {
  local attempt_num="$1"
  # Feature branch: stash 대신 변경 유지, 다음 attempt에서 추가 커밋
  [[ -n "$RUN_LOG" ]] && printf '{"event":"rollback","attempt":%d,"method":"keep-on-branch","t":%d}\n' \
    "$attempt_num" "$(date +%s)" >> "$RUN_LOG"
  hlog "ROLLBACK attempt=${attempt_num} — changes kept on feature branch"
}

check_agent_output() {
  local agent_name="$1" out_file="$2"
  if [[ ! -s "$out_file" ]]; then
    hlog "WARNING: ${agent_name} 출력 파일 없음 또는 비어있음 — agent 호출 실패"
    echo "[HARNESS] WARNING: ${agent_name} agent가 출력을 생성하지 못함"
    return 1
  fi
  return 0
}

append_success() {
  local attempt_num="$1"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  local tmp_entry; tmp_entry=$(mktemp)
  printf -- "- %s | %s | success | attempt %s\n" \
    "$date_str" "$impl_name" "$attempt_num" \
    > "$tmp_entry"
  cat "$tmp_entry" >> "$MEM_LOCAL"
  rm -f "$tmp_entry"
}

# extract_files_from_error() → harness/utils.sh로 이동 (공용)
# build_smart_context() → harness/utils.sh로 이동 (공용)

run_automated_checks() {
  local impl_file="$1"
  local out_file="/tmp/${PREFIX}_autocheck_fail.txt"
  rm -f "$out_file"

  # Check 1: has_changes — engineer가 실제로 파일을 수정했는가?
  if ! git status --short | grep -qE "^ M|^M |^A "; then
    echo "no_changes: engineer가 아무 파일도 수정하지 않음" > "$out_file"
    echo "AUTOMATED_CHECKS_FAIL: no_changes"
    return 1
  fi

  # Check 2: no_new_deps — package.json 무단 의존성 추가 여부
  if git show HEAD:package.json >/dev/null 2>&1; then
    if git diff HEAD -- package.json 2>/dev/null | grep -qE '^\+\s+"[a-z@]'; then
      echo "new_deps: package.json에 새 의존성이 추가됨 (사전 승인 필요)" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: new_deps"
      return 1
    fi
  fi

  # Check 3: file_unchanged — impl 파일에 명시된 변경 금지 파일 위반 여부
  local protected_files
  protected_files=$(grep -oE '\(PROTECTED\)[[:space:]]+[^[:space:]]+' "$impl_file" 2>/dev/null \
    | awk '{print $NF}' || true)
  while IFS= read -r pf; do
    [[ -z "$pf" ]] && continue
    if git diff HEAD -- "$pf" 2>/dev/null | grep -qE "^[-+]"; then
      echo "file_unchanged: 변경 금지 파일 수정됨: $pf" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: file_unchanged ($pf)"
      return 1
    fi
  done <<< "$protected_files"

  echo "AUTOMATED_CHECKS_PASS"
  return 0
}

generate_pr_body() {
  local attempt_num="$1"
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)

  # 테스트 결과 요약 (마지막 3줄)
  local test_summary
  test_summary=$(grep -E "Tests |passed|failed" "/tmp/${PREFIX}_test_out.txt" 2>/dev/null \
    | tail -3 | tr '\n' ' ' || echo "PASS")

  # 보안 최고 등급
  local sec_level
  sec_level=$(grep -oEm1 '\bHIGH\b|\bMEDIUM\b|\bLOW\b' "/tmp/${PREFIX}_sec_out.txt" 2>/dev/null) || sec_level="LOW"

  # pr-reviewer 권고사항 (NICE TO HAVE 아래 bullet)
  local pr_notes
  pr_notes=$(grep -A5 -i "nice to have\|권고사항" "/tmp/${PREFIX}_pr_out.txt" 2>/dev/null \
    | grep "^[-•*]" | head -3 | tr '\n' ' ' || echo "없음")

  # impl 결정 근거 첫 줄
  local why
  why=$(grep -A3 "^## 결정 근거" "$IMPL_FILE" 2>/dev/null \
    | grep "^-" | head -1 | sed 's/^- //' || echo "Issue #${ISSUE_NUM} 구현")

  cat <<PRBODY
## What / Why
Issue #${ISSUE_NUM} — \`${impl_name}\`
${why}

## 작동 증거
- vitest: ${test_summary}
- 시도: ${attempt_num}/${MAX}회 성공

## 위험 + AI 역할
- 보안 최고 등급: ${sec_level}
- AI(Claude) 구현·테스트·검증·리뷰 완료. 인간 최종 확인 권장: 비즈니스 로직

## 리뷰 포커스
${pr_notes}
PRBODY
}

# generate_commit_msg() → harness/utils.sh로 이동 (executor와 공유)

# ── 타임스탬프 디버그 로그 ─────────────────────────────────────────────
HLOG="/tmp/${PREFIX}-harness-debug.log"
ATTEMPT=0
hlog() { echo "[$(date +%H:%M:%S)] [attempt=${ATTEMPT}] $*" | tee -a "$HLOG"; }

# ── 구조화 이벤트 로그 (JSONL) ────────────────────────────────────────
log_decision() {
  local key="$1" value="$2" reason="$3"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"decision","key":"%s","value":"%s","reason":"%s","t":%d,"attempt":%d}\n' \
    "$key" "$value" "$reason" "$(date +%s)" "$ATTEMPT" >> "$RUN_LOG"
}
log_phase() {
  local phase="$1"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"phase","name":"%s","t":%d,"attempt":%d}\n' \
    "$phase" "$(date +%s)" "$ATTEMPT" >> "$RUN_LOG"
}

# ── harness_active 플래그 정리 (성공/실패 모두) ────────────────────────
cleanup() {
  rm -f "/tmp/${PREFIX}_harness_active"
  write_run_end
}
trap cleanup EXIT

# ── S31: 킬 스위치 / S32: 비용 추적 ───────────────────────────────────
TOTAL_COST=0
MAX_TOTAL_COST=10  # 달러 — 전체 루프 비용 상한

budget_check() {
  local agent_name="$1" out_file="$2"
  local cost_file="${out_file%.txt}_cost.txt"
  local agent_cost
  agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
  TOTAL_COST=$(echo "$TOTAL_COST + $agent_cost" | bc 2>/dev/null || echo "$TOTAL_COST")
  hlog "COST: ${agent_name} \$${agent_cost} | total: \$${TOTAL_COST}/${MAX_TOTAL_COST}"
  if [[ "$(echo "$TOTAL_COST > $MAX_TOTAL_COST" | bc 2>/dev/null)" == "1" ]]; then
    hlog "BUDGET EXCEEDED (\$${TOTAL_COST} > \$${MAX_TOTAL_COST})"
    export HARNESS_RESULT="HARNESS_BUDGET_EXCEEDED"
    echo "HARNESS_BUDGET_EXCEEDED: \$${TOTAL_COST} spent, limit \$${MAX_TOTAL_COST}"
    rm -f "/tmp/${PREFIX}_harness_active"
    exit 1
  fi
}

# ══════════════════════════════════════════════════════════════════════
# mode: impl (engineer 루프)
# ══════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "impl" ]]; then

  touch "/tmp/${PREFIX}_harness_active"
  [[ ! -f "/tmp/${PREFIX}_plan_validation_passed" ]] && touch "/tmp/${PREFIX}_plan_validation_passed"
  rotate_harness_logs "$PREFIX" "impl"

  # ── Feature branch 생성 ──────────────────────────────────────
  FEATURE_BRANCH=$(create_feature_branch "$BRANCH_TYPE" "$ISSUE_NUM")
  export HARNESS_BRANCH="$FEATURE_BRANCH"
  hlog "feature branch: $FEATURE_BRANCH"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"branch_create","branch":"%s","t":%d}\n' \
    "$FEATURE_BRANCH" "$(date +%s)" >> "$RUN_LOG"

  # ══════════════════════════════════════════════════════════════
  # fast mode: engineer → validator → commit → merge
  # (테스트·보안·리뷰 스킵, LLM 2회)
  # ══════════════════════════════════════════════════════════════
  if [[ "$DEPTH" == "fast" ]]; then
    hlog "=== 하네스 루프 시작 (depth=fast) ==="
    [[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"fast","max_retries":1,"constraints_chars":%d}\n' \
      "$IMPL_FILE" "$ISSUE_NUM" "${#CONSTRAINTS}" >> "$RUN_LOG"

    # ── fast: engineer ────────────────────────────────────────
    kill_check
    log_phase "engineer"
    echo "[HARNESS/fast] engineer"
    context=$(head -c 30000 "$IMPL_FILE")
    hlog "engineer 시작 (depth=fast, timeout=900s)"
    head_before=$(git rev-parse HEAD)
    AGENT_EXIT=0
    _agent_call "engineer" 900 \
      "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: impl 파일의 구현 명세 이행
context:
$context
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    hlog "engineer 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "engineer timeout"; fi
    budget_check "engineer" "/tmp/${PREFIX}_eng_out.txt"

    # engineer가 커밋했는지 + 미커밋 변경이 있는지 확인
    head_after=$(git rev-parse HEAD)
    engineer_committed=false
    [[ "$head_before" != "$head_after" ]] && engineer_committed=true

    changed_list=$(collect_changed_files || true)

    if [[ "$engineer_committed" == "false" && -z "$changed_list" ]]; then
      export HARNESS_RESULT="HARNESS_DONE"
      echo "[HARNESS/fast] 변경사항 없음"
      hlog "=== 루프 종료 (no_changes) ==="
      exit 0
    fi

    # 미커밋 변경이 있으면 하네스가 커밋
    if [[ -n "$changed_list" ]]; then
      echo "$changed_list" | while IFS= read -r _cf; do
        [[ -n "$_cf" ]] && git add -- "$_cf"
      done
      git commit -m "$(generate_commit_msg) [fast-mode]"
    fi

    # ── fast: pr-reviewer ────────────────────────────────────
    kill_check
    log_phase "pr-reviewer"
    echo "[HARNESS/fast] pr-reviewer"
    hlog "pr-reviewer 시작 (depth=fast, timeout=180s)"
    fast_diff=$(git diff HEAD~1 2>&1 | head -300)
    fast_src=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ' ')
    AGENT_EXIT=0
    _agent_call "pr-reviewer" 180 \
      "@MODE:PR_REVIEWER:REVIEW
@PARAMS: { \"impl_path\": \"$IMPL_FILE\", \"src_files\": \"$fast_src\" }
변경 diff:
$fast_diff" \
      "/tmp/${PREFIX}_pr_out.txt" || AGENT_EXIT=$?
    hlog "pr-reviewer 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "pr-reviewer timeout"; fi
    budget_check "pr-reviewer" "/tmp/${PREFIX}_pr_out.txt"

    pr_result=$(parse_marker "/tmp/${PREFIX}_pr_out.txt" "LGTM|CHANGES_REQUESTED")
    echo "[HARNESS/fast] pr-reviewer 결과: $pr_result"

    if [[ "$pr_result" == "CHANGES_REQUESTED" ]]; then
      # fast: CHANGES_REQUESTED → engineer에게 추가커밋 요청 (1회)
      pr_out=$(cat "/tmp/${PREFIX}_pr_out.txt" 2>/dev/null | head -c 5000)
      AGENT_EXIT=0
      _agent_call "engineer" 900 \
        "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: [코드 품질 수정] pr-reviewer MUST FIX 항목만 수정하라. 기능 변경 금지.
pr_review:
$pr_out
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_fix_out.txt" || AGENT_EXIT=$?
      budget_check "engineer" "/tmp/${PREFIX}_eng_fix_out.txt"

      # 추가 변경 커밋
      fix_list=$(collect_changed_files || true)
      if [[ -n "$fix_list" ]]; then
        echo "$fix_list" | while IFS= read -r _cf; do
          [[ -n "$_cf" ]] && git add -- "$_cf"
        done
        git commit -m "$(generate_commit_msg) [fast-pr-fix]"
        hlog "pr-reviewer CHANGES_REQUESTED → 추가커밋 완료"
      fi
    fi

    touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
    echo "[HARNESS/fast] pr-reviewer LGTM (또는 fix 완료)"

    # ── fast: merge to main ───────────────────────────────────
    impl_commit=$(git rev-parse --short HEAD)
    if ! merge_to_main "$FEATURE_BRANCH" "$ISSUE_NUM" "fast" "$PREFIX"; then
      export HARNESS_RESULT="MERGE_CONFLICT_ESCALATE"
      echo "MERGE_CONFLICT_ESCALATE"
      echo "branch: $FEATURE_BRANCH"
      echo "impl_commit: $impl_commit"
      hlog "=== merge conflict ==="
      exit 1
    fi
    merge_commit=$(git rev-parse --short HEAD)
    [[ -n "$RUN_LOG" ]] && printf '{"event":"branch_merge","branch":"%s","impl_commit":"%s","merge_commit":"%s","t":%d}\n' \
      "$FEATURE_BRANCH" "$impl_commit" "$merge_commit" "$(date +%s)" >> "$RUN_LOG"

    # ── fast: 완료 ────────────────────────────────────────────
    export HARNESS_RESULT="HARNESS_DONE"
    echo "HARNESS_DONE (fast)"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "commit: $merge_commit"
    hlog "=== 루프 종료 (HARNESS_DONE, fast) ==="
    exit 0
  fi

  # ══════════════════════════════════════════════════════════════
  # std / deep mode: engineer → commit → test-engineer → vitest
  #                  → validator → pr-reviewer
  #                  [deep: + security-reviewer]
  #                  → merge
  # ══════════════════════════════════════════════════════════════
  attempt=0
  spec_gap_count=0
  spec_gap_context=""
  sg_result=""
  MAX=3
  MAX_SPEC_GAP=2
  error_trace=""
  fail_type=""
  hlog "=== 하네스 루프 시작 (depth=$DEPTH, max_retries=$MAX) ==="

  # HIST_DIR — attempt별 구조화 히스토리
  HIST_DIR="/tmp/${PREFIX}_history"
  LOOP_OUT_DIR="${HIST_DIR}/impl"  # explore_instruction이 참조하는 경로
  mkdir -p "$LOOP_OUT_DIR"

  # config 이벤트: 루프 설정 스냅샷
  [[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"%s","max_retries":%d,"constraints_chars":%d}\n' \
    "$IMPL_FILE" "$ISSUE_NUM" "$DEPTH" "$MAX" "${#CONSTRAINTS}" >> "$RUN_LOG"

  while [[ $attempt -lt $MAX ]]; do
    ATTEMPT=$attempt
    kill_check

    # attempt 디렉토리 생성 → prune → 파일 기록
    attempt_dir="${LOOP_OUT_DIR}/attempt-${attempt}"
    mkdir -p "$attempt_dir"
    prune_history "$LOOP_OUT_DIR"  # 생성 직후, 파일 기록 전 (race condition 방지)

    # ── Context GC: 스마트 컨텍스트 (관련 청크만 로드) ──────────────
    context=$(build_smart_context "$IMPL_FILE" 0)
    if [[ $attempt -eq 0 ]]; then
      task="impl 파일의 구현 명세 전체 이행"
    else
      # ── C1: 실패 유형별 수정 전략 (탐색 지시 + next_action_hints 경로 활용) ─
      prev_dir="${LOOP_OUT_DIR}/attempt-$((attempt-1))"
      wt_prefix="[주의] 이전 attempt의 변경이 working tree에 남아있음. 추가 수정으로 해결하라 (stash/reset 금지).
"
      case "$fail_type" in
        autocheck_fail)
          task="[사전 검사 실패] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/autocheck.log")
위 문제를 해결한 뒤 다시 구현하라. 테스트·벨리데이터 호출은 검사 통과 후 진행된다."
          ;;
        test_fail)
          task="[테스트 실패] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/test-results.log")
구현 코드를 수정하라. 테스트 코드 자체는 수정 금지."
          ;;
        validator_fail)
          task="[스펙 불일치] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/validator.log")
impl 파일의 해당 항목을 다시 확인하고 누락된 부분을 구현하라."
          ;;
        pr_fail)
          task="[코드 품질] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/pr.log")
MUST FIX 항목만 수정하라. 기능 변경 금지."
          ;;
        security_fail)
          task="[보안 취약점] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/security.log")
취약점의 수정 방안대로 적용하라."
          ;;
        *)
          task="[재시도] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR")"
          ;;
      esac
      task="${wt_prefix}${task}"
    fi

    # ── context 크기 기록 ──────────────────────────────────────────
    [[ -n "$RUN_LOG" ]] && printf '{"event":"context","chars":%d,"attempt":%d}\n' \
      "${#context}" "$attempt" >> "$RUN_LOG"

    # ── 워커 1: engineer ──────────────────────────────────────────
    log_phase "engineer"
    echo "[HARNESS] engineer (attempt $((attempt+1))/$MAX)"
    hlog "engineer 시작 (depth=$DEPTH, timeout=900s)"
    kill_check
    AGENT_EXIT=0
    _agent_call "engineer" 900 \
      "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task:
$task
context:
$context
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    hlog "engineer 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "engineer timeout"; fi
    budget_check "engineer" "/tmp/${PREFIX}_eng_out.txt"
    # attempt별 engineer 출력 보존 (에이전트 자율 탐색용)
    cp "/tmp/${PREFIX}_eng_out.txt" "${attempt_dir}/engineer.log" 2>/dev/null || true

    # ── S39: engineer 출력 가드 ──────────────────────────────────────
    if ! check_agent_output "engineer" "/tmp/${PREFIX}_eng_out.txt"; then
      fail_type="autocheck_fail"
      error_trace="engineer agent produced no output (exit=${AGENT_EXIT})"
      append_failure "$fail_type" "$error_trace"
      _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "$fail_type" "engineer 출력 없음 — 프롬프트 길이/타임아웃 확인"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi

    # ── SPEC_GAP 감지 (정책 15: attempt 동결, spec_gap_count 별도) ──
    if grep -q "SPEC_GAP_FOUND" "/tmp/${PREFIX}_eng_out.txt" 2>/dev/null; then
      spec_gap_count=$((spec_gap_count + 1))
      hlog "SPEC_GAP_FOUND (spec_gap_count=${spec_gap_count}/${MAX_SPEC_GAP})"
      log_decision "spec_gap" "$spec_gap_count" "SPEC_GAP_FOUND in engineer output"

      if [[ $spec_gap_count -gt $MAX_SPEC_GAP ]]; then
        hlog "SPEC_GAP 동결 초과 → IMPLEMENTATION_ESCALATE"
        export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
        echo "IMPLEMENTATION_ESCALATE (spec_gap_count ${spec_gap_count} > ${MAX_SPEC_GAP})"
        echo "branch: ${FEATURE_BRANCH:-unknown}"
        exit 1
      fi

      # architect SPEC_GAP 호출
      log_phase "architect-spec-gap"
      echo "[HARNESS] SPEC_GAP → architect"
      spec_gap_context=$(tail -50 "/tmp/${PREFIX}_eng_out.txt")
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:SPEC_GAP
engineer가 SPEC_GAP_FOUND 보고. impl: $IMPL_FILE issue: #$ISSUE_NUM
engineer 보고:
$spec_gap_context" \
        "/tmp/${PREFIX}_arch_sg_out.txt"
      budget_check "architect" "/tmp/${PREFIX}_arch_sg_out.txt"

      # architect 결과 3-way 분기
      sg_result=$(parse_marker "/tmp/${PREFIX}_arch_sg_out.txt" "SPEC_GAP_RESOLVED|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")

      case "$sg_result" in
        SPEC_GAP_RESOLVED)
          hlog "SPEC_GAP_RESOLVED → engineer 재시도 (attempt 동결)"
          # attempt 증가 없이 루프 처음으로 (동결). error_trace 초기화.
          error_trace=""
          fail_type=""
          continue
          ;;
        PRODUCT_PLANNER_ESCALATION_NEEDED)
          export HARNESS_RESULT="PRODUCT_PLANNER_ESCALATION_NEEDED"
          echo "PRODUCT_PLANNER_ESCALATION_NEEDED"
          echo "branch: ${FEATURE_BRANCH:-unknown}"
          exit 1
          ;;
        TECH_CONSTRAINT_CONFLICT)
          export HARNESS_RESULT="TECH_CONSTRAINT_CONFLICT"
          echo "TECH_CONSTRAINT_CONFLICT"
          echo "branch: ${FEATURE_BRANCH:-unknown}"
          exit 1
          ;;
        *)
          hlog "architect SPEC_GAP 결과 불명확: $sg_result → engineer 재시도 (attempt 동결)"
          error_trace=""
          fail_type=""
          continue
          ;;
      esac
    fi

    # ── S17-2: pre-evaluator automated_checks ────────────────────────
    if ! run_automated_checks "$IMPL_FILE"; then
      error_trace=$(cat "/tmp/${PREFIX}_autocheck_fail.txt" 2>/dev/null || echo "automated_checks FAIL")
      fail_type="autocheck_fail"
      log_decision "fail_type" "$fail_type" "automated_checks failed"
      append_failure "autocheck_fail" "$error_trace"
      cp "/tmp/${PREFIX}_autocheck_fail.txt" "${attempt_dir}/autocheck.log" 2>/dev/null || true
      _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "autocheck_fail" "${attempt_dir}/autocheck.log 에서 사전 검사 실패 원인 확인"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi
    echo "[HARNESS] automated_checks PASS"

    # ── 즉시 커밋: engineer 변경을 feature branch에 즉시 기록 ──────────
    if collect_changed_files > /dev/null 2>&1; then
      collect_changed_files | while IFS= read -r _cf; do
        [[ -n "$_cf" ]] && git add -- "$_cf"
      done
      commit_suffix=""
      [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
      git commit -m "$(generate_commit_msg)${commit_suffix}"
      early_commit=$(git rev-parse --short HEAD)
      [[ -n "$RUN_LOG" ]] && printf '{"event":"commit","hash":"%s","attempt":%d,"t":%d}\n' \
        "$early_commit" "$((attempt+1))" "$(date +%s)" >> "$RUN_LOG"
      hlog "early commit: $early_commit (attempt=$((attempt+1)))"
    fi

    # ── 워커 2: test-engineer ─────────────────────────────────────
    changed_files=$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ' || \
      git status --short | grep -E "^ M|^M |^A " | awk '{print $2}' | tr '\n' ' ' || echo "")
    log_phase "test-engineer"
    echo "[HARNESS] test-engineer (attempt $((attempt+1))/$MAX)"
    hlog "test-engineer 시작 (depth=$DEPTH, timeout=600s)"
    kill_check
    AGENT_EXIT=0
    # attempt > 0 (재시도): 테스트 파일 이미 존재 → 새 작성 불필요, vitest만 실행
    if [[ $attempt -gt 0 ]]; then
      te_prompt="[RETRY 모드] 이전 attempt에서 테스트 파일이 이미 작성됨. 새 테스트 파일 작성 불필요.
impl: $IMPL_FILE
수정된 파일: $changed_files
issue: #$ISSUE_NUM

[지시] npx vitest run만 실행해서 결과를 TESTS_PASS / TESTS_FAIL로 보고하라. 파일 읽기 최소화."
    else
      te_prompt="@MODE:TEST_ENGINEER:TEST
@PARAMS: { \"impl_path\": \"$IMPL_FILE\", \"src_files\": \"$changed_files\" }

[지시] 위 src_files 목록이 이번 구현에서 변경된 파일 전체다. 추가 탐색 없이 이 파일들만 테스트하라.
issue: #$ISSUE_NUM"
    fi
    _agent_call "test-engineer" 600 "$te_prompt" "/tmp/${PREFIX}_te_out.txt" || AGENT_EXIT=$?
    hlog "test-engineer 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "test-engineer timeout"; fi
    budget_check "test-engineer" "/tmp/${PREFIX}_te_out.txt"

    # ── S39: test-engineer 출력 가드 ─────────────────────────────────
    if ! check_agent_output "test-engineer" "/tmp/${PREFIX}_te_out.txt"; then
      fail_type="test_fail"
      error_trace="test-engineer agent produced no output (exit=${AGENT_EXIT})"
      append_failure "$fail_type" "$error_trace"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi

    # ── Ground truth: 실제 테스트 실행 (LLM 주장과 독립) ──────────
    echo "[HARNESS] vitest 실행 (attempt $((attempt+1))/$MAX)"
    hlog "vitest 시작"
    kill_check
    set +e
    npx vitest run > "/tmp/${PREFIX}_test_out.txt" 2>&1
    test_exit=$?
    set -e
    hlog "vitest 종료 (exit=$test_exit)"
    if [[ $test_exit -ne 0 ]]; then
      echo "[HARNESS] TESTS_FAIL"
      error_trace=$(cat "/tmp/${PREFIX}_test_out.txt")
      fail_type="test_fail"
      log_decision "fail_type" "$fail_type" "vitest exit=$test_exit"
      append_failure "test_fail" "$error_trace"
      cp "/tmp/${PREFIX}_test_out.txt" "${attempt_dir}/test-results.log" 2>/dev/null || true
      cp "/tmp/${PREFIX}_te_out.txt" "${attempt_dir}/test-engineer.log" 2>/dev/null || true
      _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "test_fail" "${attempt_dir}/test-results.log 의 실패 케이스 확인. 테스트 코드 자체 수정 금지."
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_test_engineer_passed"
    echo "[HARNESS] TESTS_PASS"

    # ── 워커 3: validator ─────────────────────────────────────────
    log_phase "validator"
    echo "[HARNESS] validator (attempt $((attempt+1))/$MAX)"
    hlog "validator 시작 (depth=$DEPTH, timeout=300s)"
    kill_check
    val_context=$(build_validator_context "$IMPL_FILE")
    AGENT_EXIT=0
    _agent_call "validator" 300 \
      "@MODE:VALIDATOR:CODE_VALIDATION
impl: $IMPL_FILE
context:
$val_context" \
      "/tmp/${PREFIX}_val_out.txt" || AGENT_EXIT=$?
    hlog "validator 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "validator timeout"; fi
    budget_check "validator" "/tmp/${PREFIX}_val_out.txt"
    # validator 출력 보존
    cp "/tmp/${PREFIX}_val_out.txt" "${attempt_dir}/validator.log" 2>/dev/null || true

    # ── S39: validator 출력 가드 ─────────────────────────────────────
    if ! check_agent_output "validator" "/tmp/${PREFIX}_val_out.txt"; then
      fail_type="validator_fail"
      error_trace="validator agent produced no output (exit=${AGENT_EXIT})"
      append_failure "$fail_type" "$error_trace"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi

    val_result=$(parse_marker "/tmp/${PREFIX}_val_out.txt" "PASS|FAIL|SPEC_MISSING")
    echo "[HARNESS] validator 결과: $val_result"

    # SPEC_MISSING → architect MODULE_PLAN (impl 복구)
    if [[ "$val_result" == "SPEC_MISSING" ]]; then
      hlog "SPEC_MISSING → architect MODULE_PLAN 복구"
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:MODULE_PLAN
SPEC_MISSING 복구. impl: $IMPL_FILE issue: #$ISSUE_NUM" \
        "/tmp/${PREFIX}_arch_sm_out.txt"
      budget_check "architect" "/tmp/${PREFIX}_arch_sm_out.txt"
      # impl 파일 복구 후 재시도
      fail_type="validator_fail"
      error_trace="SPEC_MISSING: impl 파일 복구 후 재시도"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi

    if [[ "$val_result" != "PASS" ]]; then
      fail_type="validator_fail"
      log_decision "fail_type" "$fail_type" "validator result=$val_result"
      append_failure "validator_fail" "validator FAIL (see ${attempt_dir}/validator.log)"
      _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "validator_fail" "${attempt_dir}/validator.log 의 FAIL 항목을 impl 파일과 대조하라"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_validator_b_passed"

    # ── 워커 4: pr-reviewer (fast/std/deep 모두) ─────────────────────
    log_phase "pr-reviewer"
    echo "[HARNESS] pr-reviewer (attempt $((attempt+1))/$MAX)"
    hlog "pr-reviewer 시작 (depth=$DEPTH, timeout=180s)"
    kill_check
    diff_out=$(git diff HEAD~1 2>&1 | head -300 || git diff HEAD 2>&1 | head -300)
    AGENT_EXIT=0
    _agent_call "pr-reviewer" 180 \
      "@MODE:PR_REVIEWER:REVIEW
@PARAMS: { \"impl_path\": \"$IMPL_FILE\", \"src_files\": \"$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ' || true)\" }
변경 diff:
$diff_out" "/tmp/${PREFIX}_pr_out.txt" || AGENT_EXIT=$?
    hlog "pr-reviewer 종료 (exit=${AGENT_EXIT})"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "pr-reviewer timeout"; fi
    budget_check "pr-reviewer" "/tmp/${PREFIX}_pr_out.txt"
    # pr-reviewer 출력 보존
    cp "/tmp/${PREFIX}_pr_out.txt" "${attempt_dir}/pr.log" 2>/dev/null || true

    # ── S39: pr-reviewer 출력 가드 ───────────────────────────────────
    if ! check_agent_output "pr-reviewer" "/tmp/${PREFIX}_pr_out.txt"; then
      fail_type="pr_fail"
      error_trace="pr-reviewer agent produced no output (exit=${AGENT_EXIT})"
      append_failure "$fail_type" "$error_trace"
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi

    pr_result=$(parse_marker "/tmp/${PREFIX}_pr_out.txt" "LGTM|CHANGES_REQUESTED")
    echo "[HARNESS] pr-reviewer 결과: $pr_result"
    if [[ "$pr_result" != "LGTM" ]]; then
      fail_type="pr_fail"
      log_decision "fail_type" "$fail_type" "pr-reviewer result=$pr_result"
      append_failure "pr_fail" "pr-reviewer CHANGES_REQUESTED (see ${attempt_dir}/pr.log)"
      _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "pr_fail" "${attempt_dir}/pr.log 의 MUST FIX 항목만 수정. 기능 변경 금지."
      rollback_attempt $attempt
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
    echo "[HARNESS] LGTM"

    # ── 워커 5: security-reviewer (deep only) ────────────────────────
    if [[ "$DEPTH" == "deep" ]]; then
      log_phase "security-reviewer"
      echo "[HARNESS] security-reviewer (attempt $((attempt+1))/$MAX)"
      hlog "security-reviewer 시작 (deep only, timeout=180s)"
      kill_check
      changed_src=$(git diff HEAD~1 --name-only 2>/dev/null | grep -E '\.(ts|tsx|js|jsx)$' | head -10 | tr '\n' ' ' || true)
      AGENT_EXIT=0
      _agent_call "security-reviewer" 180 \
        "보안 리뷰 대상 파일:
$changed_src

변경 diff:
$(git diff HEAD~1 2>&1 | head -500 || git diff HEAD 2>&1 | head -500)" "/tmp/${PREFIX}_sec_out.txt" || AGENT_EXIT=$?
      hlog "security-reviewer 종료 (exit=${AGENT_EXIT})"
      if [[ $AGENT_EXIT -eq 124 ]]; then hlog "security-reviewer timeout"; fi
      budget_check "security-reviewer" "/tmp/${PREFIX}_sec_out.txt"
      # security-reviewer 출력 보존
      cp "/tmp/${PREFIX}_sec_out.txt" "${attempt_dir}/security.log" 2>/dev/null || true

      # ── S39: security-reviewer 출력 가드 ─────────────────────────────
      if ! check_agent_output "security-reviewer" "/tmp/${PREFIX}_sec_out.txt"; then
        fail_type="security_fail"
        error_trace="security-reviewer agent produced no output (exit=${AGENT_EXIT})"
        append_failure "$fail_type" "$error_trace"
        rollback_attempt $attempt
        attempt=$((attempt+1))
        continue
      fi

      sec_result=$(parse_marker "/tmp/${PREFIX}_sec_out.txt" "SECURE|VULNERABILITIES_FOUND")
      echo "[HARNESS] security-reviewer 결과: $sec_result"
      if [[ "$sec_result" != "SECURE" ]]; then
        fail_type="security_fail"
        log_decision "fail_type" "$fail_type" "security result=$sec_result"
        append_failure "security_fail" "security VULNERABILITIES_FOUND (see ${attempt_dir}/security.log)"
        _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "security_fail" "${attempt_dir}/security.log 의 HIGH/MEDIUM 취약점 수정"
        rollback_attempt $attempt
        attempt=$((attempt+1))
        continue
      fi
      touch "/tmp/${PREFIX}_security_review_passed"
      echo "[HARNESS] SECURE"
    else
      # std: security-reviewer 스킵, 플래그만 자동 생성
      touch "/tmp/${PREFIX}_security_review_passed"
      hlog "security-reviewer 스킵 (depth=$DEPTH)"
    fi

    # ── merge to main ────────────────────────────────────────────
    # test-engineer가 추가한 테스트 파일 등 미커밋 변경 처리
    if collect_changed_files > /dev/null 2>&1; then
      collect_changed_files | while IFS= read -r _cf; do
        [[ -n "$_cf" ]] && git add -- "$_cf"
      done
      git commit -m "$(generate_commit_msg) [test-files]"
      hlog "test 파일 추가 커밋 완료"
    fi
    impl_commit=$(git rev-parse --short HEAD)
    if ! merge_to_main "$FEATURE_BRANCH" "$ISSUE_NUM" "$DEPTH" "$PREFIX"; then
      export HARNESS_RESULT="MERGE_CONFLICT_ESCALATE"
      echo "MERGE_CONFLICT_ESCALATE"
      echo "branch: $FEATURE_BRANCH"
      echo "impl_commit: $impl_commit"
      hlog "=== merge conflict ==="
      exit 1
    fi
    merge_commit=$(git rev-parse --short HEAD)
    [[ -n "$RUN_LOG" ]] && printf '{"event":"branch_merge","branch":"%s","impl_commit":"%s","merge_commit":"%s","t":%d}\n' \
      "$FEATURE_BRANCH" "$impl_commit" "$merge_commit" "$(date +%s)" >> "$RUN_LOG"

    # ── G6: PR body 생성 ─────────────────────────────────────────
    generate_pr_body $((attempt+1)) > "/tmp/${PREFIX}_pr_body.txt" 2>/dev/null || true

    append_success $((attempt+1))
    # 성공 meta.json 기록
    _save_impl_meta "$attempt_dir" "$attempt" "PASS" "" "구현 완료"

    # ── S7: last_issue 저장 (다음 세션 컨텍스트 브리지용) ───────────────
    echo "$ISSUE_NUM" > "/tmp/${PREFIX}_last_issue"

    export HARNESS_RESULT="HARNESS_DONE"
    hlog "=== 루프 종료 (HARNESS_DONE, attempt=$((attempt+1))) ==="
    echo "HARNESS_DONE"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "attempts: $((attempt+1))"
    echo "commit: $merge_commit"
    echo "pr_body: /tmp/${PREFIX}_pr_body.txt"

    # ── P1: Memory 후보 존재 시 유저에게 기록 제안 ───────────────────────
    candidate_file="/tmp/${PREFIX}_memory_candidate.md"
    if [[ -f "$candidate_file" ]]; then
      echo ""
      echo "[HARNESS MEMORY] 이번 루프에서 실패 패턴이 감지됐습니다."
      echo "   아래 후보를 harness-memory.md에 기록하면 다음 루프의 CONSTRAINTS로 활용됩니다."
      echo "   파일: $candidate_file"
      echo "   내용:"
      cat "$candidate_file"
      echo ""
      echo "   기록 여부: 메인 Claude에게 Y/N 응답"
      echo "memory_candidate: $candidate_file"
    fi

    exit 0

  done

  # 3회 모두 실패 — plan_validation_passed 플래그 정리 (재진입 시 stale 방지)
  rm -f "/tmp/${PREFIX}_plan_validation_passed"
  export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
  hlog "=== 루프 종료 (IMPLEMENTATION_ESCALATE, attempt=$MAX) ==="
  echo "IMPLEMENTATION_ESCALATE"
  echo "attempts: $MAX"
  echo "spec_gap_count: $spec_gap_count"
  echo "branch: ${FEATURE_BRANCH:-unknown}"
  echo "마지막 에러:"
  echo "$error_trace" | head -20
  exit 1

fi

export HARNESS_RESULT="HARNESS_CRASH"
echo "[HARNESS] 알 수 없는 mode: $MODE"
exit 1
