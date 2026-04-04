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

MODE=${1:-""}; shift || true
IMPL_FILE=""; ISSUE_NUM=""; PREFIX="mb"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --impl)   IMPL_FILE="$2"; shift 2 ;;
    --issue)  ISSUE_NUM="$2"; shift 2 ;;
    --prefix) PREFIX="$2";    shift 2 ;;
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
[[ -f "$MEM_GLOBAL" ]] && CONSTRAINTS=$(tail -20 "$MEM_GLOBAL")
[[ -f "$MEM_LOCAL"  ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$MEM_LOCAL")"
[[ -f "CLAUDE.md"   ]] && CONSTRAINTS="${CONSTRAINTS}
$(cat CLAUDE.md)"

# ── 헬퍼 함수 ──────────────────────────────────────────────────────────

append_failure() {
  local type="$1" err="$2"
  local date_str; date_str=$(date +%Y-%m-%d)
  local impl_name; impl_name=$(basename "$IMPL_FILE" .md)
  printf -- "- %s | %s | %s | %s\n" \
    "$date_str" "$impl_name" "$type" "$(echo "$err" | head -1 | cut -c1-100)" \
    >> "$MEM_LOCAL"
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

# ── harness_active 플래그 정리 (성공/실패 모두) ────────────────────────
cleanup() {
  rm -f "/tmp/${PREFIX}_harness_active"
}
trap cleanup EXIT

# ══════════════════════════════════════════════════════════════════════
# mode: impl2
# ══════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "impl2" ]]; then

  touch "/tmp/${PREFIX}_harness_active"
  [[ ! -f "/tmp/${PREFIX}_validator_a_passed" ]] && touch "/tmp/${PREFIX}_validator_a_passed"

  attempt=0
  MAX=3
  error_trace=""

  while [[ $attempt -lt $MAX ]]; do

    # ── Context GC: 매 attempt마다 재계산 ──────────────────────────
    if [[ $attempt -eq 0 ]]; then
      context=$(cat "$IMPL_FILE")
      task="impl 파일의 구현 명세 전체 이행"
    else
      failed_files=$(extract_files_from_error "$error_trace")
      if [[ -n "$failed_files" ]]; then
        context=$(cat $failed_files 2>/dev/null || echo "(파일 읽기 실패)")
      else
        context=$(cat "$IMPL_FILE")
      fi
      error_1line=$(echo "$error_trace" | head -1 | cut -c1-200)
      task="이전 시도(${attempt}회) 에러: ${error_1line}. 해당 부분만 수정."
    fi

    # ── 워커 1: engineer ──────────────────────────────────────────
    # 파이프 SIGPIPE 방지: 출력을 파일로 저장
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — engineer 호출 중"
    claude --agent engineer --print \
      -p "impl: $IMPL_FILE
issue: #$ISSUE_NUM
task:
$task
context:
$context
constraints:
$CONSTRAINTS" > "/tmp/${PREFIX}_eng_out.txt" 2>&1 || true
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — engineer 완료"

    # ── 워커 2: test-engineer ─────────────────────────────────────
    changed_files=$(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}' || echo "")
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — test-engineer 호출 중"
    claude --agent test-engineer --print \
      -p "구현된 파일:
$changed_files

테스트 작성 후 npx vitest run. issue: #$ISSUE_NUM" > "/tmp/${PREFIX}_te_out.txt" 2>&1 || true
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — test-engineer 완료"

    # ── Ground truth: 실제 테스트 실행 (LLM 주장과 독립) ──────────
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — npx vitest run"
    set +e
    npx vitest run > "/tmp/${PREFIX}_test_out.txt" 2>&1
    test_exit=$?
    set -e
    if [[ $test_exit -ne 0 ]]; then
      echo "[HARNESS] TESTS_FAIL"
      error_trace=$(cat "/tmp/${PREFIX}_test_out.txt")
      append_failure "test_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_test_engineer_passed"
    echo "[HARNESS] TESTS_PASS"

    # ── 워커 3: validator Mode B ──────────────────────────────────
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — validator Mode B 호출 중"
    claude --agent validator --print \
      -p "Mode B — impl: $IMPL_FILE" > "/tmp/${PREFIX}_val_out.txt" 2>&1 || true
    val_out=$(cat "/tmp/${PREFIX}_val_out.txt")
    val_result=$(echo "$val_out" | grep -oE '\bPASS\b|\bFAIL\b' | head -1 || echo "UNKNOWN")
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — validator Mode B 결과: $val_result"
    if [[ "$val_result" == "FAIL" ]]; then
      error_trace=$(echo "$val_out" | grep -A5 "FAIL" | head -6)
      append_failure "validator_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_validator_b_passed"

    # ── 워커 4: pr-reviewer ───────────────────────────────────────
    diff_out=$(git diff HEAD 2>&1 | head -300)
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — pr-reviewer 호출 중"
    claude --agent pr-reviewer --print \
      -p "변경 내용 리뷰:
$diff_out" > "/tmp/${PREFIX}_pr_out.txt" 2>&1 || true
    pr_out=$(cat "/tmp/${PREFIX}_pr_out.txt")
    pr_result=$(echo "$pr_out" | grep -oE 'LGTM|CHANGES_REQUESTED' | head -1 || echo "UNKNOWN")
    echo "[HARNESS] Phase 1 attempt $((attempt+1))/$MAX — pr-reviewer 결과: $pr_result"
    if [[ "$pr_result" == "CHANGES_REQUESTED" ]]; then
      error_trace=$(echo "$pr_out" | grep -A10 "MUST FIX" | head -10)
      append_failure "pr_fail" "$error_trace"
      attempt=$((attempt+1))
      continue
    fi
    touch "/tmp/${PREFIX}_pr_reviewer_lgtm"
    echo "[HARNESS] LGTM"

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

    append_success $((attempt+1))

    echo "HARNESS_DONE"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "attempts: $((attempt+1))"
    echo "commit: $commit_hash"
    exit 0

  done

  # 3회 모두 실패
  echo "IMPLEMENTATION_ESCALATE"
  echo "attempts: $MAX"
  echo "마지막 에러:"
  echo "$error_trace" | head -20
  exit 1

fi

echo "[HARNESS] 알 수 없는 mode: $MODE"
exit 1
