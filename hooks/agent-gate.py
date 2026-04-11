#!/usr/bin/env python3
"""
agent-gate.py — PreToolUse(Agent) 글로벌 훅
에이전트 실행 순서·조건을 검증한다. 프로젝트별 인라인 원라이너를 대체.

prefix는 환경변수 HARNESS_PREFIX로 주입 (기본값: mb).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import subprocess
from datetime import datetime
from harness_common import get_prefix, get_state_dir, deny, flag_exists, FLAGS

PREFIX = get_prefix()


def flag(name):
    return flag_exists(PREFIX, name)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    t = d.get("tool_input", {})
    agent = t.get("subagent_type", "")
    prompt = t.get("prompt", "")
    bg = t.get("run_in_background", False)

    if not agent:
        sys.exit(0)

    # 1. architect/engineer 호출 전 이슈 번호 필수
    # (designer는 UX 시안 먼저 → DESIGN_HANDOFF 후 이슈 생성 흐름이므로 제외)
    if agent in ("architect", "engineer"):
        if not re.search(r"#\d+", prompt):
            deny(f"❌ {agent} 호출 전 GitHub 이슈 등록 필요. 프롬프트에 이슈 번호(#NNN)가 없습니다.")

    # 2. architect 호출 시 Mode A-F 명시 필수
    if agent == "architect":
        if not re.search(r"Mode [A-F]", prompt, re.IGNORECASE):
            deny("❌ architect 호출 시 Mode A/B/C/D/E/F를 프롬프트에 명시하세요.")

    # 3. engineer 전 Plan Validation PASS 필요
    if agent == "engineer" and not flag(FLAGS.PLAN_VALIDATION_PASSED):
        # light_plan_ready도 허용 (Light Plan 경로)
        if not flag(FLAGS.LIGHT_PLAN_READY):
            deny(f"❌ engineer 전 Plan Validation PASS 필요. {get_state_dir()}/{PREFIX}_{FLAGS.PLAN_VALIDATION_PASSED} 없음.")

    # 3b. 하네스 내부 에이전트는 harness/executor.sh 경유 필수
    # (qa는 하네스 진입 전 분류 역할 — HARNESS_ONLY에서 제외)
    HARNESS_ONLY_AGENTS = ("engineer", "architect")
    if agent in HARNESS_ONLY_AGENTS and not flag(FLAGS.HARNESS_ACTIVE):
        cmds = {
            "engineer": "bash ~/.claude/harness/executor.sh impl --impl <path> --issue <N>",
            "qa":       "bash ~/.claude/harness/executor.sh bugfix --bug '<설명>' [--issue <N>]",
            "architect": "bash ~/.claude/harness/executor.sh bugfix|impl|plan ...",
        }
        deny(f"❌ {agent}는 harness/executor.sh를 통해서만 호출 가능. "
             f"{get_state_dir()}/{PREFIX}_{FLAGS.HARNESS_ACTIVE} 없음. "
             f"직접 호출 금지 → {cmds.get(agent, 'executor.sh')}")

    # 3c. engineer는 feature branch에서만 실행 (main 직접 작업 방지)
    if agent == "engineer" and flag(FLAGS.HARNESS_ACTIVE):
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            current_branch = branch_result.stdout.strip()
            if current_branch in ("main", "master"):
                deny("❌ engineer는 feature branch에서만 실행 가능. "
                     f"현재: {current_branch}. "
                     "harness가 create_feature_branch()를 먼저 호출해야 합니다.")
        except Exception:
            pass  # git 실패 시 차단 안 함 (safety net)

    # 4. designer 실행 후 design-critic PICK 전까지 engineer 차단
    if agent == "engineer" and flag(FLAGS.DESIGNER_RAN) and not flag(FLAGS.DESIGN_CRITIC_PASSED):
        deny("❌ designer 실행 후 engineer 바로 불가. "
             "올바른 순서: design-critic PICK → 유저 승인 → architect impl 계획 → validator Mode A PASS → engineer")

    # 5. validator Mode B 전 test-engineer PASS 필요
    if agent == "validator" and re.search(r"Mode B", prompt, re.IGNORECASE):
        if not flag(FLAGS.TEST_ENGINEER_PASSED):
            deny(f"❌ validator Mode B 전 test-engineer PASS 필요. {get_state_dir()}/{PREFIX}_{FLAGS.TEST_ENGINEER_PASSED} 없음.")

    # 6. pr-reviewer 전 validator Mode B PASS 필요
    if agent == "pr-reviewer" and not flag(FLAGS.VALIDATOR_B_PASSED):
        deny(f"❌ pr-reviewer 전 validator Mode B PASS 필요. {get_state_dir()}/{PREFIX}_{FLAGS.VALIDATOR_B_PASSED} 없음.")

    # 7. 백그라운드 에이전트 금지
    if bg:
        deny(f"❌ 백그라운드 에이전트 금지. {agent} 호출 시 run_in_background=false 필수. "
             "포그라운드에서만 실행해야 중단 가능.")

    # 8. 에이전트 호출 로그
    caller = "harness-executor" if flag(FLAGS.HARNESS_ACTIVE) else "main-claude"
    ts = datetime.now().strftime("%H:%M:%S")
    snippet = prompt[:80].replace("\n", " ")
    try:
        with open(f"{get_state_dir()}/{PREFIX}-agent-calls.log", "a") as f:
            f.write(f"[{ts}] {caller} → {agent} | {snippet}\n")
    except Exception:
        pass

    # 9. 에이전트 활성 플래그 설정 (agent-boundary.py 연동)
    try:
        open(f"{get_state_dir()}/{PREFIX}_{agent}_active", "w").close()
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
