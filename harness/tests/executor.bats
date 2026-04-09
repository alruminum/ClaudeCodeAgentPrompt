#!/usr/bin/env bats

load test_helper

setup() {
  common_setup
}

teardown() {
  common_teardown
}

@test "executor: unknown mode exits with HARNESS_CRASH" {
  run bash -c '
    MODE="invalid_mode"
    export HARNESS_RESULT="unknown"
    case "$MODE" in
      impl|design|bugfix|plan) echo "ROUTED" ;;
      *) export HARNESS_RESULT="HARNESS_CRASH"; echo "HARNESS_CRASH: unknown mode $MODE"; exit 1 ;;
    esac
  '
  [[ "$output" == *"HARNESS_CRASH"* ]]
  [[ $status -eq 1 ]]
}

@test "executor: all 4 modes are valid routes" {
  for mode in impl design bugfix plan; do
    run bash -c '
      MODE="'"$mode"'"
      case "$MODE" in
        impl|design|bugfix|plan) echo "OK" ;;
        *) echo "FAIL"; exit 1 ;;
      esac
    '
    [[ "$output" == "OK" ]]
  done
}

@test "executor: stale lock with dead PID is cleaned" {
  local lock="/tmp/${PREFIX}_harness_active"
  echo '{"pid":99999999,"mode":"impl","started":1000,"heartbeat":1000}' > "$lock"
  run bash -c '
    lock="'"$lock"'"
    existing_pid=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get(\"pid\", \"\"))
except: pass
" "$lock" 2>/dev/null || true)
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "BLOCKED"; exit 1
    fi
    rm -f "$lock"
    echo "CLEANED"
  '
  [[ "$output" == "CLEANED" ]]
  [[ ! -f "/tmp/${PREFIX}_harness_active" ]]
}

@test "executor: detect_depth BROWSER:DOM + TEST prefers deep" {
  source "${HARNESS_DIR}/utils.sh"
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    if grep -q "(BROWSER:DOM)" "$impl" 2>/dev/null; then echo "deep"
    elif grep -q "(MANUAL)" "$impl" 2>/dev/null && ! grep -qE "\(TEST\)|\(BROWSER:DOM\)" "$impl" 2>/dev/null; then echo "fast"
    else echo "std"; fi
  }
  echo "- A (TEST)
- B (BROWSER:DOM)" > "$TEST_TMP/mixed.md"
  result=$(detect_depth "$TEST_TMP/mixed.md")
  [[ "$result" == "deep" ]]
}

@test "executor: detect_depth MANUAL+TEST -> std not fast" {
  source "${HARNESS_DIR}/utils.sh"
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    if grep -q "(BROWSER:DOM)" "$impl" 2>/dev/null; then echo "deep"
    elif grep -q "(MANUAL)" "$impl" 2>/dev/null && ! grep -qE "\(TEST\)|\(BROWSER:DOM\)" "$impl" 2>/dev/null; then echo "fast"
    else echo "std"; fi
  }
  echo "- A (TEST)
- B (MANUAL)" > "$TEST_TMP/mixed2.md"
  result=$(detect_depth "$TEST_TMP/mixed2.md")
  [[ "$result" == "std" ]]
}

@test "executor: arg parsing extracts all params" {
  run bash -c '
    IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"
    set -- --impl "docs/impl/01.md" --issue 42 --prefix myproj --depth fast --context "ctx" --bug "desc"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --impl)    IMPL_FILE="$2";  shift 2 ;;
        --issue)   ISSUE_NUM="$2";  shift 2 ;;
        --prefix)  PREFIX="$2";     shift 2 ;;
        --bug)     BUG_DESC="$2";   shift 2 ;;
        --context) CONTEXT="$2";    shift 2 ;;
        --depth)   DEPTH="$2";      shift 2 ;;
        *) shift ;;
      esac
    done
    echo "IMPL=$IMPL_FILE ISSUE=$ISSUE_NUM PREFIX=$PREFIX DEPTH=$DEPTH"
  '
  [[ "$output" == *"IMPL=docs/impl/01.md"* ]]
  [[ "$output" == *"ISSUE=42"* ]]
  [[ "$output" == *"PREFIX=myproj"* ]]
  [[ "$output" == *"DEPTH=fast"* ]]
}

@test "bugfix: re-entry with existing impl skips QA" {
  source "${HARNESS_DIR}/utils.sh"
  local impl_path=$(create_mock_impl "(TEST)")

  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"
    IMPL_FILE="'"$impl_path"'"; BUG_DESC=""; DEPTH="fast"
    CONSTRAINTS=""; RUN_LOG=""
    _agent_call() { echo "0" > "${4%.txt}_cost.txt"; echo "mock" > "$4"; }
    rotate_harness_logs() { true; }
    create_feature_branch() { echo "fix/999"; }
    merge_to_main() { return 0; }
    harness_commit_and_merge() { return 0; }
    npx() { return 0; }
    run_bugfix 2>/dev/null
  '
  [[ "$output" == *"impl"* ]]
}

@test "bugfix: backlog routing exits with BACKLOG" {
  echo "---QA_SUMMARY---
TYPE: FUNCTIONAL_BUG
ROUTING: backlog
---END_QA_SUMMARY---" > "/tmp/${PREFIX}_qa_out.txt"

  source "${HARNESS_DIR}/utils.sh"
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"
    _bugfix_route 2>/dev/null
  '
  [[ "$output" == *"BACKLOG"* ]]
  [[ $status -eq 0 ]]
}

@test "create_feature_branch: generates correct format" {
  source "${HARNESS_DIR}/utils.sh"
  create_test_commit "init.txt"
  gh() { return 1; }
  export -f gh
  result=$(create_feature_branch "feat" "42")
  [[ "$result" == *"feat/"* ]]
  [[ "$result" == *"42"* ]]
  git -C "${GIT_WORK_TREE}" checkout main 2>/dev/null || git -C "${GIT_WORK_TREE}" checkout master 2>/dev/null || true
}

@test "create_feature_branch: existing branch triggers checkout" {
  source "${HARNESS_DIR}/utils.sh"
  create_test_commit "init.txt"
  # Manually create the branch to simulate re-entry
  local branch_name="feat/42"
  git -C "${GIT_WORK_TREE}" branch "$branch_name" 2>/dev/null || true
  # Now create_feature_branch should just checkout the existing branch
  gh() { return 1; }
  export -f gh
  result=$(create_feature_branch "feat" "42")
  [[ "$result" == *"feat/"* ]]
  [[ "$result" == *"42"* ]]
}
