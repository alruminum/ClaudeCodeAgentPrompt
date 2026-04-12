#!/usr/bin/env python3
"""
executor.py — executor.sh 대체.
CLI 진입점: python3 executor.py <mode> [--impl PATH] [--issue N] ...
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="하네스 워크플로우 라우터")
    parser.add_argument("mode", choices=["impl", "plan"], help="실행 모드")
    parser.add_argument("--impl", dest="impl_file", default="", help="impl 파일 경로")
    parser.add_argument("--issue", dest="issue_num", default="", help="이슈 번호")
    parser.add_argument("--prefix", default="", help="프로젝트 prefix")
    parser.add_argument("--depth", default="auto", choices=["auto", "simple", "std", "deep"])
    parser.add_argument("--context", default="", help="추가 컨텍스트")
    parser.add_argument("--branch-type", default="feat", help="브랜치 타입 (feat|fix)")

    args = parser.parse_args()

    # config + state_dir 초기화
    from .config import load_config
    from .core import StateDir, RunLogger, Flag

    config = load_config()
    prefix = args.prefix or config.prefix
    state_dir = StateDir(Path.cwd(), prefix)

    # ── 병렬 실행 가드 ──
    lock_file = state_dir.path / f"{prefix}_harness_active"
    if lock_file.exists():
        try:
            data = json.loads(lock_file.read_text())
            existing_pid = data.get("pid", 0)
            if existing_pid:
                try:
                    os.kill(existing_pid, 0)  # 살아있는지 확인
                    print(f"[HARNESS] 오류: 같은 PREFIX({prefix})로 이미 실행 중 (PID={existing_pid})")
                    print("동시 실행은 지원하지 않습니다. /harness-kill로 기존 실행을 중단하거나 완료를 기다리세요.")
                    sys.exit(1)
                except OSError:
                    # PID 죽었음 — stale lock 정리
                    lock_file.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            lock_file.unlink(missing_ok=True)

    lock_started = int(time.time())
    os.environ["HARNESS_RESULT"] = "unknown"

    def write_lease() -> None:
        try:
            lock_file.write_text(json.dumps({
                "pid": os.getpid(),
                "mode": args.mode,
                "started": lock_started,
                "heartbeat": int(time.time()),
            }))
        except OSError:
            pass

    write_lease()

    # ── Heartbeat (15초마다) ──
    hb_stop = threading.Event()

    def heartbeat_loop() -> None:
        while not hb_stop.is_set():
            hb_stop.wait(15)
            if not hb_stop.is_set():
                write_lease()

    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    # ── EXIT 정리 ──
    run_logger_ref: list = [None]  # mutable container for atexit closure
    _run_end_written = [False]

    def cleanup() -> None:
        hb_stop.set()
        lock_file.unlink(missing_ok=True)
        (state_dir.path / f"{prefix}_harness_kill").unlink(missing_ok=True)
        # *_active 정리
        for f in state_dir.path.glob(f"{prefix}_*_active"):
            f.unlink(missing_ok=True)
        # write_run_end — 루프 함수에서 이미 호출했으면 스킵 (이중 호출 방지)
        if run_logger_ref[0] and not _run_end_written[0]:
            result = os.environ.get("HARNESS_RESULT", "unknown")
            branch = os.environ.get("HARNESS_BRANCH", "")
            run_logger_ref[0].write_run_end(result, branch, args.issue_num)

    atexit.register(cleanup)

    # SIGTERM/SIGINT 핸들러 — bash trap EXIT가 SIGTERM에도 반응한 것과 동일
    def _signal_cleanup(signum: int, frame: object) -> None:
        cleanup()
        sys.exit(128 + signum)
    signal.signal(signal.SIGTERM, _signal_cleanup)
    signal.signal(signal.SIGINT, _signal_cleanup)

    # ── 모드 라우터 ──
    if args.mode == "impl":
        from .impl_router import run_impl
        run_logger = RunLogger(prefix, "impl", args.issue_num)
        run_logger_ref[0] = run_logger
        result = run_impl(
            impl_file=args.impl_file,
            issue_num=args.issue_num,
            prefix=prefix,
            depth=args.depth,
            context=args.context,
            branch_type=args.branch_type,
            run_logger=run_logger,
            config=config,
            state_dir=state_dir,
        )
        os.environ["HARNESS_RESULT"] = result
        _run_end_written[0] = True  # run_impl 내부에서 write_run_end 호출됨

    elif args.mode == "plan":
        from .plan_loop import run_plan
        run_logger = RunLogger(prefix, "plan", args.issue_num)
        run_logger_ref[0] = run_logger
        result = run_plan(
            issue_num=args.issue_num,
            prefix=prefix,
            context=args.context,
            config=config,
            state_dir=state_dir,
            run_logger=run_logger,
        )
        os.environ["HARNESS_RESULT"] = result
        _run_end_written[0] = True


if __name__ == "__main__":
    main()
