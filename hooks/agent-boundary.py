#!/usr/bin/env python3
"""
agent-boundary.py — PreToolUse(Edit/Write/Read) 훅
에이전트별 파일 접근 경계 + 메인 Claude 파일 소유권을 물리적으로 강제한다.

1. 에이전트 활성 시: Write/Edit → 허용 경로 매트릭스 기반 차단.
2. 에이전트 활성 시: Read → 하네스 인프라 파일 접근 차단.
3. 에이전트 미활성(메인 Claude) 시: src/** 및 설계 문서 직접 수정 차단.
   (file-ownership-gate.py 역할 통합)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import glob
import json
import re
import time
from harness_common import get_prefix, get_state_dir, deny

# 하네스 인프라 파일 패턴 — 모든 에이전트에서 Read/Write/Edit 차단
HARNESS_INFRA_PATTERNS = [
    r'[./]claude/',
    r'hooks/',
    r'harness-(executor|loop|utils)\.sh',
    r'orchestration-rules\.md',
    r'setup-(harness|agents)\.sh',
]

# 에이전트별 허용 경로 패턴 (regex) — Write/Edit용
# 매치되면 허용, 매치 안 되면 deny
ALLOW_MATRIX = {
    "engineer": [
        r'(^|/)src/',                   # src/** 전체 (테스트 포함)
    ],
    "architect": [
        r'(^|/)docs/',                  # docs/** 전체 (impl 포함)
        r'(^|/)backlog\.md$',           # backlog.md
    ],
    "designer": [
        r'(^|/)design-variants/',       # design-variants/** (Pencil MCP 코드 출력)
        r'(^|/)docs/ui-spec',           # docs/ui-spec*
    ],
    "test-engineer": [
        r'(^|/)src/__tests__/',             # src/__tests__/** (dedicated test dir)
        r'(^|/)src/.*\.test\.[jt]sx?$',     # co-located *.test.{js,jsx,ts,tsx}
        r'(^|/)src/.*\.spec\.[jt]sx?$',     # co-located *.spec.{js,jsx,ts,tsx}
    ],
    "product-planner": [
        r'(^|/)prd\.md$',              # prd.md
        r'(^|/)trd\.md$',              # trd.md
    ],
    # ReadOnly 에이전트 — 모든 Write/Edit deny
    "validator": [],
    "design-critic": [],
    "pr-reviewer": [],
    "qa": [],
    "security-reviewer": [],
}

def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = d.get("tool_name", "")
    fp = d.get("tool_input", {}).get("file_path", "")
    if not fp:
        sys.exit(0)

    prefix = get_prefix()

    # 진단 로그: prefix/CWD/env/active 플래그 기록 → 훅 오진단 시 분석용
    try:
        import datetime
        _dbg = {
            "ts": datetime.datetime.now().isoformat(),
            "prefix": prefix,
            "cwd": os.getcwd(),
            "HARNESS_PREFIX": os.environ.get("HARNESS_PREFIX", ""),
            "active_flags": [f for f in os.listdir(get_state_dir()) if "_active" in f],
            "tool": tool_name,
            "fp": fp,
        }
        with open(os.path.join(get_state_dir(), "agent_boundary_debug.log"), "a") as _f:
            _f.write(json.dumps(_dbg, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # 활성 에이전트 탐색
    active_agent = None
    # 1차: 계산된 prefix로 정확 매칭
    for agent in ALLOW_MATRIX:
        if os.path.exists(os.path.join(get_state_dir(), f"{prefix}_{agent}_active")):
            active_agent = agent
            break

    # 2차 fallback: prefix 불일치 대비 glob 탐색 (900초 TTL = engineer 최대 타임아웃)
    # HARNESS_PREFIX가 훅 서브프로세스에 전파되지 않아 prefix가 틀릴 수 있음.
    if active_agent is None:
        now = time.time()
        for agent in ALLOW_MATRIX:
            for f in glob.glob(os.path.join(get_state_dir(), f"*_{agent}_active")):
                try:
                    if now - os.path.getmtime(f) < 900:
                        active_agent = agent
                        break
                except Exception:
                    pass
            if active_agent:
                break

    # 에이전트 활성화 안 됨 → 메인 Claude 직접 수정 제한 (file-ownership 통합)
    if active_agent is None:
        # Read는 제한 없음
        if tool_name == "Read":
            sys.exit(0)

        # src/** 소스 코드 직접 수정 차단 (src/__tests__/ 포함)
        if re.search(r'(^|/)src/', fp):
            deny("❌ [file-ownership] src/** 는 engineer 에이전트 소유. "
                 "직접 수정 금지 → harness/executor.py를 통해 루프 C 진입.")

        # 설계 문서 직접 수정 차단
        DOCS_PATTERN = re.compile(
            r"(docs/(architecture|game-logic|db-schema|sdk|ui-spec|domain-logic|reference)[^/]*[.]md"
            r"|(^|/)prd[.]md"
            r"|(^|/)trd[.]md)"
        )
        if DOCS_PATTERN.search(fp):
            deny("❌ [file-ownership] 설계 문서는 에이전트 소유. "
                 "직접 수정 금지 → architect/designer/product-planner 에이전트 호출.")

        # 그 외 파일은 메인 Claude 수정 허용
        sys.exit(0)

    # ── 하네스 인프라 파일 Read/Write/Edit 차단 (모든 에이전트 공통) ──
    for pattern in HARNESS_INFRA_PATTERNS:
        if re.search(pattern, fp):
            deny(f"❌ [agent-boundary] {active_agent}는 하네스 인프라 파일 접근 금지: "
                 f"{os.path.basename(fp)}. 프로젝트 소스(src/, docs/)만 분석 대상.")

    # Read 도구는 하네스 인프라만 차단, 나머지 프로젝트 파일은 허용
    if tool_name == "Read":
        sys.exit(0)

    # ── 이하 Write/Edit 전용: 허용 경로 매트릭스 확인 ──
    allowed_patterns = ALLOW_MATRIX.get(active_agent, [])

    # ReadOnly 에이전트 (빈 리스트) → 모든 Write/Edit deny
    if not allowed_patterns:
        deny(f"❌ [agent-boundary] {active_agent}는 ReadOnly 에이전트. "
             f"파일 수정 금지: {os.path.basename(fp)}")

    # 허용 경로 매치 확인
    for pattern in allowed_patterns:
        if re.search(pattern, fp):
            # 허용
            sys.exit(0)

    # 매치 안 됨 → deny (+ structured deny 로그)
    try:
        import datetime
        _deny_log = {
            "ts": datetime.datetime.now().isoformat(),
            "event": "agent_boundary_deny",
            "agent": active_agent,
            "fp": fp,
            "allowed": allowed_patterns,
        }
        with open(os.path.join(get_state_dir(), "agent_boundary_debug.log"), "a") as _f:
            _f.write(json.dumps(_deny_log, ensure_ascii=False) + "\n")
    except Exception:
        pass
    allowed_desc = ", ".join(allowed_patterns)
    deny(f"❌ [agent-boundary] {active_agent}는 {os.path.basename(fp)} 수정 불가. "
         f"허용 경로: {allowed_desc}")

if __name__ == "__main__":
    main()
