#!/usr/bin/env python3
"""
agent-gate.py — PreToolUse(Agent) 글로벌 훅

## 책임 분리 원칙 (A1)
이 훅 = "외부 직접 호출 방지" — 에이전트가 하네스 없이 호출되는 것을 차단.
내부 순서 보장(engineer 전 plan validation, pr-reviewer 전 validator 등)은
harness/impl_*.sh 스크립트가 담당한다. 여기서는 중복하지 않는다.

이 훅이 담당하는 것:
  - 프롬프트 검증 (이슈 번호, architect Mode)
  - harness_only 에이전트의 하네스 외부 호출 차단
  - engineer의 main branch 직접 작업 차단
  - background 에이전트 금지
  - 에이전트 호출 로그 + 활성 플래그

이 훅이 담당하지 않는 것 (impl_*.sh 에서 관리):
  - engineer 전 plan_validation_passed 필요 (→ impl_std.sh:54)
  - validator Mode B 전 test-engineer 필요 (→ impl_std.sh:300)
  - pr-reviewer 전 validator B 필요 (→ impl_std.sh:360)
  - designer → design-critic 순서 (→ design.sh)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import subprocess
from datetime import datetime
from harness_common import get_prefix, get_state_dir, get_flags_dir, deny, flag_exists, FLAGS, HARNESS_ONLY_AGENTS, ISSUE_REQUIRED_AGENTS, CUSTOM_AGENTS
import session_state as ss

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

    # Phase 3: 훅 stdin에서 session_id 파싱 — live.json 기록에 사용
    session_id = ss.session_id_from_stdin(d)

    if not agent:
        sys.exit(0)

    # 1. 프롬프트 검증: 이슈 번호 필수 에이전트
    #    예외: architect Mode D (Task Decompose) — 이슈를 생성하는 역할
    #    예외: architect Mode A / SYSTEM_DESIGN — 전체 구조 설계, 특정 이슈 귀속 아님
    if agent in ISSUE_REQUIRED_AGENTS:
        is_exempt = agent == "architect" and re.search(
            r"Mode\s*D|Task\s*Decompose|SYSTEM_DESIGN|Mode\s*A", prompt, re.IGNORECASE
        )
        if not is_exempt and not re.search(r"#\d+", prompt):
            deny(f"❌ {agent} 호출 전 GitHub 이슈 등록 필요. 프롬프트에 이슈 번호(#NNN)가 없습니다.")

    # 2. 프롬프트 검증: architect 호출 시 Mode A-F 명시 필수
    if agent == "architect":
        if not re.search(r"Mode [A-F]", prompt, re.IGNORECASE):
            deny("❌ architect 호출 시 Mode A/B/C/D/E/F를 프롬프트에 명시하세요.")

    # 3. 하네스 내부 에이전트는 harness/executor.py 경유 필수
    if agent in HARNESS_ONLY_AGENTS and not flag(FLAGS.HARNESS_ACTIVE):
        cmds = {
            "engineer": "python3 ~/.claude/harness/executor.py impl --impl <path> --issue <N>",
            "architect": "python3 ~/.claude/harness/executor.py impl|plan ...",
        }
        deny(f"❌ {agent}는 harness/executor.py를 통해서만 호출 가능. "
             f"{get_flags_dir()}/{PREFIX}_{FLAGS.HARNESS_ACTIVE} 없음. "
             f"직접 호출 금지 → {cmds.get(agent, 'executor.py')}")

    # 4. engineer는 feature branch에서만 실행 (main 보호)
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
            pass

    # 5. 백그라운드 에이전트 금지
    if bg:
        deny(f"❌ 백그라운드 에이전트 금지. {agent} 호출 시 run_in_background=false 필수. "
             "포그라운드에서만 실행해야 중단 가능.")

    # 6. 에이전트 호출 로그
    caller = "harness-executor" if flag(FLAGS.HARNESS_ACTIVE) else "main-claude"
    ts = datetime.now().strftime("%H:%M:%S")
    snippet = prompt[:80].replace("\n", " ")
    try:
        with open(f"{get_state_dir()}/{PREFIX}-agent-calls.log", "a") as f:
            f.write(f"[{ts}] {caller} → {agent} | {snippet}\n")
    except Exception:
        pass

    # 7. Phase 3: 활성 에이전트를 세션 live.json에 기록.
    #    CC 내장 서브에이전트(Explore, Plan 등)는 우리 권한 제어 대상이 아니므로 기록하지 않는다.
    #    → 훅이 활성 에이전트 판정 시 live.json만 읽음 (env var 폴백/TTL/화이트리스트 필터 불필요).
    if agent in CUSTOM_AGENTS and session_id:
        try:
            ss.update_live(session_id, agent=agent)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
