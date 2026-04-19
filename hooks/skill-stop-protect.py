#!/usr/bin/env python3
"""skill-stop-protect.py — Stop 훅.

Phase 4.B: 활성 medium/heavy 스킬이 있으면 조기 종료 방지.

흐름:
1. /harness-kill 신호 감지 → 즉시 청소 + Stop 통과.
2. 활성 스킬 없음 → Stop 통과.
3. 활성 스킬 있음 + level이 medium/heavy:
   a. age >= TTL  OR  reinforcements >= max → 강제 청소 + Stop 통과.
   b. 그 외 → reinforcements +1, Stop을 차단(continue 메시지 주입).

heavy(ralph 등)는 PostToolUse(Skill)이 청소하지 않으므로 여기까지 도달.
medium도 보호 — 사용자가 medium 스킬 도중 실수로 Stop 발동한 경우 1~2회 재강화.

청소 책임 단일화:
- heavy 정상 lifecycle 종료 = 이 훅 (TTL/max 또는 kill).
- light/medium 정상 lifecycle 종료 = post-skill-flags (PostToolUse Skill).

OMC `cancel-skill-active-state-gap.md` 결함 회피: 청소 경로가 분산되면 한 곳
누락 시 상태가 잔존해 재강화 루프에 빠짐. 책임 단일화로 해결.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402
from skill_protection import get_policy, should_block_stop  # noqa: E402


def _read_stdin() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _log_event(event: dict) -> None:
    """진단 로그 — .claude/harness-state/.logs/skill-protect.jsonl"""
    try:
        root = ss.state_root()
        log_dir = root / ".logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "skill-protect.jsonl"
        event["ts"] = int(time.time())
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> int:
    d = _read_stdin()
    sid = ss.session_id_from_stdin(d) or ss.current_session_id()
    if not sid:
        return 0

    # 1) /harness-kill 신호 — 즉시 해제 후 Stop 통과
    try:
        if ss.get_global_signal().get("harness_kill"):
            cleared = ss.clear_active_skill(sid)
            if cleared:
                _log_event({"event": "kill_clear", "sid": sid})
            return 0
    except Exception:
        pass

    skill = ss.get_active_skill(sid)
    if not skill:
        return 0

    name = skill.get("name", "")
    level = skill.get("level", "none")
    if not should_block_stop(name, level):
        # 보호 대상 아님 (none/light, 또는 SELF_MANAGED_LIFECYCLE).
        # ralph-loop:ralph-loop는 자체 stop-hook이 prompt 재주입으로 lifecycle을
        # 관리한다 — 여기서 block을 출력하면 그 재주입을 막아 루프가 망가진다.
        return 0

    policy = get_policy(level)
    ttl = int(policy["ttl_sec"])
    max_reinf = int(policy["max_reinforcements"])
    started = int(skill.get("started_at", 0)) or int(time.time())
    reinf = int(skill.get("reinforcements", 0))
    age = int(time.time()) - started

    # 2a) TTL 또는 max 도달 → 청소 + Stop 통과
    if (ttl and age >= ttl) or reinf >= max_reinf:
        ss.clear_active_skill(sid, expect_name=name)
        _log_event({
            "event": "auto_release",
            "sid": sid, "skill": name, "level": level,
            "age": age, "ttl": ttl, "reinf": reinf, "max": max_reinf,
        })
        return 0

    # 2b) Stop 차단 + 재강화
    try:
        ss.bump_skill_reinforcement(sid)
    except Exception:
        pass

    msg = (
        f"⏳ [skill-protect] 스킬 '{name}' ({level}) 진행 중 — 조기 종료 방지. "
        f"작업을 계속하세요. ({reinf + 1}/{max_reinf}회 재강화, "
        f"age={age}s/TTL={ttl}s)"
    )
    _log_event({
        "event": "block_stop",
        "sid": sid, "skill": name, "level": level,
        "age": age, "reinf": reinf + 1, "max": max_reinf,
    })
    print(json.dumps({
        "decision": "block",
        "reason": msg,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
