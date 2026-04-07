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
from datetime import datetime
from harness_common import get_prefix, deny, flag_exists

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

    # 1. architect/engineer/designer 호출 전 이슈 번호 필수
    if agent in ("architect", "engineer", "designer"):
        if not re.search(r"#\d+", prompt):
            deny(f"❌ {agent} 호출 전 GitHub 이슈 등록 필요. 프롬프트에 이슈 번호(#NNN)가 없습니다.")

    # 2. architect 호출 시 Mode A-F 명시 필수
    if agent == "architect":
        if not re.search(r"Mode [A-F]", prompt, re.IGNORECASE):
            deny("❌ architect 호출 시 Mode A/B/C/D/E/F를 프롬프트에 명시하세요.")

    # 3. engineer 전 Plan Validation PASS 필요
    if agent == "engineer" and not flag("plan_validation_passed"):
        # bugfix_plan_ready도 허용 (Mode F 경로)
        if not flag("bugfix_plan_ready"):
            deny(f"❌ engineer 전 Plan Validation PASS 필요. /tmp/{PREFIX}_plan_validation_passed 없음.")

    # 3b. engineer는 harness-executor.sh 경유 필수
    if agent == "engineer" and not flag("harness_active"):
        deny(f"❌ engineer는 harness-executor.sh를 통해서만 호출 가능. "
             f"/tmp/{PREFIX}_harness_active 없음. "
             "메인 Claude에서 직접 engineer 호출 금지 — bash .claude/harness-executor.sh impl2로 호출하라.")

    # 4. designer 실행 후 design-critic PICK 전까지 engineer 차단
    if agent == "engineer" and flag("designer_ran") and not flag("design_critic_passed"):
        deny("❌ designer 실행 후 engineer 바로 불가. "
             "올바른 순서: design-critic PICK → 유저 승인 → architect impl 계획 → validator Mode A PASS → engineer")

    # 5. validator Mode B 전 test-engineer PASS 필요
    if agent == "validator" and re.search(r"Mode B", prompt, re.IGNORECASE):
        if not flag("test_engineer_passed"):
            deny(f"❌ validator Mode B 전 test-engineer PASS 필요. /tmp/{PREFIX}_test_engineer_passed 없음.")

    # 6. pr-reviewer 전 validator Mode B PASS 필요
    if agent == "pr-reviewer" and not flag("validator_b_passed"):
        deny(f"❌ pr-reviewer 전 validator Mode B PASS 필요. /tmp/{PREFIX}_validator_b_passed 없음.")

    # 7. 백그라운드 에이전트 금지
    if bg:
        deny(f"❌ 백그라운드 에이전트 금지. {agent} 호출 시 run_in_background=false 필수. "
             "포그라운드에서만 실행해야 중단 가능.")

    # 8. 에이전트 호출 로그
    caller = "harness-executor" if flag("harness_active") else "main-claude"
    ts = datetime.now().strftime("%H:%M:%S")
    snippet = prompt[:80].replace("\n", " ")
    try:
        with open(f"/tmp/{PREFIX}-agent-calls.log", "a") as f:
            f.write(f"[{ts}] {caller} → {agent} | {snippet}\n")
    except Exception:
        pass

    # 9. 에이전트 활성 플래그 설정 (agent-boundary.py 연동)
    try:
        open(f"/tmp/{PREFIX}_{agent}_active", "w").close()
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
