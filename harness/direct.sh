#!/bin/bash
# ~/.claude/harness/direct.sh
# direct 모드: impl 파일 없이 engineer 직행하는 경량 구현 루프
#
# 진입 조건:
#   - qa 스킬이 FUNCTIONAL_BUG 분류 후 GitHub 이슈 생성 완료
#   - ux 스킬 DESIGN_HANDOFF 후 GitHub 이슈 생성 완료
#
# 흐름:
#   GitHub 이슈 body (QA 분석 / DESIGN_HANDOFF) 읽기
#   → engineer 직행 (impl 파일 없음, depth=std 고정)
#   → SPEC_GAP_FOUND → architect SPEC_GAP inline
#   → test-engineer → vitest → validator → pr-reviewer → merge
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

run_direct() {
  rotate_harness_logs "$PREFIX" "direct"

  # ── 필수 파라미터 검증: --issue 필요 ──
  if [[ -z "$ISSUE_NUM" || "$ISSUE_NUM" == "N" ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] 오류: direct 모드는 --issue가 필요합니다"
    echo "사용법: executor.sh direct --issue <N> [--prefix <P>]"
    exit 1
  fi

  # ── GitHub 이슈에서 컨텍스트 읽기 ──
  echo "[HARNESS] GitHub 이슈 #${ISSUE_NUM} 읽기"
  local issue_context=""
  issue_context=$(gh issue view "$ISSUE_NUM" --json body,title \
    -q '"## 이슈: " + .title + "\n\n" + .body' 2>/dev/null || echo "")

  if [[ -z "$issue_context" ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] 오류: GitHub 이슈 #${ISSUE_NUM}를 읽을 수 없습니다"
    exit 1
  fi

  # ── CONSTRAINTS 로딩 ──
  if [[ -z "$CONSTRAINTS" ]]; then
    local mem_global="${HOME}/.claude/harness-memory.md"
    local mem_local=".claude/harness-memory.md"
    [[ -f "$mem_global" ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$mem_global")"
    [[ -f "$mem_local" ]] && CONSTRAINTS="${CONSTRAINTS}
$(tail -20 "$mem_local")"
    if [[ -f "CLAUDE.md" ]]; then
      CONSTRAINTS="${CONSTRAINTS}
$(sed -n '/^## 개발 명령어/,/^---/p; /^## 작업 순서/,/^---/p; /^## Git/,/^---/p' CLAUDE.md | head -c 10000)"
    fi
  fi

  # ── Feature branch 생성 ──
  local FEATURE_BRANCH
  FEATURE_BRANCH=$(create_feature_branch "fix" "$ISSUE_NUM")
  export HARNESS_BRANCH="$FEATURE_BRANCH"
  echo "[HARNESS] feature branch: $FEATURE_BRANCH"

  local attempt=0
  local MAX=3
  local spec_gap_count=0
  local MAX_SPEC_GAP=2
  local HIST_DIR="/tmp/${PREFIX}_history"
  local LOOP_OUT_DIR="${HIST_DIR}/direct"
  mkdir -p "$LOOP_OUT_DIR"

  while [[ $attempt -lt $MAX ]]; do
    attempt=$((attempt + 1))
    kill_check

    local attempt_dir="${LOOP_OUT_DIR}/attempt-${attempt}"
    mkdir -p "$attempt_dir"
    prune_history "$LOOP_OUT_DIR"

    echo "[HARNESS] engineer 직행 (attempt $attempt/$MAX, depth=std)"

    local explore_instr=""
    if [[ $attempt -gt 1 ]]; then
      explore_instr="
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/attempt-$((attempt-1))/test-results.log")"
    fi

    local eng_prompt="issue: #${ISSUE_NUM}
task: 이슈의 버그를 수정하라. impl 파일 없음 — 이슈 컨텍스트와 코드 탐색으로 직접 판단하라.${explore_instr}
issue_context:
${issue_context}
constraints:
${CONSTRAINTS}"

    local AGENT_EXIT=0
    _agent_call "engineer" 900 "$eng_prompt" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    cp "/tmp/${PREFIX}_eng_out.txt" "${attempt_dir}/engineer.log" 2>/dev/null || true

    if [[ $AGENT_EXIT -eq 124 ]]; then
      echo "[HARNESS] engineer timeout — 재시도"
      continue
    fi

    # ── SPEC_GAP_FOUND 감지 ──
    if grep -qF 'SPEC_GAP_FOUND' "/tmp/${PREFIX}_eng_out.txt" 2>/dev/null; then
      spec_gap_count=$((spec_gap_count + 1))
      if [[ $spec_gap_count -gt $MAX_SPEC_GAP ]]; then
        export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
        echo "IMPLEMENTATION_ESCALATE: SPEC_GAP ${MAX_SPEC_GAP}회 초과"
        echo "issue: #${ISSUE_NUM}"
        exit 1
      fi
      echo "[HARNESS] SPEC_GAP_FOUND → architect SPEC_GAP inline (spec_gap_count=$spec_gap_count)"
      local spec_gap_out
      spec_gap_out=$(head -c 30000 "/tmp/${PREFIX}_eng_out.txt" 2>/dev/null)
      _agent_call "architect" 600 \
        "@MODE:ARCHITECT:SPEC_GAP
issue: #${ISSUE_NUM}
engineer 출력:
${spec_gap_out}" \
        "/tmp/${PREFIX}_arch_sg_out.txt"
      # attempt 카운터 동결: 다시 같은 attempt 번호로 engineer 재시도
      attempt=$((attempt - 1))
      continue
    fi

    # ── 즉시 커밋: engineer 변경을 feature branch에 기록 ──
    local eng_changed
    eng_changed=$(collect_changed_files || true)
    if [[ -n "$eng_changed" ]]; then
      echo "$eng_changed" | while IFS= read -r _cf; do
        [[ -n "$_cf" ]] && git add -- "$_cf"
      done
      local fix_suffix=""
      [[ $attempt -gt 1 ]] && fix_suffix=" [attempt-${attempt}-fix]"
      git commit -m "$(generate_commit_msg)${fix_suffix}"
      echo "[HARNESS] engineer commit: $(git rev-parse --short HEAD)"
    fi

    # ── test-engineer ──
    echo "[HARNESS] test-engineer"
    _agent_call "test-engineer" 600 \
      "@MODE:TEST_ENGINEER:TEST
issue: #${ISSUE_NUM}
engineer 변경 파일: $(echo "$eng_changed" | head -5 | tr '\n' ',')" \
      "/tmp/${PREFIX}_te_out.txt"
    cp "/tmp/${PREFIX}_te_out.txt" "${attempt_dir}/test-engineer.log" 2>/dev/null || true

    # ── vitest run ──
    echo "[HARNESS] vitest run"
    local vitest_exit=0
    npx vitest run --reporter=verbose 2>&1 | tail -100 > "/tmp/${PREFIX}_vitest_out.txt" || vitest_exit=$?
    cp "/tmp/${PREFIX}_vitest_out.txt" "${attempt_dir}/test-results.log" 2>/dev/null || true

    if [[ $vitest_exit -ne 0 ]]; then
      write_attempt_meta "${attempt_dir}/meta.json" "$attempt" "direct" "std" "FAIL" \
        "test_fail" "" "$(git diff HEAD~1 --name-only 2>/dev/null | head -5 | tr '\n' ',' || echo "")" \
        "engineer" "vitest exit=$vitest_exit" "${attempt_dir}/test-results.log 참조"
      echo "[HARNESS] vitest 실패 (exit=$vitest_exit) — engineer 재시도"
      continue
    fi

    # ── validator Code Validation ──
    echo "[HARNESS] validator Code Validation"
    _agent_call "validator" 300 \
      "@MODE:VALIDATOR:CODE_VALIDATION
issue: #${ISSUE_NUM}
vitest: PASS
변경 파일: $(echo "$eng_changed" | head -5 | tr '\n' ',')" \
      "/tmp/${PREFIX}_val_out.txt"
    cp "/tmp/${PREFIX}_val_out.txt" "${attempt_dir}/validator.log" 2>/dev/null || true

    local val_result
    val_result=$(parse_marker "/tmp/${PREFIX}_val_out.txt" "PASS|FAIL|SPEC_MISSING")

    if [[ "$val_result" == "FAIL" ]]; then
      write_attempt_meta "${attempt_dir}/meta.json" "$attempt" "direct" "std" "FAIL" \
        "validator_fail" "" "" "validator" "" "${attempt_dir}/validator.log 참조"
      echo "[HARNESS] validator FAIL — engineer 재시도"
      continue
    fi

    # ── pr-reviewer ──
    echo "[HARNESS] pr-reviewer"
    _agent_call "pr-reviewer" 300 \
      "@MODE:PR_REVIEWER:REVIEW
issue: #${ISSUE_NUM}
변경 파일: $(echo "$eng_changed" | head -5 | tr '\n' ',')" \
      "/tmp/${PREFIX}_pr_out.txt"
    cp "/tmp/${PREFIX}_pr_out.txt" "${attempt_dir}/pr.log" 2>/dev/null || true

    local pr_result
    pr_result=$(parse_marker "/tmp/${PREFIX}_pr_out.txt" "LGTM|CHANGES_REQUESTED")

    if [[ "$pr_result" == "CHANGES_REQUESTED" ]]; then
      write_attempt_meta "${attempt_dir}/meta.json" "$attempt" "direct" "std" "FAIL" \
        "pr_fail" "" "" "pr-reviewer" "" "${attempt_dir}/pr.log 참조"
      echo "[HARNESS] pr-reviewer CHANGES_REQUESTED — engineer 재시도"
      continue
    fi

    # ── commit + merge ──
    touch "/tmp/${PREFIX}_validator_b_passed"
    if ! harness_commit_and_merge "$FEATURE_BRANCH" "$ISSUE_NUM" "direct" "$PREFIX" "[direct-std]"; then
      exit 1
    fi

    local merge_commit
    merge_commit=$(git rev-parse --short HEAD)
    export HARNESS_RESULT="HARNESS_DONE"
    echo "HARNESS_DONE (direct, depth=std)"
    echo "issue: #${ISSUE_NUM}"
    echo "commit: $merge_commit"
    exit 0
  done

  rm -f "/tmp/${PREFIX}_validator_b_passed"
  export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
  echo "IMPLEMENTATION_ESCALATE (direct ${MAX}회 실패)"
  echo "branch: ${FEATURE_BRANCH:-unknown}"
  exit 1
}
