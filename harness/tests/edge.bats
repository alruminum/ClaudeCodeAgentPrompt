#!/usr/bin/env bats
# harness/tests/edge.bats - edge cases + regression guards

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# === rotate_harness_logs: FIFO 10-run ===

@test "rotate_harness_logs creates log file and sets RUN_LOG" {
  rotate_harness_logs "$PREFIX" "test"
  [[ -n "$RUN_LOG" ]]
  [[ -f "$RUN_LOG" ]]
  # Should contain run_start event
  run grep "run_start" "$RUN_LOG"
  [[ $status -eq 0 ]]
}

@test "rotate_harness_logs preserves max 10 files" {
  local dir="${HARNESS_LOG_DIR}/${PREFIX}"
  mkdir -p "$dir"
  # Create 12 fake log files
  for i in $(seq 1 12); do
    touch "$dir/run_2026010${i}_000000.jsonl"
    sleep 0.01  # ensure different mtime
  done
  rotate_harness_logs "$PREFIX" "test"
  local count=$(ls "$dir"/run_*.jsonl 2>/dev/null | wc -l | tr -d ' ')
  # Should be <= 11 (10 kept + 1 new)
  [[ $count -le 11 ]]
}

# === write_run_end: branch name recorded ===

@test "write_run_end records branch name" {
  mkdir -p "$TEST_TMP/logs"
  RUN_LOG="$TEST_TMP/logs/test.jsonl"
  _HARNESS_RUN_START=$(date +%s)
  echo '{"event":"run_start"}' > "$RUN_LOG"
  HARNESS_RESULT="HARNESS_DONE"
  HARNESS_BRANCH="feat/42-test"
  write_run_end
  run grep "feat/42-test" "$RUN_LOG"
  [[ $status -eq 0 ]]
}

# === parse_marker: BUGFIX markers ===

@test "parse_marker detects BUGFIX_PASS" {
  echo "validation: BUGFIX_PASS" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "BUGFIX_PASS|BUGFIX_FAIL|PASS|FAIL")
  [[ "$result" == "BUGFIX_PASS" ]]
}

@test "parse_marker detects BUGFIX_FAIL" {
  echo "BUGFIX_FAIL: regression found" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "BUGFIX_PASS|BUGFIX_FAIL|PASS|FAIL")
  [[ "$result" == "BUGFIX_FAIL" ]]
}

@test "parse_marker detects SECURE" {
  echo "security review: SECURE" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "SECURE|VULNERABILITIES_FOUND")
  [[ "$result" == "SECURE" ]]
}

@test "parse_marker detects VULNERABILITIES_FOUND" {
  echo "HIGH risk! VULNERABILITIES_FOUND" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "SECURE|VULNERABILITIES_FOUND")
  [[ "$result" == "VULNERABILITIES_FOUND" ]]
}

# === design PICK/ITERATE/ESCALATE markers ===

@test "parse_marker detects PICK" {
  echo "PICK variant A" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PICK|ITERATE|ESCALATE")
  [[ "$result" == "PICK" ]]
}

@test "parse_marker detects ITERATE" {
  echo "ITERATE with feedback" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PICK|ITERATE|ESCALATE")
  [[ "$result" == "ITERATE" ]]
}

# === bugfix: DUPLICATE_OF detection ===

@test "bugfix: DUPLICATE_OF updates ISSUE_NUM" {
  source "${HARNESS_DIR}/bugfix.sh"
  cat > "$TEST_TMP/qa_dup.txt" <<'EOF'
---QA_SUMMARY---
TYPE: FUNCTIONAL_BUG
DUPLICATE_OF: #42
---END_QA_SUMMARY---
EOF
  result=$(_parse_qa_summary "$TEST_TMP/qa_dup.txt" "DUPLICATE_OF")
  [[ "$result" == "#42" ]]
}

# === impl: depth auto-detection from impl file ===

@test "impl: depth auto-detect passes correct value to process" {
  local mock_script="$TEST_TMP/mock_process.sh"
  echo '#!/bin/bash
echo "RECEIVED_ARGS: $@"
exit 0' > "$mock_script"
  chmod +x "$mock_script"

  local impl_path=$(create_mock_impl "(BROWSER:DOM)")
  touch "/tmp/${PREFIX}_plan_validation_passed"

  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/impl.sh"'"
    PREFIX="'"$PREFIX"'"
    IMPL_FILE="'"$impl_path"'"
    ISSUE_NUM="999"
    DEPTH="auto"
    BRANCH_TYPE="feat"
    touch "/tmp/'"$PREFIX"'_plan_validation_passed"
    PROCESS_SCRIPT="'"$mock_script"'"
    detect_depth() {
      local impl="$1"
      if grep -q "(BROWSER:DOM)" "$impl" 2>/dev/null; then echo "deep"; else echo "std"; fi
    }
    run_impl
  '
  [[ "$output" == *"--depth deep"* ]]
}

# === harness_commit_and_merge: merge failure returns 1 ===

@test "harness_commit_and_merge: merge conflict returns 1" {
  create_test_commit "init.txt"
  IMPL_FILE=""
  ISSUE_NUM="999"
  merge_to_main() {
    echo "MERGE_CONFLICT_ESCALATE"
    return 1
  }
  echo "modified" > "${GIT_WORK_TREE}/init.txt"
  git -C "${GIT_WORK_TREE}" add init.txt
  run harness_commit_and_merge "feat/999" "999" "fast" "$PREFIX"
  [[ $status -eq 1 ]]
  [[ "$output" == *"MERGE_CONFLICT_ESCALATE"* ]]
}

# === regression: fast mode HAS pr-reviewer (since commit-strategy refactor) ===

@test "regression: fast mode calls pr-reviewer" {
  # After commit-strategy refactor, pr-reviewer runs on fast/std/deep
  run bash -c '
    grep -c "pr-reviewer" "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  # Must appear in the file (covers fast path)
  [[ "$output" -ge 1 ]]
}

@test "regression: fast mode uses git diff HEAD~1 for pr-reviewer diff" {
  # After early commit, diff must reference HEAD~1 (not HEAD)
  run bash -c '
    sed -n "/fast: pr-reviewer/,/fast: merge/p" "'"${HARNESS_DIR}/impl_fast.sh"'" \
      | grep "diff HEAD~1"
  '
  [[ "$output" == *"HEAD~1"* ]]
}

# === regression: pr_reviewer_lgtm set after fast pr-reviewer ===

@test "regression: fast path touches pr_reviewer_lgtm after pr-reviewer" {
  run bash -c '
    # The fast section should touch pr_reviewer_lgtm
    sed -n "/HARNESS.fast. pr-reviewer/,/HARNESS.fast. merge/p" "'"${HARNESS_DIR}/impl_fast.sh"'" \
      | grep "pr_reviewer_lgtm"
  '
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

# === policy 15: max rounds = attempt 3 + spec_gap 2 = 5 ===

@test "policy15: max total rounds is 5 (attempt 3 + spec_gap 2)" {
  run grep 'MAX=3' "${HARNESS_DIR}/impl_std.sh"
  [[ $status -eq 0 ]]
  run grep 'MAX_SPEC_GAP=2' "${HARNESS_DIR}/impl_std.sh"
  [[ $status -eq 0 ]]
  # Both exist, so max rounds = 3 + 2 = 5
}
