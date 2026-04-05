#!/usr/bin/env python3
"""
Harness Session Start — SessionStart hook
S7: 세션 컨텍스트 브리지 — 프로젝트 상태 자동 주입
Usage: python3 harness-session-start.py [PREFIX|auto]
  auto: reads prefix from .claude/harness.config.json in CWD
"""
import glob
import json
import os
import re
import subprocess
import sys


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
            stderr=subprocess.DEVNULL
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
    issue_file = f"/tmp/{prefix}_last_issue"
    if os.path.exists(issue_file):
        try:
            issue = open(issue_file).read().strip()
            if issue:
                lines.append(f"마지막 이슈: #{issue}")
        except Exception:
            pass

    return lines


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else "auto"
    prefix = get_prefix(raw)

    # 플래그 초기화 (last_issue는 보존)
    for f in glob.glob(f'/tmp/{prefix}_*'):
        if not f.endswith('_last_issue'):
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
                "additionalContext": ctx
            }
        }))
    else:
        print("OK")


if __name__ == "__main__":
    main()
