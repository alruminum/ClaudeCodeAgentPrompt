#!/bin/bash
# ~/.claude/harness/impl_std.sh
# std depth 구현 루프: engineer → test-engineer → vitest → validator → pr-reviewer → merge
# 상세: orchestration/impl_std.md
#
# 호출 형식 (impl.sh dispatcher에서 호출):
#   bash ~/.claude/harness/impl_std.sh \
#     --impl <impl_file_path> \
#     --issue <issue_number> \
#     [--prefix <prefix>] \
#     [--branch-type <feat|fix>]

set -euo pipefail

command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/impl_helpers.sh"

export HARNESS_RESULT="unknown"

IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BRANCH_TYPE="feat"
RUN_LOG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)        IMPL_FILE="$2";   shift 2 ;;
    --issue)       ISSUE_NUM="$2";   shift 2 ;;
    --prefix)      PREFIX="$2";      shift 2 ;;
    --branch-type) BRANCH_TYPE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

DEPTH="std"

if [[ -z "$IMPL_FILE" || -z "$ISSUE_NUM" ]]; then
  echo "사용법: bash harness/impl_std.sh --impl <path> --issue <N> [--prefix <prefix>]"
  exit 1
fi

if [[ ! -f "$IMPL_FILE" ]]; then
  echo "[HARNESS] 오류: impl 파일을 찾을 수 없음: $IMPL_FILE"
  exit 1
fi

_load_constraints
_setup_hlog
_setup_cleanup

touch "${STATE_DIR}/${PREFIX}_harness_active"
[[ ! -f "${STATE_DIR}/${PREFIX}_plan_validation_passed" ]] && touch "${STATE_DIR}/${PREFIX}_plan_validation_passed"
rotate_harness_logs "$PREFIX" "impl" "$ISSUE_NUM"

FEATURE_BRANCH=$(create_feature_branch "$BRANCH_TYPE" "$ISSUE_NUM")
export HARNESS_BRANCH="$FEATURE_BRANCH"
hlog "feature branch: $FEATURE_BRANCH"
[[ -n "$RUN_LOG" ]] && printf '{"event":"branch_create","branch":"%s","t":%d}\n' \
  "$FEATURE_BRANCH" "$(date +%s)" >> "$RUN_LOG"

attempt=0
spec_gap_count=0
spec_gap_context=""
sg_result=""
MAX=3
MAX_SPEC_GAP=2
error_trace=""
fail_type=""
hlog "=== 하네스 루프 시작 (depth=std, max_retries=$MAX) ==="

HIST_DIR="${STATE_DIR}/${PREFIX}_history"
LOOP_OUT_DIR="${HIST_DIR}/impl"
mkdir -p "$LOOP_OUT_DIR"

[[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"std","max_retries":%d,"constraints_chars":%d}\n' \
  "$IMPL_FILE" "$ISSUE_NUM" "$MAX" "${#CONSTRAINTS}" >> "$RUN_LOG"

while [[ $attempt -lt $MAX ]]; do
  ATTEMPT=$attempt
  kill_check

  attempt_dir="${LOOP_OUT_DIR}/attempt-${attempt}"
  mkdir -p "$attempt_dir"
  prune_history "$LOOP_OUT_DIR"

  context=$(build_smart_context "$IMPL_FILE" 0)
  if [[ $attempt -eq 0 ]]; then
    task="impl 파일의 구현 명세 전체 이행"
  else
    prev_dir="${LOOP_OUT_DIR}/attempt-$((attempt-1))"
    wt_prefix="[주의] 이전 attempt의 변경이 working tree에 남아있음. 추가 수정으로 해결하라 (stash/reset 금지).
"
    case "$fail_type" in
      autocheck_fail)
        task="[사전 검사 실패] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR" "${prev_dir}/autocheck.log")
위 문제를 해결한 뒤 다시 구현하라."
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
      *)
        task="[재시도] 시도 ${attempt}회.
$(explore_instruction "$LOOP_OUT_DIR")"
        ;;
    esac
    task="${wt_prefix}${task}"
  fi

  [[ -n "$RUN_LOG" ]] && printf '{"event":"context","chars":%d,"attempt":%d}\n' \
    "${#context}" "$attempt" >> "$RUN_LOG"

  # ── 워커 1: engineer ─────────────────────────────────────────────
  log_phase "engineer"
  echo "[HARNESS] engineer (attempt $((attempt+1))/$MAX)"
  hlog "engineer 시작 (depth=std, timeout=900s)"
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
$CONSTRAINTS" "${STATE_DIR}/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
  hlog "engineer 종료 (exit=${AGENT_EXIT})"
  if [[ $AGENT_EXIT -eq 124 ]]; then hlog "engineer timeout"; fi
  budget_check "engineer" "${STATE_DIR}/${PREFIX}_eng_out.txt"
  cp "${STATE_DIR}/${PREFIX}_eng_out.txt" "${attempt_dir}/engineer.log" 2>/dev/null || true

  if ! check_agent_output "engineer" "${STATE_DIR}/${PREFIX}_eng_out.txt"; then
    fail_type="autocheck_fail"
    error_trace="engineer agent produced no output (exit=${AGENT_EXIT})"
    append_failure "$fail_type" "$error_trace"
    _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "$fail_type" "engineer 출력 없음"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi

  # ── SPEC_GAP 감지 ──────────────────────────────────────────────
  if grep -q "SPEC_GAP_FOUND" "${STATE_DIR}/${PREFIX}_eng_out.txt" 2>/dev/null; then
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

    log_phase "architect-spec-gap"
    echo "[HARNESS] SPEC_GAP → architect (depth 재판정 포함)"
    spec_gap_context=$(tail -50 "${STATE_DIR}/${PREFIX}_eng_out.txt")
    _agent_call "architect" 900 \
      "@MODE:ARCHITECT:SPEC_GAP
engineer가 SPEC_GAP_FOUND 보고. impl: $IMPL_FILE issue: #$ISSUE_NUM
현재 depth: std
engineer 보고:
$spec_gap_context
[지시] SPEC_GAP 해결 후 depth 재판정. frontmatter depth: 필드를 재선언하라. 상향만 허용(simple→std→deep)." \
      "${STATE_DIR}/${PREFIX}_arch_sg_out.txt"
    budget_check "architect" "${STATE_DIR}/${PREFIX}_arch_sg_out.txt"

    sg_result=$(parse_marker "${STATE_DIR}/${PREFIX}_arch_sg_out.txt" "SPEC_GAP_RESOLVED|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")

    case "$sg_result" in
      SPEC_GAP_RESOLVED)
        # depth 재판정 확인: impl frontmatter에서 새 depth 읽기
        local new_depth
        new_depth=$(awk '/^---$/{n++} n==1 && /^depth:/{sub(/^depth:[[:space:]]*/,""); sub(/[[:space:]]*#.*/,""); print; exit}' "$IMPL_FILE" 2>/dev/null || echo "std")
        if [[ "$new_depth" == "deep" ]]; then
          hlog "depth 상향: std → deep. deep 루프로 전환 (attempt=${attempt} 이어가기)"
          exec bash "${HOME}/.claude/harness/impl_deep.sh" --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --branch-type "$BRANCH_TYPE"
        fi
        hlog "SPEC_GAP_RESOLVED → engineer 재시도 (depth=std 유지, attempt 동결)"
        error_trace=""; fail_type=""
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
        hlog "architect SPEC_GAP 결과 불명확: $sg_result → engineer 재시도"
        error_trace=""; fail_type=""
        continue
        ;;
    esac
  fi

  # ── automated_checks ───────────────────────────────────────────
  if ! run_automated_checks "$IMPL_FILE"; then
    error_trace=$(cat "${STATE_DIR}/${PREFIX}_autocheck_fail.txt" 2>/dev/null || echo "automated_checks FAIL")
    fail_type="autocheck_fail"
    log_decision "fail_type" "$fail_type" "automated_checks failed"
    append_failure "autocheck_fail" "$error_trace"
    cp "${STATE_DIR}/${PREFIX}_autocheck_fail.txt" "${attempt_dir}/autocheck.log" 2>/dev/null || true
    _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "autocheck_fail" "${attempt_dir}/autocheck.log 참조"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi
  echo "[HARNESS] automated_checks PASS"

  # ── 즉시 커밋 ──────────────────────────────────────────────────
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

  # ── 워커 2: test-engineer ──────────────────────────────────────
  changed_files=$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ' || \
    git status --short | grep -E "^ M|^M |^A " | awk '{print $2}' | tr '\n' ' ' || echo "")
  log_phase "test-engineer"
  echo "[HARNESS] test-engineer (attempt $((attempt+1))/$MAX)"
  hlog "test-engineer 시작 (depth=std, timeout=600s)"
  kill_check
  AGENT_EXIT=0
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
  _agent_call "test-engineer" 600 "$te_prompt" "${STATE_DIR}/${PREFIX}_te_out.txt" || AGENT_EXIT=$?
  hlog "test-engineer 종료 (exit=${AGENT_EXIT})"
  if [[ $AGENT_EXIT -eq 124 ]]; then hlog "test-engineer timeout"; fi
  budget_check "test-engineer" "${STATE_DIR}/${PREFIX}_te_out.txt"

  if ! check_agent_output "test-engineer" "${STATE_DIR}/${PREFIX}_te_out.txt"; then
    fail_type="test_fail"
    error_trace="test-engineer agent produced no output (exit=${AGENT_EXIT})"
    append_failure "$fail_type" "$error_trace"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi

  # ── vitest run (ground truth) ─────────────────────────────────
  echo "[HARNESS] vitest 실행 (attempt $((attempt+1))/$MAX)"
  hlog "vitest 시작"
  kill_check
  set +e
  npx vitest run > "${STATE_DIR}/${PREFIX}_test_out.txt" 2>&1
  test_exit=$?
  set -e
  hlog "vitest 종료 (exit=$test_exit)"
  if [[ $test_exit -ne 0 ]]; then
    echo "[HARNESS] TESTS_FAIL"
    error_trace=$(cat "${STATE_DIR}/${PREFIX}_test_out.txt")
    fail_type="test_fail"
    log_decision "fail_type" "$fail_type" "vitest exit=$test_exit"
    append_failure "test_fail" "$error_trace"
    cp "${STATE_DIR}/${PREFIX}_test_out.txt" "${attempt_dir}/test-results.log" 2>/dev/null || true
    cp "${STATE_DIR}/${PREFIX}_te_out.txt" "${attempt_dir}/test-engineer.log" 2>/dev/null || true
    _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "test_fail" "${attempt_dir}/test-results.log 의 실패 케이스 확인"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi
  touch "${STATE_DIR}/${PREFIX}_test_engineer_passed"
  echo "[HARNESS] TESTS_PASS"

  # ── 워커 3: validator ─────────────────────────────────────────
  log_phase "validator"
  echo "[HARNESS] validator (attempt $((attempt+1))/$MAX)"
  hlog "validator 시작 (depth=std, timeout=300s)"
  kill_check
  val_context=$(build_validator_context "$IMPL_FILE")
  AGENT_EXIT=0
  _agent_call "validator" 300 \
    "@MODE:VALIDATOR:CODE_VALIDATION
impl: $IMPL_FILE
context:
$val_context" \
    "${STATE_DIR}/${PREFIX}_val_out.txt" || AGENT_EXIT=$?
  hlog "validator 종료 (exit=${AGENT_EXIT})"
  if [[ $AGENT_EXIT -eq 124 ]]; then hlog "validator timeout"; fi
  budget_check "validator" "${STATE_DIR}/${PREFIX}_val_out.txt"
  cp "${STATE_DIR}/${PREFIX}_val_out.txt" "${attempt_dir}/validator.log" 2>/dev/null || true

  if ! check_agent_output "validator" "${STATE_DIR}/${PREFIX}_val_out.txt"; then
    fail_type="validator_fail"
    error_trace="validator agent produced no output (exit=${AGENT_EXIT})"
    append_failure "$fail_type" "$error_trace"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi

  val_result=$(parse_marker "${STATE_DIR}/${PREFIX}_val_out.txt" "PASS|FAIL|SPEC_MISSING")
  echo "[HARNESS] validator 결과: $val_result"

  if [[ "$val_result" == "SPEC_MISSING" ]]; then
    hlog "SPEC_MISSING → architect MODULE_PLAN 복구"
    _agent_call "architect" 900 \
      "@MODE:ARCHITECT:MODULE_PLAN
SPEC_MISSING 복구. impl: $IMPL_FILE issue: #$ISSUE_NUM" \
      "${STATE_DIR}/${PREFIX}_arch_sm_out.txt"
    budget_check "architect" "${STATE_DIR}/${PREFIX}_arch_sm_out.txt"
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
    _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "validator_fail" "${attempt_dir}/validator.log 의 FAIL 항목 확인"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi
  touch "${STATE_DIR}/${PREFIX}_validator_b_passed"

  # ── 워커 4: pr-reviewer ───────────────────────────────────────
  log_phase "pr-reviewer"
  echo "[HARNESS] pr-reviewer (attempt $((attempt+1))/$MAX)"
  hlog "pr-reviewer 시작 (depth=std, timeout=240s)"
  kill_check
  diff_out=$(git diff HEAD~1 2>&1 | head -300 || git diff HEAD 2>&1 | head -300)
  AGENT_EXIT=0
  _agent_call "pr-reviewer" 240 \
    "@MODE:PR_REVIEWER:REVIEW
@PARAMS: { \"impl_path\": \"$IMPL_FILE\", \"src_files\": \"$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ' || true)\" }
변경 diff:
$diff_out" "${STATE_DIR}/${PREFIX}_pr_out.txt" || AGENT_EXIT=$?
  hlog "pr-reviewer 종료 (exit=${AGENT_EXIT})"
  if [[ $AGENT_EXIT -eq 124 ]]; then hlog "pr-reviewer timeout"; fi
  budget_check "pr-reviewer" "${STATE_DIR}/${PREFIX}_pr_out.txt"
  cp "${STATE_DIR}/${PREFIX}_pr_out.txt" "${attempt_dir}/pr.log" 2>/dev/null || true

  if ! check_agent_output "pr-reviewer" "${STATE_DIR}/${PREFIX}_pr_out.txt"; then
    fail_type="pr_fail"
    error_trace="pr-reviewer agent produced no output (exit=${AGENT_EXIT})"
    append_failure "$fail_type" "$error_trace"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi

  pr_result=$(parse_marker "${STATE_DIR}/${PREFIX}_pr_out.txt" "LGTM|CHANGES_REQUESTED")
  echo "[HARNESS] pr-reviewer 결과: $pr_result"
  if [[ "$pr_result" != "LGTM" ]]; then
    fail_type="pr_fail"
    log_decision "fail_type" "$fail_type" "pr-reviewer result=$pr_result"
    append_failure "pr_fail" "pr-reviewer CHANGES_REQUESTED (see ${attempt_dir}/pr.log)"
    _save_impl_meta "$attempt_dir" "$attempt" "FAIL" "pr_fail" "${attempt_dir}/pr.log 의 MUST FIX 항목만 수정"
    rollback_attempt $attempt
    attempt=$((attempt+1))
    continue
  fi
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  echo "[HARNESS] LGTM"

  # std: security-reviewer 스킵, 플래그만 자동 생성
  touch "${STATE_DIR}/${PREFIX}_security_review_passed"
  hlog "security-reviewer 스킵 (depth=std)"

  # ── merge to main ───────────────────────────────────────────────
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "$(generate_commit_msg) [test-files]"
    hlog "test 파일 추가 커밋 완료"
  fi
  impl_commit=$(git rev-parse --short HEAD)
  if ! merge_to_main "$FEATURE_BRANCH" "$ISSUE_NUM" "std" "$PREFIX"; then
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

  generate_pr_body $((attempt+1)) > "${STATE_DIR}/${PREFIX}_pr_body.txt" 2>/dev/null || true
  append_success $((attempt+1))
  _save_impl_meta "$attempt_dir" "$attempt" "PASS" "" "구현 완료"
  echo "$ISSUE_NUM" > "${STATE_DIR}/${PREFIX}_last_issue"

  export HARNESS_RESULT="HARNESS_DONE"
  hlog "=== 루프 종료 (HARNESS_DONE, attempt=$((attempt+1))) ==="
  echo "HARNESS_DONE"
  echo "impl: $IMPL_FILE"
  echo "issue: #$ISSUE_NUM"
  echo "attempts: $((attempt+1))"
  echo "commit: $merge_commit"
  echo "pr_body: ${STATE_DIR}/${PREFIX}_pr_body.txt"

  candidate_file="${STATE_DIR}/${PREFIX}_memory_candidate.md"
  if [[ -f "$candidate_file" ]]; then
    echo ""
    echo "[HARNESS MEMORY] 이번 루프에서 실패 패턴이 감지됐습니다."
    echo "   파일: $candidate_file"
    cat "$candidate_file"
    echo ""
    echo "memory_candidate: $candidate_file"
  fi

  exit 0

done

rm -f "${STATE_DIR}/${PREFIX}_plan_validation_passed"
export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
hlog "=== 루프 종료 (IMPLEMENTATION_ESCALATE, attempt=$MAX) ==="
echo "IMPLEMENTATION_ESCALATE"
echo "attempts: $MAX"
echo "spec_gap_count: $spec_gap_count"
echo "branch: ${FEATURE_BRANCH:-unknown}"
echo "마지막 에러:"
echo "$error_trace" | head -20
exit 1
