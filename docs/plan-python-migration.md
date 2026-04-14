# 하네스 코어 전면 Python 전환 플랜

> 작성일: 2026-04-12
> 목표: ~/.claude/harness/*.sh (약 4,500 LOC Bash) → Python 3.9+ stdlib only (약 1,500 LOC 예상)
> 전제: Claude가 구현, 토큰 비용으로 해결. 사람 엔지니어링 시간 아님.

---

## 1. 왜 Python인가 (TypeScript/Bun이 아닌 이유)

### OMO가 TypeScript/Bun을 선택한 이유
- OpenCode 자체가 TypeScript → 같은 언어로 플러그인 작성
- Bun의 `$` shell API가 쉘 스크립팅에 편리
- `bun build --compile`로 단일 바이너리 배포 가능

### 우리 사용 사례에서 Python이 맞는 근거

**근거 1: 런타임 가용성**
- macOS에 `python3`이 Xcode CLT와 함께 기본 탑재 (3.9.6+)
- `bun`은 어떤 OS에도 기본 탑재되지 않음 → 추가 설치 필요
- Claude Code의 Bash 도구에서 호출: `python3 executor.py` = `bash executor.sh`와 동일한 가용성

**근거 2: 프로세스 관리**
- 현재 `_agent_call()`의 핵심: `claude --print --verbose ... | tee | python3 -c '...'`
- 이 스트리밍 파이프라인이 Python의 `subprocess.Popen` + `for line in proc.stdout`로 가장 자연스럽게 매핑됨
- Node.js의 `child_process.spawn`은 콜백/이벤트 기반 → 같은 패턴에 더 많은 코드 필요

**근거 3: 의존성 제로**
- 필요한 모든 기능이 Python stdlib: `subprocess`, `json`, `pathlib`, `argparse`, `fcntl`, `dataclasses`
- TypeScript는 argparse(`commander`), file lock(`proper-lockfile`) 등 npm 의존 필요

**근거 4: 생태계 정렬**
- SWE-agent, OpenHands, Aider, CrewAI, AutoGPT — 에이전트 오케스트레이션 도구 전부 Python
- TypeScript는 IDE 제품(Cursor, Claude Code 자체)에 사용 → 다른 레이어

**근거 5: 기존 코드와의 연속성**
- 현재 hooks/*.py가 이미 Python (harness_common.py, agent-boundary.py 등)
- harness-review.py도 Python
- Python 전환 시 hooks와 같은 언어 → import 공유 가능

---

## 2. 목표

### 기능 동등성 (Feature Parity)
전환 후 시스템이 동일하게 동작해야 함:
- `python3 executor.py impl --impl <path> --issue <N> --prefix <P>` = 현재 `bash executor.sh impl ...`
- 동일한 JSONL 이벤트 출력 (run_start, agent_start, agent_end, agent_stats, run_end)
- 동일한 마커 파싱 (---MARKER:PASS--- 등)
- 동일한 플래그 파일 생성/삭제 (.claude/harness-state/)
- 동일한 harness-memory.md 기록
- 동일한 git 브랜치 생성/커밋/머지 동작

### 동시 달성할 개선 (전환 과정에서 자연스럽게)
- `harness.config.json`에서 `test_command`, `lint_command` 읽기 (W5 해결)
- BSD/GNU grep 호환 문제 영구 제거 (Python re 모듈로 대체)
- jq 의존 제거 (Python json 모듈로 대체)
- 도메인별 토큰 예산 (`token_budget` config)

### 하지 않는 것
- 에이전트 팀 전환 (별도 Phase)
- 에이전트 프롬프트(agents/*.md) 변경 없음
- 훅(hooks/*.py) 변경 없음 (호출 인터페이스 동일)
- orchestration-rules.md 변경 없음
- JSONL 이벤트 스키마 변경 없음 (harness-review.py 호환 유지)

---

## 3. 파일 매핑

### 현재 Bash → Python 매핑

| 현재 Bash | Python 대체 | 비고 |
|-----------|------------|------|
| `executor.sh` (134줄) | `executor.py` | CLI 진입점. argparse로 모드/플래그 파싱 |
| `impl.sh` (212줄) | `impl_router.py` | architect 선택 + depth 감지 + dispatcher |
| `impl_std.sh` (465줄) | `impl_loop.py` 내 `run_std()` | depth별 로직을 하나의 모듈로 통합 |
| `impl_simple.sh` (329줄) | `impl_loop.py` 내 `run_simple()` | 〃 |
| `impl_deep.sh` (495줄) | `impl_loop.py` 내 `run_deep()` | 〃 |
| `impl_helpers.sh` (255줄) | `helpers.py` | constraints, checks, memory, commit |
| `utils.sh` (966줄) | `core.py` | state, logging, agent_call, context, git |
| `flags.sh` (29줄) | `core.py` 내 `Flag` enum + helpers | 상수 + touch/rm/exists |
| `markers.sh` (35줄) | `core.py` 내 `Marker` enum + parser | 상수 + regex 파서 |
| `plan.sh` (102줄) | `plan_loop.py` | product-planner → architect → validator |
| `design.sh` (209줄) | 제거 (DEPRECATED) | ux 스킬이 직접 호출 |
| `review-agent.sh` (176줄) | `review_agent.py` | 리뷰 트리거 |

### 새로 생성되는 파일

```
~/.claude/harness/
├── executor.py          # CLI 진입점 (executor.sh 대체)
├── core.py              # 공용 인프라 (utils.sh + flags.sh + markers.sh 통합)
├── config.py            # harness.config.json 로더 (신규)
├── impl_router.py       # impl.sh 대체 (architect 선택 + depth 감지)
├── impl_loop.py         # impl_simple/std/deep.sh 통합
├── helpers.py           # impl_helpers.sh 대체
├── plan_loop.py         # plan.sh 대체
├── review_agent.py      # review-agent.sh 대체
├── executor.sh          # 1줄 래퍼: exec python3 "$(dirname "$0")/executor.py" "$@"
└── (기존 .sh 파일들은 삭제하지 않고 .sh.bak으로 보존)
```

### 변경하지 않는 파일

```
~/.claude/harness/
├── RULE_INDEX.md        # 변경 없음
├── tests/               # BATS → pytest로 점진 전환 (별도 작업)
~/.claude/agents/*.md    # 변경 없음
~/.claude/hooks/*.py     # 변경 없음 (호출 인터페이스 동일)
~/.claude/scripts/harness-review.py  # 변경 없음 (JSONL 스키마 동일)
~/.claude/orchestration-rules.md     # 변경 없음
~/.claude/orchestration/*.md         # 변경 없음
~/.claude/commands/*.md              # executor.sh 호출 경로만 변경 (→ executor.py)
```

---

## 4. 모듈별 상세 설계

### 4.1 config.py — 설정 로더 (신규)

```python
@dataclass
class HarnessConfig:
    prefix: str = "proj"
    test_command: str = "npx vitest run"       # W5 해결
    lint_command: str = "npx tsc --noEmit"     # W5 해결
    max_total_cost: float = 10.0
    token_budget: dict = field(default_factory=lambda: {
        "frontend": 180_000,
        "backend": 280_000,
        "default": 250_000
    })

def load_config(project_root: Path) -> HarnessConfig:
    """harness.config.json → HarnessConfig. 파일 없으면 기본값."""
```

**영향**: 현재 PREFIX 감지 로직이 executor.sh, utils.sh, hooks/harness_common.py에 3중 구현. config.py로 단일화.

### 4.2 core.py — 공용 인프라 (utils.sh 966줄 대체)

```python
# ── 상태 관리 ──
class StateDir:
    """프로젝트별 .claude/harness-state/ 관리"""
    def __init__(self, project_root: Path, prefix: str): ...
    def flag_touch(self, name: str): ...
    def flag_rm(self, name: str): ...
    def flag_exists(self, name: str) -> bool: ...

# ── 플래그 상수 ──
class Flag(str, Enum):
    HARNESS_ACTIVE = "harness_active"
    PLAN_VALIDATION_PASSED = "plan_validation_passed"
    TEST_ENGINEER_PASSED = "test_engineer_passed"
    # ... (flags.sh의 모든 상수)

# ── 마커 ──
class Marker(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SPEC_GAP_FOUND = "SPEC_GAP_FOUND"
    # ... (markers.sh의 모든 마커)

def parse_marker(filepath: Path, patterns: str) -> str:
    """파일에서 ---MARKER:X--- 추출. BSD/GNU grep 호환 문제 없음."""
    # re.search(r'---MARKER:(PASS|FAIL|...)---', content)

# ── JSONL 로깅 ──
class RunLogger:
    """JSONL 이벤트 로거 (rotate + write)"""
    def __init__(self, prefix: str, mode: str, issue: str = ""): ...
    def log_event(self, event: dict): ...
    def log_agent_start(self, agent: str, prompt_chars: int): ...
    def log_agent_end(self, agent: str, elapsed: int, cost: float): ...

# ── 에이전트 호출 ──
def agent_call(
    agent: str,
    timeout_secs: int,
    prompt: str,
    out_file: Path,
    run_logger: RunLogger,
    config: HarnessConfig,
) -> int:
    """
    claude --agent <agent> --print --verbose ... 실행
    stream-json을 line-by-line 파싱하여 result/cost/stats 추출
    현재 _agent_call()의 Bash+Python 파이프라인을 순수 Python으로 통합
    """
    # subprocess.Popen → for line in proc.stdout → json.loads

# ── Git 유틸 ──
def create_feature_branch(branch_type: str, issue: str) -> str: ...
def collect_changed_files() -> list[str]: ...
def generate_commit_msg() -> str: ...
def merge_to_main(branch: str, issue: str, depth: str, prefix: str) -> bool: ...

# ── 컨텍스트 빌더 ──
def build_smart_context(impl_file: Path, attempt: int) -> str: ...
def build_validator_context(impl_file: Path) -> str: ...

# ── 히스토리 관리 ──
def prune_history(loop_dir: Path): ...
def write_attempt_meta(meta_file: Path, **kwargs): ...

# ── 킬 체크 ──
def kill_check(state_dir: StateDir, prefix: str): ...
```

### 4.3 impl_loop.py — 구현 루프 통합 (impl_simple/std/deep.sh 합계 1,289줄 대체)

```python
def run_simple(impl_file: Path, issue: str, config: HarnessConfig, ...):
    """depth=simple: engineer → pr-reviewer → merge"""

def run_std(impl_file: Path, issue: str, config: HarnessConfig, ...):
    """depth=std: engineer → test-engineer → validator → pr-reviewer → merge"""

def run_deep(impl_file: Path, issue: str, config: HarnessConfig, ...):
    """depth=deep: std + security-reviewer"""
```

핵심 차이: 세 함수 모두 같은 패턴(while attempt < MAX: agent_call → check → next)이므로 공통 루프를 추출하고 depth별 에이전트 체인만 다르게 구성.

```python
@dataclass
class AgentStep:
    agent: str
    timeout: int
    prompt_builder: Callable
    success_marker: str
    fail_type: str

DEPTH_CHAINS = {
    "simple": [engineer_step, pr_reviewer_step],
    "std":    [engineer_step, test_engineer_step, validator_step, pr_reviewer_step],
    "deep":   [engineer_step, test_engineer_step, validator_step, security_step, pr_reviewer_step],
}
```

### 4.4 helpers.py — 공유 헬퍼 (impl_helpers.sh 255줄 대체)

```python
def load_constraints(config: HarnessConfig) -> str: ...
def run_automated_checks(impl_file: Path, config: HarnessConfig) -> tuple[bool, str]:
    """config.test_command / config.lint_command 사용"""
def append_failure(impl_file: Path, fail_type: str, error: str): ...
def append_success(impl_file: Path, attempt: int): ...
def budget_check(agent: str, cost: float, total: float, limit: float): ...
```

### 4.5 executor.py — CLI 진입점 (executor.sh 134줄 대체)

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["impl", "plan"])
    parser.add_argument("--impl", dest="impl_file")
    parser.add_argument("--issue", dest="issue_num")
    parser.add_argument("--prefix")
    parser.add_argument("--depth", default="auto")
    args = parser.parse_args()

    config = load_config(Path.cwd())
    state = StateDir(Path.cwd(), args.prefix or config.prefix)

    # 병렬 실행 가드 (fcntl.flock)
    acquire_lock(state, config)

    # heartbeat 스레드
    start_heartbeat(state)

    # 모드 라우터
    if args.mode == "impl":
        run_impl(args, config, state)
    elif args.mode == "plan":
        run_plan(args, config, state)
```

### 4.6 executor.sh — 1줄 래퍼 (호환성)

```bash
#!/bin/bash
exec python3 "$(dirname "$0")/executor.py" "$@"
```

commands/*.md의 `bash ~/.claude/harness/executor.sh` 호출이 그대로 동작.

---

## 5. 검증 전략

### 5.1 기능 동등성 검증

**방법: 같은 입력 → 같은 JSONL 이벤트**

```bash
# 1. 현재 Bash 버전으로 실행 → JSONL 캡처
bash executor.sh impl --impl test.md --issue 999 --prefix test
cp ~/.claude/harness-logs/test/run_*.jsonl /tmp/bash_run.jsonl

# 2. Python 버전으로 동일 실행 → JSONL 캡처
python3 executor.py impl --impl test.md --issue 999 --prefix test
cp ~/.claude/harness-logs/test/run_*.jsonl /tmp/python_run.jsonl

# 3. 이벤트 시퀀스 비교 (타임스탬프 제외)
python3 -c "
import json
for name in ['bash', 'python']:
    events = []
    for line in open(f'/tmp/{name}_run.jsonl'):
        e = json.loads(line)
        del e['t']  # 타임스탬프 제외
        events.append(e['event'])
    print(f'{name}: {events}')
"
# 출력이 동일해야 함:
# bash: ['run_start', 'config', 'branch_create', 'agent_start', 'agent_end', ...]
# python: ['run_start', 'config', 'branch_create', 'agent_start', 'agent_end', ...]
```

### 5.2 하네스 리뷰 호환성

harness-review.py가 Python 버전의 JSONL을 정상 파싱하는지 확인:
```bash
python3 ~/.claude/scripts/harness-review.py ~/.claude/harness-logs/test/run_*.jsonl
# EXPECTED_SEQUENCE 검증 통과해야 함
```

### 5.3 훅 호환성

hooks/*.py가 의존하는 인터페이스:
- `/tmp/{prefix}_{agent}_active` 플래그 파일 → Python 버전도 동일 경로에 생성
- `.claude/harness-state/{prefix}_*` 상태 파일 → 동일 경로
- `HARNESS_INTERNAL=1` 환경변수 → 동일하게 설정
- `HARNESS_PREFIX` 환경변수 → 동일하게 설정

### 5.4 스킬/커맨드 호환성

commands/*.md에서 호출하는 경로:
```bash
bash ~/.claude/harness/executor.sh impl --impl ...
```
executor.sh가 1줄 래퍼로 남으므로 호출 변경 없음.

### 5.5 회귀 테스트 체크리스트

| # | 검증 항목 | 방법 |
|---|----------|------|
| 1 | executor.py 모드 라우팅 (impl/plan) | argparse 단위 테스트 |
| 2 | depth 자동 감지 (frontmatter 파싱) | impl 파일 3종(simple/std/deep) 대상 테스트 |
| 3 | 병렬 실행 가드 (lock) | 동시 실행 시 두 번째가 에러로 종료 |
| 4 | agent_call() 스트리밍 파싱 | mock claude CLI 출력으로 result/cost/stats 추출 |
| 5 | 마커 파싱 | 각 마커 문자열 대상 단위 테스트 |
| 6 | SPEC_GAP 동결 카운터 | attempt=3 + spec_gap=2 시나리오 |
| 7 | automated_checks | git status mock 대상 테스트 |
| 8 | harness-memory append_failure + auto-promotion | 3회 실패 → PROMOTED 생성 |
| 9 | JSONL 이벤트 스키마 | harness-review.py EXPECTED_SEQUENCE 통과 |
| 10 | 플래그 생성/삭제 | StateDir 단위 테스트 |
| 11 | git 브랜치 생성/커밋/머지 | 실제 git repo 대상 통합 테스트 |
| 12 | kill_check | kill 파일 존재 시 종료 |
| 13 | budget_check | 상한 초과 시 HARNESS_BUDGET_EXCEEDED |
| 14 | test_command config | vitest 외 명령 (pytest 등) 동작 |
| 15 | 훅 연동 | agent_active 플래그 + HARNESS_INTERNAL 환경변수 |

---

## 6. 영향 범위 분석

### 직접 영향 (반드시 확인)

| 파일/시스템 | 영향 | 확인 방법 |
|-----------|------|----------|
| `commands/qa.md` | executor.sh 호출 경로 | 래퍼가 있으므로 변경 불필요. 동작 확인만 |
| `commands/product-plan.md` | executor.sh plan 모드 | 래퍼 경유 동작 확인 |
| `commands/harness-test.md` | 하네스 dry-run 검증 | Python 버전 대상 재실행 |
| `commands/harness-kill.md` | kill 파일 경로 | STATE_DIR 경로 동일 확인 |
| `commands/harness-status.md` | 플래그 파일 읽기 | 경로/이름 동일 확인 |
| `commands/harness-monitor.md` | JSONL tail -f | 로그 경로 동일 확인 |
| `commands/harness-review.md` | harness-review.py 호출 | JSONL 스키마 호환 확인 |
| `hooks/harness-router.py` | executor.sh 경로 참조 | 래퍼 경유 → 변경 불필요 |
| `hooks/harness_common.py` | PREFIX 감지, STATE_DIR | 경로 규칙 동일 확인 |
| `hooks/agent-gate.py` | agent_active 플래그 | /tmp/{prefix}_{agent}_active 경로 동일 |
| `hooks/post-agent-flags.py` | 마커 파싱, 플래그 생성 | 마커 형식 + 플래그 경로 동일 |
| `hooks/harness-review-trigger.py` | HARNESS_DONE 감지 | stdout 마커 출력 형식 동일 |
| `hooks/commit-gate.py` | PR_REVIEWER_LGTM 플래그 | 플래그 경로 동일 |
| `scripts/harness-review.py` | JSONL 파싱 | 이벤트 스키마 동일 |
| `harness/tests/*.bats` | Bash 함수 테스트 | Python 전환 후 pytest로 재작성 필요 |
| `.claude/harness-state/` | 상태 파일 경로/형식 | 동일 |
| `.claude/harness-logs/` | JSONL 로그 경로/형식 | 동일 |
| `.claude/harness-memory.md` | 실패/성공 기록 형식 | 동일한 텍스트 형식 유지 |

### 간접 영향 (확인 권장)

| 파일/시스템 | 영향 | 확인 방법 |
|-----------|------|----------|
| `settings.json` hooks | executor.sh를 Bash로 실행하는 훅들 | 래퍼 경유 → 대부분 영향 없음 |
| CLAUDE.md (프로젝트별) | executor.sh 경로 언급 | 래퍼 유지로 변경 불필요 |
| `orchestration-rules.md` | executor.sh 호출 예시 | 래퍼 유지로 변경 불필요. 문서에 Python 전환 사실 추가 권장 |
| `agents/README.md` | 하네스 아키텍처 설명 | Python 전환 반영 업데이트 권장 |
| ralph-loop 플러그인 | stop-hook.sh가 하네스 상태 참조 | 직접 의존 없음. 확인만 |
| Git pre-commit hook | rule-audit.bats 실행 | BATS 테스트가 Bash 함수에 의존 → 별도 마이그레이션 |

### 영향 없음 (확인 불필요)

| 파일/시스템 | 이유 |
|-----------|------|
| `agents/*.md` (에이전트 프롬프트) | 하네스 인프라와 무관. 에이전트는 프롬프트만 받음 |
| `orchestration/policies.md` | 정책 문서. 코드 아님 |
| `orchestration/agent-boundaries.md` | 경계 규칙. hooks/*.py가 강제 |
| Pencil MCP 관련 | 하네스 외부. ux 스킬 직접 호출 |

---

## 7. 전환 순서

### Step 1: 인프라 레이어 (`config.py` + `core.py`)

가장 많이 재사용되는 기반 모듈을 먼저 작성.

**config.py**: harness.config.json 로더 + test_command/lint_command/token_budget
**core.py**: StateDir, Flag, Marker, RunLogger, agent_call, git 유틸, kill_check

검증: 단위 테스트로 각 함수 동작 확인. 기존 Bash와 병행 가능 (아직 호출하지 않음).

### Step 2: 헬퍼 레이어 (`helpers.py`)

impl_helpers.sh의 함수들을 Python으로 포팅.

**helpers.py**: load_constraints, run_automated_checks, append_failure/success, budget_check, rollback

검증: 기존 harness-memory.md에 동일 형식으로 기록되는지 확인.

### Step 3: 루프 레이어 (`impl_loop.py` + `impl_router.py`)

impl_simple/std/deep.sh → 통합 루프. impl.sh → 라우터.

검증: dry-run 모드(에이전트 호출 없이 루프 구조만 확인)로 depth별 에이전트 체인 검증.

### Step 4: 진입점 (`executor.py`) + plan (`plan_loop.py`)

executor.sh → Python 진입점. plan.sh → Python.

검증: `python3 executor.py impl --help`가 동작하고, 기존 executor.sh를 1줄 래퍼로 교체.

### Step 5: 통합 검증 + 래퍼 교체

실제 프로젝트에서 `executor.sh impl` 실행 → 전체 루프 통과 확인.
기존 .sh 파일을 .sh.bak으로 이동.

### Step 6: 테스트 마이그레이션 (선택적, 별도 작업)

harness/tests/*.bats → pytest로 전환. 이것은 Python 전환의 필수 조건이 아니라 후속 작업.

---

## 8. 롤백 전략

- 기존 .sh 파일을 `.sh.bak`으로 보존 (삭제하지 않음)
- executor.sh 래퍼를 원본으로 복원하면 즉시 Bash 버전으로 복귀
- git에서 전환 커밋을 revert하면 완전 롤백

```bash
# 롤백 (30초)
cd ~/.claude/harness
for f in *.sh.bak; do mv "$f" "${f%.bak}"; done
```

---

## 9. 리스크

| 리스크 | 심각도 | 대응 |
|--------|--------|------|
| agent_call 스트리밍 파싱 미묘한 차이 | 높음 | 현재 인라인 Python 코드를 그대로 옮기므로 로직 동일. 실제 claude 호출로 E2E 검증 |
| fcntl.flock이 macOS에서 다르게 동작 | 중간 | macOS Python 3.9에서 flock 정상 동작 확인됨. 현재도 lock 파일 기반이므로 패턴 동일 |
| BATS 테스트가 깨짐 | 중간 | 예상된 결과. pytest 마이그레이션 병행 또는 BATS 테스트 비활성화 후 Python 테스트로 대체 |
| 훅과의 상호작용 회귀 | 중간 | 플래그 경로 + 환경변수가 핵심 인터페이스. 경로 동일 유지로 대응 |
| subprocess 타임아웃이 Bash timeout과 다르게 동작 | 낮음 | Python subprocess.run(timeout=N)은 SIGTERM → SIGKILL 시퀀스. Bash timeout과 동등 |

---

## 10. 성공 기준

전환 완료 판정:

1. `python3 executor.py impl --impl <path> --issue <N>` 로 depth=simple/std/deep 각 1회 성공
2. harness-review.py가 Python 버전 JSONL을 정상 파싱
3. 모든 hooks/*.py가 기존과 동일하게 동작 (플래그 생성/삭제, 마커 감지)
4. `harness.config.json`의 `test_command`로 vitest 외 명령 실행 성공
5. 기존 .sh 파일 전부 .sh.bak으로 이동 완료
6. 최소 3개 프로젝트에서 실제 하네스 루프 정상 완주
