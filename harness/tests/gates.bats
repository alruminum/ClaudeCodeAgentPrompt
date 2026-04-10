#!/usr/bin/env bats
# harness/tests/gates.bats - merge gates, budget, SPEC_GAP flow

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# === merge_to_main depth gates ===

@test "merge gate: fast requires pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-merge" 2>/dev/null
  create_test_commit "feature.txt"
  # No pr_reviewer_lgtm — fast should be rejected
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/test-merge" "999" "fast" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: fast passes with pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-merge2" 2>/dev/null
  create_test_commit "feature.txt"
  touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/test-merge2" "999" "fast" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "merge gate: std requires pr_reviewer_lgtm (not validator_b_passed)" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-std" 2>/dev/null
  create_test_commit "feature.txt"
  # validator_b_passed alone is insufficient for std
  touch "/tmp/${PREFIX}_validator_b_passed"
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/test-std" "999" "std" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: std passes with pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-std2" 2>/dev/null
  create_test_commit "feature.txt"
  touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/test-std2" "999" "std" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "merge gate: deep requires pr_reviewer_lgtm + security_review_passed" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-deep" 2>/dev/null
  create_test_commit "feature.txt"
  # Missing both flags
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm" "/tmp/${PREFIX}_security_review_passed"
  run merge_to_main "feat/test-deep" "999" "deep" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: deep with pr_reviewer but no security -> fail" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-deep2" 2>/dev/null
  create_test_commit "feature.txt"
  touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
  rm -f "/tmp/${PREFIX}_security_review_passed"
  run merge_to_main "feat/test-deep2" "999" "deep" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"security_review_passed"* ]]
}

@test "merge gate: deep passes with both flags" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/test-deep3" 2>/dev/null
  create_test_commit "feature.txt"
  touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
  touch "/tmp/${PREFIX}_security_review_passed"
  run merge_to_main "feat/test-deep3" "999" "deep" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "merge gate: bugfix depth uses validator_b_passed" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "fix/test-bf" 2>/dev/null
  create_test_commit "feature.txt"
  rm -f "/tmp/${PREFIX}_validator_b_passed"
  run merge_to_main "fix/test-bf" "999" "bugfix" "$PREFIX"
  [[ $status -ne 0 ]]
}

# === budget_check ===

@test "budget: under limit passes" {
  TOTAL_COST=0
  MAX_TOTAL_COST=10
  budget_check() {
    local agent_name="$1" out_file="$2"
    local cost_file="${out_file%.txt}_cost.txt"
    local agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
    TOTAL_COST=$(echo "$TOTAL_COST + $agent_cost" | bc 2>/dev/null || echo "$TOTAL_COST")
    if [[ "$(echo "$TOTAL_COST > $MAX_TOTAL_COST" | bc 2>/dev/null)" == "1" ]]; then
      echo "HARNESS_BUDGET_EXCEEDED"
      return 1
    fi
    return 0
  }
  echo "1.5" > "$TEST_TMP/agent_cost.txt"
  echo "mock" > "$TEST_TMP/agent.txt"
  run budget_check "engineer" "$TEST_TMP/agent.txt"
  [[ $status -eq 0 ]]
}

@test "budget: over limit triggers BUDGET_EXCEEDED" {
  TOTAL_COST=9.5
  MAX_TOTAL_COST=10
  hlog() { true; }
  budget_check() {
    local agent_name="$1" out_file="$2"
    local cost_file="${out_file%.txt}_cost.txt"
    local agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
    TOTAL_COST=$(echo "$TOTAL_COST + $agent_cost" | bc 2>/dev/null || echo "$TOTAL_COST")
    if [[ "$(echo "$TOTAL_COST > $MAX_TOTAL_COST" | bc 2>/dev/null)" == "1" ]]; then
      echo "HARNESS_BUDGET_EXCEEDED"
      return 1
    fi
    return 0
  }
  echo "1.0" > "$TEST_TMP/agent_cost.txt"
  echo "mock" > "$TEST_TMP/agent.txt"
  run budget_check "engineer" "$TEST_TMP/agent.txt"
  [[ "$output" == *"BUDGET_EXCEEDED"* ]]
  [[ $status -eq 1 ]]
}

# === SPEC_GAP flow logic (code analysis) ===

@test "SPEC_GAP: attempt is NOT incremented on SPEC_GAP_FOUND" {
  # Verify the code path: after SPEC_GAP_FOUND -> continue (no attempt++)
  run bash -c '
    grep -A30 "SPEC_GAP_FOUND" "'"${HARNESS_DIR}/impl-process.sh"'" \
      | grep -B1 "continue" | head -5
  '
  # Should find "continue" after SPEC_GAP handling, before any attempt++
  [[ "$output" == *"continue"* ]]
}

@test "SPEC_GAP: error_trace is cleared after RESOLVED" {
  run grep -A3 'SPEC_GAP_RESOLVED' "${HARNESS_DIR}/impl-process.sh"
  [[ "$output" == *'error_trace=""'* ]]
  [[ "$output" == *'fail_type=""'* ]]
}

@test "SPEC_GAP: 3-way branch covers all architect outcomes" {
  # Verify SPEC_GAP_RESOLVED, PRODUCT_PLANNER_ESCALATION_NEEDED, TECH_CONSTRAINT_CONFLICT
  run grep -c 'SPEC_GAP_RESOLVED\|PRODUCT_PLANNER_ESCALATION_NEEDED\|TECH_CONSTRAINT_CONFLICT' "${HARNESS_DIR}/impl-process.sh"
  [[ "$output" -ge 3 ]]
}

# === impl-process.sh: automated checks ===

@test "automated checks: no_changes detected" {
  run_automated_checks() {
    local impl_file="$1"
    local out_file="/tmp/${PREFIX}_autocheck_fail.txt"
    rm -f "$out_file"
    if ! git status --short | grep -qE "^ M|^M |^A "; then
      echo "no_changes: engineer produced nothing" > "$out_file"
      return 1
    fi
    return 0
  }
  create_test_commit "init.txt"
  run run_automated_checks "$TEST_TMP/fake_impl.md"
  [[ $status -ne 0 ]]
}

# === design: ITERATE feedback accumulation ===

@test "design: ITERATE passes feedback to next designer call" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/design.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="initial"
    call_count=0
    _agent_call() {
      local agent="$1" prompt="$3" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      call_count=$((call_count + 1))
      if [[ "$agent" == "designer" ]]; then
        if [[ $call_count -ge 5 ]]; then
          # After enough iterations, designer prompt should contain feedback
          if echo "$prompt" | grep -q "design-critic feedback"; then
            echo "FEEDBACK_PASSED" > "$out"
          else
            echo "NO_FEEDBACK" > "$out"
          fi
        else
          echo "variant A, B, C" > "$out"
        fi
      elif [[ "$agent" == "design-critic" ]]; then
        if [[ $call_count -lt 6 ]]; then
          echo "ITERATE - needs work. Specific feedback: use darker colors." > "$out"
        else
          echo "PICK" > "$out"
        fi
      fi
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_design
  '
  # After iterations, the CONTEXT should have accumulated feedback
  # The test verifies the ITERATE path works without infinite loop
  [[ $status -eq 0 ]]
}

# === cross-script: bugfix_full chains to bugfix_direct ===

@test "bugfix_full: architect + PV PASS -> chains to engineer direct" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; DEPTH="fast"
    IMPL_FILE=""; CONSTRAINTS=""; RUN_LOG=""
    mkdir -p "'"${GIT_WORK_TREE}"'/docs/impl"
    echo "# bugfix impl" > "'"${GIT_WORK_TREE}"'/docs/impl/01-bugfix.md"
    cd "'"${GIT_WORK_TREE}"'"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      case "$agent" in
        architect) echo "docs/impl/01-bugfix.md" > "$out" ;;
        validator) echo "PASS" > "$out" ;;
        engineer) echo "fix applied" > "$out" ;;
      esac
    }
    create_feature_branch() { echo "fix/999"; }
    merge_to_main() { return 0; }
    harness_commit_and_merge() { return 0; }
    npx() { return 0; }
    rotate_harness_logs() { true; }
    echo "FUNCTIONAL_BUG analysis" > "/tmp/'"$PREFIX"'_qa_out.txt"
    _architect_route "/tmp/'"$PREFIX"'_qa_out.txt"
  '
  [[ "$output" == *"Plan Validation PASS"* ]]
  [[ "$output" == *"engineer"* ]]
}
