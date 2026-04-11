#!/usr/bin/env bats
# harness/tests/hooks.bats - 훅 로직 검증 (S70)

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
}

teardown() {
  common_teardown
}

# ═══════════════════════════════════════════════════════════════════════
# orch-rules-first.py: HARNESS_INFRA_PATTERNS 매칭 검증
# ═══════════════════════════════════════════════════════════════════════

@test "orch-rules-first: matches harness/executor.sh" {
  run python3 -c '
import re
patterns = [
    r"harness/executor\.sh",
    r"harness/impl\.sh",
    r"harness/impl_std\.sh",
    r"harness/design\.sh",
    r"harness/bugfix\.sh",
    r"harness/plan\.sh",
    r"harness/utils\.sh",
    r"setup-harness\.sh",
    r"setup-agents\.sh",
    r"hooks/[^/]+\.py$",
]
test_files = [
    ".claude/harness/executor.sh",
    ".claude/harness/impl.sh",
    ".claude/harness/impl_simple.sh",
    ".claude/harness/impl_std.sh",
    ".claude/harness/design.sh",
    ".claude/harness/plan.sh",
    ".claude/harness/utils.sh",
    "setup-harness.sh",
    "setup-agents.sh",
    "hooks/agent-boundary.py",
    "hooks/commit-gate.py",
    "hooks/harness-router.py",
    "hooks/orch-rules-first.py",
]
for f in test_files:
    matched = any(re.search(p, f) for p in patterns)
    if not matched:
        print(f"MISS: {f}")
        exit(1)
print("ALL_MATCH")
'
  [[ "$output" == "ALL_MATCH" ]]
}

@test "orch-rules-first: does NOT match non-infra files" {
  run python3 -c '
import re
patterns = [
    r"harness/executor\.sh",
    r"harness/impl\.sh",
    r"harness/impl_std\.sh",
    r"harness/design\.sh",
    r"harness/bugfix\.sh",
    r"harness/plan\.sh",
    r"harness/utils\.sh",
    r"setup-harness\.sh",
    r"setup-agents\.sh",
    r"hooks/[^/]+\.py$",
]
safe_files = [
    "src/main.ts",
    "docs/architecture.md",
    "backlog.md",
    "CLAUDE.md",
    "prd.md",
    ".claude/settings.json",
    ".claude/harness.config.json",
]
for f in safe_files:
    matched = any(re.search(p, f) for p in patterns)
    if matched:
        print(f"FALSE_POSITIVE: {f}")
        exit(1)
print("ALL_SAFE")
'
  [[ "$output" == "ALL_SAFE" ]]
}

@test "orch-rules-first: old flat names do NOT match" {
  run python3 -c '
import re
patterns = [
    r"harness/executor\.sh",
    r"harness/impl\.sh",
    r"harness/impl_std\.sh",
    r"harness/design\.sh",
    r"harness/bugfix\.sh",
    r"harness/plan\.sh",
    r"harness/utils\.sh",
    r"setup-harness\.sh",
    r"setup-agents\.sh",
    r"hooks/[^/]+\.py$",
]
old_names = [
    "harness-executor.sh",
    "harness-impl-plan.sh",
    "harness-impl_std.sh",
    "harness-design.sh",
    "harness-plan.sh",
]
for f in old_names:
    matched = any(re.search(p, f) for p in patterns)
    if matched:
        print(f"OLD_NAME_MATCHED: {f}")
        exit(1)
print("OLD_NAMES_REJECTED")
'
  [[ "$output" == "OLD_NAMES_REJECTED" ]]
}

# ═══════════════════════════════════════════════════════════════════════
# harness-drift-check.py: DRIFT_MAP 완결성 검증
# ═══════════════════════════════════════════════════════════════════════

@test "drift-check: all harness scripts covered in orchestration-rules mapping" {
  run python3 -c '
import sys
sys.path.insert(0, "'${BATS_TEST_DIRNAME}'/../..")
# Read DRIFT_MAP from the actual file
import ast, re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/harness-drift-check.py") as f:
    content = f.read()
# Extract DRIFT_MAP dict
m = re.search(r"DRIFT_MAP\s*=\s*(\{.*?\})", content, re.DOTALL)
drift_map = eval(m.group(1))

orch_scripts = drift_map.get("orchestration-rules.md", [])
required = [
    "harness/executor.sh",
    "harness/impl_simple.sh",
    "harness/impl_std.sh",
    "harness/impl.sh",
    "harness/design.sh",
    "harness/plan.sh",
    "harness/utils.sh",
]
missing = [s for s in required if s not in orch_scripts]
if missing:
    print(f"MISSING: {missing}")
    exit(1)
print("ORCH_SCRIPTS_COMPLETE")
'
  [[ "$output" == "ORCH_SCRIPTS_COMPLETE" ]]
}

@test "drift-check: all agent files have script mappings" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/harness-drift-check.py") as f:
    content = f.read()
m = re.search(r"DRIFT_MAP\s*=\s*(\{.*?\})", content, re.DOTALL)
drift_map = eval(m.group(1))

required_agents = [
    "agents/qa.md",
    "agents/architect.md",
    "agents/validator.md",
    "agents/engineer.md",
    "agents/test-engineer.md",
    "agents/designer.md",
    "agents/design-critic.md",
    "agents/product-planner.md",
    "agents/pr-reviewer.md",
    "agents/security-reviewer.md",
]
missing = [a for a in required_agents if a not in drift_map]
if missing:
    print(f"MISSING_AGENTS: {missing}")
    exit(1)
print("ALL_AGENTS_MAPPED")
'
  [[ "$output" == "ALL_AGENTS_MAPPED" ]]
}

@test "drift-check: designer maps to design.sh" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/harness-drift-check.py") as f:
    content = f.read()
m = re.search(r"DRIFT_MAP\s*=\s*(\{.*?\})", content, re.DOTALL)
drift_map = eval(m.group(1))
scripts = drift_map.get("agents/designer.md", [])
assert "harness/design.sh" in scripts, f"designer → {scripts}"
print("OK")
'
  [[ "$output" == "OK" ]]
}

@test "drift-check: product-planner maps to plan.sh" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/harness-drift-check.py") as f:
    content = f.read()
m = re.search(r"DRIFT_MAP\s*=\s*(\{.*?\})", content, re.DOTALL)
drift_map = eval(m.group(1))
scripts = drift_map.get("agents/product-planner.md", [])
assert "harness/plan.sh" in scripts, f"product-planner → {scripts}"
print("OK")
'
  [[ "$output" == "OK" ]]
}

# ═══════════════════════════════════════════════════════════════════════
# agent-boundary.py: ALLOW_MATRIX 완결성 검증
# ═══════════════════════════════════════════════════════════════════════

@test "agent-boundary: all 10 agents in ALLOW_MATRIX" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/agent-boundary.py") as f:
    content = f.read()
m = re.search(r"ALLOW_MATRIX\s*=\s*(\{.*?\})", content, re.DOTALL)
matrix = eval(m.group(1))
required = [
    "engineer", "architect", "designer", "test-engineer",
    "product-planner", "validator", "design-critic",
    "pr-reviewer", "qa", "security-reviewer",
]
missing = [a for a in required if a not in matrix]
if missing:
    print(f"MISSING: {missing}")
    exit(1)
print("ALL_AGENTS_IN_MATRIX")
'
  [[ "$output" == "ALL_AGENTS_IN_MATRIX" ]]
}

@test "agent-boundary: ReadOnly agents have empty allow list" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/agent-boundary.py") as f:
    content = f.read()
m = re.search(r"ALLOW_MATRIX\s*=\s*(\{.*?\})", content, re.DOTALL)
matrix = eval(m.group(1))
readonly = ["validator", "design-critic", "pr-reviewer", "qa", "security-reviewer"]
for agent in readonly:
    if matrix.get(agent) != []:
        print(f"NOT_READONLY: {agent} = {matrix[agent]}")
        exit(1)
print("READONLY_OK")
'
  [[ "$output" == "READONLY_OK" ]]
}

@test "agent-boundary: engineer allows src/**" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/agent-boundary.py") as f:
    content = f.read()
m = re.search(r"ALLOW_MATRIX\s*=\s*(\{.*?\})", content, re.DOTALL)
matrix = eval(m.group(1))
patterns = matrix.get("engineer", [])
test_paths = ["src/main.ts", "src/__tests__/main.test.ts"]
for tp in test_paths:
    matched = any(re.search(p, tp) for p in patterns)
    if not matched:
        print(f"MISS: {tp}")
        exit(1)
print("ENGINEER_SRC_OK")
'
  [[ "$output" == "ENGINEER_SRC_OK" ]]
}

@test "agent-boundary: engineer blocked from docs/**" {
  run python3 -c '
import re
with open("'${BATS_TEST_DIRNAME}'/../../hooks/agent-boundary.py") as f:
    content = f.read()
m = re.search(r"ALLOW_MATRIX\s*=\s*(\{.*?\})", content, re.DOTALL)
matrix = eval(m.group(1))
patterns = matrix.get("engineer", [])
blocked_paths = ["docs/architecture.md", "docs/impl/01-foo.md", "prd.md"]
for bp in blocked_paths:
    matched = any(re.search(p, bp) for p in patterns)
    if matched:
        print(f"FALSE_ALLOW: {bp}")
        exit(1)
print("ENGINEER_DOCS_BLOCKED")
'
  [[ "$output" == "ENGINEER_DOCS_BLOCKED" ]]
}

# ═══════════════════════════════════════════════════════════════════════
# file-ownership-gate.py: 데드코드 삭제 확인
# ═══════════════════════════════════════════════════════════════════════

@test "file-ownership-gate.py does not exist (dead code removed)" {
  [[ ! -f "${BATS_TEST_DIRNAME}/../../hooks/file-ownership-gate.py" ]]
}

# ═══════════════════════════════════════════════════════════════════════
# commit-gate.py: feature branch 자유 커밋 검증
# ═══════════════════════════════════════════════════════════════════════

@test "commit-gate: feature branch bypasses LGTM check" {
  # Verify the code path: feature branch → sys.exit(0)
  run grep -A2 'not in.*main.*master' "${BATS_TEST_DIRNAME}/../../hooks/commit-gate.py"
  [[ "$output" == *"sys.exit(0)"* ]]
}

# ═══════════════════════════════════════════════════════════════════════
# agent-gate.py: light_plan_ready 폴백 검증
# ═══════════════════════════════════════════════════════════════════════

@test "agent-gate: engineer allows light_plan_ready as alternative to plan_validation_passed" {
  run grep -A2 'light_plan_ready' "${BATS_TEST_DIRNAME}/../../hooks/agent-gate.py"
  [[ "$output" == *"light_plan_ready"* ]]
}

# ═══════════════════════════════════════════════════════════════════════
# settings.json: 모든 훅이 올바르게 등록됐는지 검증
# ═══════════════════════════════════════════════════════════════════════

@test "settings.json: all hook python files are registered" {
  run python3 -c '
import json
with open("'${BATS_TEST_DIRNAME}'/../../settings.json") as f:
    settings = json.load(f)
hooks = settings.get("hooks", {})

# 등록된 모든 python 훅 파일 수집
registered = set()
for event_hooks in hooks.values():
    for group in event_hooks:
        for h in group.get("hooks", []):
            cmd = h.get("command", "")
            import re
            m = re.search(r"hooks/([^/ ]+\.py)", cmd)
            if m:
                registered.add(m.group(1))

expected = {
    "harness-router.py",
    "harness-session-start.py",
    "harness-settings-watcher.py",
    "post-agent-flags.py",
    "post-commit-cleanup.py",
    "orch-rules-first.py",
    "agent-boundary.py",
    "harness-drift-check.py",
    "commit-gate.py",
    "agent-gate.py",
}
missing = expected - registered
if missing:
    print(f"NOT_REGISTERED: {missing}")
    exit(1)
print("ALL_REGISTERED")
'
  [[ "$output" == "ALL_REGISTERED" ]]
}

@test "settings.json: file-ownership-gate.py is NOT registered" {
  run python3 -c '
import json
with open("'${BATS_TEST_DIRNAME}'/../../settings.json") as f:
    content = f.read()
if "file-ownership-gate" in content:
    print("STILL_REGISTERED")
    exit(1)
print("NOT_REGISTERED_OK")
'
  [[ "$output" == "NOT_REGISTERED_OK" ]]
}
