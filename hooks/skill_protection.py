"""skill_protection.py — Phase 4 스킬 보호 레벨 매핑 (Single Source of Truth).

각 스킬이 어떤 보호 강도를 갖는지 정의한다. 훅(skill-gate, post-skill-flags,
skill-stop-protect)이 이 모듈만 import해서 일관된 분류를 사용한다.

레벨:
- none: 즉시 종료/읽기 전용. 보호 없음 (live.json.skill에 기록은 하되 Stop 보호 미적용).
- light: 짧은 상호작용. PostToolUse 즉시 청소.
- medium: 다중 에이전트 호출. PostToolUse 즉시 청소 + Stop 훅이 1~2회 보호.
- heavy: 장시간 루프(ralph 등). PostToolUse 청소 안 함 — Stop 훅이 lifecycle 관리.

레벨별 정책 값(TTL/재강화 횟수)은 OMC `skill-active-state.json` 모델 참고:
- light: 5분/3회, medium: 15분/5회, heavy: 30분/10회.
"""
from __future__ import annotations

from typing import Dict

# 레벨별 정책 — 변경 시 이 dict 한 곳만 수정.
LEVEL_POLICIES: Dict[str, Dict[str, int]] = {
    "none":   {"ttl_sec": 0,    "max_reinforcements": 0},
    "light":  {"ttl_sec": 300,  "max_reinforcements": 3},
    "medium": {"ttl_sec": 900,  "max_reinforcements": 5},
    "heavy":  {"ttl_sec": 1800, "max_reinforcements": 10},
}

# 스킬 → 레벨 매핑. 매핑되지 않은 스킬은 DEFAULT_LEVEL.
# `plugin:skill` 네임스페이스 형태와 단순 이름 둘 다 지원
# (`get_skill_level`이 fallback 처리).
SKILL_LEVELS: Dict[str, str] = {
    # ── none: 즉시 종료/읽기 전용 ─────────────────────────────────────
    "harness-status": "none",
    "harness-monitor": "none",
    "harness-kill": "none",
    "harness-test": "none",
    "harness-review": "none",
    "deliver": "none",
    "doc-garden": "none",
    "ralph-loop:cancel-ralph": "none",
    "ralph-loop:help": "none",

    # ── light: 짧은 상호작용 ─────────────────────────────────────────
    "fewer-permission-prompts": "light",
    "update-config": "light",
    "keybindings-help": "light",
    "claude-api": "light",
    "skill-creator:skill-creator": "light",
    "init": "light",
    "review": "light",
    "security-review": "light",
    "simplify": "light",
    "knowledge-skills:docs-search": "light",
    "knowledge-skills:project-validator": "light",

    # ── medium: 다중 에이전트 호출 ────────────────────────────────────
    "ux": "medium",
    "qa": "medium",
    "product-plan": "medium",
    "init-project": "medium",

    # ── heavy: 장시간 루프 ───────────────────────────────────────────
    "ralph": "heavy",
    "loop": "heavy",
    "schedule": "heavy",
    "ralph-loop:ralph-loop": "heavy",
}

DEFAULT_LEVEL = "light"


def get_skill_level(name: str) -> str:
    """스킬 이름 → 레벨. 매핑 없으면 DEFAULT_LEVEL.
    `plugin:skill` 형태와 bare `skill` 형태를 모두 시도한다.
    빈 이름은 "none".
    """
    if not name:
        return "none"
    if name in SKILL_LEVELS:
        return SKILL_LEVELS[name]
    # plugin:skill → skill 단순 이름으로 fallback (마켓 명 변경에 강건)
    if ":" in name:
        bare = name.split(":", 1)[1]
        if bare in SKILL_LEVELS:
            return SKILL_LEVELS[bare]
    return DEFAULT_LEVEL


def get_policy(level: str) -> Dict[str, int]:
    """레벨 → {ttl_sec, max_reinforcements}. 알 수 없는 레벨은 light 폴백."""
    return LEVEL_POLICIES.get(level, LEVEL_POLICIES["light"])


# Stop 훅 보호에서 제외할 스킬 (자체 stop-hook이 lifecycle 관리하는 경우).
# 이 스킬들은 자기 plugin/stop-hook이 prompt 재주입으로 다음 iteration을 트리거하는데,
# skill-stop-protect가 `decision: block`을 출력하면 그 재주입이 막혀 루프가 망가진다.
# 따라서 level이 heavy여도 Stop 차단은 하지 않고, lifecycle은 자체 메커니즘에 위임.
SELF_MANAGED_LIFECYCLE: frozenset = frozenset({
    "ralph-loop:ralph-loop",
    "ralph-loop",
})


def should_block_stop(name: str, level: str) -> bool:
    """skill-stop-protect가 Stop을 차단해야 하는지.
    medium/heavy + SELF_MANAGED_LIFECYCLE에 속하지 않은 경우에만 True.
    """
    if name in SELF_MANAGED_LIFECYCLE:
        return False
    return level in ("medium", "heavy")


def is_protected(level: str) -> bool:
    """Stop 훅 보호 대상 여부 (이름 무관 — 레벨 기준).
    이름 기반 예외(SELF_MANAGED_LIFECYCLE) 처리는 should_block_stop이 담당.
    """
    return level in ("medium", "heavy")


def clears_on_post(level: str) -> bool:
    """PostToolUse(Skill)가 즉시 청소해도 되는지.
    heavy는 PostToolUse가 끝나도 작업이 Stop 훅 루프로 이어지므로 청소 금지.
    """
    return level != "heavy"
