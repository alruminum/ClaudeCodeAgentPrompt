#!/bin/bash
# ~/.claude/harness/design.sh
#
# ⚠️  DEPRECATED — v4 아키텍처에서 designer는 하네스 루프 밖으로 이동됨.
# ux 스킬이 designer 에이전트를 Agent 도구로 직접 호출한다.
# executor.sh design 진입은 더 이상 사용하지 않는다.
#
# 이 파일은 레거시 참조용으로 보존. 신규 프로젝트에서는 사용 금지.
# 새 흐름: orchestration/design.md 참조.
#
# --- 구 아키텍처 (보존) ---
# design 모드: DEFAULT(1variant, 크리틱 없음) 또는 CHOICE(3variant, 크리틱 PASS/REJECT)
#
# 구 흐름 (v3, orchestration/design.md v3 기반):
#   DEFAULT 모드 (DESIGN_MODE=default, 기본값):
#     Phase 0: 컨텍스트 수집 + Pencil 캔버스 준비
#     Phase 1: designer — 1 variant (Pencil 프레임 + 스크린샷)
#     Phase 2: 유저 직접 확인 (APPROVE/REJECT) → DESIGN_DONE
#     Phase 4: 유저 선택 후 DESIGN_HANDOFF
#
#   CHOICE 모드 (DESIGN_MODE=choice, --choice 플래그):
#     Phase 0: 컨텍스트 수집 + Pencil 캔버스 준비
#     Phase 1: designer — 3 variants (Pencil 프레임 + 스크린샷)
#     Phase 2: design-critic — VARIANTS_APPROVED / VARIANTS_ALL_REJECTED 판정
#       VARIANTS_APPROVED → Phase 3 유저 PICK 안내 (DESIGN_DONE)
#       VARIANTS_ALL_REJECTED → Phase 1 재시도 (max 3회)
#     Phase 4: 유저 variant 선택 후 DESIGN_HANDOFF
#
# harness/executor.sh에서 source — 전역변수(PREFIX, ISSUE_NUM, DESIGN_MODE 등) 사용

run_design() {
  rotate_harness_logs "$PREFIX" "design"
  # 루프 타입별 컨텍스트 prepend
  local _lc
  _lc=$(build_loop_context "design" 2>/dev/null || true)
  if [[ -n "$_lc" ]]; then
    CONTEXT="${_lc}
${CONTEXT}"
  fi

  # DESIGN_MODE 미지정 시 default
  local mode="${DESIGN_MODE:-default}"

  if [[ "$mode" == "choice" ]]; then
    _run_design_choice
  else
    _run_design_default
  fi
}

# ── DEFAULT 모드: 1 variant → 유저 직접 확인 ─────────────────────────────
_run_design_default() {
  local attempt=0
  local MAX=3
  local HIST_DIR="/tmp/${PREFIX}_history"
  local LOOP_OUT_DIR="${HIST_DIR}/design"
  mkdir -p "$LOOP_OUT_DIR"

  while [[ $attempt -lt $MAX ]]; do
    kill_check
    local round_dir="${LOOP_OUT_DIR}/round-${attempt}"
    mkdir -p "$round_dir"
    prune_history "$LOOP_OUT_DIR"

    hlog "designer DEFAULT (round $((attempt+1))/$MAX, 1 variant, Pencil MCP)"
    local designer_prompt="@MODE:DESIGNER:DEFAULT
issue: #${ISSUE_NUM}
context: ${CONTEXT}"
    if [[ $attempt -gt 0 ]]; then
      designer_prompt="${designer_prompt}
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/round-$((attempt-1))/designer.log")
이전 variant가 REJECT됐습니다. 개선된 variant-A를 새 방향으로 재생성하라."
    fi
    _agent_call "designer" 900 "$designer_prompt" "/tmp/${PREFIX}_des_out.txt"
    cp "/tmp/${PREFIX}_des_out.txt" "${round_dir}/designer.log" 2>/dev/null || true

    # DEFAULT 모드: 크리틱 없음 — 유저 직접 확인
    touch "/tmp/${PREFIX}_design_critic_passed"

    echo ""
    echo "✅ Design DEFAULT — variant-A가 준비됐습니다."
    echo ""
    echo "Pencil 캔버스에서 확인 후 APPROVE 또는 REJECT를 입력해주세요."
    echo ""

    local chg_d; chg_d=$(git diff HEAD~1 --name-only 2>/dev/null | head -3 | tr '\n' ',' | sed 's/,$//' || echo "")
    write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "PASS" \
      "" "" "$chg_d" "designer" "" "DEFAULT 모드 — 유저 직접 확인 대기"

    export HARNESS_RESULT="DESIGN_DONE"
    echo "DESIGN_DONE"
    echo "issue: #${ISSUE_NUM}"
    echo "variant: ${round_dir}/designer.log"
    echo "필요 조치: Pencil 캔버스에서 variant-A 확인 후 APPROVE → DESIGN_HANDOFF 진행 / REJECT → 재시도 요청"
    exit 0
  done

  # 3회 재시도 후에도 미완료 — DESIGN_LOOP_ESCALATE
  hlog "DESIGN_LOOP_ESCALATE — DEFAULT ${MAX}회 후 유저 직접 선택 대기"
  touch "/tmp/${PREFIX}_design_critic_passed"

  echo ""
  echo "⚠️  DESIGN_LOOP_ESCALATE — DEFAULT 모드 ${MAX}회 재시도 후에도 미승인."
  echo "디자인 방향을 직접 지시하거나 variant를 확인해주세요."
  echo ""

  export HARNESS_RESULT="DESIGN_LOOP_ESCALATE"
  echo "DESIGN_LOOP_ESCALATE: DEFAULT ${MAX}회 후 REJECT 반복"
  echo "issue: #${ISSUE_NUM}"
  echo "variants: /tmp/${PREFIX}_des_out.txt"
  echo "필요 조치: 유저가 디자인 방향을 직접 지시하거나 APPROVE"
  exit 0
}

# ── CHOICE 모드: 3 variants → design-critic PASS/REJECT → 유저 PICK ──────
_run_design_choice() {
  local attempt=0
  local MAX=3
  local HIST_DIR="/tmp/${PREFIX}_history"
  local LOOP_OUT_DIR="${HIST_DIR}/design"
  mkdir -p "$LOOP_OUT_DIR"

  while [[ $attempt -lt $MAX ]]; do
    kill_check
    local round_dir="${LOOP_OUT_DIR}/round-${attempt}"
    mkdir -p "$round_dir"
    prune_history "$LOOP_OUT_DIR"

    hlog "designer CHOICE (round $((attempt+1))/$MAX, 3 variants, Pencil MCP)"
    local designer_prompt="@MODE:DESIGNER:CHOICE
issue: #${ISSUE_NUM}
context: ${CONTEXT}"
    if [[ $attempt -gt 0 ]]; then
      designer_prompt="${designer_prompt}
$(explore_instruction "$LOOP_OUT_DIR" "${LOOP_OUT_DIR}/round-$((attempt-1))/critic.log")
design-critic 피드백을 직접 확인하고 개선된 variants를 생성하라."
    fi
    _agent_call "designer" 900 "$designer_prompt" "/tmp/${PREFIX}_des_out.txt"
    cp "/tmp/${PREFIX}_des_out.txt" "${round_dir}/designer.log" 2>/dev/null || true

    hlog "design-critic 심사 CHOICE (round $((attempt+1))/$MAX)"
    _agent_call "design-critic" 300 \
      "@MODE:CRITIC:REVIEW
designer 출력 파일: ${round_dir}/designer.log
이 파일을 직접 읽어 variant 3개를 각각 PASS/REJECT 판정하라." \
      "/tmp/${PREFIX}_dc_out.txt"
    cp "/tmp/${PREFIX}_dc_out.txt" "${round_dir}/critic.log" 2>/dev/null || true
    local dc_result
    dc_result=$(parse_marker "/tmp/${PREFIX}_dc_out.txt" "VARIANTS_APPROVED|VARIANTS_ALL_REJECTED")

    case "$dc_result" in
      VARIANTS_APPROVED)
        hlog "VARIANTS_APPROVED — Phase 3 유저 variant PICK 대기"
        touch "/tmp/${PREFIX}_design_critic_passed"

        echo ""
        echo "✅ Design-Critic VARIANTS_APPROVED — PASS된 variant가 있습니다."
        echo ""
        echo "Pencil 캔버스에서 확인하세요:"
        grep -A1 "## variant-A:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-A: /' 2>/dev/null || echo "  variant-A: Pencil 캔버스 확인"
        grep -A1 "## variant-B:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-B: /' 2>/dev/null || echo "  variant-B: Pencil 캔버스 확인"
        grep -A1 "## variant-C:" "/tmp/${PREFIX}_des_out.txt" | tail -1 | sed 's/\*\*미적 방향:\*\* /  variant-C: /' 2>/dev/null || echo "  variant-C: Pencil 캔버스 확인"
        echo ""
        echo "PASS된 variant를 확인하고 선택할 variant를 입력하세요 (A/B/C):"
        echo ""

        export HARNESS_RESULT="DESIGN_DONE"
        local chg_d; chg_d=$(git diff HEAD~1 --name-only 2>/dev/null | head -3 | tr '\n' ',' | sed 's/,$//' || echo "")
        write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "PASS" \
          "" "" "$chg_d" "designer,design-critic" "" "VARIANTS_APPROVED — 유저 variant PICK 대기"
        echo "DESIGN_DONE"
        echo "issue: #${ISSUE_NUM}"
        echo "variants: ${round_dir}/designer.log"
        echo "critic: ${round_dir}/critic.log"
        echo "필요 조치: Pencil 캔버스에서 PASS variant 확인 후 선택 입력 (A/B/C) → DESIGN_HANDOFF 진행"
        exit 0
        ;;
      VARIANTS_ALL_REJECTED)
        write_attempt_meta "${round_dir}/meta.json" "$attempt" "design" "" "FAIL" \
          "variants_all_rejected" "" "" "designer,design-critic" "VARIANTS_ALL_REJECTED" "${round_dir}/critic.log 에서 피드백 확인 후 개선"
        attempt=$((attempt+1))
        hlog "VARIANTS_ALL_REJECTED — designer 재시도 ($attempt/$MAX)"
        continue
        ;;
      *)
        hlog "design-critic 결과 불명확: ${dc_result}"
        attempt=$((attempt+1))
        continue
        ;;
    esac
  done

  # 3라운드 모두 VARIANTS_ALL_REJECTED → DESIGN_LOOP_ESCALATE
  hlog "DESIGN_LOOP_ESCALATE — CHOICE ${MAX}라운드 후 유저 직접 선택 대기"
  touch "/tmp/${PREFIX}_design_critic_passed"

  echo ""
  echo "⚠️  DESIGN_LOOP_ESCALATE — CHOICE ${MAX}라운드 반복 후에도 PASS variant 없음."
  echo "Pencil 캔버스에서 variant(A/B/C)를 직접 확인하고 선택해주세요."
  echo ""

  export HARNESS_RESULT="DESIGN_LOOP_ESCALATE"
  echo "DESIGN_LOOP_ESCALATE: CHOICE ${MAX}라운드 후에도 VARIANTS_ALL_REJECTED"
  echo "issue: #${ISSUE_NUM}"
  echo "variants: /tmp/${PREFIX}_des_out.txt"
  echo "critic: /tmp/${PREFIX}_dc_out.txt"
  echo "필요 조치: 유저가 직접 variant를 선택하거나 디자인 방향을 지시"
  exit 0
}
