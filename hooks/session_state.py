"""
session_state.py — 세션 격리 상태 API (Phase 3, session-isolation).

모든 훅과 하네스가 이 모듈을 통해 세션 스코프 상태를 읽고 쓴다.
기존의 `.flags/{prefix}_{agent}_active` 파일 + env var 폴백 + 15분 TTL 화이트리스트
같은 방어 로직을 하나의 `live.json` 단일 소스로 대체한다.

디렉토리 구조:
  .claude/harness-state/
  ├── .global.json                # 전역 신호 (lenient read — 세션 소유자 없음)
  ├── .session-id                 # 현재 세션 ID (subprocess 전파용)
  ├── .sessions/{sid}/            # 세션 스코프 (strict)
  │   ├── live.json               # 활성 agent/skill/issue/harness 상태
  │   └── flags/{prefix}_{issue}/ # 워크플로우 플래그 (Phase 2 구조 유지)
  ├── .issues/{prefix}_{issue}/
  │   └── lock                    # 이슈 단위 lock (세션 ID 기록)
  ├── .logs/
  └── .rate/

핵심 원칙:
  1. session_id는 훅 stdin(sessionId/session_id/sessionid)에서 파싱 — OMC 3변형.
  2. session_id regex 검증(path traversal 방지).
  3. 쓰기는 모두 atomic: O_EXCL tmp + fsync + rename + dir fsync, 0o600.
  4. `_meta` envelope으로 소유자 검증 — 다른 세션 쓰기면 읽을 때 무시.
  5. strict(session 스코프) / lenient(전역) 구분은 경로 자체가 강제.
  6. 워크플로우 플래그는 세션 × 이슈 스코프 파일로 유지 (Phase 2 호환).
"""
from __future__ import annotations

import json
import os
import re
import select
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ── session_id 검증 (OMC 패턴) ────────────────────────────────────────────
# path traversal 방어: 영숫자로 시작, 그 외 _/- 허용, 최대 256자
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$")

# ── TTL 상수 ────────────────────────────────────────────────────────────
DEFAULT_SESSION_TTL_SEC = 6 * 60 * 60     # 세션 디렉토리 stale 기준: 6시간
DEFAULT_LOCK_STALE_SEC = 30 * 60          # 이슈 lock heartbeat stale: 30분
STDIN_TIMEOUT_SEC = 2.0                   # 훅 stdin read 타임아웃 — hang 방지

_ATOMIC_FILE_MODE = 0o600


# ═══════════════════════════════════════════════════════════════════════
# 1. session_id 검증 / 획득
# ═══════════════════════════════════════════════════════════════════════

def valid_session_id(sid: Any) -> bool:
    if not isinstance(sid, str):
        return False
    return bool(_SESSION_ID_RE.match(sid))


def session_id_from_stdin(
    data: Optional[Dict[str, Any]] = None,
    timeout_sec: float = STDIN_TIMEOUT_SEC,
) -> str:
    """훅 stdin 또는 파싱된 dict에서 session_id 추출.
    OMC 패턴: sessionId / session_id / sessionid 3변형 fallback.
    검증 실패 시 빈 문자열.
    """
    d: Optional[Dict[str, Any]] = data
    if d is None:
        try:
            if sys.stdin.isatty():
                return ""
            if timeout_sec > 0:
                r, _, _ = select.select([sys.stdin], [], [], timeout_sec)
                if not r:
                    return ""
            raw = sys.stdin.read()
            d = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError, ValueError):
            return ""
    if not isinstance(d, dict):
        return ""
    sid = d.get("session_id") or d.get("sessionId") or d.get("sessionid") or ""
    return sid if valid_session_id(sid) else ""


def current_session_id(project_root: Optional[Path] = None) -> str:
    """현재 세션 ID 우선순위: HARNESS_SESSION_ID env → .session-id 파일.
    훅 서브프로세스가 stdin 이외 경로에서 세션을 알아내야 할 때 사용.
    """
    sid = os.environ.get("HARNESS_SESSION_ID", "")
    if valid_session_id(sid):
        return sid
    return read_session_pointer(project_root)


# ═══════════════════════════════════════════════════════════════════════
# 2. 프로젝트 루트 / state 루트 탐색
# ═══════════════════════════════════════════════════════════════════════

def _find_project_root(start: Optional[Path] = None) -> Path:
    """상위 순환 탐색으로 .claude/ 포함 디렉토리를 찾는다.
    훅 서브프로세스의 CWD가 프로젝트 하위일 수 있음.
    CWD가 삭제됐거나 접근 불가하면 home 폴백.
    """
    try:
        cwd = Path(start or os.getcwd()).resolve()
    except (FileNotFoundError, OSError):
        return Path.home()
    while True:
        try:
            if (cwd / ".claude").is_dir():
                return cwd
        except OSError:
            break
        if cwd.parent == cwd:
            break
        cwd = cwd.parent
    # 폴백: home — 전역 ~/.claude 모드
    return Path.home()


def state_root(project_root: Optional[Path] = None) -> Path:
    root = _find_project_root(project_root)
    d = root / ".claude" / "harness-state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_skeleton(project_root: Optional[Path] = None) -> Path:
    root = state_root(project_root)
    for sub in (".sessions", ".issues", ".logs", ".rate"):
        (root / sub).mkdir(exist_ok=True)
    return root


# ═══════════════════════════════════════════════════════════════════════
# 3. Atomic JSON read / write
# ═══════════════════════════════════════════════════════════════════════

def atomic_write_json(
    path: Path,
    data: Dict[str, Any],
    mode: str = "session",
    session_id: str = "",
) -> None:
    """OMC atomic write — O_EXCL tmp + fsync + rename + dir fsync, 0o600.
    data["_meta"]는 자동 주입(written_at/mode/sessionId).
    session_id 인자가 있으면 _meta.sessionId를 그것으로 세팅.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    prior_meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    payload["_meta"] = {
        "written_at": int(time.time()),
        "mode": mode,
        "sessionId": session_id or prior_meta.get("sessionId") or payload.get("session_id") or "",
    }
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _ATOMIC_FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    # directory fsync — rename durability
    try:
        dfd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════
# 4. 세션 스코프 경로
# ═══════════════════════════════════════════════════════════════════════

def session_dir(
    session_id: str,
    project_root: Optional[Path] = None,
    create: bool = True,
) -> Path:
    """세션 디렉토리. session_id 없거나 잘못된 형식이면 '_global' 폴백.
    전역 폴백은 하네스 루프 없이 스킬만 도는 lenient 경로용.
    create=False면 디렉토리 생성하지 않음(읽기 전용 경로).
    """
    root = state_root(project_root) if create else (_find_project_root(project_root) / ".claude" / "harness-state")
    slot = session_id if valid_session_id(session_id) else "_global"
    d = root / ".sessions" / slot
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def live_path(session_id: str, project_root: Optional[Path] = None) -> Path:
    """live.json 경로 — 읽기 전용이므로 디렉토리 미생성."""
    return session_dir(session_id, project_root, create=False) / "live.json"


def session_flags_dir(
    session_id: str,
    prefix: str,
    issue_num: str = "",
    project_root: Optional[Path] = None,
) -> Path:
    """세션 × 이슈 플래그 디렉토리. Phase 2 `{prefix}_{issue}` 구조 유지.
    하네스 executor가 이 경로를 StateDir.flags_dir로 사용 — 쓰기 용도이므로 생성.
    """
    sd = session_dir(session_id, project_root, create=True)
    if issue_num:
        d = sd / "flags" / f"{prefix}_{issue_num}"
    else:
        d = sd / "flags"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ═══════════════════════════════════════════════════════════════════════
# 5. .session-id 포인터 (subprocess 전파용)
# ═══════════════════════════════════════════════════════════════════════

def write_session_pointer(session_id: str, project_root: Optional[Path] = None) -> Optional[Path]:
    if not valid_session_id(session_id):
        return None
    root = state_root(project_root)
    pointer = root / ".session-id"
    try:
        pointer.write_text(session_id, encoding="utf-8")
        try:
            os.chmod(pointer, _ATOMIC_FILE_MODE)
        except OSError:
            pass
    except OSError:
        return None
    return pointer


def read_session_pointer(project_root: Optional[Path] = None) -> str:
    pointer = state_root(project_root) / ".session-id"
    if not pointer.exists():
        return ""
    try:
        sid = pointer.read_text(encoding="utf-8").strip()
        return sid if valid_session_id(sid) else ""
    except OSError:
        return ""


# ═══════════════════════════════════════════════════════════════════════
# 6. live.json (세션의 현재 활성 에이전트/스킬/이슈/하네스 상태)
# ═══════════════════════════════════════════════════════════════════════

def get_live(session_id: str, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """live.json 읽기. 소유자 불일치(_meta.sessionId ≠ session_id)면 빈 dict."""
    if not valid_session_id(session_id):
        return {}
    data = read_json(live_path(session_id, project_root))
    if not data:
        return {}
    meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    meta_sid = meta.get("sessionId", "")
    if meta_sid and meta_sid != session_id:
        # 다른 세션이 같은 경로에 덮어썼으면(이론상 불가능하나 방어) 거부
        return {}
    return {k: v for k, v in data.items() if k != "_meta"}


def update_live(session_id: str, project_root: Optional[Path] = None, **fields: Any) -> None:
    """read → merge → atomic write. 값이 None이면 필드 삭제."""
    if not valid_session_id(session_id):
        return
    current = get_live(session_id, project_root)
    current["session_id"] = session_id
    for k, v in fields.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v
    atomic_write_json(
        live_path(session_id, project_root),
        current,
        mode="session",
        session_id=session_id,
    )


def clear_live_field(
    session_id: str,
    field: str,
    expect_value: Any = None,
    project_root: Optional[Path] = None,
) -> bool:
    """필드 하나 삭제. expect_value가 주어지면 값이 일치할 때만 삭제.
    반환: 실제 삭제됐는지 여부.
    """
    if not valid_session_id(session_id):
        return False
    live = get_live(session_id, project_root)
    if field not in live:
        return False
    if expect_value is not None and live.get(field) != expect_value:
        return False
    update_live(session_id, project_root, **{field: None})
    return True


def clear_live(session_id: str, project_root: Optional[Path] = None) -> None:
    if not valid_session_id(session_id):
        return
    p = live_path(session_id, project_root)
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════
# 7. 현재 세션의 활성 에이전트 — 훅이 가장 자주 호출
# ═══════════════════════════════════════════════════════════════════════

def active_agent(
    stdin_data: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None,
) -> Optional[str]:
    """현재 세션의 활성 에이전트 이름 반환. 없으면 None.

    우선순위 (하네스 subprocess 경로 ↔ Agent 툴 in-process 경로 양쪽 대응):
      1) HARNESS_AGENT_NAME env — 하네스가 직접 주입한 권위 있는 신호.
         subprocess 경로(harness/core.py agent_call)에서는 새로 spawn된 claude CLI가
         고유 session_id를 갖는 서브프로세스이므로, stdin session_id로 live.json을 찾으면
         **빈 live.json**을 보게 됨. env가 이 갭을 막는다.
      2) stdin session_id → live.json.agent — Agent 툴 in-process 경로.
         부모 CC 세션의 PreToolUse(Agent)가 live.json.agent를 기록.
      3) HARNESS_SESSION_ID env / .session-id 파일 → live.json.agent — 최종 폴백.
    """
    # 1) 하네스가 명시적으로 주입한 에이전트 이름 (subprocess 경로 권위)
    env_agent = os.environ.get("HARNESS_AGENT_NAME") or ""
    if env_agent:
        return env_agent
    # 2) 훅 stdin 기반 — Agent 툴 경로
    sid = ""
    if stdin_data is not None:
        sid = session_id_from_stdin(stdin_data)
    # 3) 폴백 — pointer/env 세션 ID
    if not sid:
        sid = current_session_id(project_root)
    if not sid:
        return None
    live = get_live(sid, project_root)
    agent = live.get("agent") or ""
    return agent or None


# ═══════════════════════════════════════════════════════════════════════
# 8. 이슈 lock — 세션 밖 전역 경로에 저장, 두 세션 동일 이슈 진입 방지
# ═══════════════════════════════════════════════════════════════════════

def issue_lock_path(prefix: str, issue_num: str, project_root: Optional[Path] = None) -> Path:
    d = state_root(project_root) / ".issues" / f"{prefix}_{issue_num}"
    d.mkdir(parents=True, exist_ok=True)
    return d / "lock"


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def claim_issue_lock(
    prefix: str,
    issue_num: str,
    session_id: str,
    mode: str = "impl",
    project_root: Optional[Path] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """이슈 lock 획득 시도.
    성공: (True, None).
    이미 다른 세션이 잡고 있고 heartbeat 유효: (False, holder_info).
    holder의 PID 죽었거나 heartbeat stale: 인계하여 (True, None).
    """
    if not (valid_session_id(session_id) and issue_num):
        return (False, None)
    p = issue_lock_path(prefix, issue_num, project_root)
    now = int(time.time())
    if p.exists():
        data = read_json(p) or {}
        holder_sid = data.get("session_id", "")
        holder_pid = int(data.get("pid", 0) or 0)
        heartbeat = int(data.get("heartbeat", 0) or 0)
        # 같은 세션 재진입 — 업데이트만
        if holder_sid == session_id:
            data.update({
                "session_id": session_id,
                "pid": os.getpid(),
                "mode": mode,
                "heartbeat": now,
            })
            atomic_write_json(p, data, mode="issue-lock", session_id=session_id)
            return (True, None)
        # 다른 세션 — stale 판정
        alive = _pid_alive(holder_pid)
        fresh = heartbeat and (now - heartbeat) < DEFAULT_LOCK_STALE_SEC
        if alive and fresh:
            return (False, data)
        # stale — 인계
    data = {
        "session_id": session_id,
        "pid": os.getpid(),
        "mode": mode,
        "prefix": prefix,
        "issue_num": issue_num,
        "started": now,
        "heartbeat": now,
    }
    atomic_write_json(p, data, mode="issue-lock", session_id=session_id)
    return (True, None)


def heartbeat_issue_lock(
    prefix: str,
    issue_num: str,
    session_id: str,
    project_root: Optional[Path] = None,
) -> bool:
    p = issue_lock_path(prefix, issue_num, project_root)
    data = read_json(p)
    if not data or data.get("session_id") != session_id:
        return False
    data["heartbeat"] = int(time.time())
    atomic_write_json(p, data, mode="issue-lock", session_id=session_id)
    return True


def release_issue_lock(
    prefix: str,
    issue_num: str,
    session_id: str,
    project_root: Optional[Path] = None,
) -> bool:
    p = issue_lock_path(prefix, issue_num, project_root)
    if not p.exists():
        return True
    data = read_json(p)
    if data and data.get("session_id") != session_id:
        return False
    try:
        p.unlink()
    except OSError:
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════
# 9. 전역 신호 (lenient) — /harness-kill 등
# ═══════════════════════════════════════════════════════════════════════

def global_signal_path(project_root: Optional[Path] = None) -> Path:
    return state_root(project_root) / ".global.json"


def get_global_signal(project_root: Optional[Path] = None) -> Dict[str, Any]:
    return read_json(global_signal_path(project_root)) or {}


def set_global_signal(project_root: Optional[Path] = None, **fields: Any) -> None:
    current = get_global_signal(project_root)
    for k, v in fields.items():
        if v is None:
            current.pop(k, None)
        else:
            current[k] = v
    atomic_write_json(global_signal_path(project_root), current, mode="global")


# ═══════════════════════════════════════════════════════════════════════
# 10. Stale cleanup — SessionStart 훅이 호출
# ═══════════════════════════════════════════════════════════════════════

_PID_SLOT_RE = re.compile(r"^_pid-(\d+)-\d+$")


def cleanup_stale_sessions(
    project_root: Optional[Path] = None,
    ttl_sec: int = DEFAULT_SESSION_TTL_SEC,
    keep: Optional[str] = None,
) -> int:
    """오래된 세션 디렉토리 제거.

    스코프 (Phase 4 T4 명시):
    - 정규 session_id 디렉토리: live.json 또는 디렉토리 mtime이 ttl_sec 초과 시 제거.
    - `_pid-<pid>-<ts>` 폴백 슬롯 (commands/ralph.md가 session_id 미가용 시 생성):
      * holder PID가 살아있으면 보존(작업 중일 가능성).
      * 죽었거나 mtime이 ttl_sec 초과면 제거.
    - `_global` 폴백은 항상 보존(여러 일회성 작업이 공유 가능).
    - keep=현재 세션은 절대 제거하지 않음.

    반환: 삭제된 세션 수.
    """
    root = state_root(project_root)
    sessions_dir = root / ".sessions"
    if not sessions_dir.is_dir():
        return 0
    now = time.time()
    removed = 0
    for s in sessions_dir.iterdir():
        if not s.is_dir():
            continue
        if s.name == "_global":
            continue
        if keep and s.name == keep:
            continue
        try:
            live = s / "live.json"
            mtime = live.stat().st_mtime if live.exists() else s.stat().st_mtime
        except OSError:
            continue

        # `_pid-<pid>-<ts>` 폴백 슬롯: PID 활성 검사 우선
        m = _PID_SLOT_RE.match(s.name)
        if m:
            try:
                pid = int(m.group(1))
            except ValueError:
                pid = 0
            if pid and _pid_alive(pid):
                # 작업 중 — 보존. mtime 갱신은 호출자(ralph 등)의 기록이 알아서 함.
                continue
            # 죽은 PID — TTL과 무관하게 즉시 제거 (재현 불가)
            shutil.rmtree(s, ignore_errors=True)
            removed += 1
            continue

        # 정규 session_id: TTL 기반 제거
        if (now - mtime) > ttl_sec:
            shutil.rmtree(s, ignore_errors=True)
            removed += 1
    return removed


def cleanup_stale_issue_locks(
    project_root: Optional[Path] = None,
    ttl_sec: int = DEFAULT_LOCK_STALE_SEC,
) -> int:
    """heartbeat이 stale하거나 holder PID 죽은 이슈 lock 해제."""
    root = state_root(project_root)
    issues_dir = root / ".issues"
    if not issues_dir.is_dir():
        return 0
    now = time.time()
    removed = 0
    for d in issues_dir.iterdir():
        if not d.is_dir():
            continue
        lock = d / "lock"
        if not lock.exists():
            continue
        data = read_json(lock) or {}
        pid = int(data.get("pid", 0) or 0)
        heartbeat = int(data.get("heartbeat", 0) or 0)
        alive = _pid_alive(pid)
        fresh = heartbeat and (now - heartbeat) < ttl_sec
        if not (alive and fresh):
            try:
                lock.unlink()
                removed += 1
            except OSError:
                pass
    return removed


# ═══════════════════════════════════════════════════════════════════════
# 11. 레거시 `.flags/` 마이그레이션 (1회)
# ═══════════════════════════════════════════════════════════════════════

def migrate_legacy_flags(project_root: Optional[Path] = None) -> Dict[str, int]:
    """구 `.claude/harness-state/.flags/` 정리.
    활성 하네스 루프가 있으면 skip (안전 가드).
    반환: {"removed": N, "skipped": 0|1}.
    """
    root = state_root(project_root)
    result = {"removed": 0, "skipped": 0}
    # 활성 하네스 감지 — 탑레벨 *_harness_active 파일의 PID가 살아있으면 skip
    for active_file in root.glob("*_harness_active"):
        try:
            data = json.loads(active_file.read_text(encoding="utf-8"))
            if _pid_alive(int(data.get("pid", 0) or 0)):
                result["skipped"] = 1
                return result
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    legacy = root / ".flags"
    if legacy.is_dir():
        try:
            shutil.rmtree(legacy, ignore_errors=True)
            result["removed"] += 1
        except OSError:
            pass
    # 탑레벨 _active 잔재 (.claude_Explore_active 같은) 정리
    for f in root.glob("*_active"):
        # harness_active 계열은 살려둠 (executor lock)
        if f.name.endswith("_harness_active"):
            continue
        try:
            f.unlink()
            result["removed"] += 1
        except OSError:
            pass
    return result


# ═══════════════════════════════════════════════════════════════════════
# 12. 세션 초기화 (SessionStart에서 호출)
# ═══════════════════════════════════════════════════════════════════════

def initialize_session(
    session_id: str,
    project_root: Optional[Path] = None,
) -> Optional[Path]:
    """세션 시작 — 스켈레톤 확보 + .session-id 기록 + 빈 live.json 생성.
    session_id 무효하면 None 반환 (전역 모드로 운영).
    """
    if not valid_session_id(session_id):
        return None
    ensure_skeleton(project_root)
    write_session_pointer(session_id, project_root)
    sd = session_dir(session_id, project_root)
    lp = sd / "live.json"
    if not lp.exists():
        atomic_write_json(lp, {"session_id": session_id}, mode="session", session_id=session_id)
    return sd


# ═══════════════════════════════════════════════════════════════════════
# 13. Ralph 세션 작업 디렉토리 — /tmp 글로벌 경로의 세션 교차오염 차단
# ═══════════════════════════════════════════════════════════════════════

def ralph_dir(
    session_id: str,
    project_root: Optional[Path] = None,
    create: bool = True,
) -> Path:
    """세션 스코프 ralph 작업 디렉토리.
    기존 `/tmp/ralph_task_*.md`, `/tmp/ralph_{slug}_progress.md`가 세션 간에 공유돼
    stop-hook이 다른 세션 transcript를 claim하는 버그(ralph 루프2 오작동)를 일으켰기에,
    `.sessions/{sid}/ralph/` 하위로 옮겨 격리한다. session_id 무효 시 `_global` 폴백."""
    sd = session_dir(session_id, project_root, create=create)
    d = sd / "ralph"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def ralph_task_path(session_id: str, project_root: Optional[Path] = None) -> Path:
    """구조화된 프롬프트(task.md) 경로 — /tmp/ralph_task_*.md 대체."""
    return ralph_dir(session_id, project_root) / "task.md"


def ralph_progress_path(session_id: str, project_root: Optional[Path] = None) -> Path:
    """회차별 진행 상태(progress.md) 경로 — /tmp/ralph_{slug}_progress.md 대체."""
    return ralph_dir(session_id, project_root) / "progress.md"


def ralph_state_path(session_id: str, project_root: Optional[Path] = None) -> Path:
    """stop-hook이 참조하는 세션별 claim/iteration 상태(state.json)."""
    return ralph_dir(session_id, project_root) / "state.json"


# ═══════════════════════════════════════════════════════════════════════
# 14. 활성 스킬 (Phase 4 — 스킬 컨텍스트 보호)
# ═══════════════════════════════════════════════════════════════════════
#
# 메인 Claude가 /ux, /qa, /product-plan, /ralph 같은 스킬을 실행 중일 때
# 다른 훅(agent-boundary, harness-router, orch-rules-first)이 "지금 어떤
# 스킬이 돌고 있는지" 알 수 있어야 정당한 Bash/Edit를 오인 차단하지 않는다.
#
# OMC `skill-active-state.json`의 분리 파일 모델 대신 `live.json.skill` 단일
# 필드로 통합한다. 이유:
# - live.json은 이미 세션 단일 소스 — 별도 파일은 청소 책임자 분산을 야기
# - OMC `cancel-skill-active-state-gap.md`가 정확히 그 결함을 박제
# - "쓰는 자가 지운다" 원칙: PreToolUse(Skill)이 쓰고 PostToolUse(Skill)이 지움.
#
# heavy 스킬(ralph 등)은 PostToolUse가 청소하지 않는다 — Stop 훅 보호가
# lifecycle을 관리한다(skill-stop-protect.py).

def set_active_skill(
    session_id: str,
    name: str,
    level: str,
    project_root: Optional[Path] = None,
    started_at: Optional[int] = None,
) -> None:
    """live.json.skill 기록.
    skill = {name, level, started_at, reinforcements}.
    """
    if not (valid_session_id(session_id) and name):
        return
    update_live(session_id, project_root, skill={
        "name": name,
        "level": level or "light",
        "started_at": started_at if started_at is not None else int(time.time()),
        "reinforcements": 0,
    })


def get_active_skill(
    session_id: str,
    project_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """live.json.skill 읽기. 없거나 형식 오류면 None."""
    if not valid_session_id(session_id):
        return None
    live = get_live(session_id, project_root)
    skill = live.get("skill")
    if isinstance(skill, dict) and skill.get("name"):
        return skill
    return None


def clear_active_skill(
    session_id: str,
    expect_name: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """live.json.skill 삭제. expect_name 지정 시 이름 일치할 때만 삭제(중첩 안전).
    반환: 실제로 삭제됐는지."""
    if not valid_session_id(session_id):
        return False
    live = get_live(session_id, project_root)
    skill = live.get("skill")
    if not isinstance(skill, dict):
        return False
    if expect_name and skill.get("name") != expect_name:
        return False
    update_live(session_id, project_root, skill=None)
    return True


def bump_skill_reinforcement(
    session_id: str,
    project_root: Optional[Path] = None,
) -> int:
    """reinforcements 카운트 +1 후 반환. 활성 스킬 없으면 -1."""
    if not valid_session_id(session_id):
        return -1
    live = get_live(session_id, project_root)
    skill = live.get("skill")
    if not isinstance(skill, dict) or not skill.get("name"):
        return -1
    skill = dict(skill)
    skill["reinforcements"] = int(skill.get("reinforcements", 0)) + 1
    update_live(session_id, project_root, skill=skill)
    return skill["reinforcements"]


def active_skill(
    stdin_data: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """현재 세션의 활성 스킬 dict 또는 None.
    훅이 active_agent와 대칭으로 사용한다.
    """
    sid = ""
    if stdin_data is not None:
        sid = session_id_from_stdin(stdin_data)
    if not sid:
        sid = current_session_id(project_root)
    if not sid:
        return None
    return get_active_skill(sid, project_root)


# ═══════════════════════════════════════════════════════════════════════
# 15. 디버그/진단
# ═══════════════════════════════════════════════════════════════════════

def diagnostic_snapshot(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """현재 세션 상태 덤프 — harness-status 스킬용."""
    sid = current_session_id(project_root)
    return {
        "session_id": sid,
        "pointer": str(state_root(project_root) / ".session-id"),
        "live": get_live(sid, project_root) if sid else {},
        "global": get_global_signal(project_root),
    }
