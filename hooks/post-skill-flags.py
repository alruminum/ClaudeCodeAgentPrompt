#!/usr/bin/env python3
"""post-skill-flags.py — PostToolUse(Skill) 글로벌 훅.

Phase 4.A: 스킬 종료 후 live.json.skill 청소 (단일 책임자).

청소 정책 — `skill_protection.clears_on_post(level)`:
- none/light/medium: 즉시 청소.
- heavy: PostToolUse가 청소하지 않는다. Stop 훅 보호(skill-stop-protect)가
  TTL/max_reinforcements 또는 /harness-kill로 lifecycle을 관리한다.
  이유: heavy 스킬(ralph 등)은 Skill 툴이 return해도 후속 Stop-hook 루프로
  작업이 지속됨.

`expect_name`으로 race 가드: 같은 세션에서 다른 스킬이 즉시 새로 시작했을 때
이전 스킬의 PostToolUse가 새 스킬을 잘못 청소하는 사고 방지.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402
from skill_protection import get_skill_level, clears_on_post  # noqa: E402


def _read_stdin() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _skill_name(d: dict) -> str:
    inp = d.get("tool_input") or {}
    return (
        inp.get("skill")
        or inp.get("skillName")
        or inp.get("name")
        or ""
    )


def main() -> int:
    d = _read_stdin()
    if d.get("tool_name") != "Skill":
        return 0
    name = _skill_name(d)
    if not name:
        return 0

    level = get_skill_level(name)
    if not clears_on_post(level):
        # heavy: Stop 훅이 lifecycle 관리. 여기선 스킵.
        return 0

    sid = ss.session_id_from_stdin(d) or ss.current_session_id()
    if not sid:
        return 0

    try:
        ss.clear_active_skill(sid, expect_name=name)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
