---
depth: std
---
# impl #84 — `is_infra_project()` 헬퍼 + debug 로그 `is_infra` 필드

## 수용 기준 (이슈 #84 재인용)

- `is_infra_project()` 함수: 4신호 중 하나라도 참이면 `True` 반환
- 4신호 모두 거짓이면 `False` 반환
- `agent_boundary_debug.log` JSON 항목에 `"is_infra": true/false` 포함
- 일반 프로젝트(jajang, mb 등) cwd에서 `False` 반환 확인

---

## 변경 파일 목록

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `hooks/agent-boundary.py` | 수정 | `is_infra_project()` 함수 추가 + `_dbg` 딕셔너리에 `is_infra` 필드 삽입 |
| `hooks/tests/test_agent_boundary_is_infra.py` | 신규 | 4신호 단독 True, all-False, 로그 필드 존재 검증 |

---

## 1. `hooks/agent-boundary.py` — 변경 상세

### 1-1. `is_infra_project()` 함수 삽입 위치

현재 코드 구조:
```
# 상수 블록 (HARNESS_INFRA_PATTERNS, ALLOW_MATRIX, READ_DENY_MATRIX)
# ↓
def _resolve_active_agent(stdin_data): ...
# ↓
def main(): ...
```

**삽입 위치**: `_resolve_active_agent()` 정의 **바로 위** (상수 블록 끝과 `_resolve_active_agent` 사이).  
이유: 모듈 레벨 헬퍼 함수는 상수 다음, 주요 로직 함수 이전에 두는 기존 파일 관례를 따름.

### 1-2. `is_infra_project()` 구현 스펙

```python
def is_infra_project() -> bool:
    """현재 실행 컨텍스트가 인프라 프로젝트(~/.claude)인지 판단한다.

    4신호 OR 조건 — 하나라도 True이면 즉시 True 반환.
      신호 1: 환경변수 HARNESS_INFRA=1
      신호 2: 마커 파일 ~/.claude/.harness-infra 존재
      신호 3: 환경변수 CLAUDE_PLUGIN_ROOT 설정됨 (non-empty)
      신호 4: cwd가 ~/.claude 와 resolve() 기준으로 일치
    """
    from pathlib import Path

    # 신호 1 — env var explicit flag
    if os.environ.get("HARNESS_INFRA") == "1":
        return True

    # 신호 2 — 마커 파일
    if Path.home().joinpath(".claude", ".harness-infra").exists():
        return True

    # 신호 3 — plugin root env var
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return True

    # 신호 4 — cwd 일치
    try:
        infra_root = Path.home().joinpath(".claude").resolve()
        if Path(os.getcwd()).resolve() == infra_root:
            return True
    except Exception:
        pass  # getcwd() 실패(삭제된 디렉토리 등) 시 안전하게 False

    return False
```

**설계 결정:**

- `from pathlib import Path`를 함수 내부 import: `pathlib`은 현재 파일 최상단에 없으므로 함수 스코프 import로 추가 → 전역 import 블록 변경 없이 diff 최소화. 성능 영향 무시 가능 (훅 기준 < 1ms, Python 모듈 캐시로 재호출 비용 없음).
- `Path.home()` 사용: `os.environ.get("HOME")` fallback 내장 → CI 환경 안전.
- `resolve()` 사용: symlink가 `~/.claude`를 가리키는 경우도 인프라로 인식. 일관성 보장.
- `except Exception`으로 `getcwd()` OS 오류 전체 흡수: 훅은 fail-open 원칙. 예외가 차단 로직을 오염시키면 안 됨.

### 1-3. debug 로그 `_dbg` 딕셔너리 패치

**현재 `main()` 내 debug log 블록:**
```python
_dbg = {
    "ts": datetime.datetime.now().isoformat(),
    "prefix": prefix,
    "HARNESS_AGENT_NAME": os.environ.get("HARNESS_AGENT_NAME", ""),
    "HARNESS_SESSION_ID": os.environ.get("HARNESS_SESSION_ID", ""),
    "stdin_sid": ss.session_id_from_stdin(d),
    "HARNESS_PREFIX": os.environ.get("HARNESS_PREFIX", ""),
    "HARNESS_INTERNAL": os.environ.get("HARNESS_INTERNAL", ""),
    "tool": tool_name,
    "fp": fp,
}
```

**변경 후** (`"is_infra"` 필드를 마지막에 추가):
```python
_dbg = {
    "ts": datetime.datetime.now().isoformat(),
    "prefix": prefix,
    "HARNESS_AGENT_NAME": os.environ.get("HARNESS_AGENT_NAME", ""),
    "HARNESS_SESSION_ID": os.environ.get("HARNESS_SESSION_ID", ""),
    "stdin_sid": ss.session_id_from_stdin(d),
    "HARNESS_PREFIX": os.environ.get("HARNESS_PREFIX", ""),
    "HARNESS_INTERNAL": os.environ.get("HARNESS_INTERNAL", ""),
    "tool": tool_name,
    "fp": fp,
    "is_infra": is_infra_project(),   # ← 추가
}
```

**결정 근거:**
- `is_infra_project()`는 debug 로그 기록 시점에만 호출. 이번 이슈 스코프에서 차단 로직에는 사용하지 않음.
- 마지막 추가 → diff 최소화, 기존 로그 파서의 키 순서 의존성 미파괴.
- `_dbg` 블록 전체가 `try/except Exception: pass`로 감싸져 있어 `is_infra_project()` 내부 예외도 자동 흡수.

---

## 2. `hooks/tests/test_agent_boundary_is_infra.py` — 테스트 설계

### 2-1. 테스트 전략 선택 근거

`agent-boundary.py`는 최상단에 bypass 조건(`sys.exit(0)`)과 `harness_common`/`session_state` 의존성이 있어 **직접 import 불가**. 기존 테스트(`test_plugin_write_guard.py`)와 동일한 **subprocess + `HARNESS_FORCE_ENABLE=1`** 패턴 사용.

`is_infra_project()` 결과는 debug 로그(`agent_boundary_debug.log`)의 JSON에서 추출.

> **구현 전 확인 필수**: `harness_common.get_state_dir()`가 `HARNESS_STATE_DIR` env를 지원하는지 확인. 지원하면 `tempfile.TemporaryDirectory()`로 테스트별 격리 가능. 미지원이면 실제 state_dir 경로에서 마지막 로그 라인을 읽는 방식으로 대체.

### 2-2. 헬퍼 함수 스펙

```python
HOOKS_DIR = Path(__file__).resolve().parent.parent
HOOK = HOOKS_DIR / "agent-boundary.py"
PYTHON = sys.executable

# 최소 유효 payload — fp가 있어야 debug 로그 기록 경로를 통과
_MINIMAL_PAYLOAD = {
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/harmless.txt"},
}

def _run_hook(
    env_extra: dict | None = None,
    cwd: str | None = None,
) -> tuple[str, str, int]:
    env = {**os.environ}
    env["HARNESS_FORCE_ENABLE"] = "1"
    # 신호 1·3 환경변수 격리 (기존 값 제거)
    for k in ("HARNESS_INFRA", "CLAUDE_PLUGIN_ROOT"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [PYTHON, str(HOOK)],
        input=json.dumps(_MINIMAL_PAYLOAD),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )
    return p.stdout, p.stderr, p.returncode


def _last_log_is_infra(state_dir: str) -> bool | None:
    """state_dir의 마지막 debug 로그 라인에서 is_infra 값 추출."""
    log_path = Path(state_dir) / "agent_boundary_debug.log"
    if not log_path.exists():
        return None
    lines = log_path.read_text().strip().splitlines()
    if not lines:
        return None
    return json.loads(lines[-1]).get("is_infra")
```

### 2-3. 테스트 케이스 목록

| 클래스 | 메서드 | 검증 내용 |
|---|---|---|
| `TestIsInfraSignal1` | `test_harness_infra_env_true` | `HARNESS_INFRA=1` 설정 → `is_infra=True` |
| `TestIsInfraSignal3` | `test_claude_plugin_root_env_true` | `CLAUDE_PLUGIN_ROOT=/some/path` 설정 → `is_infra=True` |
| `TestIsInfraSignal4` | `test_cwd_equals_home_claude_true` | subprocess cwd=`~/.claude` → `is_infra=True` |
| `TestIsInfraSignal2` | `test_marker_file_true` | `mock.patch`로 `Path.exists` → True 강제 → `is_infra=True` |
| `TestIsInfraAllFalse` | `test_all_signals_off_false` | 4신호 모두 비활성, cwd=`/tmp` → `is_infra=False` |
| `TestDebugLogField` | `test_is_infra_key_present` | debug log JSON에 `"is_infra"` 키 존재 확인 |
| `TestDebugLogField` | `test_is_infra_value_is_bool` | `is_infra` 값이 Python `bool` 타입 (`true` 또는 `false`) |

**신호 2 (마커 파일) 테스트 주의:**
- `mock.patch("pathlib.Path.exists")` 로 실제 파일 조작 없이 테스트 (권장).
- 실파일 조작이 필요하면 `setUp()`에서 파일 사전 부재 확인, `tearDown()`에서 반드시 삭제.

**신호 4 (cwd) 테스트 주의:**
- `~/.claude` 디렉토리가 실제로 존재해야 함. 없으면 `self.skipTest()` 처리.
- subprocess `cwd` 파라미터로 `str(Path.home() / ".claude")` 전달.

### 2-4. 실행 커맨드

```bash
# 이슈 #84 테스트만
python3 -m unittest discover \
  -s ~/.claude/hooks/tests \
  -p 'test_agent_boundary_is_infra.py' -v

# 회귀 확인 (기존 integration 테스트)
python3 -m unittest discover \
  -s ~/.claude/hooks/tests \
  -p 'test_hook_integration.py' -v
```

---

## 3. 회귀 위험 & 방어

| 위험 | 가능성 | 방어 |
|---|---|---|
| `is_infra_project()` 내 예외가 차단 로직 오염 | 없음 | `_dbg` 블록 전체가 `try/except Exception: pass`로 보호됨 |
| `from pathlib import Path` 함수 스코프 부작용 | 없음 | stdlib, import 캐시됨 |
| 신호 4 cwd 테스트가 부모 프로세스에 영향 | 없음 | subprocess 격리 |
| 신호 2 마커 파일 테스트의 실환경 오염 | 있음 | `mock.patch` 우선; 실파일 조작 시 `tearDown` cleanup 필수 |
| 기존 차단 로직 회귀 | 낮음 | `test_hook_integration.py` PR 전후 실행으로 검증 |

---

## 4. 구현 순서

```
1. harness_common.get_state_dir()가 HARNESS_STATE_DIR env를 지원하는지 확인
2. hooks/tests/test_agent_boundary_is_infra.py 작성 (TDD — RED 확인)
3. hooks/agent-boundary.py 수정:
   a. is_infra_project() 함수 삽입
      (READ_DENY_MATRIX 상수 블록 끝 이후, _resolve_active_agent 바로 위)
   b. _dbg 딕셔너리 마지막에 "is_infra": is_infra_project() 추가
4. 테스트 GREEN 확인
5. test_hook_integration.py 회귀 확인
```

---

## 5. 경계 & 향후 확장 주의사항

- `is_infra_project()`는 **이번 이슈 스코프에서 진단/로깅 전용**. 차단 로직(`HARNESS_INFRA_PATTERNS`, `ALLOW_MATRIX`)에 연결하지 않는다.
- 향후 차단 로직 분기에 연결하려면 별도 이슈 + `deep` depth impl로 재계획할 것.
- `harness_common.py` 이전 검토: 다른 훅에서도 인프라 여부가 필요해지면 그 시점에 이전. 현재 스코프는 `agent-boundary.py` 단일 파일에 국한.
