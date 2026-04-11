#!/usr/bin/env bats
# harness/tests/utils.bats — utils.sh unit tests

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# === parse_marker ===

@test "parse_marker detects PASS" {
  echo "result: PASS — all items OK" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PASS|FAIL")
  [[ "$result" == "PASS" ]]
}

@test "parse_marker detects FAIL" {
  echo "validation FAIL: 3 items missing" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PASS|FAIL")
  [[ "$result" == "FAIL" ]]
}

@test "parse_marker detects LGTM" {
  echo "code review done. LGTM" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "LGTM|CHANGES_REQUESTED")
  [[ "$result" == "LGTM" ]]
}

@test "parse_marker detects CHANGES_REQUESTED" {
  echo "MUST FIX 3 items. CHANGES_REQUESTED" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "LGTM|CHANGES_REQUESTED")
  [[ "$result" == "CHANGES_REQUESTED" ]]
}

@test "parse_marker returns UNKNOWN when no marker" {
  echo "agent output without any marker" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PASS|FAIL")
  [[ "$result" == "UNKNOWN" ]]
}

@test "parse_marker returns UNKNOWN for empty file" {
  : > "$TEST_TMP/empty.txt"
  result=$(parse_marker "$TEST_TMP/empty.txt" "PASS|FAIL")
  [[ "$result" == "UNKNOWN" ]]
}

@test "parse_marker returns UNKNOWN for missing file" {
  result=$(parse_marker "$TEST_TMP/nonexistent.txt" "PASS|FAIL")
  [[ "$result" == "UNKNOWN" ]]
}

@test "parse_marker returns first match only" {
  printf "PASS\nFAIL\n" > "$TEST_TMP/multi.txt"
  result=$(parse_marker "$TEST_TMP/multi.txt" "PASS|FAIL")
  [[ "$result" == "PASS" ]]
}

@test "parse_marker detects SPEC_MISSING" {
  echo "validator: SPEC_MISSING — no impl file" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PASS|FAIL|SPEC_MISSING")
  [[ "$result" == "SPEC_MISSING" ]]
}

@test "parse_marker detects SPEC_GAP_RESOLVED" {
  echo "architect: SPEC_GAP_RESOLVED — impl updated" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "SPEC_GAP_RESOLVED|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")
  [[ "$result" == "SPEC_GAP_RESOLVED" ]]
}

@test "parse_marker rejects partial word PASSING != PASS" {
  echo "PASSING all checks" > "$TEST_TMP/out.txt"
  result=$(parse_marker "$TEST_TMP/out.txt" "PASS|FAIL")
  [[ "$result" == "UNKNOWN" ]]
}

# === kill_check ===

@test "kill_check passes when no kill file" {
  rm -f "${STATE_DIR}/${PREFIX}_harness_kill"
  run bash -c "source '${HARNESS_DIR}/utils.sh'; PREFIX='${PREFIX}'; kill_check; echo 'survived'"
  [[ "$output" == *"survived"* ]]
}

@test "kill_check exits with HARNESS_KILLED when kill file exists" {
  touch "${STATE_DIR}/${PREFIX}_harness_kill"
  touch "${STATE_DIR}/${PREFIX}_harness_active"
  run bash -c "source '${HARNESS_DIR}/utils.sh'; PREFIX='${PREFIX}'; kill_check"
  [[ "$output" == *"HARNESS_KILLED"* ]]
  [[ $status -eq 0 ]]
  [[ ! -f "${STATE_DIR}/${PREFIX}_harness_kill" ]]
}

# === collect_changed_files ===

@test "collect_changed_files returns 1 when no changes" {
  create_test_commit "initial.txt"
  run collect_changed_files
  [[ $status -eq 1 ]]
}

@test "collect_changed_files returns 0 and filenames when changes exist" {
  create_test_commit "initial.txt"
  echo "changed" > "${GIT_WORK_TREE}/initial.txt"
  git -C "${GIT_WORK_TREE}" add initial.txt
  run collect_changed_files
  [[ $status -eq 0 ]]
  [[ "$output" == *"initial.txt"* ]]
}

# === detect_depth ===

@test "detect_depth: frontmatter depth: std -> std" {
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  local impl="$TEST_TMP/impl_std.md"
  printf '---\ndepth: std\nissue: 1\n---\n# Test\n- item (TEST)\n' > "$impl"
  result=$(detect_depth "$impl")
  [[ "$result" == "std" ]]
}

@test "detect_depth: frontmatter depth: simple -> simple" {
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  local impl="$TEST_TMP/impl_simple.md"
  printf '---\ndepth: simple\nissue: 1\nreason: text change\n---\n# Test\n' > "$impl"
  result=$(detect_depth "$impl")
  [[ "$result" == "simple" ]]
}

@test "detect_depth: frontmatter depth: deep -> deep" {
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  local impl="$TEST_TMP/impl_deep.md"
  printf '---\ndepth: deep\nissue: 1\n---\n# Test\n- item (BROWSER:DOM)\n' > "$impl"
  result=$(detect_depth "$impl")
  [[ "$result" == "deep" ]]
}

@test "detect_depth: missing impl -> std" {
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  result=$(detect_depth "/nonexistent/path.md")
  [[ "$result" == "std" ]]
}

@test "detect_depth: no frontmatter -> std" {
  detect_depth() {
    local impl="$1"
    if [[ -z "$impl" || ! -f "$impl" ]]; then echo "std"; return; fi
    local depth_val
    depth_val=$(sed -n '/^---$/,/^---$/{ /^depth:/{ s/^depth:[[:space:]]*//; s/[[:space:]]*#.*//; p; q; } }' "$impl" 2>/dev/null || echo "")
    case "$depth_val" in simple|std|deep) echo "$depth_val" ;; *) echo "std" ;; esac
  }
  local impl="$TEST_TMP/impl_nofm.md"
  printf '# Test\n- item (TEST)\n' > "$impl"
  result=$(detect_depth "$impl")
  [[ "$result" == "std" ]]
}

# === generate_commit_msg ===

@test "generate_commit_msg extracts impl name" {
  create_test_commit "dummy.txt"
  echo "change" >> "${GIT_WORK_TREE}/dummy.txt"
  git -C "${GIT_WORK_TREE}" add dummy.txt
  IMPL_FILE="docs/impl/01-test-module.md"
  ISSUE_NUM="42"
  msg=$(generate_commit_msg)
  [[ "$msg" == *"01-test-module"* ]]
  [[ "$msg" == *"#42"* ]]
}

@test "generate_commit_msg uses bugfix prefix when no impl" {
  create_test_commit "dummy.txt"
  echo "change" >> "${GIT_WORK_TREE}/dummy.txt"
  git -C "${GIT_WORK_TREE}" add dummy.txt
  IMPL_FILE=""
  ISSUE_NUM="57"
  msg=$(generate_commit_msg)
  [[ "$msg" == *"bugfix-57"* ]]
}

# === write_run_end ===

@test "write_run_end converts unknown to HARNESS_CRASH" {
  mkdir -p "$TEST_TMP/logs"
  RUN_LOG="$TEST_TMP/logs/test.jsonl"
  _HARNESS_RUN_START=$(date +%s)
  echo '{"event":"run_start"}' > "$RUN_LOG"
  HARNESS_RESULT="unknown"
  write_run_end
  run grep -c "HARNESS_CRASH" "$RUN_LOG"
  [[ "$output" -ge 1 ]]
}

@test "write_run_end records HARNESS_DONE correctly" {
  mkdir -p "$TEST_TMP/logs"
  RUN_LOG="$TEST_TMP/logs/test.jsonl"
  _HARNESS_RUN_START=$(date +%s)
  echo '{"event":"run_start"}' > "$RUN_LOG"
  HARNESS_RESULT="HARNESS_DONE"
  write_run_end
  run grep -c "HARNESS_DONE" "$RUN_LOG"
  [[ "$output" -ge 1 ]]
}
