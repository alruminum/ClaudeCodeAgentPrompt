"""
harness_common.py — 훅 공유 유틸리티
PREFIX 결정, deny 헬퍼, 플래그 상수, 마커 파싱 등 훅 간 공통 로직.
"""
import json
import os
import re
import sys


# ── 마커 포맷 (Single Source of Truth) ──
# 에이전트 출력 마커: ---MARKER:<NAME>---
MARKER_RE = re.compile(r'---MARKER:([A-Z_]+)---')


def parse_marker_text(text, allowed=None):
    """텍스트에서 구조화된 마커를 추출.
    allowed: 허용 마커 집합 (None이면 모든 마커 허용).
    반환: 첫 번째 매칭 마커 또는 None.
    """
    for m in MARKER_RE.finditer(text):
        name = m.group(1)
        if allowed is None or name in allowed:
            return name
    return None


# ── 플래그 이름 상수 ──
class FLAGS:
    HARNESS_ACTIVE = "harness_active"
    HARNESS_KILL = "harness_kill"
    PLAN_VALIDATION_PASSED = "plan_validation_passed"
    TEST_ENGINEER_PASSED = "test_engineer_passed"
    VALIDATOR_B_PASSED = "validator_b_passed"
    PR_REVIEWER_LGTM = "pr_reviewer_lgtm"
    SECURITY_REVIEW_PASSED = "security_review_passed"
    BUGFIX_VALIDATION_PASSED = "bugfix_validation_passed"
    LIGHT_PLAN_READY = "light_plan_ready"
    DESIGNER_RAN = "designer_ran"
    DESIGN_CRITIC_PASSED = "design_critic_passed"


# ── 에이전트 분류 상수 (Single Source of Truth) ──
# 훅에서 에이전트별 권한/제약을 판단할 때 이 상수만 참조한다.
# 변경 시 이 파일만 수정 → 모든 훅에 즉시 반영.

# 하네스(executor.sh) 경유 필수 에이전트 — 직접 Agent 호출 금지
HARNESS_ONLY_AGENTS = ("engineer",)

# 이슈 생성 가능 에이전트 — issue-gate.py에서 harness_active 없이도 허용
ISSUE_CREATORS = ("qa", "designer", "architect", "product-planner")

# 이슈 번호 필수 에이전트 — 프롬프트에 #NNN 없으면 차단
ISSUE_REQUIRED_AGENTS = ("architect", "engineer")

# 하네스가 소유하는 커스텀 에이전트 화이트리스트 (Single Source of Truth).
# Claude Code 내장 서브에이전트(Explore, Plan, general-purpose, claude-code-guide,
# statusline-setup 등)는 이 집합 밖이며, 훅은 이들에 관여하지 않는다.
# - agent-gate.py: 이 집합 밖의 에이전트에는 {prefix}_{agent}_active 플래그를 만들지 않음.
# - agent-boundary.py: 이 집합 밖이면 active_agent로 인정하지 않고 메인 Claude와 동일 경로로 통과.
CUSTOM_AGENTS = frozenset({
    "architect",
    "engineer",
    "designer",
    "ux-architect",
    "validator",
    "pr-reviewer",
    "qa",
    "test-engineer",
    "security-reviewer",
    "design-critic",
    "product-planner",
})


def get_prefix():
    """프로젝트별 prefix를 env → harness.config.json (상위 순환) → 디렉토리명 → "proj" 폴백으로 유도."""
    # 훅 서브프로세스에서는 HARNESS_PREFIX env var가 전파되지 않을 수 있음.
    # HARNESS_PREFIX 환경변수가 있으면 최우선 사용.
    env_prefix = os.environ.get('HARNESS_PREFIX')
    if env_prefix:
        return env_prefix
    # CWD가 프로젝트 하위 디렉토리이거나 ~./claude 등 엉뚱한 위치일 수 있으므로
    # 현재 디렉토리부터 루트까지 순환하며 .claude/harness.config.json 탐색.
    cwd = os.path.abspath(os.getcwd())
    while True:
        config_path = os.path.join(cwd, ".claude", "harness.config.json")
        if os.path.exists(config_path):
            try:
                prefix = json.load(open(config_path)).get("prefix")
                if prefix:
                    return prefix
            except Exception:
                pass
        parent = os.path.dirname(cwd)
        if parent == cwd:   # 파일시스템 루트 도달
            break
        cwd = parent
    raw = os.path.basename(os.getcwd()).lower()
    return re.sub(r'[^a-z0-9]', '', raw)[:8] or "proj"


def deny(reason):
    """PreToolUse 훅에서 도구 실행을 거부한다."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)


def get_state_dir():
    """하네스 상태 디렉토리 반환. 프로젝트 .claude/harness-state/ 우선, 없으면 /tmp 폴백."""
    cwd = os.path.abspath(os.getcwd())
    while True:
        state_dir = os.path.join(cwd, ".claude", "harness-state")
        if os.path.isdir(state_dir):
            return state_dir
        # .claude 디렉토리만 있어도 harness-state 생성 가능한 프로젝트 루트
        claude_dir = os.path.join(cwd, ".claude")
        if os.path.isdir(claude_dir):
            os.makedirs(state_dir, exist_ok=True)
            return state_dir
        parent = os.path.dirname(cwd)
        if parent == cwd:
            break
        cwd = parent
    return "/tmp"


def get_flags_dir(issue_num=""):
    """플래그 전용 숨김 디렉토리 반환.
    issue_num이 있으면 이슈별 서브디렉토리. HARNESS_ISSUE_NUM env var도 참조."""
    state_dir = get_state_dir()
    if not issue_num:
        issue_num = os.environ.get("HARNESS_ISSUE_NUM", "")
    if issue_num:
        prefix = get_prefix()
        flags_dir = os.path.join(state_dir, ".flags", f"{prefix}_{issue_num}")
    else:
        flags_dir = os.path.join(state_dir, ".flags")
    os.makedirs(flags_dir, exist_ok=True)
    return flags_dir


def get_active_agent():
    """env var로 현재 에이전트 판별. 메인 Claude에는 없으므로 None 반환."""
    return os.environ.get("HARNESS_AGENT_NAME") or None


def flag_path(prefix, name):
    """플래그 파일 경로 반환."""
    return os.path.join(get_flags_dir(), f"{prefix}_{name}")


def flag_exists(prefix, name):
    """플래그 파일 존재 여부."""
    return os.path.exists(flag_path(prefix, name))
