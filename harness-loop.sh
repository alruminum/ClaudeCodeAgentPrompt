#!/bin/bash
# ~/.claude/harness-loop.sh
# 코드 기반 하네스 루프 — LLM 루프 해석 방지
#
# 호출 형식:
#   bash .claude/harness-loop.sh impl2 \
#     --impl <impl_file_path> \
#     --issue <issue_number> \
#     [--prefix <prefix>]
#
# 출력:
#   HARNESS_DONE         — 성공 (commit 완료)
#   IMPLEMENTATION_ESCALATE — 3회 모두 실패

set -euo pipefail

# macOS timeout 호환 — perl은 macOS 기본 탑재, Linux timeout 있으면 무시
command -v timeout &>/dev/null || timeout() {
  perl -e 'alarm shift; exec @ARGV' -- "$@"
}

# shellcheck source=/dev/null
source "${HOME}/.claude/harness-utils.sh"

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"; DEPTH="std"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)   IMPL_FILE="$2"; shift 2 ;;
    --issue)  ISSUE_NUM="$2"; shift 2 ;;
    --prefix) PREFIX="$2";    shift 2 ;;
    --depth)  DEPTH="$2";     shift 2 ;;
    *) shift ;;
  esac
done

# ── 필수 인자 검증 ─────────────────────────────────────────────────────
if [[ -z "$MODE" || -z "$IMPL_FILE" || -z "$ISSUE_NUM" ]]; then
  echo "사용법: bash harness-loop.sh impl2 --impl <path> --issue <N> [--prefix <prefix>]"
  exit 1
fi

if [[ ! -f "$IMPL_FILE" ]]; then
  echo "[HARNESS] 오류: impl 파일을 찾을 수 없음: $IMPL_FILE"
  exit 1
fi

# ── Phase 0: constraints 로드 (1회 — 재시도에도 고정) ──────────────────
MEM_GLOBAL="${HOME}/.claude/harness-memory.md"
MEM_LOCAL=".claude/harness-memory.md"

# harness-memory.md가 없으면 생성
[[ ! -f "$MEM_LOCAL" ]] && mkdir -p .claude && printf "# Harness Memory\n\n## Known Failure Patterns\n\n## Success Patterns\n" > "$MEM_LOCAL"

CONSTRAINTS=""
# Auto-Promoted Rules 우선 로드 (자동 프로모션된 규칙이 최우선)
for mf in "$MEM_GLOBAL" "$MEM_LOCAL"; do
  if [[ -f "$mf" ]]; then
    promoted=$(sed -n '/^## Auto-Promoted Rules/,/^##/p' "$mf" 2>/dev/null | grep "^- PROMOTED:" | head -10)
    [[ -n "$promoted" ]] && CONSTRAINTS="${CONSTRAINTS}
[AUTO-PROMOTED RULES — 반복 실패 패턴, 반드시 회피]:
${promoted}"
  fi
done
[[ -f "$MEM_GLOBAL" ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_GLOBAL")"
[[ -f "$MEM_LOCAL"  ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_LOCAL")"
# CLAUDE.md: 관련 섹션만 추출 (전체 cat 대신 토큰 절약)
if [[ -f "CLAUDE.md" ]]; then
  CONSTRAINTS="${CONSTRAINTS}
$(sed -n '/^## 개발 명령어/,/^---/p; /^## 작업 순서/,/^---/p; /^## Git/,/^---/p' CLAUDE.md | head -c 10000)"
fi

# ── 헬퍼 함수 ──────────────────────────────────────────────────────────

append_failure() {
  local type="$1" err="$2"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  local err_1line; err_1line=$(echo "$err" | head -1 | cut -c1-100)
  printf -- "- %s | %s | %s | %s\n" \
    "$date_str" "$impl_name" "$type" "$err_1line" \
    >> "$MEM_LOCAL"

  # ── B2: 실패 패턴 자동 프로모션 (같은 impl+type 3회 → Auto-Promoted Rules) ──
  local pattern_key="${impl_name}|${type}"
  local count; count=$(grep -c "$pattern_key" "$MEM_LOCAL" 2>/dev/null || echo 0)
  if [[ $count -ge 3 ]]; then
    # Auto-Promoted Rules 섹션이 없으면 생성
    if ! grep -q "## Auto-Promoted Rules" "$MEM_LOCAL" 2>/dev/null; then
      printf "\n## Auto-Promoted Rules\n\n" >> "$MEM_LOCAL"
    fi
    # 중복 프로모션 방지: 이미 프로모션된 패턴인지 확인
    if ! grep -q "PROMOTED: $pattern_key" "$MEM_LOCAL" 2>/dev/null; then
      printf -- "- PROMOTED: %s | %s회 반복 | %s | MUST NOT: %s\n" \
        "$pattern_key" "$count" "$date_str" "$err_1line" \
        >> "$MEM_LOCAL"
      echo "[HARNESS] ⚠️ 실패 패턴 자동 프로모션: $pattern_key ($count회)"
    fi
  fi

  # ── P1: Memory 후보 파일 기록 (HARNESS_DONE 후 유저에게 제안) ─────────────
  local candidate_file="/tmp/${PREFIX}_memory_candidate.md"
  # 같은 루프 내 중복 기록 방지
  if ! grep -q "$pattern_key" "$candidate_file" 2>/dev/null; then
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

append_success() {
  local attempt_num="$1"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  printf -- "- %s | %s | success | attempt %s\n" \
    "$date_str" "$impl_name" "$attempt_num" \
    >> "$MEM_LOCAL"
}

extract_files_from_error() {
  # errorTrace에서 "src/..." 패턴 역추적
  echo "$1" | grep -oE 'src/[^ :()]+\.(ts|tsx|js|jsx)' | sort -u | head -5
}

build_smart_context() {
  # 스마트 컨텍스트 구성 — 파일 통째가 아닌 관련 청크만
  local impl="$1" attempt_n="$2" err_trace="$3"
  local ctx=""

  if [[ $attempt_n -eq 0 ]]; then
    # impl 파일 자체
    ctx=$(cat "$impl")
    # impl에서 언급된 소스 파일 내용 추가
    local mentioned
    mentioned=$(grep -oE 'src/[^ `"'"'"']+\.(ts|tsx)' "$impl" 2>/dev/null | sort -u | head -5)
    for f in $mentioned; do
      if [[ -f "$f" ]]; then
        ctx="${ctx}
=== ${f} ===
$(cat "$f")"
      fi
    done
  else
    # 재시도: error trace에서 관련 파일만
    local failed_files
    failed_files=$(extract_files_from_error "$err_trace")
    if [[ -n "$failed_files" ]]; then
      for f in $failed_files; do
        [[ -f "$f" ]] && ctx="${ctx}
=== ${f} ===
$(cat "$f")"
      done
    else
      ctx=$(cat "$impl")
    fi
  fi

  # 50KB 캡 (토큰 폭발 방지)
  echo "$ctx" | head -c 50000
}

run_automated_checks() {
  local impl_file="$1"
  local out_file="/tmp/${PREFIX}_autocheck_fail.txt"
  rm -f "$out_file"

  # Check 1: has_changes — engineer가 실제로 파일을 수정했는가?
  if ! git status --short | grep -qE "^ M|^M |^A "; then
    echo "no_changes: engineer가 아무 파일도 수정하지 않음" > "$out_file"
    echo "AUTOMATED_CHECKS_FAIL: no_changes"
    return 1
  fi

  # Check 2: no_new_deps — package.json 무단 의존성 추가 여부
  if git show HEAD:package.json >/dev/null 2>&1; then
    if git diff HEAD -- package.json 2>/dev/null | grep -qE '^\+\s+"[a-z@]'; then
      echo "new_deps: package.json에 새 의존성이 추가됨 (사전 승인 필요)" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: new_deps"
      return 1
    fi
  fi

  # Check 3: file_unchanged — impl 파일에 명시된 변경 금지 파일 위반 여부
  local protected_files
  protected_files=$(grep -oE '\(PROTECTED\)[[:space:]]+[^[:space:]]+' "$impl_file" 2>/dev/null \
    | awk '{print $NF}' || true)
  for pf in $protected_files; do
    if git diff HEAD -- "$pf" 2>/dev/null | grep -qE "^[-+]"; then
      echo "file_unchanged: 변경 금지 파일 수정됨: $pf" > "$out_file"
      echo "AUTOMATED_CHECKS_FAIL: file_unchanged ($pf)"
      return 1
    fi
  done

  echo "AUTOMATED_CHECKS_PASS"
  return 0
}

generate_pr_body() {
  local attempt_num="$1"
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)

  # 테스트 결과 요약 (마지막 3줄)
  local test_summary
  test_summary=$(grep -E "Tests |passed|failed" "/tmp/${PREFIX}_test_out.txt" 2>/dev/null \
    | tail -3 | tr '\n' ' ' || echo "PASS")

  # 보안 최고 등급
  local sec_level
  sec_level=$(grep -oE '\bHIGH\b|\bMEDIUM\b|\bLOW\b' "/tmp/${PREFIX}_sec_out.txt" 2>/dev/null \
    | head -1 || echo "LOW")

  # pr-reviewer 권고사항 (NICE TO HAVE 아래 bullet)
  local pr_notes
  pr_notes=$(grep -A5 -i "nice to have\|권고사항" "/tmp/${PREFIX}_pr_out.txt" 2>/dev/null \
    | grep "^[-•*]" | head -3 | tr '\n' ' ' || echo "없음")

  # impl 결정 근거 첫 줄
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

generate_commit_msg() {
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  # git add 이후 staged 파일 목록 사용 (HEAD~1은 최초 커밋 시 없을 수 있음)
  local changed; changed=$(git diff --cached --name-only 2>/dev/null | head -5 | tr '\n' ' ' || echo "(파일 목록 없음)")
  cat <<MSGEOF
feat: implement ${impl_name} (#${ISSUE_NUM})

[왜] Issue #${ISSUE_NUM} 구현
[변경]
- ${changed}

Closes #${ISSUE_NUM}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
MSGEOF
}

# ── 타임스탬프 디버그 로그 ─────────────────────────────────────────────
HLOG="/tmp/${PREFIX}-harness-debug.log"
ATTEMPT=0
hlog() { echo "[$(date +%H:%M:%S)] [attempt=${ATTEMPT}] $*" | tee -a "$HLOG"; }

# ── harness_active 플래그 정리 (성공/실패 모두) ────────────────────────
cleanup() {
  rm -f "/tmp/${PREFIX}_harness_active"
  write_run_end
}
trap cleanup EXIT

# ══════════════════════════════════════════════════════════════════════
# mode: impl2
# ══════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "impl2" ]]; then

  touch "/tmp/${PREFIX}_harness_active"
  [[ ! -f "/tmp/${PREFIX}_plan_validation_passed" ]] && touch "/tmp/${PREFIX}_plan_validation_passed"
  rotate_harness_logs "$PREFIX" "impl2"

  # ── fast mode: engineer → commit (테스트·리뷰·보안 스킵) ─────────────
  if [[ "$DEPTH" == "fast" ]]; then
    hlog "=== 하네스 루프 시작 (depth=fast) ==="
    echo "[HARNESS/fast] engineer 호출 중 (테스트·리뷰·보안 스킵)"
    context=$(cat "$IMPL_FILE" | head -c 30000)
    hlog "▶ engineer 시작 (depth=fast, timeout=900s)"
    AGENT_EXIT=0
    _agent_call "engineer" 900 \
      "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: impl 파일의 구현 명세 이행
context:
$context
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    hlog "◀ engineer 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_eng_out.txt" 2>/dev/null || echo 0)bytes)"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ engineer timeout — skip"; fi

    mapfile -t commit_files < <(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}')
    if [[ ${#commit_files[@]} -gt 0 ]]; then
      git add -- "${commit_files[@]}"
      git commit -m "$(generate_commit_msg) [fast-mode]"
      commit_hash=$(git rev-parse --short HEAD)
      echo "HARNESS_DONE (fast)"
      echo "impl: $IMPL_FILE"
      echo "issue: #$ISSUE_NUM"
      echo "commit: $commit_hash"
      echo "⚠️ fast mode: 테스트·리뷰·보안 검사 스킵됨. 중요 변경엔 --depth=std 사용."
      hlog "=== 하네스 루프 종료 (결과=HARNESS_DONE, 시도=1) ==="
    else
      echo "[HARNESS/fast] 변경사항 없음"
      hlog "=== 하네스 루프 종료 (결과=no_changes, 시도=1) ==="
    fi
    exit 0
  fi

  attempt=0
  MAX=3
  error_trace=""
  fail_type=""
  hlog "=== 하네스 루프 시작 (depth=$DEPTH, max_retries=$MAX) ==="

  while [[ $attempt -lt $MAX ]]; do
    ATTEMPT=$attempt

    # ── Context GC: 스마트 컨텍스트 (관련 청크만 로드) ──────────────
    context=$(build_smart_context "$IMPL_FILE" "$attempt" "$error_trace")
    if [[ $attempt -eq 0 ]]; then
      task="impl 파일의 구현 명세 전체 이행"
    else
      # ── C1: 실패 유형별 수정 전략 ────────────────────────────────
      error_1line=$(echo "$error_trace" | head -1 | cut -c1-200)
      case "$fail_type" in
        autocheck_fail)
          task="[사전 검사 실패] 시도 ${attempt}회. 검사 결과:
${error_1line}
위 문제를 해결한 뒤 다시 구현하라. 테스트·벨리데이터 호출은 검사 통과 후 진행된다."
          ;;
        test_fail)
          task="[테스트 실패] 시도 ${attempt}회. 테스트 출력:
${error_1line}
구현 코드를 수정하라. 테스트 코드 자체는 수정 금지."
          ;;
        validator_fail)
          task="[스펙 불일치] 시도 ${attempt}회. validator 리포트:
${error_1line}
impl 파일의 해당 항목을 다시 확인하고 누락된 부분을 구현하라."
          ;;
        pr_fail)
          task="[코드 품질] 시도 ${attempt}회. MUST FIX:
${error_1line}
위 MUST FIX 항목만 수정하라. 기능 변경 금지."
          ;;
        security_fail)
          task="[보안 취약점] 시도 ${attempt}회. 취약점:
${error_1line}
위 취약점의 수정 방안대로 적용하라."
          ;;
        *)
          task="이전 시도(${attempt}회) 에러: ${error_1line}. 해당 부분만 수정."
          ;;
      esac
    fi

    # ── 워커 1: engineer ──────────────────────────────────────────
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — engineer 호출 중"
    hlog "▶ engineer 시작 (depth=$DEPTH, timeout=900s)"
    AGENT_EXIT=0
    _agent_call "engineer" 900 \
      "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task:
$task
context:
$context
constraints:
$CONSTRAINTS" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    hlog "◀ engineer 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_eng_out.txt" 2>/dev/null || echo 0)bytes)"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ engineer timeout — skip"; fi

    # ── S17-2: pre-evaluator automated_checks ────────────────────────
    if ! run_automated_checks "$IMPL_FILE"; then
      error_trace=$(cat "/tmp/${PREFIX}_autocheck_fail.txt" 2>/dev/null || echo "automated_checks FAIL")
      fail_type="autocheck_fail"
      append_failure "autocheck_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    echo "[HARNESS] automated_checks PASS"

    # ── 워커 2: test-engineer ─────────────────────────────────────
    changed_files=$(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}' || echo "")
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — test-engineer 호출 중"
    hlog "▶ test-engineer 시작 (depth=$DEPTH, timeout=300s)"
    AGENT_EXIT=0
    _agent_call "test-engineer" 300 \
      "구현된 파일:
$changed_files

테스트 작성 후 npx vitest run. issue: #$ISSUE_NUM" "/tmp/${PREFIX}_te_out.txt" || AGENT_EXIT=$?
    hlog "◀ test-engineer 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_te_out.txt" 2>/dev/null || echo 0)bytes)"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ test-engineer timeout — skip"; fi

    # ── Ground truth: 실제 테스트 실행 (LLM 주장과 독립) ──────────
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — npx vitest run"
    hlog "▶ vitest 시작"
    set +e
    npx vitest run > "/tmp/${PREFIX}_test_out.txt" 2>&1
    test_exit=$?
    set -e
    hlog "◀ vitest 종료 (exit=$test_exit)"
    if [[ $test_exit -ne 0 ]]; then
      echo "[HARNESS] TESTS_FAIL"
      error_trace=$(cat "/tmp/${PREFIX}_test_out.txt")
      fail_type="test_fail"
      append_failure "test_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_test_engineer_passed"
    echo "[HARNESS] TESTS_PASS"

    # ── 워커 3: validator Mode B ──────────────────────────────────
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — validator Mode B 호출 중"
    hlog "▶ validator 시작 (depth=$DEPTH, timeout=300s)"
    AGENT_EXIT=0
    _agent_call "validator" 300 \
      "Mode B — impl: $IMPL_FILE" \
      "/tmp/${PREFIX}_val_out.txt" || AGENT_EXIT=$?
    hlog "◀ validator 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_val_out.txt" 2>/dev/null || echo 0)bytes)"
    if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ validator timeout — skip"; fi
    val_out=$(cat "/tmp/${PREFIX}_val_out.txt")
    if echo "$val_out" | grep -qE "^PASS$"; then
      val_result="PASS"
    elif echo "$val_out" | grep -qE "^FAIL$"; then
      val_result="FAIL"
    else
      val_result="UNKNOWN"
      echo "[HARNESS] ⚠️ validator 출력에서 마커(PASS/FAIL)를 찾지 못함"
    fi
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — validator Mode B 결과: $val_result"
    if [[ "$val_result" != "PASS" ]]; then
      error_trace=$(echo "$val_out" | grep -A5 "FAIL" | head -6)
      [[ -z "$error_trace" ]] && error_trace=$(echo "$val_out" | tail -6)
      fail_type="validator_fail"
      append_failure "validator_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_validator_b_passed"

    # ── 워커 4+5: pr-reviewer / security-reviewer (deep only) ────────
    if [[ "$DEPTH" == "deep" ]]; then
      diff_out=$(git diff HEAD 2>&1 | head -300)
      echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — pr-reviewer 호출 중"
      hlog "▶ pr-reviewer 시작 (deep only, timeout=180s)"
      AGENT_EXIT=0
      _agent_call "pr-reviewer" 180 \
        "변경 내용 리뷰:
$diff_out" "/tmp/${PREFIX}_pr_out.txt" || AGENT_EXIT=$?
      hlog "◀ pr-reviewer 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_pr_out.txt" 2>/dev/null || echo 0)bytes)"
      if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ pr-reviewer timeout — skip"; fi
      pr_out=$(cat "/tmp/${PREFIX}_pr_out.txt")
      if echo "$pr_out" | grep -qE "^LGTM$"; then
        pr_result="PASS"
      elif echo "$pr_out" | grep -qE "^CHANGES_REQUESTED$"; then
        pr_result="FAIL"
      else
        pr_result="UNKNOWN"
        echo "[HARNESS] ⚠️ pr-reviewer 출력에서 마커(LGTM/CHANGES_REQUESTED)를 찾지 못함"
      fi
      echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — pr-reviewer 결과: $pr_result"
      if [[ "$pr_result" != "PASS" ]]; then
        error_trace=$(echo "$pr_out" | grep -A10 "MUST FIX" | head -10)
        [[ -z "$error_trace" ]] && error_trace=$(echo "$pr_out" | tail -6)
        fail_type="pr_fail"
        append_failure "pr_fail" "$error_trace"
        attempt=$((attempt+1))
        continue
      fi
      touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
      echo "[HARNESS] LGTM"

      echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — security-reviewer 호출 중"
      hlog "▶ security-reviewer 시작 (deep only, timeout=180s)"
      changed_src=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(ts|tsx|js|jsx)$' | head -10 | tr '\n' ' ')
      AGENT_EXIT=0
      _agent_call "security-reviewer" 180 \
        "보안 리뷰 대상 파일:
$changed_src

변경 diff:
$(git diff HEAD 2>&1 | head -500)" "/tmp/${PREFIX}_sec_out.txt" || AGENT_EXIT=$?
      hlog "◀ security-reviewer 종료 (exit=${AGENT_EXIT}, $(wc -c < "/tmp/${PREFIX}_sec_out.txt" 2>/dev/null || echo 0)bytes)"
      if [[ $AGENT_EXIT -eq 124 ]]; then hlog "⏰ security-reviewer timeout — skip"; fi
      sec_out=$(cat "/tmp/${PREFIX}_sec_out.txt")
      if echo "$sec_out" | grep -qE "^SECURE$"; then
        sec_result="PASS"
      elif echo "$sec_out" | grep -qE "^VULNERABILITIES_FOUND$"; then
        sec_result="FAIL"
      else
        sec_result="UNKNOWN"
        echo "[HARNESS] ⚠️ security-reviewer 출력에서 마커(SECURE/VULNERABILITIES_FOUND)를 찾지 못함"
      fi
      echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — security-reviewer 결과: $sec_result"
      if [[ "$sec_result" != "PASS" ]]; then
        # HIGH/MEDIUM만 차단, LOW만 있으면 SECURE 판정이므로 FAIL 도달 시 HIGH/MEDIUM 존재
        error_trace=$(echo "$sec_out" | grep -E 'HIGH|MEDIUM' | head -10)
        [[ -z "$error_trace" ]] && error_trace=$(echo "$sec_out" | tail -6)
        fail_type="security_fail"
        append_failure "security_fail" "$error_trace"
        attempt=$((attempt+1))
        continue
      fi
      touch "/tmp/${PREFIX}_security_review_passed"
      echo "[HARNESS] SECURE"
    else
      # std/fast: pr-reviewer·security-reviewer 스킵, 플래그만 자동 생성
      touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
      touch "/tmp/${PREFIX}_security_review_passed"
      hlog "⏭ pr-reviewer/security-reviewer 스킵 (depth=$DEPTH)"
    fi

    # ── git commit ────────────────────────────────────────────────
    # test-engineer가 테스트 파일 추가했을 수 있으므로 commit 직전 재계산
    # 배열로 관리해 파일명 공백 이슈 방지
    mapfile -t commit_files < <(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}')
    if [[ ${#commit_files[@]} -gt 0 ]]; then
      git add -- "${commit_files[@]}"
    else
      git add -u
    fi
    git commit -m "$(generate_commit_msg)"
    commit_hash=$(git rev-parse --short HEAD)

    # ── G6: PR body 생성 ─────────────────────────────────────────
    generate_pr_body $((attempt+1)) > "/tmp/${PREFIX}_pr_body.txt" 2>/dev/null || true

    append_success $((attempt+1))

    # ── S7: last_issue 저장 (다음 세션 컨텍스트 브리지용) ───────────────
    echo "$ISSUE_NUM" > "/tmp/${PREFIX}_last_issue"

    hlog "=== 하네스 루프 종료 (결과=HARNESS_DONE, 시도=$((attempt+1))) ==="
    echo "HARNESS_DONE"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "attempts: $((attempt+1))"
    echo "commit: $commit_hash"
    echo "pr_body: /tmp/${PREFIX}_pr_body.txt"

    # ── P1: Memory 후보 존재 시 유저에게 기록 제안 ───────────────────────
    local candidate_file="/tmp/${PREFIX}_memory_candidate.md"
    if [[ -f "$candidate_file" ]]; then
      echo ""
      echo "💾 [HARNESS MEMORY] 이번 루프에서 실패 패턴이 감지됐습니다."
      echo "   아래 후보를 harness-memory.md에 기록하면 다음 루프의 CONSTRAINTS로 활용됩니다."
      echo "   파일: $candidate_file"
      echo "   내용:"
      cat "$candidate_file"
      echo ""
      echo "   → 기록할까요? (메인 Claude에게 'Y' 또는 'N' 응답 요청)"
      echo "memory_candidate: $candidate_file"
    fi

    exit 0

  done

  # 3회 모두 실패
  hlog "=== 하네스 루프 종료 (결과=IMPLEMENTATION_ESCALATE, 시도=$MAX) ==="
  echo "IMPLEMENTATION_ESCALATE"
  echo "attempts: $MAX"
  echo "마지막 에러:"
  echo "$error_trace" | head -20
  exit 1

fi

echo "[HARNESS] 알 수 없는 mode: $MODE"
exit 1
