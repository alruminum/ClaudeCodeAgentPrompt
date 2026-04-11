#!/bin/bash
# ~/.claude/harness/impl.sh
# 루프 C (구현 루프): plan_validation_passed → depth별 dispatcher (simple/std/deep)
# planning fallback: impl 없으면 architect MODULE_PLAN 또는 BUGFIX_PLAN → validator Plan Validation
#
# QA/DESIGN_HANDOFF 경로:
#   impl 파일 없이 --issue <N>만 지정 → pre-analysis → architect BUGFIX_PLAN → depth별 라우팅
#
# harness/executor.sh에서 source — 전역변수(PREFIX, IMPL_FILE, ISSUE_NUM 등) 사용

run_impl() {
  # ── 재진입 상태 감지 ──
  # plan_validation_passed 플래그 + impl 파일 있으면 → engineer 루프로 바로 진입
  if [[ -f "/tmp/${PREFIX}_plan_validation_passed" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: plan_validation_passed + impl 존재 → engineer 루프 직접 진입"
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    local sub_script="${IMPL_SCRIPT_DIR}/impl_${DEPTH}.sh"
    bash "$sub_script" --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --branch-type "$BRANCH_TYPE"
    return
  fi

  # UI 키워드 감지 (design 루프 전환 판단)
  if [[ -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    local ui_kw
    ui_kw=$(grep -iE "화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이" "$IMPL_FILE" || true)
    if [[ -n "$ui_kw" && ! -f "/tmp/${PREFIX}_design_critic_passed" ]]; then
      export HARNESS_RESULT="UI_DESIGN_REQUIRED"
      echo "UI_DESIGN_REQUIRED"
      echo "impl: $IMPL_FILE"
      echo "이유: $ui_kw"
      echo "필요 조치: mode:design 완료 후 mode:impl 재호출"
      exit 0
    fi
  fi

  # run_bugfix → run_impl 이중 로테이션 방지: RUN_LOG 이미 설정돼있으면 스킵
  [[ -z "$RUN_LOG" ]] && rotate_harness_logs "$PREFIX" "impl"

  # impl 파일 없으면 architect 호출 (MODULE_PLAN 또는 BUGFIX_PLAN)
  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    # issue labels로 BUGFIX_PLAN vs MODULE_PLAN 분기
    local issue_labels=""
    local issue_summary=""
    local suspected_files=""
    local arch_mode="MODULE_PLAN"

    if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
      # issue 정보 읽기
      issue_labels=$(gh issue view "$ISSUE_NUM" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
      issue_summary=$(gh issue view "$ISSUE_NUM" --json title,body -q '"## " + .title + "\n\n" + .body' 2>/dev/null || echo "")

      # bug/design-fix 라벨이면 BUGFIX_PLAN
      if echo "$issue_labels" | grep -qiE "bug|design-fix|fix|hotfix"; then
        arch_mode="BUGFIX_PLAN"
        # pre-analysis: suspected_files (issue 키워드 grep 상위 10개)
        local issue_title
        issue_title=$(gh issue view "$ISSUE_NUM" --json title -q '.title' 2>/dev/null || echo "")
        if [[ -n "$issue_title" ]]; then
          # 제목에서 키워드 추출 (한국어/영어 단어 2글자 이상)
          local keywords
          keywords=$(echo "$issue_title" | grep -oE '[a-zA-Z가-힣]{2,}' | head -5 | tr '\n' '|' | sed 's/|$//')
          if [[ -n "$keywords" ]]; then
            suspected_files=$(grep -rlE "$keywords" src/ 2>/dev/null | head -10 | tr '\n' ',' | sed 's/,$//' || echo "")
          fi
        fi
      fi
    fi

    if [[ "$arch_mode" == "BUGFIX_PLAN" ]]; then
      echo "[HARNESS] architect BUGFIX_PLAN 작성 (issue #${ISSUE_NUM})"
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:BUGFIX_PLAN
issue #${ISSUE_NUM}
suspected_files: ${suspected_files}
labels: ${issue_labels}
issue_summary:
${issue_summary}
context: ${CONTEXT}" \
        "/tmp/${PREFIX}_arch_out.txt"
    else
      echo "[HARNESS] architect Module Plan 작성"
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:MODULE_PLAN
issue #${ISSUE_NUM} impl 계획 작성. context: ${CONTEXT}" \
        "/tmp/${PREFIX}_arch_out.txt"
    fi

    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "/tmp/${PREFIX}_arch_out.txt") || IMPL_FILE=""
    echo "[HARNESS] impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # Plan Validation (구현 전 게이트)
  echo "[HARNESS] Plan Validation"
  if run_plan_validation "$IMPL_FILE" "$ISSUE_NUM" "$PREFIX" 1; then
    echo "$IMPL_FILE" > "/tmp/${PREFIX}_impl_path"
    export HARNESS_RESULT="PLAN_VALIDATION_PASS"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    echo "필요 조치: 계획 확인 후 mode:impl 로 재호출"
    exit 0
  fi

  export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
  echo "PLAN_VALIDATION_ESCALATE"
  exit 1
}
