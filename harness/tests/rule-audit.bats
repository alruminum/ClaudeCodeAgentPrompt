#!/usr/bin/env bats
# harness/tests/rule-audit.bats
# RULE_INDEX.md 일관성 자동 검증:
#   1. 각 rule의 script grep이 실제 스크립트 파일에 존재하는지 확인
#   2. 각 rule의 커버 테스트 이름이 실제 *.bats 파일에 존재하는지 확인
#   3. RULE_INDEX.md 자체가 최소 7개 이상의 규칙을 포함하는지 확인

RULE_INDEX="${BATS_TEST_DIRNAME}/../RULE_INDEX.md"
HARNESS_DIR="${BATS_TEST_DIRNAME}/.."
TESTS_DIR="${BATS_TEST_DIRNAME}"

# python3으로 RULE_INDEX.md 테이블 파싱 → TSV 출력 (ID\t설명\tgrep\t파일\t테스트)
_parse_rules() {
  if command -v python3 &>/dev/null; then
    python3 - "$RULE_INDEX" <<'PYEOF'
import sys, re

try:
    with open(sys.argv[1]) as f:
        lines = f.readlines()
except Exception as e:
    print(f"ERROR: cannot read {sys.argv[1]}: {e}", file=sys.stderr)
    sys.exit(1)

rules = []
for line in lines:
    line = line.strip()
    if not line.startswith('|'):
        continue
    cells = [c.strip() for c in line.split('|')[1:-1]]
    if len(cells) >= 5 and re.match(r'^R\d+$', cells[0]):
        rules.append(cells)

for r in rules:
    print('\t'.join(r[:5]))
PYEOF
  else
    # python3 없으면 awk 폴백 (ID가 R로 시작하는 행만 파싱)
    awk -F'|' '
      /^\|[[:space:]]*R[0-9]/ {
        for(i=1; i<=NF; i++) gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)
        if ($2 ~ /^R[0-9]+$/) print $2 "\t" $3 "\t" $4 "\t" $5 "\t" $6
      }
    ' "$RULE_INDEX"
  fi
}

@test "RULE_INDEX.md exists" {
  [ -f "$RULE_INDEX" ]
}

@test "RULE_INDEX.md has at least 7 rules" {
  local count
  count=$(_parse_rules | wc -l | tr -d ' ')
  if [ "$count" -lt 7 ]; then
    echo "rule count: $count (expected >= 7)"
    false
  fi
}

@test "each rule's script grep exists in its script file" {
  local failed=0
  local output_lines=""

  while IFS=$'\t' read -r id desc grep_pat script_file cover_test; do
    local script_path="${HARNESS_DIR}/${script_file}"
    if [[ ! -f "$script_path" ]]; then
      output_lines="${output_lines}FAIL[${id}]: script file not found: ${script_file}\n"
      failed=$((failed + 1))
      continue
    fi
    if ! grep -qE "$grep_pat" "$script_path" 2>/dev/null; then
      output_lines="${output_lines}FAIL[${id}]: pattern not found: '${grep_pat}' in ${script_file}\n"
      failed=$((failed + 1))
    fi
  done < <(_parse_rules)

  if [ "$failed" -gt 0 ]; then
    printf "%b" "$output_lines"
    false
  fi
}

@test "each rule's cover test exists in bats files" {
  local failed=0
  local output_lines=""

  while IFS=$'\t' read -r id desc grep_pat script_file cover_test; do
    if ! grep -rqF "$cover_test" "${TESTS_DIR}"/*.bats 2>/dev/null; then
      output_lines="${output_lines}FAIL[${id}]: cover test not found: '${cover_test}'\n"
      failed=$((failed + 1))
    fi
  done < <(_parse_rules)

  if [ "$failed" -gt 0 ]; then
    printf "%b" "$output_lines"
    false
  fi
}
