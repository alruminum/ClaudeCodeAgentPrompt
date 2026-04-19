#!/usr/bin/env python3
"""
Harness Session Start — SessionStart hook
S7: 세션 컨텍스트 브리지 — 프로젝트 상태 자동 주입
Phase 3: 세션 ID 기록 + 레거시 마이그레이션 + stale 세션/lock 청소
Usage: python3 harness-session-start.py [PREFIX|auto]
  auto: reads prefix from .claude/harness.config.json in CWD
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import get_state_dir
import session_state as ss

# .flags/ 내 _active 플래그 stale 기준 — 1시간 초과 시 세션 시작 시 제거
STALE_ACTIVE_FLAG_SEC = 60 * 60


def get_prefix(raw):
    if raw != "auto":
        return raw
    config_path = os.path.join(os.getcwd(), ".claude", "harness.config.json")
    if os.path.exists(config_path):
        try:
            cfg = json.load(open(config_path))
            return cfg.get("prefix", "proj")
        except Exception:
            pass
    return re.sub(r'[^a-z0-9]', '', os.path.basename(os.getcwd()).lower())[:8] or "proj"


def get_project_context(prefix):
    lines = []

    # 프로젝트 이름
    project_name = os.path.basename(os.getcwd())
    lines.append(f"프로젝트: {project_name}")

    # 최근 커밋
    try:
        log = subprocess.check_output(
            ["git", "log", "--oneline", "-3"],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode().strip()
        if log:
            lines.append(f"최근 커밋:\n  " + "\n  ".join(log.splitlines()))
    except Exception:
        pass

    # 백로그 진행 중 항목
    backlog_paths = [
        os.path.join(os.getcwd(), "backlog.md"),
        os.path.join(os.getcwd(), "docs", "harness-backlog.md"),
    ]
    for bp in backlog_paths:
        if os.path.exists(bp):
            try:
                content = open(bp).read()
                in_progress = re.findall(r'\|\s*\S+\s*\|\s*(.+?)\s*\|\s*\S+\s*\|\s*🔄', content)
                if in_progress:
                    lines.append("진행 중 항목: " + ", ".join(in_progress[:3]))
            except Exception:
                pass
            break

    # 현재 이슈 (이전 세션에서 기록된 경우)
    issue_file = os.path.join(get_state_dir(), f"{prefix}_last_issue")
    if os.path.exists(issue_file):
        try:
            issue = open(issue_file).read().strip()
            if issue:
                lines.append(f"마지막 이슈: #{issue}")
        except Exception:
            pass

    return lines


def _read_stdin_session_id():
    """SessionStart 훅 stdin에서 session_id 파싱. hang 방지 2초 타임아웃."""
    try:
        import select as _select
        if sys.stdin.isatty():
            return ""
        r, _, _ = _select.select([sys.stdin], [], [], 2.0)
        if not r:
            return ""
        raw = sys.stdin.read()
        if not raw.strip():
            return ""
        data = json.loads(raw)
        return ss.session_id_from_stdin(data)
    except (json.JSONDecodeError, OSError, ValueError):
        return ""


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else "auto"
    prefix = get_prefix(raw)

    # ── Phase 3: 세션 ID 기록 + 스켈레톤 확보 ─────────────────────────────
    sid = _read_stdin_session_id()
    if sid:
        try:
            ss.initialize_session(sid)
        except Exception:
            pass

    # ── Phase 3: 레거시 `.flags/` 1회 마이그레이션 (활성 하네스 있으면 skip) ──
    try:
        ss.migrate_legacy_flags()
    except Exception:
        pass

    # ── Phase 3: stale 세션/lock 청소 ──────────────────────────────────
    try:
        ss.cleanup_stale_sessions(keep=sid or None)
        ss.cleanup_stale_issue_locks()
    except Exception:
        pass

    # ── 탑레벨 플래그 초기화 (last_issue는 보존, harness_active 계열은 executor 소관이라 보존) ──
    for f in glob.glob(os.path.join(get_state_dir(), f'{prefix}_*')):
        if f.endswith('_last_issue'):
            continue
        if f.endswith('_harness_active'):
            continue
        try:
            os.remove(f)
        except Exception:
            pass

    # 컨텍스트 브리지 (S7)
    ctx_lines = get_project_context(prefix)
    if len(ctx_lines) > 1:  # 프로젝트명 외 정보가 있을 때만 주입
        ctx = "[HARNESS] 세션 시작\n" + "\n".join(ctx_lines)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": ctx
            }
        }))
    else:
        print("OK")


if __name__ == "__main__":
    main()
