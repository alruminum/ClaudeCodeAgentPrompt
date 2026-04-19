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

import json
import re
import time
from harness_common import get_prefix, get_state_dir, deny, CUSTOM_AGENTS
import session_state as ss


def _resolve_active_agent(stdin_data):
    """Phase 3: live.json 단일 소스로 활성 에이전트 판정.
    훅 stdin의 session_id → live.json.agent 경로.
    env var 폴백 / 15분 TTL / 화이트리스트 필터 모두 제거 — live.json이 SSOT.

    live.json은 agent-gate.py(PreToolUse Agent)가 기록, post-agent-flags.py(PostToolUse)가 해제.
    CC 내장 서브에이전트(Explore/Plan 등)는 agent-gate가 애초에 기록하지 않으므로 별도 필터 불필요.
    """
    return ss.active_agent(stdin_data=stdin_data)

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
        r'(^|/)trd\.md$',               # trd.md — architect 단독 소유 (PRD 기반 기술 설계)
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
        r'(^|/)prd\.md$',              # prd.md — product-planner 소유
        r'stories\.md$',               # stories.md (에픽 스토리)
        # trd.md 제외: architect 단독 소유 (기술 세부가 기획에 간섭 못 하게)
    ],
    "ux-architect": [
        r'(^|/)docs/ux-flow\.md$',     # docs/ux-flow.md만
    ],
    # ReadOnly 에이전트 — 모든 Write/Edit deny
    "validator": [],
    "design-critic": [],
    "pr-reviewer": [],
    "qa": [],
    "security-reviewer": [],
}

# 에이전트별 Read 금지 경로 (regex) — 매치되면 Read deny
# HARNESS_INFRA_PATTERNS는 전 에이전트 공통이므로 여기에 포함하지 않음
READ_DENY_MATRIX = {
    "product-planner": [
        r'(^|/)src/',                   # 소스 코드 읽기 금지 — 기획자가 코드 레벨 결정 방지
        r'(^|/)docs/impl/',             # impl 계획 파일 — architect 소유
        r'(^|/)trd\.md$',               # TRD 읽기 금지 — 기술 세부가 기획에 간섭 방지. architect가 PRD 기반으로 번역
    ],
    "designer": [
        r'(^|/)src/',                   # 소스 코드 읽기 금지 — 디자인은 Pencil + 스펙 기반
    ],
    "test-engineer": [
        r'(^|/)src/',                   # TDD: impl 기반 테스트 선작성 — 구현 코드 읽기 금지
        r'(^|/)docs/(architecture|game-logic|db-schema|sdk|domain-logic|reference)',  # domain 문서 금지
    ],
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

    # 진단 로그: Phase 3 세션 판정 경로 기록 (env / stdin / pointer)
    try:
        import datetime
        _dbg = {
            "ts": datetime.datetime.now().isoformat(),
            "prefix": prefix,
            "HARNESS_AGENT_NAME": os.environ.get("HARNESS_AGENT_NAME", ""),
            "HARNESS_SESSION_ID": os.environ.get("HARNESS_SESSION_ID", ""),
            "stdin_sid": ss.session_id_from_stdin(d),
            "HARNESS_PREFIX": os.environ.get("HARNESS_PREFIX", ""),
            "HARNESS_INTERNAL": os.environ.get("HARNESS_INTERNAL", ""),
            "tool": tool_name,
            "fp": fp,
        }
        with open(os.path.join(get_state_dir(), "agent_boundary_debug.log"), "a") as _f:
            _f.write(json.dumps(_dbg, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Phase 3: 활성 에이전트 판별 — live.json 단일 소스
    active_agent = _resolve_active_agent(d)

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

    # Read 도구: 하네스 인프라 차단 + 에이전트별 READ_DENY_MATRIX 적용
    if tool_name in ("Read", "Glob", "Grep"):
        deny_patterns = READ_DENY_MATRIX.get(active_agent, [])
        for pattern in deny_patterns:
            if re.search(pattern, fp):
                deny(f"❌ [agent-boundary] {active_agent}는 {os.path.basename(fp)} 읽기 금지. "
                     f"이 에이전트의 역할 범위 밖 파일입니다.")
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
