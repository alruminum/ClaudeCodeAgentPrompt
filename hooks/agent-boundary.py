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

# /hardcarry, /softcarry 과제 모드 우회 — HardcarryDryRun / softcarray 프로젝트에선 훅 bypass.
# 과제 종료 후 'softcarray' 조건 삭제 (또는 ~/.claude/hooks/agent-boundary.py.bak-hardcarry 복원).
if ('HardcarryDryRun' in os.getcwd()
        or 'softcarray' in os.getcwd()
        or os.path.exists(os.path.join(os.getcwd(), '.no-harness'))):
    sys.exit(0)

import json
import re
import time
from harness_common import get_prefix, get_state_dir, deny, CUSTOM_AGENTS, is_harness_enabled
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
        r'(^|/)src/',                   # src/** 전체 (단일 레포 기존)
        r'(^|/)apps/[^/]+/src/',        # apps/<name>/src/** (모노레포 frontend/mobile)
        r'(^|/)apps/[^/]+/app/',        # apps/<name>/app/** (FastAPI 등 백엔드 앱 코드)
        r'(^|/)apps/[^/]+/alembic/',    # apps/<name>/alembic/** (DB 마이그레이션)
        r'(^|/)packages/[^/]+/src/',    # packages/<name>/src/** (npm 워크스페이스)
        r'(^|/)apps/[^/]+/[^/]+\.toml$',  # apps/<name>/*.toml (pyproject.toml 등)
        r'(^|/)apps/[^/]+/[^/]+\.cfg$',   # apps/<name>/*.cfg (setup.cfg 등)
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
        r'(^|/)src/__tests__/',             # src/__tests__/** (단일 레포 기존)
        r'(^|/)src/.*\.test\.[jt]sx?$',     # co-located *.test.{js,jsx,ts,tsx}
        r'(^|/)src/.*\.spec\.[jt]sx?$',     # co-located *.spec.{js,jsx,ts,tsx}
        r'(^|/)apps/[^/]+/tests/',          # apps/<name>/tests/** (pytest 등 백엔드 테스트)
        r'(^|/)apps/[^/]+/src/__tests__/',  # apps/<name>/src/__tests__/** (모노레포 JS 테스트)
        r'(^|/)apps/[^/]+/src/.*\.test\.[jt]sx?$',  # apps/<name>/src/*.test.*
        r'(^|/)apps/[^/]+/src/.*\.spec\.[jt]sx?$',  # apps/<name>/src/*.spec.*
        r'(^|/)packages/[^/]+/src/__tests__/',       # packages/<name>/src/__tests__/**
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
    "plan-reviewer": [
        r'(^|/)src/',                   # 소스 코드 읽기 금지 — 판단 게이트는 문서 레벨에서만
        r'(^|/)docs/impl/',             # impl 계획 파일 — architect 소유 (세부 구현 스펙은 리뷰 범위 초과)
        r'(^|/)trd\.md$',               # TRD 금지 — architect 내부 결정. reviewer가 TRD 기반으로 기획 쳐내면 역방향 오염.
        # ✅ docs/architecture.md / docs/sdk.md / docs/reference.md 는 허용 — 외부 기술 사실 + 현행 아키 확인용
    ],
}

def main():
    # 화이트리스트 가드 — `~/.claude/harness-projects.json` 등록된 프로젝트에서만 동작.
    if not is_harness_enabled():
        sys.exit(0)

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
        # Phase 4: 활성 스킬이 있으면 스킬 맥락 — 메인 Claude 일반 규칙 완화.
        # 정당한 스킬 작업(예: /ux의 designer 호출 전 docs 읽기, /qa의 src/ 분석)이
        # 메인 Claude 규칙에 막히는 사고 방지. file-ownership은 여전히 적용해 PRD/src
        # 직접 수정은 차단하되, "메인 Claude가 막무가내로 수정 중"이라는 진단 메시지를
        # "스킬 맥락" 진단으로 바꿔 유저에게 정확한 원인을 알린다.
        active_skill = ss.active_skill(stdin_data=d)
        skill_ctx = ""
        if active_skill:
            skill_ctx = f" (스킬 '{active_skill.get('name')}' 진행 중)"

        # Read는 제한 없음
        if tool_name == "Read":
            sys.exit(0)

        # src/** 소스 코드 직접 수정 차단 (src/__tests__/ 포함)
        if re.search(r'(^|/)src/', fp):
            deny(f"❌ [hooks/agent-boundary.py file-ownership] src/** 는 engineer 에이전트 소유.{skill_ctx} "
                 "직접 수정 금지 → harness/executor.py를 통해 루프 C 진입.")

        # 설계 문서 직접 수정 차단
        DOCS_PATTERN = re.compile(
            r"(docs/(architecture|game-logic|db-schema|sdk|ui-spec|domain-logic|reference)[^/]*[.]md"
            r"|(^|/)prd[.]md"
            r"|(^|/)trd[.]md)"
        )
        if DOCS_PATTERN.search(fp):
            deny(f"❌ [hooks/agent-boundary.py file-ownership] 설계 문서는 에이전트 소유.{skill_ctx} "
                 "직접 수정 금지 → architect/designer/product-planner 에이전트 호출.")

        # 그 외 파일은 메인 Claude 수정 허용
        sys.exit(0)

    # ── 핸드오프 화이트리스트 ──
    # 에이전트 간 인수인계 문서(`{prefix}_handoffs/attempt-N/{from}-to-{to}.md`)는
    # 정당한 통로다. 위 HARNESS_INFRA_PATTERNS의 `[./]claude/`가 이걸 차단해 버려
    # engineer가 validator 피드백을 못 읽고 빈 출력으로 timeout 반복하는 사례 발생
    # (jajang #99 dual-theme 32파일 마이그레이션, $8.45 손실).
    # 핸드오프 디렉토리는 모든 에이전트가 Read 가능. Write는 generate_handoff()
    # 헬퍼 경로 (engineer/architect 등 ALLOW_MATRIX 매칭) 또는 harness 내부에서만.
    HANDOFF_PATH_RE = re.compile(r'(^|/)[A-Za-z0-9_-]+_handoffs/')
    if HANDOFF_PATH_RE.search(fp):
        if tool_name in ("Read", "Glob", "Grep"):
            sys.exit(0)
        # Write/Edit는 ALLOW_MATRIX 평가로 위임 — 일반 에이전트는 어차피 차단됨

    # ── 하네스 인프라 파일 Read/Write/Edit 차단 (모든 에이전트 공통) ──
    for pattern in HARNESS_INFRA_PATTERNS:
        if re.search(pattern, fp):
            deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 하네스 인프라 파일 접근 금지: "
                 f"{os.path.basename(fp)} (matched={pattern!r}). "
                 "프로젝트 소스(src/, docs/)만 분석 대상.")

    # Read 도구: 하네스 인프라 차단 + 에이전트별 READ_DENY_MATRIX 적용
    if tool_name in ("Read", "Glob", "Grep"):
        deny_patterns = READ_DENY_MATRIX.get(active_agent, [])
        for pattern in deny_patterns:
            if re.search(pattern, fp):
                deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 {os.path.basename(fp)} 읽기 금지. "
                     f"이 에이전트의 역할 범위 밖 파일입니다.")
        sys.exit(0)

    # ── 이하 Write/Edit 전용: 허용 경로 매트릭스 확인 ──
    allowed_patterns = ALLOW_MATRIX.get(active_agent, [])

    # ReadOnly 에이전트 (빈 리스트) → 모든 Write/Edit deny
    if not allowed_patterns:
        deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 ReadOnly 에이전트. "
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
    deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 {os.path.basename(fp)} 수정 불가. "
         f"허용 경로: {allowed_desc}")

if __name__ == "__main__":
    main()
