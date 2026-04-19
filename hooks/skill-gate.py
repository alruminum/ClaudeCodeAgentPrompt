#!/usr/bin/env python3
"""skill-gate.py — PreToolUse(Skill) 글로벌 훅.

Phase 4.A: Skill 툴 호출 시 활성 스킬을 live.json.skill에 기록한다.

다른 훅(agent-boundary, harness-router, orch-rules-first)이 스킬 맥락을 읽어
정당한 작업을 오인 차단하지 않도록 한다.

청소는 PostToolUse(Skill)이 단일 책임자(post-skill-flags.py).
heavy 스킬은 PostToolUse가 청소하지 않고 Stop 훅 보호(skill-stop-protect.py)가
lifecycle을 관리한다.

설계 메모:
- OMC `skill-active-state.json` 분리 파일 모델 대신 `live.json.skill`로 통합.
  이유: live.json이 이미 세션 단일 소스 — 별도 파일은 청소 책임자 분산을 야기
  (OMC `cancel-skill-active-state-gap.md`가 정확히 그 결함을 박제).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402
from skill_protection import get_skill_level  # noqa: E402


def _read_stdin() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _skill_name(d: dict) -> str:
    """Skill 툴 입력에서 스킬 이름 추출. 가능한 키 변형 모두 시도."""
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

    sid = ss.session_id_from_stdin(d) or ss.current_session_id()
    if not sid:
        return 0

    level = get_skill_level(name)
    try:
        ss.set_active_skill(sid, name, level)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
