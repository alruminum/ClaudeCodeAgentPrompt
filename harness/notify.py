"""하네스 종료 알림.

하네스 루프가 HARNESS_DONE / *_ESCALATE / HARNESS_CRASH 로 끝날 때 외부 알림을 보낸다.
`HARNESS_NOTIFY` 환경변수로 sink 선택. 미설정이면 아무것도 안 함.

### 지원 sink
- `osascript` : macOS Dock 알림 (기본 추천)
- `file:PATH` : 지정 파일에 줄 단위 append (예: `file:~/.claude/harness-events.log`)
- `webhook:URL` : POST JSON {tag, message}

### 복수 sink
쉼표로 나열: `HARNESS_NOTIFY=osascript,file:~/.claude/harness-events.log`

### 트리거
`HARNESS_DONE` + 모든 `*_ESCALATE` + `HARNESS_CRASH`. 중간 마커는 울리지 않는다.

### 호출
- `harness/core.py::RunLogger.write_run_end` 에서 자동 호출
- CLI 테스트: `python3 ~/.claude/harness/notify.py HARNESS_DONE mb 129 2712 3.42`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

# HARNESS_DONE 외 모든 ESCALATE 계열 + CRASH
_TRIGGER_SUFFIXES = ("ESCALATE", "ESCALATION_NEEDED", "CRASH", "CONFLICT")
_TRIGGER_EXACT = {"HARNESS_DONE"}


def _is_trigger(result: str) -> bool:
    if not result:
        return False
    if result in _TRIGGER_EXACT:
        return True
    return any(result.endswith(suf) for suf in _TRIGGER_SUFFIXES)


def notify(
    result: str,
    prefix: str = "",
    issue: str = "",
    elapsed: int = 0,
    cost_usd: float = 0.0,
    extra: str = "",
) -> None:
    """결과를 env var sink로 보낸다. 실패는 조용히."""
    if not _is_trigger(result):
        return
    sink_env = os.environ.get("HARNESS_NOTIFY", "").strip()
    if not sink_env:
        return

    is_done = result == "HARNESS_DONE"
    tag = "HARNESS_DONE" if is_done else "ESCALATE"

    m, s = divmod(max(0, int(elapsed)), 60)
    head = f"[{tag}] prefix={prefix or '?'}"
    if issue:
        head += f" issue=#{issue}"
    head += f" ({m}m{s:02d}s"
    if cost_usd > 0:
        head += f", ${cost_usd:.2f}"
    head += ")"
    if not is_done:
        head += f" result={result}"
    if extra:
        head += f" — {str(extra)[:120]}"

    for sink in [x.strip() for x in sink_env.split(",") if x.strip()]:
        try:
            _dispatch(sink, tag, head, is_done)
        except Exception as e:  # 알림 실패는 하네스 흐름을 막지 않음
            print(f"[notify] sink={sink} failed: {e}", file=sys.stderr)


def _dispatch(sink: str, tag: str, msg: str, is_done: bool) -> None:
    if sink == "osascript":
        _osascript(tag, msg, is_done)
    elif sink.startswith("file:"):
        _file_sink(sink[5:], msg)
    elif sink.startswith("webhook:"):
        _webhook(sink[8:], tag, msg)
    # 그 외는 조용히 무시


def _osascript(tag: str, msg: str, is_done: bool) -> None:
    title = "하네스 완료" if is_done else "하네스 에스컬레이션"
    sound = "Glass" if is_done else "Sosumi"
    # AppleScript 문자열 이스케이프 (역슬래시 먼저)
    msg_safe = msg.replace("\\", "\\\\").replace('"', '\\"')
    title_safe = title.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display notification "{msg_safe}" '
        f'with title "{title_safe}" sound name "{sound}"'
    )
    subprocess.run(
        ["osascript", "-e", script],
        timeout=3,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _file_sink(path: str, msg: str) -> None:
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")


def _webhook(url: str, tag: str, msg: str) -> None:
    data = json.dumps({"tag": tag, "message": msg}).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with request.urlopen(req, timeout=5) as resp:
            resp.read()
    except error.URLError:
        pass


if __name__ == "__main__":
    # CLI 테스트: python3 notify.py RESULT [prefix] [issue] [elapsed_s] [cost_usd]
    args = sys.argv[1:]
    if not args:
        print("usage: notify.py RESULT [prefix] [issue] [elapsed_s] [cost_usd]")
        sys.exit(2)
    notify(
        result=args[0],
        prefix=args[1] if len(args) > 1 else "",
        issue=args[2] if len(args) > 2 else "",
        elapsed=int(args[3]) if len(args) > 3 else 0,
        cost_usd=float(args[4]) if len(args) > 4 else 0.0,
    )
