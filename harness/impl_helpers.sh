#!/bin/bash
# ~/.claude/harness/impl_helpers.sh
# impl_simple/std/deep.sh 공유 헬퍼 함수 모음
# 기능 변경 없이 순수 추출됨
#
# 이 파일은 단독 실행 불가. impl_simple/std/deep.sh에서 source로 사용:
#   source "${HOME}/.claude/harness/impl_helpers.sh"
#
# 전제 조건: 호출 스크립트에서 아래 변수가 설정돼 있어야 함:
#   IMPL_FILE, ISSUE_NUM, PREFIX, DEPTH, CONSTRAINTS, RUN_LOG

# shellcheck source=/dev/null
source "${HOME}/.claude/harness/utils.sh"

# ── Phase 0: constraints 로드 ────────────────────────────────────────────
_load_constraints() {
  local MEM_GLOBAL="${HOME}/.claude/harness-memory.md"
  local MEM_LOCAL=".claude/harness-memory.md"

  if [[ ! -f "$MEM_LOCAL" ]]; then
    mkdir -p .claude
    printf "# Harness Memory\n\n## impl 패턴\n\n## design 패턴\n\n## bugfix 패턴\n\n## Auto-Promoted Rules\n\n## Known Failure Patterns\n\n## Success Patterns\n" > "$MEM_LOCAL"
  else
    for sec in "impl 패턴" "design 패턴" "bugfix 패턴"; do
      grep -qF "## ${sec}" "$MEM_LOCAL" 2>/dev/null || printf "\n## %s\n" "$sec" >> "$MEM_LOCAL"
    done
  fi

  CONSTRAINTS=""
  for mf in "$MEM_GLOBAL" "$MEM_LOCAL"; do
    if [[ -f "$mf" ]]; then
      promoted=$(sed -n '/^## Auto-Promoted Rules/,/^##/p' "$mf" 2>/dev/null | grep "^- PROMOTED:" | head -10 || true)
      [[ -n "$promoted" ]] && CONSTRAINTS="${CONSTRAINTS}
[AUTO-PROMOTED RULES — 반복 실패 패턴, 반드시 회피]:
${promoted}"
    fi
  done
  [[ -f "$MEM_GLOBAL" ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_GLOBAL")"
  [[ -f "$MEM_LOCAL"  ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_LOCAL")"
  if [[ -f "CLAUDE.md" ]]; then
    CONSTRAINTS="${CONSTRAINTS}
$(sed -n '/^## 개발 명령어/,/^---/p; /^## 작업 순서/,/^---/p; /^## Git/,/^---/p' CLAUDE.md | head -c 10000)"
  fi
}

# ── 헬퍼 함수 ────────────────────────────────────────────────────────────

_save_impl_meta() {
  local adir="$1" anum="$2" res="$3" ftype="${4:-}" hints="${5:-}"
  local chg; chg=$(git diff HEAD~1 --name-only 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//' || echo "")
  local ftests=""
  if [[ -f "${adir}/test-results.log" ]]; then
    ftests=$(grep -E "✗| FAIL |× " "${adir}/test-results.log" 2>/dev/null | head -3 | tr '\n' ',' | cut -c1-200 || echo "")
  fi
  local err1=""
  if [[ -f "${adir}/engineer.log" ]]; then
    err1=$(head -1 "${adir}/engineer.log" | cut -c1-150 || echo "")
  fi
  write_attempt_meta "${adir}/meta.json" "$anum" "impl" "$DEPTH" "$res" \
    "$ftype" "$ftests" "$chg" "engineer,test-engineer,validator,pr-reviewer" "$err1" "$hints"
}

append_failure() {
  local type="$1" err="$2"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  local err_1line; err_1line=$(echo "$err" | head -1 | cut -c1-100)
  local MEM_LOCAL=".claude/harness-memory.md"

  local tmp_entry; tmp_entry=$(mktemp)
  printf -- "- %s | %s | %s | %s\n" \
    "$date_str" "$impl_name" "$type" "$err_1line" \
    > "$tmp_entry"
  cat "$tmp_entry" >> "$MEM_LOCAL"
  rm -f "$tmp_entry"

  local pattern_key="${impl_name}|${type}"
  local count; count=$(grep -Fc "$pattern_key" "$MEM_LOCAL" 2>/dev/null) || count=0
  if [[ $count -ge 3 ]]; then
    if ! grep -Fq "## Auto-Promoted Rules" "$MEM_LOCAL" 2>/dev/null; then
      printf "\n## Auto-Promoted Rules\n\n" >> "$MEM_LOCAL"
    fi
    if ! grep -Fq "PROMOTED: $pattern_key" "$MEM_LOCAL" 2>/dev/null; then
      local tmp_promo; tmp_promo=$(mktemp)
      printf -- "- PROMOTED: %s | %s회 반복 | %s | MUST NOT: %s\n" \
        "$pattern_key" "$count" "$date_str" "$err_1line" \
        > "$tmp_promo"
      cat "$tmp_promo" >> "$MEM_LOCAL"
      rm -f "$tmp_promo"
      echo "[HARNESS] 실패 패턴 자동 프로모션: ${pattern_key} (${count}회)"
    fi
  fi

  local candidate_file="/tmp/${PREFIX}_memory_candidate.md"
  if ! grep -Fq "$pattern_key" "$candidate_file" 2>/dev/null; then
    cat >> "$candidate_file" <<CANDIDATE
---
date: $date_str
impl: $impl_name
type: $type
pattern: $err_1line
suggestion: "impl 파일에 관련 제약 추가 또는 에이전트 지시 보강 검토"
CANDIDATE
  fi
}

rollback_attempt() {
  local attempt_num="$1"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"rollback","attempt":%d,"method":"keep-on-branch","t":%d}\n' \
    "$attempt_num" "$(date +%s)" >> "$RUN_LOG"
  hlog "ROLLBACK attempt=${attempt_num} — changes kept on feature branch"
}

check_agent_output() {
  local agent_name="$1" out_file="$2"
  if [[ ! -s "$out_file" ]]; then
    hlog "WARNING: ${agent_name} 출력 파일 없음 또는 비어있음 — agent 호출 실패"
    echo "[HARNESS] WARNING: ${agent_name} agent가 출력을 생성하지 못함"
    return 1
  fi
  return 0
}

append_success() {
  local attempt_num="$1"
  local MEM_LOCAL=".claude/harness-memory.md"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  local tmp_entry; tmp_entry=$(mktemp)
  printf -- "- %s | %s | success | attempt %s\n" \
    "$date_str" "$impl_name" "$attempt_num" \
    > "$tmp_entry"
  cat "$tmp_entry" >> "$MEM_LOCAL"
  rm -f "$tmp_entry"
}

run_automated_checks() {
  local impl_file="$1"
  local out_file="/tmp/${PREFIX}_autocheck_fail.txt"
  rm -f "$out_file"

  if ! git status --short | grep -qE "^ M|^M |^A "; then
    echo "no_changes: engineer가 아무 파일도 수정하지 않음" > "$out_file"
    echo "AUTOMATED_CHECKS_FAIL: no_changes"
    return 1
  fi

  if git show HEAD:package.json >/dev/null 2>&1; then
    if git diff HEAD -- package.json 2>/dev/null | grep -qE '^\+\s+"[a-z@]'; then
      echo "new_deps: package.json에 새 의존성이 추가됨 (사전 승인 필요)" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: new_deps"
      return 1
    fi
  fi

  local protected_files
  protected_files=$(grep -oE '\(PROTECTED\)[[:space:]]+[^[:space:]]+' "$impl_file" 2>/dev/null \
    | awk '{print $NF}' || true)
  while IFS= read -r pf; do
    [[ -z "$pf" ]] && continue
    if git diff HEAD -- "$pf" 2>/dev/null | grep -qE "^[-+]"; then
      echo "file_unchanged: 변경 금지 파일 수정됨: $pf" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: file_unchanged ($pf)"
      return 1
    fi
  done <<< "$protected_files"

  echo "AUTOMATED_CHECKS_PASS"
  return 0
}

generate_pr_body() {
  local attempt_num="$1"
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)

  local test_summary
  test_summary=$(grep -E "Tests |passed|failed" "/tmp/${PREFIX}_test_out.txt" 2>/dev/null \
    | tail -3 | tr '\n' ' ' || echo "PASS")

  local sec_level
  sec_level=$(grep -oEm1 '\bHIGH\b|\bMEDIUM\b|\bLOW\b' "/tmp/${PREFIX}_sec_out.txt" 2>/dev/null) || sec_level="LOW"

  local pr_notes
  pr_notes=$(grep -A5 -i "nice to have\|권고사항" "/tmp/${PREFIX}_pr_out.txt" 2>/dev/null \
    | grep "^[-•*]" | head -3 | tr '\n' ' ' || echo "없음")

  local why
  why=$(grep -A3 "^## 결정 근거" "$IMPL_FILE" 2>/dev/null \
    | grep "^-" | head -1 | sed 's/^- //' || echo "Issue #${ISSUE_NUM} 구현")

  cat <<PRBODY
## What / Why
Issue #${ISSUE_NUM} — \`${impl_name}\`
${why}

## 작동 증거
- vitest: ${test_summary}
- 시도: ${attempt_num}/${MAX}회 성공

## 위험 + AI 역할
- 보안 최고 등급: ${sec_level}
- AI(Claude) 구현·테스트·검증·리뷰 완료. 인간 최종 확인 권장: 비즈니스 로직

## 리뷰 포커스
${pr_notes}
PRBODY
}

# ── 타임스탬프 디버그 로그 ──────────────────────────────────────────────
_setup_hlog() {
  HLOG="/tmp/${PREFIX}-harness-debug.log"
  ATTEMPT=0
  hlog() { echo "[$(date +%H:%M:%S)] [attempt=${ATTEMPT}] $*" | tee -a "$HLOG"; }
}

log_decision() {
  local key="$1" value="$2" reason="$3"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"decision","key":"%s","value":"%s","reason":"%s","t":%d,"attempt":%d}\n' \
    "$key" "$value" "$reason" "$(date +%s)" "$ATTEMPT" >> "$RUN_LOG"
}

log_phase() {
  local phase="$1"
  [[ -n "$RUN_LOG" ]] && printf '{"event":"phase","name":"%s","t":%d,"attempt":%d}\n' \
    "$phase" "$(date +%s)" "$ATTEMPT" >> "$RUN_LOG"
}

_setup_cleanup() {
  cleanup() {
    rm -f "/tmp/${PREFIX}_harness_active"
    write_run_end
  }
  trap cleanup EXIT
}

TOTAL_COST=0
MAX_TOTAL_COST=10

budget_check() {
  local agent_name="$1" out_file="$2"
  local cost_file="${out_file%.txt}_cost.txt"
  local agent_cost
  agent_cost=$(cat "$cost_file" 2>/dev/null || echo "0")
  TOTAL_COST=$(echo "$TOTAL_COST + $agent_cost" | bc 2>/dev/null || echo "$TOTAL_COST")
  hlog "COST: ${agent_name} \$${agent_cost} | total: \$${TOTAL_COST}/${MAX_TOTAL_COST}"
  if [[ "$(echo "$TOTAL_COST > $MAX_TOTAL_COST" | bc 2>/dev/null)" == "1" ]]; then
    hlog "BUDGET EXCEEDED (\$${TOTAL_COST} > \$${MAX_TOTAL_COST})"
    export HARNESS_RESULT="HARNESS_BUDGET_EXCEEDED"
    echo "HARNESS_BUDGET_EXCEEDED: \$${TOTAL_COST} spent, limit \$${MAX_TOTAL_COST}"
    rm -f "/tmp/${PREFIX}_harness_active"
    exit 1
  fi
}
