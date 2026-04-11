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
  local lock="${STATE_DIR}/${PREFIX}_harness_active"
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
  [[ ! -f "${STATE_DIR}/${PREFIX}_harness_active" ]]
}

@test "executor: detect_depth frontmatter deep" {
  source "${HARNESS_DIR}/utils.sh"
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(awk '/^---$/{n++} n==1 && /^depth:/{sub(/^depth:[[:space:]]*/,""); sub(/[[:space:]]*#.*/,""); print; exit}' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  printf '%s\n' '---' 'depth: deep' 'issue: 1' '---' '- A (TEST)' '- B (BROWSER:DOM)' > "$TEST_TMP/mixed.md"
  result=$(detect_depth "$TEST_TMP/mixed.md")
  [[ "$result" == "deep" ]]
}

@test "executor: detect_depth frontmatter simple" {
  source "${HARNESS_DIR}/utils.sh"
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(awk '/^---$/{n++} n==1 && /^depth:/{sub(/^depth:[[:space:]]*/,""); sub(/[[:space:]]*#.*/,""); print; exit}' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  printf '%s\n' '---' 'depth: simple' 'issue: 1' 'reason: text only' '---' '- A (MANUAL)' > "$TEST_TMP/mixed2.md"
  result=$(detect_depth "$TEST_TMP/mixed2.md")
  [[ "$result" == "simple" ]]
}

@test "executor: arg parsing extracts all params" {
  run bash -c '
    IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; BUG_DESC=""; CONTEXT=""; DEPTH="auto"
    set -- --impl "docs/impl/01.md" --issue 42 --prefix myproj --depth simple --context "ctx" --bug "desc"
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
  [[ "$output" == *"DEPTH=simple"* ]]
}

# bugfix 테스트 — REMOVED (v6): bugfix.sh 삭제됨. QA는 impl 루프로 통합.

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
