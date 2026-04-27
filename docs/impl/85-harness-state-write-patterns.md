---
depth: deep
---
# impl #85 — `HARNESS_STATE_WRITE_PATTERNS` 분리 + 인프라 모드 광역 차단 우회

## 수용 기준 (이슈 #85 재인용)

- `HARNESS_STATE_WRITE_PATTERNS` 상수가 별도 정의됨
- 인프라 모드에서 `harness-state/` 하위 Write는 여전히 차단
- 인프라 모드에서 `hooks/`, `harness/`, `scripts/` 등 Write는 허용
- 일반 프로젝트에서 광역 차단 동작 변경 없음

---

## 의존 관계

- **#84 필수**: `is_infra_project()` 헬퍼가 `agent-boundary.py` 내에 이미 구현되어 있어야 함.
  현재 main 브랜치 `agent-boundary.py` 확인 결과 `is_infra_project()` 포함되어 있음 (의존 충족).

---

## 변경 파일 목록

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `hooks/agent-boundary.py` | 수정 | `HARNESS_STATE_WRITE_PATTERNS` 상수 추가 + `main()` 내 인프라 분기 삽입 |
| `hooks/tests/test_agent_boundary_is_infra.py` | 수정 | `InfraBypassTests` 클래스 추가 (4 케이스) |

---

## 1. `hooks/agent-boundary.py` — 변경 상세

### 1-1. 현재 상수 블록 구조 (참조)

```python
# 하네스 인프라 파일 패턴 — 모든 에이전트에서 Read/Write/Edit 차단
HARNESS_INFRA_PATTERNS = [
    r'[./]claude/',
    r'hooks/',
    r'harness-(executor|loop|utils)\.sh',
    r'orchestration-rules\.md',
    r'setup-(harness|agents)\.sh',
]

# 에이전트별 허용 경로 패턴 (Write/Edit용)
ALLOW_MATRIX = { ... }

# 에이전트별 Read 금지 경로
READ_DENY_MATRIX = { ... }
```

### 1-2. 신규 상수 `HARNESS_STATE_WRITE_PATTERNS` 삽입 위치

`HARNESS_INFRA_PATTERNS` 정의 **바로 아래**에 추가.

**이유**: 두 상수는 의미적으로 연관(인프라 파일 패턴 패밀리)이므로 인접 배치. 코드 독자가 "왜 두 패턴이 있는가"를 주석으로 바로 파악할 수 있도록.

```python
# 하네스 런타임 상태 파일 패턴 — 인프라 모드에서도 Write/Edit를 차단해야 하는 경로
# (하네스 소스 파일과 달리 런타임 시 자동 생성·변경되는 상태 데이터)
HARNESS_STATE_WRITE_PATTERNS = [
    r'harness-state[/\\]',    # .claude/harness-state/** (플래그, 로그, live.json 등)
    r'\.sessions[/\\]',       # .sessions/{sid}/** (세션 스코프 상태)
    r'\.flags[/\\]',          # .flags/** (레거시 전역 플래그)
]
```

**설계 결정 — 패턴 범위 선택:**

| 후보 | 결정 | 근거 |
|---|---|---|
| `harness-state/` | **포함** | 런타임 상태의 루트 디렉토리. `live.json`, `agent_boundary_debug.log`, 플래그 파일 모두 포함 |
| `.sessions/` | **포함** | Phase 3 세션 격리 상태 파일. harness-state 밖의 세션 스코프 디렉토리 |
| `.flags/` | **포함** | 레거시 전역 플래그 디렉토리. `get_flags_dir()` 폴백 경로 |
| `live.json` (파일 단위) | **제외** | `harness-state/`에 이미 포함됨. 파일 단위 패턴은 이동 시 탈락 위험 |
| `hooks/`, `harness.sh` | **제외** | 이 패턴들은 소스 코드. 인프라 모드에서 허용 대상이므로 STATE 패턴에 넣으면 안 됨 |

`[/\\]` 슬래시·백슬래시 이중 처리: 훅이 Windows 경로에서 실행될 가능성 낮으나, `re.search` 패턴에서 OS 독립성 확보. 기존 `HARNESS_INFRA_PATTERNS`는 순수 `/` 사용 중 — 레거시 일관성보다 방어성 우선.

---

### 1-3. `main()` — 인프라 분기 삽입

#### 변경 전 (현재 코드, 변경 대상 섹션)

```python
    # ── 핸드오프 화이트리스트 ──
    HANDOFF_PATH_RE = re.compile(r'(^|/)[A-Za-z0-9_-]+_handoffs/')
    if HANDOFF_PATH_RE.search(fp):
        if tool_name in ("Read", "Glob", "Grep"):
            sys.exit(0)

    # ── 하네스 인프라 파일 Read/Write/Edit 차단 (모든 에이전트 공통) ──
    for pattern in HARNESS_INFRA_PATTERNS:
        if re.search(pattern, fp):
            deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 하네스 인프라 파일 접근 금지: "
                 f"{os.path.basename(fp)} (matched={pattern!r}). "
                 "프로젝트 소스(src/, docs/)만 분석 대상.")

    # Read 도구: 하네스 인프라 차단 + 에이전트별 READ_DENY_MATRIX 적용
    if tool_name in ("Read", "Glob", "Grep"):
        deny_patterns = READ_DENY_MATRIX.get(active_agent, [])
        for pattern in deny_patterns:
            if re.search(pattern, fp):
                deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 {os.path.basename(fp)} 읽기 금지. "
                     f"이 에이전트의 역할 범위 밖 파일입니다.")
        sys.exit(0)

    # ── 이하 Write/Edit 전용: 허용 경로 매트릭스 확인 ──
    allowed_patterns = ALLOW_MATRIX.get(active_agent, [])
    ...
```

#### 변경 후 코드

```python
    # ── 핸드오프 화이트리스트 ──
    HANDOFF_PATH_RE = re.compile(r'(^|/)[A-Za-z0-9_-]+_handoffs/')
    if HANDOFF_PATH_RE.search(fp):
        if tool_name in ("Read", "Glob", "Grep"):
            sys.exit(0)

    # ── 인프라 모드 분기: is_infra_project() True 시 광역 차단 우회 ──
    # 인프라 프로젝트(~/.claude)에서는 hooks/·agents/·harness/ 등 소스 파일을
    # 에이전트가 직접 편집해야 한다. 단, 런타임 상태 파일(harness-state/ 등)은
    # 어떤 모드에서도 직접 수정 금지.
    if is_infra_project():
        if tool_name in ("Write", "Edit"):
            for pattern in HARNESS_STATE_WRITE_PATTERNS:
                if re.search(pattern, fp):
                    deny(
                        f"❌ [hooks/agent-boundary.py] 인프라 모드에서도 harness 런타임 상태 파일 "
                        f"직접 수정 금지: {os.path.basename(fp)} (matched={pattern!r}). "
                        "harness-state/**는 harness 런타임 전용 — 직접 편집 시 상태 오염."
                    )
            # 상태 파일이 아닌 모든 Write/Edit 허용 (ALLOW_MATRIX 우회)
            sys.exit(0)
        # Read/Glob/Grep: READ_DENY_MATRIX만 적용 (HARNESS_INFRA_PATTERNS 우회)
        deny_patterns = READ_DENY_MATRIX.get(active_agent, [])
        for pattern in deny_patterns:
            if re.search(pattern, fp):
                deny(
                    f"❌ [hooks/agent-boundary.py] {active_agent}는 "
                    f"{os.path.basename(fp)} 읽기 금지. 이 에이전트의 역할 범위 밖 파일입니다."
                )
        sys.exit(0)

    # ── 하네스 인프라 파일 Read/Write/Edit 차단 (일반 프로젝트 — 기존 동작 유지) ──
    for pattern in HARNESS_INFRA_PATTERNS:
        if re.search(pattern, fp):
            deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 하네스 인프라 파일 접근 금지: "
                 f"{os.path.basename(fp)} (matched={pattern!r}). "
                 "프로젝트 소스(src/, docs/)만 분석 대상.")

    # Read 도구: 에이전트별 READ_DENY_MATRIX 적용
    if tool_name in ("Read", "Glob", "Grep"):
        deny_patterns = READ_DENY_MATRIX.get(active_agent, [])
        for pattern in deny_patterns:
            if re.search(pattern, fp):
                deny(f"❌ [hooks/agent-boundary.py] {active_agent}는 {os.path.basename(fp)} 읽기 금지. "
                     f"이 에이전트의 역할 범위 밖 파일입니다.")
        sys.exit(0)

    # ── 이하 Write/Edit 전용: 허용 경로 매트릭스 확인 ──
    allowed_patterns = ALLOW_MATRIX.get(active_agent, [])
    ...
```

**설계 결정 — ALLOW_MATRIX 우회:**

인프라 모드에서 Write/Edit가 HARNESS_STATE_WRITE_PATTERNS에 걸리지 않으면 `sys.exit(0)`으로 즉시 허용한다. ALLOW_MATRIX를 거치지 않는다.

이유:
- ALLOW_MATRIX는 일반 프로젝트에서 에이전트별 "허용 경로"를 제한하는 도구다 (e.g., architect는 `docs/`만 Write 가능).
- 인프라 프로젝트에서는 에이전트가 `hooks/`, `agents/`, `scripts/` 등 어디든 수정해야 하며, ALLOW_MATRIX에 이 경로가 없으면 전부 차단된다.
- 인프라 프로젝트는 `is_infra_project()`로 명시적으로 식별한 특수 컨텍스트이므로 ALLOW_MATRIX 우회가 정당하다.
- 대안: ALLOW_MATRIX에 `"infra": [r'.*']` 항목 추가 → 에이전트명 키 구조에 모드를 섞어 혼란 야기, 기각.

**설계 결정 — `is_infra_project()` 호출 위치:**

`main()` 최상단에서 캐싱하지 않고 분기 시점에 직접 호출한다.

이유:
- `_dbg` 블록에서 이미 한 번 호출되므로 두 번 호출되는 셈이나, 각각 다른 목적(로깅 vs 분기)이라 분리가 명확하다.
- 훅 성능 기준으로 함수 호출 오버헤드 무시 수준 (<1ms).
- 향후 캐싱이 필요하면 `is_infra_project()` 내부에서 모듈 레벨 캐시로 대응 가능.

---

### 1-4. 변경 요약

| 위치 | 변경 내용 |
|---|---|
| `HARNESS_INFRA_PATTERNS` 아래 (전역 상수 영역) | `HARNESS_STATE_WRITE_PATTERNS` 상수 추가 (~7줄) |
| `# ── 하네스 인프라 파일 ...` 블록 앞 | `if is_infra_project():` 분기 추가 (~18줄) |
| `# ── 하네스 인프라 파일 ...` 주석 | `(일반 프로젝트 — 기존 동작 유지)` 주석 추가 (1줄) |
| 기존 차단 로직 이하 | **변경 없음** |

---

## 2. `hooks/tests/test_agent_boundary_is_infra.py` — 테스트 추가

기존 파일에 `InfraBypassTests` 클래스를 **추가**한다. 기존 클래스(`IsInfraSignalTests`, `IsInfraAllFalseTests`, `IsInfraDebugLogFieldTests`)는 건드리지 않음.

### 2-1. 테스트 페이로드 상수 추가

기존 `_MINIMAL_PAYLOAD` (Read) 아래에 Write 페이로드 추가:

```python
# Write 페이로드 — hooks/ 경로 (인프라 모드에서 허용 대상)
_WRITE_PAYLOAD_HOOKS = {
    "tool_name": "Write",
    "tool_input": {
        "file_path": "/tmp/hooks/test.py",
        "content": "# test",
    },
}

# Write 페이로드 — harness-state/ 경로 (인프라 모드에서도 차단 대상)
_WRITE_PAYLOAD_STATE = {
    "tool_name": "Write",
    "tool_input": {
        "file_path": "/tmp/harness-state/live.json",
        "content": "{}",
    },
}
```

### 2-2. `InfraBypassTests` 클래스 스펙

```python
class InfraBypassTests(unittest.TestCase):
    """인프라 모드에서의 Write 차단/허용 분기 검증 (이슈 #85).

    수용 기준:
    - 인프라 모드 ON: harness-state/ Write → deny
    - 인프라 모드 ON: hooks/ Write → 허용 (stdout 비거나 deny 아님)
    - 인프라 모드 OFF: hooks/ 패턴은 일반 광역 차단 로직으로 처리됨
    """

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_project(self.root)
        self.state_dir = self.root / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def _run_write(self, payload: dict, infra_on: bool) -> subprocess.CompletedProcess:
        env = {**os.environ, "HARNESS_FORCE_ENABLE": "1"}
        for k in ("HARNESS_AGENT_NAME", "HARNESS_SESSION_ID", "HARNESS_INFRA", "CLAUDE_PLUGIN_ROOT"):
            env.pop(k, None)
        if infra_on:
            env["HARNESS_INFRA"] = "1"
        return subprocess.run(
            [PYTHON, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True, text=True,
            env=env, cwd=str(self.root), timeout=10,
        )

    def _is_denied(self, proc: subprocess.CompletedProcess) -> bool:
        if not proc.stdout.strip():
            return False
        try:
            out = json.loads(proc.stdout)
            return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        except json.JSONDecodeError:
            return False

    def test_infra_mode_state_write_denied(self) -> None:
        """인프라 모드: harness-state/ Write → deny."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / ".claude" / "harness-state" / "live.json"),
                "content": "{}",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(
            self._is_denied(proc),
            f"harness-state/ Write는 인프라 모드에서도 차단되어야 한다. stdout={proc.stdout!r}"
        )

    def test_infra_mode_hooks_write_allowed(self) -> None:
        """인프라 모드: hooks/test.py Write → 허용."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "hooks" / "test.py"),
                "content": "# test",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(
            self._is_denied(proc),
            f"hooks/ Write는 인프라 모드에서 허용되어야 한다. stdout={proc.stdout!r}"
        )

    def test_infra_mode_sessions_write_denied(self) -> None:
        """인프라 모드: .sessions/ Write → deny."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / ".sessions" / "abc123" / "live.json"),
                "content": "{}",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(
            self._is_denied(proc),
            f".sessions/ Write는 인프라 모드에서도 차단되어야 한다. stdout={proc.stdout!r}"
        )

    def test_normal_mode_infra_patterns_still_block(self) -> None:
        """일반 프로젝트(infra=False): HARNESS_INFRA_PATTERNS 광역 차단 유지.

        active_agent=None(메인 Claude) 경로에서는 hooks/가 src/·설계문서 패턴에
        미해당 → 허용될 수 있음. 이 케이스는 훅이 크래시 없이 종료함을 검증.
        실 agent 경로 차단 검증은 integration suite에서 live.json 주입으로 수행.
        """
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "hooks" / "test.py"),
                "content": "# test",
            },
        }
        proc = self._run_write(payload, infra_on=False)
        # 크래시 없이 종료(returncode=0)만 확인
        self.assertEqual(proc.returncode, 0, f"훅이 예외로 종료됨: stderr={proc.stderr!r}")
```

**케이스 선택 근거:**

| 케이스 | 수용 기준 매핑 |
|---|---|
| `test_infra_mode_state_write_denied` | "인프라 모드에서 `harness-state/` 하위 Write는 여전히 차단" |
| `test_infra_mode_hooks_write_allowed` | "인프라 모드에서 `hooks/` Write는 허용" |
| `test_infra_mode_sessions_write_denied` | `HARNESS_STATE_WRITE_PATTERNS`의 `.sessions/` 패턴 커버리지 |
| `test_normal_mode_infra_patterns_still_block` | "일반 프로젝트에서 광역 차단 동작 변경 없음" (크래시 없음 최소 보장) |

`test_normal_mode_infra_patterns_still_block`의 한계: Phase 3 live.json 없이 `active_agent=None`으로 실행되어 메인 Claude 경로를 타므로 `hooks/` 차단이 실제로 발화하지 않을 수 있다. 완전한 검증은 integration suite의 live.json 주입 케이스에서 수행한다. 이 케이스는 "인프라 모드 OFF일 때 훅이 예외 없이 종료"를 보장하는 연기 테스트(smoke test)다.

---

## 3. 회귀 위험 & 방어

| 위험 | 가능성 | 방어 |
|---|---|---|
| `is_infra_project()` True가 일반 프로젝트에서 발화 → 광역 차단 해제 | **낮음** | 4신호 모두 명시적 opt-in. `HARNESS_INFRA=1`은 사용자가 설정해야 함. cwd 신호는 `~/.claude` 경로 exact match |
| `HARNESS_STATE_WRITE_PATTERNS` 패턴 누락으로 런타임 상태 파일 Write 허용 | **중간** | 3패턴이 `get_state_dir()` + `get_flags_dir()` 출력 경로 전체 커버. 향후 신규 상태 디렉토리 추가 시 이 상수도 업데이트 필요 (코드 주석으로 명시) |
| 인프라 모드에서 ALLOW_MATRIX 우회 — 에이전트가 의도치 않은 파일 수정 | **낮음** | 인프라 프로젝트에서 에이전트가 hooks/ 수정 권한을 가져야 하는 게 정상. 상태 파일만 보호하면 충분 |
| Write/Edit 허용 후 Read 경로 재진입 | **없음** | `sys.exit(0)` 호출로 즉시 종료. Read/Glob/Grep 분기 진입 불가 |
| 기존 `IsInfraSignalTests` 등 회귀 | **없음** | 기존 클래스 코드 건드리지 않음. 새 클래스 추가만 |

---

## 4. 구현 순서

```
1. hooks/tests/test_agent_boundary_is_infra.py 에 InfraBypassTests 클래스 추가
   → 테스트 실행 → RED 확인
   python3 -m unittest hooks/tests/test_agent_boundary_is_infra.py -v

2. hooks/agent-boundary.py 수정:
   a. HARNESS_INFRA_PATTERNS 아래 HARNESS_STATE_WRITE_PATTERNS 상수 추가
   b. main() 내 핸드오프 블록 직후 is_infra_project() 분기 삽입
   c. 기존 HARNESS_INFRA_PATTERNS 루프 주석에 "(일반 프로젝트 — 기존 동작 유지)" 추가

3. 테스트 GREEN 확인
   python3 -m unittest hooks/tests/test_agent_boundary_is_infra.py -v

4. 회귀 확인
   python3 -m unittest discover -s hooks/tests/ -v
```

---

## 5. 경계 & 향후 확장 주의사항

- `HARNESS_STATE_WRITE_PATTERNS`는 현재 `hooks/agent-boundary.py` 단일 파일에만 정의. 다른 훅에서도 상태 파일 보호가 필요해지면 `harness_common.py`로 이전.
- 향후 새로운 런타임 상태 디렉토리 추가 시 (`get_state_dir()` 또는 `get_flags_dir()` 변경) → `HARNESS_STATE_WRITE_PATTERNS`도 반드시 함께 업데이트 (단일 진실 공급원 원칙).
- 인프라 모드에서 `READ_DENY_MATRIX`는 여전히 적용된다. 에이전트 역할 경계는 인프라 모드에서도 Read 수준에서 유지.
- `test_normal_mode_infra_patterns_still_block`의 완전한 agent 경로 검증은 integration suite에서 live.json 주입 케이스로 추가 예정.
