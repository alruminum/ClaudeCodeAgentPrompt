#!/bin/bash
# ~/.claude/harness/impl_fast.sh
# fast depth 구현 루프: engineer → pr-reviewer → merge (LLM 2회)
# 상세: orchestration/impl_fast.md
#
# 호출 형식 (impl.sh dispatcher에서 호출):
#   bash ~/.claude/harness/impl_fast.sh \
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

DEPTH="fast"

if [[ -z "$IMPL_FILE" || -z "$ISSUE_NUM" ]]; then
  echo "사용법: bash harness/impl_fast.sh --impl <path> --issue <N> [--prefix <prefix>]"
  exit 1
fi

if [[ ! -f "$IMPL_FILE" ]]; then
  echo "[HARNESS] 오류: impl 파일을 찾을 수 없음: $IMPL_FILE"
  exit 1
fi

_load_constraints
_setup_hlog
_setup_cleanup

touch "/tmp/${PREFIX}_harness_active"
[[ ! -f "/tmp/${PREFIX}_plan_validation_passed" ]] && touch "/tmp/${PREFIX}_plan_validation_passed"
rotate_harness_logs "$PREFIX" "impl"

# run_log 경로 (write_run_end 등에서 사용)
RUN_LOG="/tmp/${PREFIX}_run.jsonl"

FEATURE_BRANCH=$(create_feature_branch "$BRANCH_TYPE" "$ISSUE_NUM")
export HARNESS_BRANCH="$FEATURE_BRANCH"
hlog "feature branch: $FEATURE_BRANCH"
[[ -n "$RUN_LOG" ]] && printf '{"event":"branch_create","branch":"%s","t":%d}\n' \
  "$FEATURE_BRANCH" "$(date +%s)" >> "$RUN_LOG"

hlog "=== 하네스 루프 시작 (depth=fast) ==="
[[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"fast","max_retries":1,"constraints_chars":%d}\n' \
  "$IMPL_FILE" "$ISSUE_NUM" "${#CONSTRAINTS}" >> "$RUN_LOG"

# ── fast: engineer ───────────────────────────────────────────────────
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

if [[ -n "$changed_list" ]]; then
  echo "$changed_list" | while IFS= read -r _cf; do
    [[ -n "$_cf" ]] && git add -- "$_cf"
  done
  git commit -m "$(generate_commit_msg) [fast-mode]"
fi

# ── fast: pr-reviewer ────────────────────────────────────────────────
kill_check
log_phase "pr-reviewer"
echo "[HARNESS/fast] pr-reviewer"
hlog "pr-reviewer 시작 (depth=fast, timeout=240s)"
fast_diff=$(git diff HEAD~1 2>&1 | head -300)
fast_src=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ' ')
AGENT_EXIT=0
_agent_call "pr-reviewer" 240 \
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

# ── fast: merge to main ──────────────────────────────────────────────
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

export HARNESS_RESULT="HARNESS_DONE"
echo "HARNESS_DONE (fast)"
echo "impl: $IMPL_FILE"
echo "issue: #$ISSUE_NUM"
echo "commit: $merge_commit"
hlog "=== 루프 종료 (HARNESS_DONE, fast) ==="
exit 0
