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
    try:
        from .config import load_config
        from .core import StateDir, RunLogger, Flag
    except ImportError:
        from config import load_config
        from core import StateDir, RunLogger, Flag

    config = load_config()
    prefix = args.prefix or config.prefix
    issue_num = getattr(args, "issue_num", "") or ""

    # Phase 3: 세션 ID 부팅 — HARNESS_SESSION_ID env → .session-id 파일
    sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
    try:
        import session_state as ss  # type: ignore
    except ImportError:
        ss = None  # type: ignore
    session_id = ""
    if ss is not None:
        session_id = ss.current_session_id()
        if session_id:
            os.environ["HARNESS_SESSION_ID"] = session_id

    state_dir = StateDir(Path.cwd(), prefix, issue_num=issue_num)

    # HARNESS_ISSUE_NUM env var — hooks가 이슈별 플래그 디렉토리 참조
    if issue_num:
        os.environ["HARNESS_ISSUE_NUM"] = issue_num

    # Phase 3: 이슈 lock 획득 — 두 세션이 같은 이슈 동시 작업 방지
    if ss is not None and session_id and issue_num:
        try:
            ok, holder = ss.claim_issue_lock(prefix, issue_num, session_id, mode=args.mode)
            if not ok and holder:
                print(f"[HARNESS] 오류: 이슈 #{issue_num}은 세션 {holder.get('session_id','')[:8]}…가 "
                      f"PID {holder.get('pid')}로 이미 작업 중입니다.")
                print("동시 작업은 지원하지 않습니다. /harness-kill 또는 세션 완료를 기다리세요.")
                sys.exit(1)
            # 세션 live.json에 하네스/이슈 상태 기록
            ss.update_live(session_id, harness_active=True, issue_num=issue_num,
                           prefix=prefix, mode=args.mode)
        except Exception as e:
            print(f"[HARNESS] session_state 초기화 경고: {e}")

    # ── 병렬 실행 가드 (이슈별 잠금 — 다른 이슈는 동시 실행 가능) ──
    if issue_num:
        lock_file = state_dir.path / f"{prefix}_{issue_num}_harness_active"
    else:
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
                # Phase 3: 이슈 lock heartbeat도 갱신 — 장시간 루프가 stale 판정되지 않도록
                if ss is not None and session_id and issue_num:
                    try:
                        ss.heartbeat_issue_lock(prefix, issue_num, session_id)
                    except Exception:
                        pass

    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    # ── EXIT 정리 ──
    run_logger_ref: list = [None]  # mutable container for atexit closure
    _run_end_written = [False]

    def cleanup() -> None:
        hb_stop.set()
        lock_file.unlink(missing_ok=True)
        state_dir.flag_rm(Flag.HARNESS_KILL)
        # *_active 정리 (레거시 폴백 경로)
        for f in state_dir.flags_dir.glob(f"{prefix}_*_active"):
            f.unlink(missing_ok=True)
        # Phase 3: 이슈 lock 해제 + live.json 정리
        if ss is not None and session_id:
            try:
                if issue_num:
                    ss.release_issue_lock(prefix, issue_num, session_id)
                ss.update_live(session_id, harness_active=None, agent=None)
            except Exception:
                pass
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
        try:
            from .impl_router import run_impl
        except ImportError:
            from impl_router import run_impl
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
        try:
            from .plan_loop import run_plan
        except ImportError:
            from plan_loop import run_plan
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
