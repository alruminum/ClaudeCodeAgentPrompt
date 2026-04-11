#!/usr/bin/env bash
# flags.sh — 플래그 이름 상수 (Single Source of Truth)
# 모든 harness/*.sh에서 source하여 사용한다.
# 오타 방지: 문자열 리터럴 대신 상수 참조.

# ── 하네스 제어 플래그 ──
FLAG_HARNESS_ACTIVE="harness_active"
FLAG_HARNESS_KILL="harness_kill"

# ── 검증 단계 플래그 ──
FLAG_PLAN_VALIDATION_PASSED="plan_validation_passed"
FLAG_TEST_ENGINEER_PASSED="test_engineer_passed"
FLAG_VALIDATOR_B_PASSED="validator_b_passed"
FLAG_PR_REVIEWER_LGTM="pr_reviewer_lgtm"
FLAG_SECURITY_REVIEW_PASSED="security_review_passed"
FLAG_BUGFIX_VALIDATION_PASSED="bugfix_validation_passed"

# ── 설계/디자인 플래그 ──
FLAG_LIGHT_PLAN_READY="light_plan_ready"
FLAG_DESIGNER_RAN="designer_ran"
FLAG_DESIGN_CRITIC_PASSED="design_critic_passed"

# ── 헬퍼 함수 ──
# flag_touch <name>  — 플래그 생성
flag_touch() { touch "${STATE_DIR}/${PREFIX}_$1"; }
# flag_rm <name>     — 플래그 삭제
flag_rm()    { rm -f "${STATE_DIR}/${PREFIX}_$1"; }
# flag_exists <name> — 플래그 존재 확인 (조건문에 사용)
flag_exists(){ [[ -f "${STATE_DIR}/${PREFIX}_$1" ]]; }
