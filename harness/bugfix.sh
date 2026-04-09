#!/bin/bash
# ~/.claude/harness/bugfix.sh
# bugfix 모드: qa 라우팅 기반 4-way 분기 (functional_bug/architect_full/design/backlog)
#
# functional_bug 경로 세부:
#   fast (AFFECTED_FILES ≤ 2): QA → engineer 직행 (architect 스킵)
#   std  (그 외):              QA → architect 경량 Bugfix Plan → engineer → vitest → validator
#
# harness/executor.sh에서 source — 전역변수(PREFIX, IMPL_FILE, ISSUE_NUM 등) 사용

# ══════════════════════════════════════════════════════════════════════
# run_bugfix — bugfix 모드 진입점
# ══════════════════════════════════════════════════════════════════════
run_bugfix() {
  rotate_harness_logs "$PREFIX" "bugfix"
  # 루프 타입별 컨텍스트 prepend
  local _lc
  _lc=$(build_loop_context "bugfix" 2>/dev/null || true)
  if [[ -n "$_lc" ]]; then
    CONTEXT="${_lc}
${CONTEXT}"
  fi

  # ── 필수 파라미터 검증: bugfix는 --bug 또는 --issue 필요 ──
  if [[ -z "$BUG_DESC" && ( -z "$ISSUE_NUM" || "$ISSUE_NUM" == "N" ) ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] 오류: bugfix 모드는 --bug 또는 --issue가 필요합니다"
    echo "사용법: harness/executor.sh bugfix --bug <설명> --issue <번호>"
    exit 1
  fi

  # ── 재진입 상태 감지 (역순 체크) ──

  # 1. impl 파일 있으면 → QA + architect 스킵, engineer 직접
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: impl 존재 ($IMPL_FILE) → engineer 직접"
    echo "[재진입 — impl 파일 기반. QA 스킵]" > "/tmp/${PREFIX}_qa_out.txt"
    _bugfix_direct "/tmp/${PREFIX}_qa_out.txt"
    return
  fi

  # 2. GitHub issue에 QA 리포트 있으면 → QA 스킵, bugfix_run으로 라우팅
  if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
    local issue_body
    issue_body=$(gh issue view "$ISSUE_NUM" --json body -q .body 2>/dev/null || echo "")
    if echo "$issue_body" | grep -qE 'QA_REPORT|QA_SUMMARY|FUNCTIONAL_BUG|SPEC_ISSUE|DESIGN_ISSUE'; then
      echo "[HARNESS] 재진입: GitHub issue #${ISSUE_NUM}에 QA 리포트 존재 → QA 스킵"
      echo "$issue_body" > "/tmp/${PREFIX}_qa_out.txt"
      _bugfix_route
      return
    fi
  fi

  # 3. 신규 — QA부터 시작

  # ── 기존 이슈 목록 수집 (중복 방지용, 실패해도 무시) ──
  local recent_bugs=""
  recent_bugs=$(gh issue list --limit 5 --label bug --state open \
    --json number,title -q '.[] | "#\(.number) \(.title)"' 2>/dev/null || echo "")

  # ── qa 버그 분석 ──
  echo "[HARNESS] qa 버그 분석"
  local existing_issues_block=""
  if [[ -n "$recent_bugs" ]]; then
    existing_issues_block="
기존 이슈 목록 (중복 시 DUPLICATE_OF로 보고, 신규 이슈 생성 금지):
$recent_bugs"
  fi

  # --issue가 있으면 신규 이슈 생성 스킵 지시
  local issue_skip_note=""
  if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
    issue_skip_note="
기존 이슈 #$ISSUE_NUM 이 전달됨 — 신규 이슈 생성 금지. 분석 결과만 출력하라."
  fi

  local _qa_exit=0
  _agent_call "qa" 600 \
    "[하네스 경유 — 역질문 금지. 가용 정보로 즉시 판단하라]
bug: $BUG_DESC issue: #$ISSUE_NUM${existing_issues_block}${issue_skip_note}
분석 완료 후 이슈를 등록하라 (DUPLICATE_OF이거나 기존 이슈가 전달된 경우 생성 금지).
QA는 Bugs 마일스톤에만 이슈를 생성한다. Feature 마일스톤 이슈 생성 권한 없음.
- FUNCTIONAL_BUG → Bugs 마일스톤 (라벨: bug)
- SPEC_ISSUE → Bugs 마일스톤 (라벨: bug, spec-gap)
- DESIGN_ISSUE → Bugs 마일스톤 (라벨: bug, design-fix)" \
    "/tmp/${PREFIX}_qa_out.txt" || _qa_exit=$?

  # ── QA 실패/타임아웃 감지 ──
  if [[ $_qa_exit -eq 124 || $_qa_exit -eq 142 ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] QA 타임아웃 (exit=$_qa_exit) — --bug 설명에 파일명/함수명을 구체화하면 QA 탐색 범위가 줄어듭니다"
    exit 1
  elif [[ $_qa_exit -ne 0 ]]; then
    export HARNESS_RESULT="HARNESS_CRASH"
    echo "[HARNESS] QA 실패 (exit=$_qa_exit)"
    exit 1
  fi

  # ── DUPLICATE_OF 감지: 중복이면 기존 이슈로 리다이렉트 ──
  local dup_of=""
  dup_of=$(_parse_qa_summary "/tmp/${PREFIX}_qa_out.txt" "DUPLICATE_OF")
  if [[ -n "$dup_of" && "$dup_of" != "N" ]]; then
    local dup_num="${dup_of//#/}"
    echo "[HARNESS] 중복 이슈 감지: #$dup_num → 기존 이슈로 라우팅"
    ISSUE_NUM="$dup_num"
  fi

  _bugfix_route
}

# ══════════════════════════════════════════════════════════════════════
# 이하 bugfix 헬퍼 함수
# ══════════════════════════════════════════════════════════════════════

# ── QA_SUMMARY 파싱: footer 우선, 기존 grep 폴백 ───────────────────
_parse_qa_summary() {
  local qa_file="$1"
  local field="$2"
  local value=""
  value=$(sed -n '/---QA_SUMMARY---/,/---END_QA_SUMMARY---/p' "$qa_file" \
    | grep -F "${field}:" | sed "s/.*${field}: //" | tr -d '[:space:]')
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

  # SEVERITY:HIGH → std 강제
  local severity=""
  severity=$(_parse_qa_summary "$qa_file" "SEVERITY")
  if [[ "$severity" == "HIGH" ]]; then
    echo "std"
    return
  fi

  if [[ "$qa_type" == "FUNCTIONAL_BUG" ]] && [[ -n "$affected" ]] && [[ "$affected" -le 2 ]] 2>/dev/null; then
    echo "fast"
  else
    echo "std"
  fi
}

# ── 메인 라우팅: QA_SUMMARY 파싱 → 4-way 분기 ────────────────────
_bugfix_route() {
  local qa_file="/tmp/${PREFIX}_qa_out.txt"

  # KNOWN_ISSUE 감지: qa가 원인 특정 불가 → 즉시 에스컬레이션
  if grep -qF 'KNOWN_ISSUE' "$qa_file" 2>/dev/null; then
    export HARNESS_RESULT="KNOWN_ISSUE"
    echo "KNOWN_ISSUE: qa가 1회 분석으로 원인을 특정하지 못함"
    echo "issue: #$ISSUE_NUM"
    head -50 "$qa_file" | grep -A5 'KNOWN_ISSUE' 2>/dev/null || true
    exit 1
  fi

  # SCOPE_ESCALATE: 관련 모듈/파일 = 0 → 신규 기능, 즉시 중단
  local routing=""
  routing=$(_parse_qa_summary "$qa_file" "ROUTING")

  if [[ "$routing" == "scope_escalate" ]] || grep -qF 'SCOPE_ESCALATE' "$qa_file" 2>/dev/null; then
    export HARNESS_RESULT="SCOPE_ESCALATE"
    echo "SCOPE_ESCALATE: 관련 모듈/파일 없음 — 신규 기능으로 판정"
    echo "issue: #$ISSUE_NUM"
    head -50 "$qa_file" | grep -A5 'SCOPE_ESCALATE' 2>/dev/null || true
    exit 1
  fi

  # QA_SUMMARY footer 우선 파싱
  if [[ -z "$routing" ]]; then
    # 폴백: grep 방식
    routing="architect"
    if grep -qF 'FUNCTIONAL_BUG' "$qa_file" 2>/dev/null; then
      routing="functional_bug"
    elif grep -qF 'DESIGN_ISSUE' "$qa_file" 2>/dev/null; then
      routing="design"
    elif grep -qF 'SPEC_ISSUE' "$qa_file" 2>/dev/null; then
      routing="architect"
    fi
  fi

  local qa_type=""
  qa_type=$(_parse_qa_summary "$qa_file" "TYPE")
  if [[ -z "$qa_type" ]]; then
    # 폴백
    if grep -qF 'FUNCTIONAL_BUG' "$qa_file" 2>/dev/null; then qa_type="FUNCTIONAL_BUG"
    elif grep -qF 'DESIGN_ISSUE' "$qa_file" 2>/dev/null; then qa_type="DESIGN_ISSUE"
    elif grep -qF 'SPEC_ISSUE' "$qa_file" 2>/dev/null; then qa_type="SPEC_ISSUE"
    fi
  fi

  echo "[HARNESS] bugfix routing: $routing (type: ${qa_type:-unknown})"

  case "$routing" in
    functional_bug)
      _bugfix_direct "$qa_file"
      ;;
    design)
      echo "[HARNESS] DESIGN_ISSUE → 디자인 루프 전환"
      export HARNESS_RESULT="DESIGN_ISSUE"
      echo "DESIGN_ISSUE: 디자인 루프로 전환 필요"
      echo "issue: #$ISSUE_NUM"
      echo "필요 조치: mode:design 완료 후 mode:impl 재호출"
      exit 0
      ;;
    backlog)
      echo "[HARNESS] BACKLOG — 이슈 생성 후 대기 (즉시 수정 불필요)"
      export HARNESS_RESULT="BACKLOG"
      echo "BACKLOG: 기능 요청/저우선 → 이슈 생성 후 대기"
      echo "issue: #$ISSUE_NUM"
      exit 0
      ;;
    architect_full|architect|*)
      _bugfix_full "$qa_file"
      ;;
  esac
}

# ── FUNCTIONAL_BUG 경로 ───────────────────────────────────────────
# fast (AFFECTED_FILES ≤ 2): QA → engineer 직행
# std  (그 외):              QA → architect 경량 Bugfix Plan → engineer → vitest → validator
_bugfix_direct() {
  local qa_file="$1"
  local depth
  if [[ "$DEPTH" != "auto" && -n "$DEPTH" ]]; then
    depth="$DEPTH"
  else
    depth=$(detect_bugfix_depth "$qa_file")
  fi

  # 실제 실행 흐름 로그 (depth 기반)
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] bugfix flow: functional_bug — impl 재진입 → engineer 직행"
  elif [[ "$depth" == "fast" ]]; then
    echo "[HARNESS] bugfix flow: functional_bug/fast → engineer 직행 (architect 스킵)"
  else
    echo "[HARNESS] bugfix flow: functional_bug/std → architect 경량 계획 → engineer"
  fi
  echo "[HARNESS] bugfix depth: $depth"

  # CONSTRAINTS 로딩 (impl-process.sh와 동일 로직)
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

  # config 이벤트 기록
  [[ -n "$RUN_LOG" ]] && printf '{"event":"config","impl_file":"%s","issue":"%s","depth":"%s","max_retries":3,"constraints_chars":%d}\n' \
    "${IMPL_FILE:-}" "$ISSUE_NUM" "$depth" "${#CONSTRAINTS}" >> "$RUN_LOG"

  local qa_out
  qa_out=$(head -c 30000 "$qa_file" 2>/dev/null)

  # impl 파일이 이미 있으면 architect 스킵
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] impl 존재 ($IMPL_FILE) → architect 스킵"
  elif [[ "$depth" == "fast" ]]; then
    echo "[HARNESS] depth=fast → architect Bugfix Plan 스킵, QA 출력을 engineer에 직접 전달"
  else
    echo "[HARNESS] architect 버그픽스 계획 작성"
    _agent_call "architect" 600 \
      "@MODE:ARCHITECT:BUGFIX_PLAN
qa 분석: ${qa_out} issue: #$ISSUE_NUM" \
      "/tmp/${PREFIX}_arch_out.txt"
    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""

    if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
      echo "[HARNESS] Bugfix Plan impl 생성 실패 → full 경로로 폴백"
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
  local error_trace=""
  # HIST_DIR/bugfix — attempt별 구조화 히스토리
  local HIST_DIR="/tmp/${PREFIX}_history"
  local LOOP_OUT_DIR="${HIST_DIR}/bugfix"
  mkdir -p "$LOOP_OUT_DIR"
  while [[ $attempt -lt $MAX_HOTFIX ]]; do
    attempt=$((attempt + 1))
    kill_check
    echo "[HARNESS] engineer 직접 (attempt $attempt/$MAX_HOTFIX, depth=$depth)"

    # attempt 디렉토리 생성 → prune → 파일 기록
    local attempt_dir="${LOOP_OUT_DIR}/attempt-${attempt}"
    mkdir -p "$attempt_dir"
    prune_history "$LOOP_OUT_DIR"

    local eng_prompt=""
    if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
      local context
      context=$(build_smart_context "$IMPL_FILE" 0)
      local explore_instr=""
      if [[ $attempt -gt 1 ]]; then
        explore_instr="
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/attempt-$((attempt-1))/vitest.log")"
      fi
      eng_prompt="impl: $IMPL_FILE
issue: #$ISSUE_NUM
task: Bugfix Plan의 버그 수정 이행${explore_instr}
context:
$context
constraints:
$CONSTRAINTS"
    else
      # fast: impl 없이 QA 출력 직접 전달 (qa_out은 QA 에이전트 원본 분석 — 인라인 유지)
      local explore_instr=""
      if [[ $attempt -gt 1 ]]; then
        explore_instr="
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/attempt-$((attempt-1))/vitest.log")"
      fi
      eng_prompt="issue: #$ISSUE_NUM
task: 버그 수정 (QA 분석 기반)${explore_instr}
qa_analysis:
$qa_out
constraints:
$CONSTRAINTS"
    fi

    local AGENT_EXIT=0
    _agent_call "engineer" 900 "$eng_prompt" "/tmp/${PREFIX}_eng_out.txt" || AGENT_EXIT=$?
    # attempt_dir에 저장
    cp "/tmp/${PREFIX}_eng_out.txt" "${attempt_dir}/engineer.log" 2>/dev/null || true

    if [[ $AGENT_EXIT -eq 124 ]]; then
      echo "[HARNESS] engineer timeout — 재시도"
      continue
    fi

    # ── 즉시 커밋: engineer 변경을 feature branch에 기록 ──────────
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
        # fast: validator 스킵 → validator_b_passed 자동 touch (bugfix merge 게이트용)
        echo "[HARNESS] depth=fast → validator 스킵"
        touch "/tmp/${PREFIX}_validator_b_passed"
      else
        # std: validator Bugfix Validation
        echo "[HARNESS] validator Bugfix Validation"
        local val_ctx
        val_ctx=$(build_validator_context "$IMPL_FILE")
        _agent_call "validator" 300 \
          "@MODE:VALIDATOR:BUGFIX_VALIDATION
impl: $IMPL_FILE issue: #$ISSUE_NUM vitest: PASS
context:
$val_ctx" \
          "/tmp/${PREFIX}_val_bf_out.txt"
        local bf_result
        bf_result=$(parse_marker "/tmp/${PREFIX}_val_bf_out.txt" "BUGFIX_PASS|BUGFIX_FAIL|PASS|FAIL")

        if [[ "$bf_result" != "BUGFIX_PASS" && "$bf_result" != "PASS" ]]; then
          error_trace=$(cat "/tmp/${PREFIX}_val_bf_out.txt" 2>/dev/null | head -c 5000 || echo "BUGFIX_FAIL")
          echo "[HARNESS] validator BUGFIX_FAIL — engineer 재시도"
          continue
        fi
        touch "/tmp/${PREFIX}_validator_b_passed"
      fi

      # commit + merge (depth="bugfix" 고정: merge 게이트는 validator_b_passed 사용)
      if ! harness_commit_and_merge "$FEATURE_BRANCH" "$ISSUE_NUM" "bugfix" "$PREFIX" "[bugfix-${depth}]"; then
        exit 1  # MERGE_CONFLICT_ESCALATE (harness_commit_and_merge가 설정)
      fi
      local merge_commit
      merge_commit=$(git rev-parse --short HEAD)
      export HARNESS_RESULT="HARNESS_DONE"
      echo "HARNESS_DONE (functional_bug, depth=$depth)"
      echo "impl: ${IMPL_FILE:-N/A}"
      echo "issue: #$ISSUE_NUM"
      echo "commit: $merge_commit"
      exit 0
    else
      error_trace=$(cat "/tmp/${PREFIX}_vitest_out.txt" 2>/dev/null | head -c 5000 || echo "vitest exit=$vitest_exit")
      # vitest 실패 결과 보존 + meta.json
      cp "/tmp/${PREFIX}_vitest_out.txt" "${attempt_dir}/vitest.log" 2>/dev/null || true
      local chg_bf; chg_bf=$(git diff HEAD~1 --name-only 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//' || echo "")
      write_attempt_meta "${attempt_dir}/meta.json" "$attempt" "bugfix" "$depth" "FAIL" \
        "test_fail" "" "$chg_bf" "engineer" \
        "vitest exit=$vitest_exit" "${attempt_dir}/vitest.log 의 실패 케이스 확인"
      echo "[HARNESS] vitest 실패 (exit=$vitest_exit) — engineer 재시도"
    fi
  done

  rm -f "/tmp/${PREFIX}_plan_validation_passed"
  export HARNESS_RESULT="IMPLEMENTATION_ESCALATE"
  echo "IMPLEMENTATION_ESCALATE (functional_bug ${MAX_HOTFIX}회 실패)"
  echo "branch: ${FEATURE_BRANCH:-unknown}"
  exit 1
}

# ── full 경로: architect Module Plan → validator Plan Validation → engineer 직접 ──
_bugfix_full() {
  local qa_file="$1"
  local qa_out
  qa_out=$(head -c 30000 "$qa_file" 2>/dev/null)

  BRANCH_TYPE="fix"  # bugfix full → fix/ 브랜치
  echo "[HARNESS] architect 버그픽스 전체 계획 작성"
  _agent_call "architect" 900 \
    "@MODE:ARCHITECT:MODULE_PLAN
버그픽스 — qa 분석: ${qa_out} issue: #$ISSUE_NUM" \
    "/tmp/${PREFIX}_arch_out.txt"
  IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # ── Plan Validation (공용 함수 활용) ──
  echo "[HARNESS] Plan Validation"
  if ! run_plan_validation "$IMPL_FILE" "$ISSUE_NUM" "$PREFIX" 1; then
    export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
    echo "PLAN_VALIDATION_ESCALATE (bugfix_full)"
    exit 1
  fi

  echo "[HARNESS] Plan Validation PASS → engineer 직접 경로로 전환"

  # _bugfix_direct: IMPL_FILE 설정 상태를 감지해 architect 스킵 → engineer 루프 직행
  _bugfix_direct "$qa_file"
}
