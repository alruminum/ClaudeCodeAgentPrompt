#!/bin/bash
# ~/.claude/harness-bugfix.sh
# bugfix 전용 함수 라이브러리 — harness-executor.sh에서 source
# Issue A 반영: QA_SUMMARY 파싱 + 폴백 라우팅을 여기서 수행
# Issue B 반영: GitHub issue 재진입 경로 명시

# ── QA_SUMMARY 파싱: footer 우선, 기존 grep 폴백 ───────────────────
_parse_qa_summary() {
  local qa_file="$1"
  local field="$2"
  local value=""
  value=$(sed -n '/---QA_SUMMARY---/,/---END_QA_SUMMARY---/p' "$qa_file" \
    | grep "${field}:" | sed "s/.*${field}: //" | tr -d '[:space:]')
  echo "$value"
}

# ── depth 자동 판정: QA_SUMMARY 기반 fast/std ──────────────────────
detect_bugfix_depth() {
  local qa_file="$1"
  local qa_type=""
  qa_type=$(_parse_qa_summary "$qa_file" "TYPE")
  local affected=""
  affected=$(_parse_qa_summary "$qa_file" "AFFECTED_FILES")

  # footer 없으면 grep 폴백
  if [[ -z "$qa_type" ]]; then
    if grep -q 'FUNCTIONAL_BUG' "$qa_file" 2>/dev/null; then
      qa_type="FUNCTIONAL_BUG"
    fi
  fi

  if [[ "$qa_type" == "FUNCTIONAL_BUG" ]] && [[ -n "$affected" ]] && [[ "$affected" -le 2 ]] 2>/dev/null; then
    echo "fast"
  else
    echo "std"
  fi
}

# ── 메인 진입점: QA_SUMMARY 파싱 → 라우팅 분기 ────────────────────
bugfix_run() {
  local qa_file="/tmp/${PREFIX}_qa_out.txt"

  # QA_SUMMARY footer 우선 파싱
  local routing=""
  routing=$(_parse_qa_summary "$qa_file" "ROUTING")

  if [[ -z "$routing" ]]; then
    # 폴백: 기존 grep 방식
    routing="architect"
    if grep -q 'FUNCTIONAL_BUG' "$qa_file" 2>/dev/null; then
      routing="engineer_direct"
    elif grep -q 'DESIGN_ISSUE' "$qa_file" 2>/dev/null; then
      routing="design"
    fi
  fi

  local qa_type=""
  qa_type=$(_parse_qa_summary "$qa_file" "TYPE")
  if [[ -z "$qa_type" ]]; then
    # 폴백
    if grep -q 'FUNCTIONAL_BUG' "$qa_file" 2>/dev/null; then qa_type="FUNCTIONAL_BUG"
    elif grep -q 'DESIGN_ISSUE' "$qa_file" 2>/dev/null; then qa_type="DESIGN_ISSUE"
    elif grep -q 'SPEC_ISSUE' "$qa_file" 2>/dev/null; then qa_type="SPEC_ISSUE"
    fi
  fi

  echo "[HARNESS] bugfix routing: $routing (type: ${qa_type:-unknown})"

  case "$routing" in
    engineer_direct)
      _bugfix_direct "$qa_file"
      ;;
    design)
      echo "[HARNESS] DESIGN_ISSUE → 루프 B 전환"
      run_design
      ;;
    architect_full|architect|*)
      _bugfix_full "$qa_file"
      ;;
  esac
}

# ── engineer 직접 경로 ─────────────────────────────────────────────
_bugfix_direct() {
  local qa_file="$1"
  local depth
  depth=$(detect_bugfix_depth "$qa_file")
  echo "[HARNESS] bugfix depth: $depth"

  # config 이벤트 기록 — harness-review.py가 depth를 파싱할 수 있도록
  [[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"%s","max_retries":3,"constraints_chars":%d}\n' \
    "${IMPL_FILE:-}" "$ISSUE_NUM" "$depth" "${#CONSTRAINTS}" >> "$RUN_LOG"

  local qa_out
  qa_out=$(head -c 30000 "$qa_file" 2>/dev/null)

  # impl 파일이 이미 있으면 architect 스킵
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] impl 존재 ($IMPL_FILE) → architect 스킵"
  elif [[ "$depth" == "fast" ]]; then
    echo "[HARNESS] depth=fast → architect Mode F 스킵, QA 출력을 engineer에 직접 전달"
  else
    echo "[HARNESS] Phase B2 — architect Bugfix Plan(Mode F) 호출 중"
    _agent_call "architect" 300 \
      "Bugfix Plan(Mode F) — ${qa_out} issue: #$ISSUE_NUM" \
      "/tmp/${PREFIX}_arch_out.txt"
    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""

    if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
      echo "[HARNESS] Mode F impl 생성 실패 → full 경로로 폴백"
      _bugfix_full "$qa_file"
      return
    fi
  fi

  # ── Feature branch 생성 ──────────────────────────────────────
  local FEATURE_BRANCH
  FEATURE_BRANCH=$(create_feature_branch "fix" "$ISSUE_NUM")
  export HARNESS_BRANCH="$FEATURE_BRANCH"
  echo "[HARNESS] feature branch: $FEATURE_BRANCH"

  local attempt=0
  local MAX_HOTFIX=3
  while [[ $attempt -lt $MAX_HOTFIX ]]; do
    attempt=$((attempt + 1))
    kill_check
    echo "[HARNESS] engineer 직접 (attempt $attempt/$MAX_HOTFIX, depth=$depth)"

    local eng_prompt=""
    if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
      local context
      context=$(cat "$IMPL_FILE" 2>/dev/null | head -c 30000)
      eng_prompt="impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: Bugfix Plan의 버그 수정 이행
context:
$context
constraints:
$CONSTRAINTS"
    else
      # fast: impl 없이 QA 출력 직접 전달
      eng_prompt="issue: #$ISSUE_NUM
task: 버그 수정 (QA 분석 기반)
qa_analysis:
$qa_out
constraints:
$CONSTRAINTS"
    fi

    local AGENT_EXIT=0
    _agent_call "engineer" 900 "$eng_prompt" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?

    if [[ $AGENT_EXIT -eq 124 ]]; then
      echo "[HARNESS] engineer timeout — 재시도"
      continue
    fi

    # vitest 실행
    echo "[HARNESS] vitest run (ground truth)"
    local vitest_exit=0
    if [[ "$depth" == "fast" ]]; then
      npx vitest run --changed HEAD --reporter=verbose 2>&1 | tail -100 > "/tmp/${PREFIX}_vitest_out.txt" || vitest_exit=$?
    else
      npx vitest run --reporter=verbose 2>&1 | tail -100 > "/tmp/${PREFIX}_vitest_out.txt" || vitest_exit=$?
    fi

    if [[ $vitest_exit -eq 0 ]]; then
      if [[ "$depth" == "fast" ]]; then
        # fast: validator 스킵 → 바로 commit
        echo "[HARNESS] depth=fast → validator 스킵"
      else
        # std: validator Mode D
        echo "[HARNESS] validator Bugfix Validation(Mode D) 호출 중"
        _agent_call "validator" 300 \
          "Mode D — Bugfix Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM vitest: PASS" \
          "/tmp/${PREFIX}_val_bf_out.txt"
        local bf_result
        bf_result=$(grep -oEm1 'BUGFIX_PASS|BUGFIX_FAIL|\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_bf_out.txt") || bf_result="UNKNOWN"

        if [[ "$bf_result" != "BUGFIX_PASS" && "$bf_result" != "PASS" ]]; then
          echo "[HARNESS] validator BUGFIX_FAIL — engineer 재시도"
          continue
        fi
        touch "/tmp/${PREFIX}_validator_b_passed"
      fi

      # commit
      commit_files=()
      while IFS= read -r _f; do [[ -n "$_f" ]] && commit_files+=("$_f"); done \
        < <(git status --short | grep -E "^ M|^M |^A " | awk '{print $2}')
      if [[ ${#commit_files[@]} -gt 0 ]]; then
        git add -- "${commit_files[@]}"
        git commit -m "$(generate_commit_msg) [bugfix-${depth}]"
        local impl_commit merge_commit
        impl_commit=$(git rev-parse --short HEAD)
        # merge to main — fast는 게이트 없음, std는 validator_b_passed 필요
        if ! merge_to_main "$FEATURE_BRANCH" "$ISSUE_NUM" "$depth" "$PREFIX"; then
          export HARNESS_RESULT="MERGE_CONFLICT_ESCALATE"
          echo "MERGE_CONFLICT_ESCALATE"
          echo "branch: $FEATURE_BRANCH"
          echo "impl_commit: $impl_commit"
          exit 1
        fi
        merge_commit=$(git rev-parse --short HEAD)
        export HARNESS_RESULT="HARNESS_DONE"
        echo "HARNESS_DONE (engineer_direct, depth=$depth)"
        echo "impl: ${IMPL_FILE:-N/A}"
        echo "issue: #$ISSUE_NUM"
        echo "commit: $merge_commit"
        exit 0
      else
        export HARNESS_RESULT="HARNESS_DONE"
        echo "[HARNESS] 변경사항 없음"
        exit 0
      fi
    else
      echo "[HARNESS] vitest 실패 (exit=$vitest_exit) — engineer 재시도"
    fi
  done

  rm -f "/tmp/${PREFIX}_plan_validation_passed"
  export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
  echo "IMPLEMENTATION_ESCALATE (engineer_direct ${MAX_HOTFIX}회 실패)"
  echo "branch: ${FEATURE_BRANCH:-unknown}"
  exit 1
}

# ── full 경로: architect Mode B → validator Plan Validation → engineer 직접 ──
# NOTE: run_impl은 exit 0으로 전체 스크립트를 종료하므로 호출하지 않는다.
#       validator를 인라인 처리하고, PASS 시 _bugfix_direct로 위임한다.
_bugfix_full() {
  local qa_file="$1"
  local qa_out
  qa_out=$(head -c 30000 "$qa_file" 2>/dev/null)

  BRANCH_TYPE="fix"  # bugfix full → fix/ 브랜치
  echo "[HARNESS] Phase B2 — architect bugfix Mode B (full) 호출 중"
  _agent_call "architect" 900 \
    "버그픽스 — Module Plan(Mode B) — ${qa_out} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_out.txt"
  IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # ── Inline Plan Validation (Mode C) — run_impl의 exit 0 문제 회피 ──
  echo "[HARNESS] Phase B2.5 — validator Plan Validation (Mode C) 호출 중"
  _agent_call "validator" 300 \
    "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_val_pv_out.txt"
  local val_result
  val_result=$(grep -oEm1 '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out.txt") || val_result="UNKNOWN"
  echo "[HARNESS] Phase B2.5 — Plan Validation 결과: $val_result"

  if [[ "$val_result" != "PASS" ]]; then
    # FAIL → architect 재보강 1회 → 재검증
    echo "[HARNESS] Phase B2.5 — FAIL → architect 재보강 중"
    local fail_feedback
    fail_feedback=$(tail -20 "/tmp/${PREFIX}_val_pv_out.txt")
    _agent_call "architect" 900 \
      "SPEC_GAP(Mode C) — Plan Validation FAIL 피드백 반영. impl: $IMPL_FILE feedback: ${fail_feedback}" \
      "/tmp/${PREFIX}_arch_fix_out.txt"

    _agent_call "validator" 300 \
      "Mode C — Plan Validation — impl: $IMPL_FILE issue: #$ISSUE_NUM" \
      "/tmp/${PREFIX}_val_pv_out2.txt"
    val_result=$(grep -oEm1 '\bPASS\b|\bFAIL\b' "/tmp/${PREFIX}_val_pv_out2.txt") || val_result="UNKNOWN"
    echo "[HARNESS] Phase B2.5 — 재검증 결과: $val_result"

    if [[ "$val_result" != "PASS" ]]; then
      export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
      echo "PLAN_VALIDATION_ESCALATE (bugfix_full)"
      tail -20 "/tmp/${PREFIX}_val_pv_out2.txt"
      exit 1
    fi
  fi

  touch "/tmp/${PREFIX}_plan_validation_passed"
  echo "[HARNESS] Plan Validation PASS → engineer 직접 경로로 전환"

  # _bugfix_direct: IMPL_FILE 설정 상태를 감지해 architect 스킵 → engineer 루프 직행
  _bugfix_direct "$qa_file"
}
