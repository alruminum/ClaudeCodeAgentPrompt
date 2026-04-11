#!/usr/bin/env python3
"""
PostToolUse(Bash) hook: HARNESS_DONE / IMPLEMENTATION_ESCALATE / HARNESS_CRASH 감지
→ /tmp/harness_review_trigger.json 저장 → Stop hook이 /harness-review 자동 주입.
"""
import sys
import os
import json
import glob

MARKERS = ("HARNESS_DONE", "IMPLEMENTATION_ESCALATE", "HARNESS_CRASH", "KNOWN_ISSUE",
           "PLAN_VALIDATION_PASS", "PLAN_VALIDATION_ESCALATE")


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    resp = str(d.get("tool_response", ""))

    matched = next((m for m in MARKERS if m in resp), None)
    if not matched:
        sys.exit(0)

    # 이미 트리거 파일 있으면 중복 방지
    if os.path.exists("/tmp/harness_review_trigger.json"):
        sys.exit(0)

    # 가장 최신 JSONL 로그 탐색 (harness-logs 하위 전체)
    search_dirs = [
        os.path.expanduser("~/.claude/harness-logs"),
    ]
    # CWD .claude/harness-logs도 탐색
    cwd_logs = os.path.join(os.getcwd(), ".claude", "harness-logs")
    if os.path.isdir(cwd_logs):
        search_dirs.append(cwd_logs)

    all_jsonl = []
    for base in search_dirs:
        all_jsonl.extend(glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True))

    latest = max(all_jsonl, key=os.path.getmtime) if all_jsonl else None

    # 세션 JSONL 경로 탐색 (메인 Claude 로그 — 게이트 모순 감지용)
    session_jsonl = None
    try:
        import subprocess
        # CMUX_CLAUDE_PID 또는 부모 프로세스에서 세션 ID 추출
        pid = os.environ.get("CMUX_CLAUDE_PID", "")
        if pid:
            args = subprocess.check_output(["ps", "-p", pid, "-o", "args="],
                                           text=True, timeout=3).strip()
            import re
            m = re.search(r"session-id\s+([0-9a-f-]+)", args)
            if m:
                sid = m.group(1)
                # 프로젝트 디렉토리 = CWD를 대시로 치환
                cwd = os.getcwd()
                proj_hash = cwd.replace("/", "-")
                candidate = os.path.expanduser(f"~/.claude/projects/{proj_hash}/{sid}.jsonl")
                if os.path.exists(candidate):
                    session_jsonl = candidate
    except Exception:
        pass

    # fallback: 프로젝트 디렉토리에서 최근 수정된 세션 JSONL
    if not session_jsonl:
        try:
            cwd = os.getcwd()
            proj_hash = cwd.replace("/", "-")
            proj_dir = os.path.expanduser(f"~/.claude/projects/{proj_hash}")
            if os.path.isdir(proj_dir):
                sjsonls = glob.glob(os.path.join(proj_dir, "*.jsonl"))
                if sjsonls:
                    session_jsonl = max(sjsonls, key=os.path.getmtime)
        except Exception:
            pass

    trigger = {
        "marker": matched,
        "jsonl": latest,
        "session_jsonl": session_jsonl,
    }
    with open("/tmp/harness_review_trigger.json", "w") as f:
        json.dump(trigger, f, ensure_ascii=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
