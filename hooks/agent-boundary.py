#!/usr/bin/env python3
"""
agent-boundary.py — PreToolUse(Edit/Write/Read) 훅
에이전트별 파일 접근 경계를 물리적으로 강제한다.

Write/Edit: 허용 경로 매트릭스 기반 차단.
Read: 하네스 인프라 파일(.claude/, hooks/, harness-*.sh 등) 접근 차단.

활성 에이전트 감지: /tmp/{prefix}_{agent}_active 플래그 존재 여부.
에이전트가 활성화되지 않은 상태(메인 Claude)에서는 이 훅은 통과.
"""
import sys
import json
import os
import re

def get_prefix():
    """프로젝트별 prefix를 harness.config.json 또는 디렉토리명에서 유도."""
    config_path = os.path.join(os.getcwd(), ".claude", "harness.config.json")
    if os.path.exists(config_path):
        try:
            config = json.load(open(config_path))
            return config.get("prefix", "proj")
        except Exception:
            pass
    raw = os.path.basename(os.getcwd()).lower()
    return re.sub(r'[^a-z0-9]', '', raw)[:8] or "proj"

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
        r'design-preview-[^/]*\.html$', # design-preview-*.html
        r'(^|/)docs/ui-spec',           # docs/ui-spec*
    ],
    "test-engineer": [
        r'(^|/)src/__tests__/',         # src/__tests__/** 만
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

    # 활성 에이전트 탐색
    active_agent = None
    for agent in ALLOW_MATRIX:
        flag_path = f"/tmp/{prefix}_{agent}_active"
        if os.path.exists(flag_path):
            active_agent = agent
            break

    # 에이전트 활성화 안 됨 → 이 훅은 관여 안 함
    if active_agent is None:
        sys.exit(0)

    # ── 하네스 인프라 파일 Read/Write/Edit 차단 (모든 에이전트 공통) ──
    for pattern in HARNESS_INFRA_PATTERNS:
        if re.search(pattern, fp):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"❌ [agent-boundary] {active_agent}는 하네스 인프라 파일 접근 금지: "
                        f"{os.path.basename(fp)}. 프로젝트 소스(src/, docs/)만 분석 대상."
                    )
                }
            }))
            sys.exit(0)

    # Read 도구는 하네스 인프라만 차단, 나머지 프로젝트 파일은 허용
    if tool_name == "Read":
        sys.exit(0)

    # ── 이하 Write/Edit 전용: 허용 경로 매트릭스 확인 ──
    allowed_patterns = ALLOW_MATRIX.get(active_agent, [])

    # ReadOnly 에이전트 (빈 리스트) → 모든 Write/Edit deny
    if not allowed_patterns:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"❌ [agent-boundary] {active_agent}는 ReadOnly 에이전트. "
                    f"파일 수정 금지: {os.path.basename(fp)}"
                )
            }
        }))
        sys.exit(0)

    # 허용 경로 매치 확인
    for pattern in allowed_patterns:
        if re.search(pattern, fp):
            # 허용
            sys.exit(0)

    # 매치 안 됨 → deny
    allowed_desc = ", ".join(allowed_patterns)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"❌ [agent-boundary] {active_agent}는 {os.path.basename(fp)} 수정 불가. "
                f"허용 경로: {allowed_desc}"
            )
        }
    }))

if __name__ == "__main__":
    main()
