# Phase 1: env var 기반 에이전트 판별

## 목표
메인 Claude 세션이 에이전트(pr-reviewer 등)로 오인되는 문제 해결.
파일 기반 active 플래그 판별을 env var로 교체.

## 배경
- hooks가 `.flags/{prefix}_{agent}_active` 파일로 "현재 에이전트인가"를 판별
- 메인 Claude 세션도 이 파일을 보고 에이전트로 오인 → Write/Read 제한 적용
- `agent-boundary.py`의 900초 TTL glob 탐색이 특히 문제

## 변경 파일 및 상세

### 1. `harness/core.py` — `agent_call()` env var 추가
- **위치**: 라인 754 (`env = os.environ.copy()` 블록)
- **변경**: `env["HARNESS_AGENT_NAME"] = agent` 추가
- 기존 `HARNESS_INTERNAL`, `HARNESS_PREFIX`와 동일한 방식으로 전파

### 2. `hooks/harness_common.py` — `get_active_agent()` 함수 신설
- **위치**: `get_flags_dir()` 함수 아래
- **내용**:
```python
def get_active_agent():
    """env var로 현재 에이전트 판별. 메인 Claude에는 없으므로 None."""
    return os.environ.get("HARNESS_AGENT_NAME") or None
```

### 3. `hooks/agent-boundary.py` — 에이전트 판별 로직 교체
- **제거**: 라인 122-143 전체 (파일 기반 active_agent 탐색 + 900초 TTL glob fallback)
- **교체**:
```python
from harness_common import get_active_agent
active_agent = get_active_agent()
```
- **디버그 로그** (라인 94-121): `_state_dir_path` 대신 `HARNESS_AGENT_NAME` env 값 기록
- `import glob` 제거 가능 (더 이상 glob 탐색 안 함)

### 4. `hooks/issue-gate.py` — `_is_issue_creator_active()` 교체
- **제거**: 라인 24-39 (파일 기반 + glob 탐색)
- **교체**:
```python
def _is_issue_creator_active():
    agent = os.environ.get("HARNESS_AGENT_NAME")
    return agent in ISSUE_CREATORS
```
- `get_flags_dir` import 제거 가능

### 5. `hooks/commit-gate.py` — `_is_issue_creator_active()` 동일 교체
- **제거**: 라인 23-37 (파일 기반 + glob 탐색)
- 동일 패턴

### 6. `hooks/agent-gate.py` — 변경 없음 (정보성 로그용 유지)
- 라인 109-113의 `{PREFIX}_{agent}_active` 파일 생성은 **유지**
- 주석에 "정보성 로그용 — 에이전트 판별에 사용하지 않음" 명시

### 7. `hooks/post-agent-flags.py` — 변경 없음
- 에이전트 완료 후 `_active` 파일 삭제 유지 (정리)

### 8. `orchestration-rules.md` — 문서 업데이트
- "상태 플래그 보호" 섹션에 env var 방식 추가
- active 플래그 파일이 정보성 로그용임을 명시

### 9. `harness/tests/test_parity.py` — TC 추가
- `HARNESS_AGENT_NAME` env var 설정/미설정 시 `get_active_agent()` 반환값 검증
- hooks 전체 AST syntax check

## 검증 방법
1. `python3 -m pytest harness/tests/test_parity.py` 전체 통과
2. hooks AST syntax check 통과
3. 하네스 루프 1회 실행 후 `agent_boundary_debug.log`에서 `HARNESS_AGENT_NAME` 값 확인
4. 메인 Claude 세션에서 Write/Edit 도구 사용 시 에이전트 제한 미적용 확인

## 범위 외 자율 수정
명시된 파일 외에도 목표 달성에 필요하다고 판단되면 자율적으로 수정한다.
단, 하네스 루프/플래그 흐름을 변경하는 수정은 하지 않는다.
