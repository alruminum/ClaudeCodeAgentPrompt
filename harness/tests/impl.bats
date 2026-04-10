#!/usr/bin/env bats
# harness/tests/impl.bats — impl.sh + impl_std.sh flow tests

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# === impl.sh: re-entry detection ===

@test "impl: re-entry with plan_validation_passed skips to process" {
  local impl_path=$(create_mock_impl "(TEST)")
  # Create a mock process script that just exits 0
  local mock_script="$TEST_TMP/mock_process.sh"
  echo '#!/bin/bash
echo "MOCK_PROCESS_CALLED $@"
exit 0' > "$mock_script"
  chmod +x "$mock_script"

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
    detect_depth() { echo "std"; }
    run_impl
  '
  [[ "$output" == *"MOCK_PROCESS_CALLED"* ]]
  [[ "$output" == *"--depth std"* ]]
  [[ $status -eq 0 ]]
}

@test "impl: UI keyword detected -> UI_DESIGN_REQUIRED" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/impl.sh"'"
    PREFIX="'"$PREFIX"'"
    ISSUE_NUM="999"
    DEPTH="auto"
    RUN_LOG=""
    # create impl with UI keywords
    mkdir -p "'"${GIT_WORK_TREE}"'/docs/impl"
    echo "## UI 화면 컴포넌트 레이아웃" > "'"${GIT_WORK_TREE}"'/docs/impl/01-ui.md"
    IMPL_FILE="'"${GIT_WORK_TREE}"'/docs/impl/01-ui.md"
    # no design_critic_passed flag
    rm -f "/tmp/'"$PREFIX"'_design_critic_passed"
    rm -f "/tmp/'"$PREFIX"'_plan_validation_passed"
    rotate_harness_logs() { true; }
    _agent_call() { echo "0" > "${4%.txt}_cost.txt"; echo "mock" > "$4"; }
    PROCESS_SCRIPT="echo"
    detect_depth() { echo "std"; }
    run_impl
  '
  [[ "$output" == *"UI_DESIGN_REQUIRED"* ]]
  [[ $status -eq 0 ]]
}

@test "impl: UI keyword with design_critic_passed -> no block" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/impl.sh"'"
    PREFIX="'"$PREFIX"'"
    ISSUE_NUM="999"
    DEPTH="auto"
    RUN_LOG=""
    mkdir -p "'"${GIT_WORK_TREE}"'/docs/impl"
    echo "## UI 화면 컴포넌트" > "'"${GIT_WORK_TREE}"'/docs/impl/01-ui.md"
    IMPL_FILE="'"${GIT_WORK_TREE}"'/docs/impl/01-ui.md"
    touch "/tmp/'"$PREFIX"'_design_critic_passed"
    rm -f "/tmp/'"$PREFIX"'_plan_validation_passed"
    rotate_harness_logs() { true; }
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      if [[ "$agent" == "validator" ]]; then echo "PASS" > "$out"
      else echo "docs/impl/01-ui.md" > "$out"; fi
    }
    cd "'"${GIT_WORK_TREE}"'"
    PROCESS_SCRIPT="echo"
    detect_depth() { echo "std"; }
    run_impl
  '
  # Should NOT show UI_DESIGN_REQUIRED, should proceed to plan validation
  [[ "$output" != *"UI_DESIGN_REQUIRED"* ]]
}

@test "impl: no impl file -> architect fallback -> PLAN_VALIDATION_PASS" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/impl.sh"'"
    PREFIX="'"$PREFIX"'"
    ISSUE_NUM="999"
    DEPTH="auto"
    IMPL_FILE=""
    CONTEXT="test"
    RUN_LOG=""
    mkdir -p "'"${GIT_WORK_TREE}"'/docs/impl"
    echo "# impl" > "'"${GIT_WORK_TREE}"'/docs/impl/01-test.md"
    cd "'"${GIT_WORK_TREE}"'"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      case "$agent" in
        architect) echo "docs/impl/01-test.md" > "$out" ;;
        validator) echo "PASS" > "$out" ;;
      esac
    }
    rotate_harness_logs() { true; }
    detect_depth() { echo "std"; }
    PROCESS_SCRIPT="echo"
    run_impl
  '
  [[ "$output" == *"PLAN_VALIDATION_PASS"* ]]
  [[ $status -eq 0 ]]
}

@test "impl: architect fails to create impl -> SPEC_GAP_ESCALATE" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/impl.sh"'"
    PREFIX="'"$PREFIX"'"
    ISSUE_NUM="999"
    IMPL_FILE=""
    CONTEXT="test"
    RUN_LOG=""
    cd "'"${GIT_WORK_TREE}"'"
    _agent_call() {
      echo "0" > "${4%.txt}_cost.txt"
      echo "no impl generated" > "$4"
    }
    rotate_harness_logs() { true; }
    run_impl
  '
  [[ "$output" == *"SPEC_GAP_ESCALATE"* ]]
  [[ $status -eq 1 ]]
}

# === run_plan_validation unit tests ===

@test "run_plan_validation: PASS on first try" {
  local impl_path=$(create_mock_impl "(TEST)")
  _agent_call() {
    echo "0" > "${4%.txt}_cost.txt"
    echo "PASS" > "$4"
  }
  run_plan_validation "$impl_path" "999" "$PREFIX" 1
  [[ $? -eq 0 ]]
  [[ -f "/tmp/${PREFIX}_plan_validation_passed" ]]
}

@test "run_plan_validation: FAIL then rework PASS" {
  local impl_path=$(create_mock_impl "(TEST)")
  local call_idx=0
  _agent_call() {
    local agent="$1" out="$4"
    echo "0" > "${out%.txt}_cost.txt"
    call_idx=$((call_idx + 1))
    if [[ "$agent" == "validator" && $call_idx -le 1 ]]; then
      echo "FAIL — missing specs" > "$out"
    elif [[ "$agent" == "architect" ]]; then
      echo "SPEC_GAP fixed" > "$out"
    else
      echo "PASS" > "$out"
    fi
  }
  run_plan_validation "$impl_path" "999" "$PREFIX" 1
  [[ $? -eq 0 ]]
}

@test "run_plan_validation: FAIL after rework -> return 1" {
  local impl_path=$(create_mock_impl "(TEST)")
  _agent_call() {
    echo "0" > "${4%.txt}_cost.txt"
    echo "FAIL — still broken" > "$4"
  }
  run run_plan_validation "$impl_path" "999" "$PREFIX" 1
  [[ $status -ne 0 ]]
}

# === run_design_validation unit tests ===

@test "run_design_validation: PASS on first try" {
  mkdir -p "${GIT_WORK_TREE}/docs"
  echo "# design" > "${GIT_WORK_TREE}/docs/architecture.md"
  _agent_call() {
    echo "0" > "${4%.txt}_cost.txt"
    echo "PASS" > "$4"
  }
  run_design_validation "${GIT_WORK_TREE}/docs/architecture.md" "999" "$PREFIX" 1
  [[ $? -eq 0 ]]
}

@test "run_design_validation: FAIL after rework -> return 1" {
  mkdir -p "${GIT_WORK_TREE}/docs"
  echo "# design" > "${GIT_WORK_TREE}/docs/architecture.md"
  _agent_call() {
    echo "0" > "${4%.txt}_cost.txt"
    echo "FAIL — design flaws" > "$4"
  }
  run run_design_validation "${GIT_WORK_TREE}/docs/architecture.md" "999" "$PREFIX" 1
  [[ $status -ne 0 ]]
}

# === harness_commit_and_merge unit tests ===

@test "harness_commit_and_merge: no changes -> return 0 (merge only)" {
  create_test_commit "initial.txt"
  # mock merge_to_main to succeed
  merge_to_main() { return 0; }
  run harness_commit_and_merge "test-branch" "999" "fast" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "harness_commit_and_merge: with changes -> commit + merge" {
  create_test_commit "initial.txt"
  echo "modified" > "${GIT_WORK_TREE}/initial.txt"
  git -C "${GIT_WORK_TREE}" add initial.txt
  IMPL_FILE=""
  ISSUE_NUM="999"
  # mock merge_to_main
  merge_to_main() { return 0; }
  run harness_commit_and_merge "test-branch" "999" "fast" "$PREFIX"
  [[ $status -eq 0 ]]
}

# === QA_SUMMARY parsing (bugfix helpers) ===

@test "bugfix: _parse_qa_summary extracts footer fields" {
  source "${HARNESS_DIR}/bugfix.sh"
  cat > "$TEST_TMP/qa.txt" <<'EOF'
analysis results here...

---QA_SUMMARY---
TYPE: FUNCTIONAL_BUG
SEVERITY: HIGH
AFFECTED_FILES: 3
ROUTING: engineer_direct
DUPLICATE_OF: N
---END_QA_SUMMARY---
EOF
  [[ "$(_parse_qa_summary "$TEST_TMP/qa.txt" "TYPE")" == "FUNCTIONAL_BUG" ]]
  [[ "$(_parse_qa_summary "$TEST_TMP/qa.txt" "SEVERITY")" == "HIGH" ]]
  [[ "$(_parse_qa_summary "$TEST_TMP/qa.txt" "AFFECTED_FILES")" == "3" ]]
  [[ "$(_parse_qa_summary "$TEST_TMP/qa.txt" "ROUTING")" == "engineer_direct" ]]
}

@test "bugfix: _parse_qa_summary returns empty for missing field" {
  source "${HARNESS_DIR}/bugfix.sh"
  echo "no footer here" > "$TEST_TMP/qa.txt"
  result=$(_parse_qa_summary "$TEST_TMP/qa.txt" "TYPE")
  [[ -z "$result" ]]
}
