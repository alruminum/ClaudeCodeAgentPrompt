#!/bin/bash
# ~/.claude/harness/design.sh
# design 모드: designer → design-critic → DESIGN_HANDOFF
#
# 흐름 (design.md 기반):
#   designer (3 variant) → design-critic (PICK/ITERATE/ESCALATE)
#     PICK → DESIGN_DONE (유저 variant 선택 대기)
#     ITERATE → designer 재시도 (max 3회)
#     ESCALATE → DESIGN_LOOP_ESCALATE (유저 직접 선택)
#   유저 선택 후 → impl 영향 체크 → architect Module Plan (필요 시) → FLAG
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM 등) 사용

run_design() {
  rotate_harness_logs "$PREFIX" "design"
  local attempt=0
  local MAX=3

  while [[ $attempt -lt $MAX ]]; do
    kill_check
    echo "[HARNESS] Phase D1 attempt $((attempt+1))/$MAX — designer 호출 중"
    _agent_call "designer" 300 \
      "issue: #$ISSUE_NUM context: $CONTEXT" \
      "/tmp/${PREFIX}_des_out.txt"

    echo "[HARNESS] Phase D2 attempt $((attempt+1))/$MAX — design-critic 호출 중"
    local des_out
    des_out=$(cat "/tmp/${PREFIX}_des_out.txt")
    _agent_call "design-critic" 300 \
      "$des_out" \
      "/tmp/${PREFIX}_dc_out.txt"
    local dc_result
    dc_result=$(parse_marker "/tmp/${PREFIX}_dc_out.txt" "PICK|ITERATE|ESCALATE")

    case "$dc_result" in
      PICK)
        echo "[HARNESS] PICK — 유저 variant 선택 대기"
        touch "/tmp/${PREFIX}_design_critic_passed"

        # design-preview HTML 생성 여부 확인
        local preview_html="design-preview-${ISSUE_NUM}.html"
        if [[ -f "$preview_html" ]]; then
          echo "[HARNESS] 시안 HTML: $preview_html"
        fi

        # DESIGN_HANDOFF → impl 영향 체크는 유저 선택 후 메인 Claude가 수행
        # (design.sh는 유저 게이트에서 멈춤)
        export HARNESS_RESULT="DESIGN_DONE"
        echo "DESIGN_DONE"
        echo "issue: #$ISSUE_NUM"
        echo "variants: /tmp/${PREFIX}_des_out.txt"
        echo "critic: /tmp/${PREFIX}_dc_out.txt"
        echo "필요 조치: 시안 확인 후 variant 선택 → mode:impl 로 재호출"
        exit 0
        ;;
      ITERATE)
        attempt=$((attempt+1))
        echo "[HARNESS] ITERATE — designer 재시도 ($attempt/$MAX)"
        # feedback을 다음 designer 호출에 전달하기 위해 CONTEXT 보강
        local iterate_feedback
        iterate_feedback=$(tail -30 "/tmp/${PREFIX}_dc_out.txt")
        CONTEXT="${CONTEXT}
[design-critic feedback]:
${iterate_feedback}"
        continue
        ;;
      ESCALATE)
        # ESCALATE: design-critic이 3개 variant 모두 기각 → 유저 직접 선택 (design.md: ESC_CRITIC → USER_PICK)
        echo "[HARNESS] ESCALATE — design-critic 기각, 유저 직접 선택 대기"
        touch "/tmp/${PREFIX}_design_critic_passed"
        export HARNESS_RESULT="DESIGN_DONE"
        echo "DESIGN_DONE (ESCALATE → 유저 직접 선택)"
        echo "issue: #$ISSUE_NUM"
        echo "variants: /tmp/${PREFIX}_des_out.txt"
        echo "critic: /tmp/${PREFIX}_dc_out.txt"
        echo "필요 조치: design-critic이 모든 variant를 기각함. 유저가 직접 선택하거나 방향을 지시"
        exit 0
        ;;
      *)
        # UNKNOWN: 마커 파싱 실패
        echo "[HARNESS] design-critic 결과 불명확: $dc_result"
        attempt=$((attempt+1))
        continue
        ;;
    esac
  done

  # 3라운드 모두 ITERATE/UNKNOWN → DESIGN_LOOP_ESCALATE → 유저 직접 선택 (design.md: DLE → USER_PICK)
  echo "[HARNESS] DESIGN_LOOP_ESCALATE — ${MAX}라운드 후 유저 직접 선택 대기"
  touch "/tmp/${PREFIX}_design_critic_passed"
  export HARNESS_RESULT="DESIGN_LOOP_ESCALATE"
  echo "DESIGN_LOOP_ESCALATE: ${MAX}라운드 후에도 PICK 없음"
  echo "issue: #$ISSUE_NUM"
  echo "variants: /tmp/${PREFIX}_des_out.txt"
  echo "critic: /tmp/${PREFIX}_dc_out.txt"
  echo "필요 조치: 유저가 직접 variant를 선택하거나 디자인 방향을 지시"
  exit 0
}
