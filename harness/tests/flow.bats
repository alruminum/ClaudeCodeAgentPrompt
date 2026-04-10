#!/usr/bin/env bats
# harness/tests/flow.bats — loop flow + marker + safety tests

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# === bugfix routing ===

@test "bugfix: KNOWN_ISSUE -> immediate escalation (exit 1)" {
  source "${HARNESS_DIR}/bugfix.sh"
  echo "KNOWN_ISSUE — cannot determine root cause" > "/tmp/${PREFIX}_qa_out.txt"
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"
    _bugfix_route 2>/dev/null
  '
  [[ "$output" == *"KNOWN_ISSUE"* ]]
  [[ $status -eq 1 ]]
}

@test "bugfix: SCOPE_ESCALATE -> new feature (exit 1)" {
  source "${HARNESS_DIR}/bugfix.sh"
  echo "SCOPE_ESCALATE: no related modules" > "/tmp/${PREFIX}_qa_out.txt"
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"
    _bugfix_route 2>/dev/null
  '
  [[ "$output" == *"SCOPE_ESCALATE"* ]]
  [[ $status -eq 1 ]]
}

@test "bugfix: DESIGN_ISSUE -> design loop handoff (exit 0)" {
  echo "DESIGN_ISSUE" > "/tmp/${PREFIX}_qa_out.txt"
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/bugfix.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"
    _bugfix_route 2>/dev/null
  '
  [[ "$output" == *"DESIGN_ISSUE"* ]]
  [[ $status -eq 0 ]]
}

@test "bugfix: SPEC_ISSUE MODULE_PLAN call has no bugfix prefix" {
  run grep -A3 'MODULE_PLAN' "${HARNESS_DIR}/bugfix.sh"
  [[ "$output" != *"버그픽스"* ]]
  [[ $status -eq 0 ]]
}

@test "bugfix: SPEC_ISSUE MODULE_PLAN call passes mode=spec_issue" {
  run grep -A5 'MODULE_PLAN' "${HARNESS_DIR}/bugfix.sh"
  [[ "$output" == *"spec_issue"* ]]
  [[ $status -eq 0 ]]
}

@test "bugfix: SEVERITY HIGH forces depth=std" {
  source "${HARNESS_DIR}/bugfix.sh"
  cat > "/tmp/${PREFIX}_qa_out.txt" <<'EOF'
---QA_SUMMARY---
TYPE: FUNCTIONAL_BUG
SEVERITY: HIGH
AFFECTED_FILES: 1
ROUTING: engineer_direct
---END_QA_SUMMARY---
EOF
  result=$(detect_bugfix_depth "/tmp/${PREFIX}_qa_out.txt")
  [[ "$result" == "std" ]]
}

@test "bugfix: FUNCTIONAL_BUG + low affected -> fast" {
  source "${HARNESS_DIR}/bugfix.sh"
  cat > "/tmp/${PREFIX}_qa_out.txt" <<'EOF'
---QA_SUMMARY---
TYPE: FUNCTIONAL_BUG
SEVERITY: LOW
AFFECTED_FILES: 1
ROUTING: engineer_direct
---END_QA_SUMMARY---
EOF
  result=$(detect_bugfix_depth "/tmp/${PREFIX}_qa_out.txt")
  [[ "$result" == "fast" ]]
}

# === design flow ===

@test "design: PICK -> DESIGN_DONE (exit 0)" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/design.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="test"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      if [[ "$agent" == "designer" ]]; then echo "variant A, B, C" > "$out"
      elif [[ "$agent" == "design-critic" ]]; then echo "PICK — variant A" > "$out"; fi
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_design
  '
  [[ "$output" == *"DESIGN_DONE"* ]]
  [[ $status -eq 0 ]]
  [[ -f "/tmp/${PREFIX}_design_critic_passed" ]]
}

@test "design: ESCALATE -> user direct pick (exit 0)" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/design.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="test"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      if [[ "$agent" == "designer" ]]; then echo "variant A, B, C" > "$out"
      elif [[ "$agent" == "design-critic" ]]; then echo "ESCALATE — all rejected" > "$out"; fi
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_design
  '
  [[ "$output" == *"DESIGN_DONE"* ]]
  [[ "$output" == *"ESCALATE"* ]]
  [[ $status -eq 0 ]]
}

@test "design: 3x ITERATE -> DESIGN_LOOP_ESCALATE (exit 0)" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/design.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="test"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      if [[ "$agent" == "designer" ]]; then echo "variant A, B, C" > "$out"
      elif [[ "$agent" == "design-critic" ]]; then echo "ITERATE — needs improvement" > "$out"; fi
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_design
  '
  [[ "$output" == *"DESIGN_LOOP_ESCALATE"* ]]
  [[ $status -eq 0 ]]
}

# === plan flow ===

@test "plan: full flow -> PLAN_VALIDATION_PASS (exit 0)" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/plan.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="test"
    GIT_WORK_TREE="'"${GIT_WORK_TREE}"'"
    mkdir -p "${GIT_WORK_TREE}/docs/impl"
    echo "# impl" > "${GIT_WORK_TREE}/docs/impl/01-test-module.md"
    cd "${GIT_WORK_TREE}"
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      case "$agent" in
        product-planner) echo "PRODUCT_PLAN_READY" > "$out" ;;
        architect) echo "SYSTEM_DESIGN_READY"; echo "docs/impl/01-test-module.md" > "$out" ;;
        validator) echo "PASS" > "$out" ;;
      esac
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_plan
  '
  [[ "$output" == *"PLAN_VALIDATION_PASS"* ]]
  [[ $status -eq 0 ]]
}

@test "plan: PV fail -> PLAN_VALIDATION_ESCALATE (exit 1)" {
  run bash -c '
    source "'"${HARNESS_DIR}/utils.sh"'"
    source "'"${HARNESS_DIR}/plan.sh"'"
    PREFIX="'"$PREFIX"'"; ISSUE_NUM="999"; CONTEXT="test"
    GIT_WORK_TREE="'"${GIT_WORK_TREE}"'"
    mkdir -p "${GIT_WORK_TREE}/docs/impl"
    echo "# impl" > "${GIT_WORK_TREE}/docs/impl/01-test-module.md"
    cd "${GIT_WORK_TREE}"
    validator_count=0
    _agent_call() {
      local agent="$1" out="$4"
      echo "0" > "${out%.txt}_cost.txt"
      case "$agent" in
        product-planner) echo "PRODUCT_PLAN_READY" > "$out" ;;
        architect) echo "docs/impl/01-test-module.md" > "$out" ;;
        validator) echo "FAIL — missing specs" > "$out" ;;
      esac
    }
    rotate_harness_logs() { true; }
    kill_check() { true; }
    run_plan
  '
  [[ "$output" == *"PLAN_VALIDATION_ESCALATE"* ]]
  [[ $status -eq 1 ]]
}

# === marker consistency ===

@test "markers: all HARNESS_RESULT values are in allowed list" {
  local allowed="HARNESS_DONE IMPLEMENTATION_ESCALATE HARNESS_KILLED HARNESS_BUDGET_EXCEEDED"
  allowed="$allowed HARNESS_CRASH MERGE_CONFLICT_ESCALATE"
  allowed="$allowed PLAN_VALIDATION_PASS PLAN_VALIDATION_ESCALATE"
  allowed="$allowed DESIGN_DONE DESIGN_LOOP_ESCALATE DESIGN_REVIEW_ESCALATE DESIGN_ESCALATE"
  allowed="$allowed UI_DESIGN_REQUIRED SPEC_GAP_ESCALATE"
  allowed="$allowed KNOWN_ISSUE SCOPE_ESCALATE BACKLOG DESIGN_ISSUE"
  allowed="$allowed PRODUCT_PLANNER_ESCALATION_NEEDED TECH_CONSTRAINT_CONFLICT"
  allowed="$allowed unknown"

  local markers
  markers=$(grep -ohE 'HARNESS_RESULT="[A-Z_]+"' "${HARNESS_DIR}"/*.sh \
    | sed 's/HARNESS_RESULT="//; s/"//' | sort -u)

  local failures=""
  while IFS= read -r m; do
    [[ -z "$m" ]] && continue
    if ! echo "$allowed" | grep -qw "$m"; then
      failures="${failures}  unregistered marker: $m\n"
    fi
  done <<< "$markers"

  [[ -z "$failures" ]] || { echo -e "$failures"; false; }
}

@test "markers: deprecated VALIDATION_ESCALATE not used in scripts" {
  run grep -l 'HARNESS_RESULT="VALIDATION_ESCALATE"' "${HARNESS_DIR}"/*.sh
  [[ $status -ne 0 ]]
}

@test "markers: deprecated REVIEW_LOOP_ESCALATE not used in scripts" {
  run grep -l 'HARNESS_RESULT="REVIEW_LOOP_ESCALATE"' "${HARNESS_DIR}"/*.sh
  [[ $status -ne 0 ]]
}

@test "markers: deprecated PLAN_DONE not used in scripts" {
  run grep -l 'HARNESS_RESULT="PLAN_DONE"' "${HARNESS_DIR}"/*.sh
  [[ $status -ne 0 ]]
}

# === safety: no infinite loops ===

@test "safety: impl attempt counter MAX=3" {
  run grep 'MAX=3' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
  run grep 'while.*attempt.*lt.*MAX' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
}

@test "safety: SPEC_GAP counter MAX_SPEC_GAP=2" {
  run grep 'MAX_SPEC_GAP=2' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
  run grep 'spec_gap_count.*gt.*MAX_SPEC_GAP' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
}

@test "safety: bugfix MAX_HOTFIX=3" {
  run grep 'MAX_HOTFIX=3' "${HARNESS_DIR}/bugfix.sh"
  [[ $status -eq 0 ]]
}

@test "safety: design MAX=3" {
  run grep -E 'local MAX=3' "${HARNESS_DIR}/design.sh"
  [[ $status -eq 0 ]]
}

@test "safety: budget check exists with limit" {
  run grep 'MAX_TOTAL_COST=10' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
  run grep 'HARNESS_BUDGET_EXCEEDED' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
}

@test "safety: SPEC_GAP_FOUND detection exists in impl-process" {
  run grep 'SPEC_GAP_FOUND' "${HARNESS_DIR}/impl-process.sh"
  [[ $status -eq 0 ]]
}

@test "safety: IMPLEMENTATION_ESCALATE in impl-process and bugfix" {
  run grep -l 'IMPLEMENTATION_ESCALATE' "${HARNESS_DIR}/impl-process.sh" "${HARNESS_DIR}/bugfix.sh"
  [[ $(echo "$output" | wc -l) -ge 2 ]]
}

@test "safety: MERGE_CONFLICT_ESCALATE exists" {
  run grep -rl 'MERGE_CONFLICT_ESCALATE' "${HARNESS_DIR}/"
  [[ $status -eq 0 ]]
}
