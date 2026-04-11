#!/bin/bash
# ~/.claude/harness/impl.sh
# 루프 C (구현 루프): plan_validation_passed → depth별 dispatcher (simple/std/deep)
# planning fallback: impl 없으면 architect MODULE_PLAN 또는 LIGHT_PLAN → validator Plan Validation
#
# QA/DESIGN_HANDOFF 경로:
#   impl 파일 없이 --issue <N>만 지정 → pre-analysis → architect LIGHT_PLAN → depth별 라우팅
#
# harness/executor.sh에서 source — 전역변수(PREFIX, IMPL_FILE, ISSUE_NUM 등) 사용

# ── depth frontmatter 강제 검증 ──────────────────────────────────────
# architect가 impl 파일 생성 시 depth: frontmatter를 누락하면
# 마이크로 재호출(1회, 60초)로 패치. 실패 시 경고 + std 폴백 (루프 안 끊김).
ensure_depth_frontmatter() {
  local impl="$1" issue="$2" prefix="$3"
  [[ -z "$impl" || ! -f "$impl" ]] && return 0

  # frontmatter depth: 필드 존재 여부 확인
  local has_depth
  has_depth=$(awk '/^---$/{n++} n==1 && /^depth:/{print; exit}' "$impl" 2>/dev/null || echo "")

  if [[ -n "$has_depth" ]]; then
    echo "[HARNESS] depth frontmatter 확인: $(echo "$has_depth" | head -1 | xargs)"
    return 0
  fi

  # frontmatter 자체가 없는지, 있는데 depth만 빠진건지 구분
  local has_frontmatter
  has_frontmatter=$(head -1 "$impl" | grep -c '^---$' || echo "0")

  echo "[HARNESS] ⚠️ impl 파일에 depth frontmatter 누락 — architect 마이크로 패치 호출"
  _agent_call "architect" 60 \
    "@MODE:ARCHITECT:SPEC_GAP
이 impl 파일에 YAML frontmatter depth 필드가 누락됐다.
파일 첫 줄부터 --- 블록을 추가하고 depth: simple|std|deep 중 하나를 선언하라.
기준: behavior 불변(이름·텍스트·스타일·색상·애니메이션·설정값)=simple, behavior 변경(로직·API·DB)=std, 보안 민감=deep.
impl: $impl
issue: #$issue
기존 frontmatter 유무: $( [[ "$has_frontmatter" -gt 0 ]] && echo '있음(depth만 누락)' || echo '없음')
파일 내용 확인 후 depth만 추가하라. 다른 내용은 수정하지 마라." \
    "${STATE_DIR}/${prefix}_depth_patch_out.txt"

  # 재확인
  has_depth=$(awk '/^---$/{n++} n==1 && /^depth:/{print; exit}' "$impl" 2>/dev/null || echo "")
  if [[ -n "$has_depth" ]]; then
    echo "[HARNESS] depth 패치 성공: $(echo "$has_depth" | head -1 | xargs)"
  else
    echo "[HARNESS] ⚠️ depth 패치 실패 — std 폴백 적용 (architect 프롬프트 개선 필요)"
    [[ -n "$RUN_LOG" ]] && printf '{"event":"warn","msg":"depth_frontmatter_missing_after_retry","impl":"%s","t":%d}\n' \
      "$impl" "$(date +%s)" >> "$RUN_LOG"
  fi
}

run_impl() {
  # ── 재진입 상태 감지 ──
  # plan_validation_passed 플래그 + impl 파일 있으면 → engineer 루프로 바로 진입
  if [[ -f "${STATE_DIR}/${PREFIX}_plan_validation_passed" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    echo "[HARNESS] 재진입: plan_validation_passed + impl 존재 → engineer 루프 직접 진입"
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    local sub_script="${IMPL_SCRIPT_DIR}/impl_${DEPTH}.sh"
    bash "$sub_script" --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --branch-type "$BRANCH_TYPE"
    return
  fi

  # UI 키워드 감지 (design 루프 전환 판단)
  # bug/fix/hotfix 라벨 이슈는 스킵 — 버그픽스도 UI 컴포넌트를 수정하므로 오탐 방지
  local _skip_design_check=false
  if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
    local _issue_labels_cache
    _issue_labels_cache=$(gh issue view "$ISSUE_NUM" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
    if echo "$_issue_labels_cache" | grep -qiE "bug|fix|hotfix"; then
      _skip_design_check=true
    fi
  fi

  if [[ "$_skip_design_check" == "false" && -n "$IMPL_FILE" && -f "$IMPL_FILE" ]]; then
    local ui_kw
    ui_kw=$(grep -iE "화면|컴포넌트|레이아웃|UI|스타일|디자인|색상|애니메이션|오버레이" "$IMPL_FILE" || true)
    if [[ -n "$ui_kw" && ! -f "${STATE_DIR}/${PREFIX}_design_critic_passed" ]]; then
      export HARNESS_RESULT="UI_DESIGN_REQUIRED"
      echo "UI_DESIGN_REQUIRED"
      echo "impl: $IMPL_FILE"
      echo "이유: $ui_kw"
      echo "필요 조치: mode:design 완료 후 mode:impl 재호출"
      exit 0
    fi
  fi

  # run_bugfix → run_impl 이중 로테이션 방지: RUN_LOG 이미 설정돼있으면 스킵
  [[ -z "$RUN_LOG" ]] && rotate_harness_logs "$PREFIX" "impl" "$ISSUE_NUM"

  # ── 히스토리: 런 단위 디렉토리 생성 (architect 출력 보존용) ──
  local _hist_dir="${STATE_DIR}/${PREFIX}_history"
  local _impl_run_dir="${_hist_dir}/impl/run_${HARNESS_RUN_TS:-$(date +%Y%m%d_%H%M%S)}"
  mkdir -p "$_impl_run_dir"
  export HARNESS_HIST_DIR="$_impl_run_dir"

  # impl 파일 없으면 architect 호출 (MODULE_PLAN 또는 LIGHT_PLAN)
  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    # issue labels 또는 이슈 본문으로 LIGHT_PLAN vs MODULE_PLAN 분기
    local issue_labels=""
    local issue_summary=""
    local suspected_files=""
    local arch_mode="MODULE_PLAN"

    if [[ -n "$ISSUE_NUM" && "$ISSUE_NUM" != "N" ]]; then
      # issue 정보 읽기
      issue_labels=$(gh issue view "$ISSUE_NUM" --json labels -q '[.labels[].name] | join(",")' 2>/dev/null || echo "")
      issue_summary=$(gh issue view "$ISSUE_NUM" --json title,body -q '"## " + .title + "\n\n" + .body' 2>/dev/null || echo "")

      # bug/design-fix 라벨 또는 DESIGN_HANDOFF 이슈 → LIGHT_PLAN
      if echo "$issue_labels" | grep -qiE "bug|design-fix|fix|hotfix|cleanup" || \
         echo "$issue_summary" | grep -q "DESIGN_HANDOFF"; then
        arch_mode="LIGHT_PLAN"
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

    if [[ "$arch_mode" == "LIGHT_PLAN" ]]; then
      # depth 힌트: 외부 전달(--depth) > DESIGN_HANDOFF > 라벨 기반 > 미지정
      local depth_hint=""
      if [[ "$DEPTH" != "auto" ]]; then
        depth_hint="$DEPTH"
      elif echo "$issue_summary" | grep -q "DESIGN_HANDOFF"; then
        depth_hint="simple"
      elif echo "$issue_labels" | grep -qiE "bug|fix|hotfix|cleanup"; then
        depth_hint="simple"
      fi

      local depth_prompt=""
      if [[ -n "$depth_hint" ]]; then
        depth_prompt="스킬/하네스 추천: ${depth_hint} (참고용 — architect가 이슈 내용 기반으로 최종 판단. 상향/하향 모두 가능)"
      else
        depth_prompt="추천 없음 — 이슈 내용 기반으로 architect가 직접 판단"
      fi

      echo "[HARNESS] architect LIGHT_PLAN 작성 (issue #${ISSUE_NUM}, depth_hint=${depth_hint:-none})"
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:LIGHT_PLAN
issue #${ISSUE_NUM}
suspected_files: ${suspected_files}
labels: ${issue_labels}
issue_summary:
${issue_summary}
context: ${CONTEXT}

[DEPTH 선택 — frontmatter depth: 필드 필수]
기준: 이 이슈의 구현이 기존 코드 구조 수정으로 완결되는가, 새 로직 구조를 신설해야 하는가?
- simple: 기존 구조 수정 — 값·조건·스타일·요소 변경, 코드 제거/정리
- std: 새 로직 구조 신설 — 새 함수·모듈·상태·API·데이터 흐름
- deep: 보안·결제·인증
${depth_prompt}" \
        "${STATE_DIR}/${PREFIX}_arch_out.txt"
    else
      echo "[HARNESS] architect Module Plan 작성"
      _agent_call "architect" 900 \
        "@MODE:ARCHITECT:MODULE_PLAN
issue #${ISSUE_NUM} impl 계획 작성. context: ${CONTEXT}" \
        "${STATE_DIR}/${PREFIX}_arch_out.txt"
    fi

    # architect 결과 마커 확인 (LIGHT_PLAN_READY 또는 READY_FOR_IMPL)
    local arch_marker
    arch_marker=$(parse_marker "${STATE_DIR}/${PREFIX}_arch_out.txt" "LIGHT_PLAN_READY|READY_FOR_IMPL|PRODUCT_PLANNER_ESCALATION_NEEDED|TECH_CONSTRAINT_CONFLICT")
    if [[ "$arch_marker" == "PRODUCT_PLANNER_ESCALATION_NEEDED" ]]; then
      export HARNESS_RESULT="PRODUCT_PLANNER_ESCALATION_NEEDED"
      echo "PRODUCT_PLANNER_ESCALATION_NEEDED"
      exit 1
    fi
    if [[ "$arch_marker" == "TECH_CONSTRAINT_CONFLICT" ]]; then
      export HARNESS_RESULT="TECH_CONSTRAINT_CONFLICT"
      echo "TECH_CONSTRAINT_CONFLICT"
      exit 1
    fi
    IMPL_FILE=$(grep -oEm1 'docs/[^ ]+\.md' "${STATE_DIR}/${PREFIX}_arch_out.txt") || IMPL_FILE=""
    echo "[HARNESS] impl: $IMPL_FILE"
  fi

  if [[ -z "$IMPL_FILE" || ! -f "$IMPL_FILE" ]]; then
    export HARNESS_RESULT="SPEC_GAP_ESCALATE"
    echo "SPEC_GAP_ESCALATE: architect가 impl 파일을 생성하지 못했다."
    exit 1
  fi

  # ── depth frontmatter 강제 검증 ──────────────────────────────────
  # architect가 impl 파일에 depth: 선언을 빠뜨리면 마이크로 재호출 (1회, 60초)
  ensure_depth_frontmatter "$IMPL_FILE" "$ISSUE_NUM" "$PREFIX"

  # Plan Validation (구현 전 게이트)
  echo "[HARNESS] Plan Validation"
  if run_plan_validation "$IMPL_FILE" "$ISSUE_NUM" "$PREFIX" 1; then
    echo "$IMPL_FILE" > "${STATE_DIR}/${PREFIX}_impl_path"
    echo "PLAN_VALIDATION_PASS"
    echo "impl: $IMPL_FILE"
    echo "issue: #$ISSUE_NUM"
    # validation PASS → engineer 루프로 직접 진입 (재호출 불필요)
    [[ "$DEPTH" == "auto" ]] && DEPTH=$(detect_depth "$IMPL_FILE")
    echo "[HARNESS] depth: $DEPTH"
    local sub_script="${IMPL_SCRIPT_DIR}/impl_${DEPTH}.sh"
    bash "$sub_script" --impl "$IMPL_FILE" --issue "$ISSUE_NUM" --prefix "$PREFIX" --branch-type "$BRANCH_TYPE"
    return
  fi

  export HARNESS_RESULT="PLAN_VALIDATION_ESCALATE"
  echo "PLAN_VALIDATION_ESCALATE"
  exit 1
}
