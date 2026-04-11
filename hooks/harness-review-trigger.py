#!/usr/bin/env python3
"""
PostToolUse(Bash) hook: HARNESS_DONE / IMPLEMENTATION_ESCALATE / HARNESS_CRASH 감지
→ harness-review.py 자동 실행 → *_review-result.json 저장 → inject 훅이 다음 프롬프트에 주입.
"""
import sys
import os
import json
import glob

MARKERS = ("HARNESS_DONE", "IMPLEMENTATION_ESCALATE", "HARNESS_CRASH", "KNOWN_ISSUE",
           "PLAN_VALIDATION_PASS", "PLAN_VALIDATION_ESCALATE")

REVIEW_SCRIPT = os.path.expanduser("~/.claude/scripts/harness-review.py")


def _find_session_jsonl():
    """현재 세션의 JSONL 경로를 탐색한다."""
    try:
        import subprocess, re
        pid = os.environ.get("CMUX_CLAUDE_PID", "")
        if pid:
            args = subprocess.check_output(["ps", "-p", pid, "-o", "args="],
                                           text=True, timeout=3).strip()
            m = re.search(r"session-id\s+([0-9a-f-]+)", args)
            if m:
                sid = m.group(1)
                proj_hash = os.getcwd().replace("/", "-")
                candidate = os.path.expanduser(f"~/.claude/projects/{proj_hash}/{sid}.jsonl")
                if os.path.exists(candidate):
                    return candidate
    except Exception:
        pass

    # fallback: 최근 수정 파일
    try:
        proj_hash = os.getcwd().replace("/", "-")
        proj_dir = os.path.expanduser(f"~/.claude/projects/{proj_hash}")
        if os.path.isdir(proj_dir):
            sjsonls = glob.glob(os.path.join(proj_dir, "*.jsonl"))
            if sjsonls:
                return max(sjsonls, key=os.path.getmtime)
    except Exception:
        pass
    return None


def _find_latest_harness_log():
    """가장 최신 하네스 JSONL 로그를 탐색한다."""
    search_dirs = [os.path.expanduser("~/.claude/harness-logs")]
    cwd_logs = os.path.join(os.getcwd(), ".claude", "harness-logs")
    if os.path.isdir(cwd_logs):
        search_dirs.append(cwd_logs)

    all_jsonl = []
    for base in search_dirs:
        all_jsonl.extend(glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True))

    return max(all_jsonl, key=os.path.getmtime) if all_jsonl else None


def _run_review(harness_jsonl, session_jsonl):
    """harness-review.py를 실행해 리포트를 반환한다."""
    import subprocess
    cmd = ["python3", REVIEW_SCRIPT, harness_jsonl]
    if session_jsonl:
        cmd.extend(["--session-jsonl", session_jsonl])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip()
    except Exception:
        return None


def _get_state_dir():
    """harness_common 없이 state_dir 계산."""
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".claude", "harness-state")
    if os.path.isdir(candidate):
        return candidate
    return os.path.expanduser("~/.claude/harness-state")


def _extract_prefix_from_log(harness_jsonl):
    """하네스 JSONL에서 prefix를 추출한다."""
    try:
        with open(harness_jsonl) as f:
            for line in f:
                e = json.loads(line.strip())
                if e.get("event") == "run_start":
                    return e.get("prefix", "")
                break
    except Exception:
        pass
    # fallback: 디렉토리 이름
    return os.path.basename(os.path.dirname(harness_jsonl))


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

    harness_jsonl = _find_latest_harness_log()
    session_jsonl = _find_session_jsonl()

    # 트리거 파일 저장 (중복 방지 + 디버그용)
    trigger = {
        "marker": matched,
        "jsonl": harness_jsonl,
        "session_jsonl": session_jsonl,
    }
    with open("/tmp/harness_review_trigger.json", "w") as f:
        json.dump(trigger, f, ensure_ascii=False)

    # harness-review.py 자동 실행 → review-result.json 저장
    if harness_jsonl and os.path.exists(REVIEW_SCRIPT):
        report = _run_review(harness_jsonl, session_jsonl)
        if report:
            prefix = _extract_prefix_from_log(harness_jsonl)
            state_dir = _get_state_dir()
            result_path = os.path.join(state_dir, f"{prefix}_review-result.json")
            try:
                result = {
                    "marker": matched,
                    "report": report,
                    "harness_jsonl": harness_jsonl,
                    "session_jsonl": session_jsonl,
                }
                os.makedirs(state_dir, exist_ok=True)
                with open(result_path, "w") as f:
                    json.dump(result, f, ensure_ascii=False)
            except Exception:
                pass

    sys.exit(0)


if __name__ == "__main__":
    main()
