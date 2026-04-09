#!/bin/bash
# ~/.claude/harness/design.sh
# design 모드: designer (Pencil MCP) → design-critic → 유저 선택 → DESIGN_HANDOFF
#
# 흐름 (orchestration/design.md 기반):
#   Phase 0: 컨텍스트 수집 + Pencil 캔버스 준비
#   Phase 1: designer — 3 variant (Pencil 프레임 + 스크린샷)
#   Phase 2: design-critic — PICK/ITERATE/ESCALATE 판정
#     PICK → Phase 3 유저 선택 안내 (DESIGN_DONE)
#     ITERATE → Phase 1 재시도 (max 3회)
#     ESCALATE → 유저 직접 선택 강제 (DESIGN_DONE)
#   Phase 4: 유저 variant 선택 후 DESIGN_HANDOFF → architect Module Plan (영향 시)
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

run_design() {
  rotate_harness_logs "$PREFIX" "design"
  # Phase C: 루프 타입별 컨텍스트를 CONTEXT에 prepend
  local _lc
  _lc=$(build_loop_context "design" 2>/dev/null || true)
  if [[ -n "$_lc" ]]; then
    CONTEXT="${_lc}
${CONTEXT}"
  fi
  local attempt=0
  local MAX=3
  # Phase B: HIST_DIR/design — round별 구조화 히스토리
  local HIST_DIR="/tmp/${PREFIX}_history"
  local LOOP_OUT_DIR="${HIST_DIR}/design"
  mkdir -p "$LOOP_OUT_DIR"

  while [[ $attempt -lt $MAX ]]; do
    kill_check
    # Phase B: round 디렉토리 생성 → prune → 파일 기록
    local round_dir="${LOOP_OUT_DIR}/round-${attempt}"
    mkdir -p "$round_dir"
    prune_history "$LOOP_OUT_DIR"

    hlog "Phase D1 attempt $((attempt+1))/$MAX — designer 호출 중 (Pencil MCP)"
    local designer_prompt="@MODE:DESIGNER:DEFAULT
issue: #${ISSUE_NUM}
context: ${CONTEXT}"
    if [[ $attempt -gt 0 ]]; then
      designer_prompt="${designer_prompt}
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/round-$((attempt-1))/critic.log")
design-critic 피드백을 직접 확인하고 개선된 variant를 생성하라."
    fi
    _agent_call "designer" 360 "$designer_prompt" "/tmp/${PREFIX}_des_out.txt"
    cp "/tmp/${PREFIX}_des_out.txt" "${round_dir}/designer.log" 2>/dev/null || true

    hlog "Phase D2 attempt $((attempt+1))/$MAX — design-critic 호출 중"
    _agent_call "design-critic" 300 \
      "@MODE:CRITIC:REVIEW
designer 출력 파일: ${round_dir}/designer.log
이 파일을 직접 읽어 variant 3개를 심사하라." \
      "/tmp/${PREFIX}_dc_out.txt"
    cp "/tmp/${PREFIX}_dc_out.txt" "${round_dir}/critic.log" 2>/dev/null || true
    local dc_result
    dc_result=$(parse_marker "/tmp/${PREFIX}_dc_out.txt" "PICK|ITERATE|ESCALATE")

    case "$dc_result" in
      PICK)
        hlog "PICK — Phase 3 유저 variant 선택 대기"
        touch "/tmp/${PREFIX}_design_critic_passed"

        # Phase 3 안내 메시지 출력
        echo ""
        echo "✅ Design-Critic PICK — 3개 variant가 준비됐습니다."
        echo ""
        echo "Pencil 캔버스에서 확인하세요:"
        # variant 설명 추출 (designer 출력에서)
        grep -A1 "## variant-A:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-A: /' 2>/dev/null || echo "  variant-A: Pencil 캔버스 확인"
        grep -A1 "## variant-B:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-B: /' 2>/dev/null || echo "  variant-B: Pencil 캔버스 확인"
        grep -A1 "## variant-C:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-C: /' 2>/dev/null || echo "  variant-C: Pencil 캔버스 확인"
        echo ""
        echo "Pencil에서 확인/수정 후 선택할 variant를 입력하세요 (A/B/C):"
        echo ""

        # DESIGN_HANDOFF → Phase 4는 유저 선택 후 메인 Claude가 수행
        export HARNESS_RESULT="DESIGN_DONE"
        # Phase B: PICK meta.json 기록
        local chg_d; chg_d=$(git diff HEAD~1 --name-only 2>/dev/null | head -3 | tr '\n' ',' | sed 's/,$//' || echo "")
        write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "PASS" \
          "" "" "$chg_d" "designer,design-critic" "" "PICK 완료 — 유저 variant 선택 대기"
        echo "DESIGN_DONE"
        echo "issue: #${ISSUE_NUM}"
        echo "variants: ${round_dir}/designer.log"
        echo "critic: ${round_dir}/critic.log"
        echo "필요 조치: Pencil 캔버스에서 variant 확인 후 선택 입력 (A/B/C) → DESIGN_HANDOFF 진행"
        exit 0
        ;;
      ITERATE)
        # Phase B: ITERATE meta.json 기록
        write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "FAIL" \
          "iterate" "" "" "designer,design-critic" "ITERATE" "${round_dir}/critic.log 에서 피드백 확인 후 개선"
        attempt=$((attempt+1))
        hlog "ITERATE — designer 재시도 ($attempt/$MAX)"
        continue
        ;;
      ESCALATE)
        hlog "ESCALATE — design-critic 기각, 유저 직접 선택 강제"
        touch "/tmp/${PREFIX}_design_critic_passed"
        write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "ESCALATE" \
          "" "" "" "designer,design-critic" "ESCALATE" "유저가 직접 variant 선택 필요"

        echo ""
        echo "⚠️  Design-Critic ESCALATE — 자동 선정 불가. 직접 variant를 선택해주세요."
        echo ""
        echo "Pencil 캔버스에서 3개 variant(A/B/C)를 확인하고"
        echo "선택할 variant를 입력하세요 (A/B/C):"
        echo ""

        export HARNESS_RESULT="DESIGN_DONE"
        echo "DESIGN_DONE (ESCALATE → 유저 직접 선택)"
        echo "issue: #${ISSUE_NUM}"
        echo "variants: ${round_dir}/designer.log"
        echo "critic: ${round_dir}/critic.log"
        echo "필요 조치: design-critic이 자동 선정 불가 판정. 유저가 Pencil에서 직접 variant 선택"
        exit 0
        ;;
      *)
        hlog "design-critic 결과 불명확: ${dc_result}"
        attempt=$((attempt+1))
        continue
        ;;
    esac
  done

  # 3라운드 모두 ITERATE/UNKNOWN → DESIGN_LOOP_ESCALATE
  hlog "DESIGN_LOOP_ESCALATE — ${MAX}라운드 후 유저 직접 선택 대기"
  touch "/tmp/${PREFIX}_design_critic_passed"

  echo ""
  echo "⚠️  DESIGN_LOOP_ESCALATE — ${MAX}라운드 반복 후에도 자동 선정 실패."
  echo "Pencil 캔버스에서 variant(A/B/C)를 직접 확인하고 선택해주세요."
  echo ""

  export HARNESS_RESULT="DESIGN_LOOP_ESCALATE"
  echo "DESIGN_LOOP_ESCALATE: ${MAX}라운드 후에도 PICK 없음"
  echo "issue: #${ISSUE_NUM}"
  echo "variants: /tmp/${PREFIX}_des_out.txt"
  echo "critic: /tmp/${PREFIX}_dc_out.txt"
  echo "필요 조치: 유저가 직접 variant를 선택하거나 디자인 방향을 지시"
  exit 0
}
