# Phase 2: 이슈별 Worktree 격리

> **선행 조건**: Phase 1 (env var 에이전트 판별) 완료 및 머지

## 목표
세션 A에서 issue #42, 세션 B에서 issue #99를 동시에 하네스 루프로 작업 가능하게 한다.
executor가 이슈별 git worktree를 생성하여 git/파일시스템 수준 격리.

## 배경
- 현재 `create_feature_branch`는 `git checkout -b`만 사용 — 하나의 작업 디렉토리에서 branch 전환
- `{prefix}_harness_active` PID 잠금이 프로젝트 전체를 직렬화
- `config.isolation = "worktree"`는 에이전트 서브프로세스에만 전달, executor는 메인 repo에서 실행
- `.claude/`는 `.gitignore`에 있으므로 worktree에 복사 안 됨 → 상태는 메인 프로젝트에서 공유

## 변경 파일 및 상세

### 1. `harness/core.py` — `WorktreeManager` 클래스 신설
- `create_feature_branch()` 근처 (라인 989)에 추가
- **메서드**:
  - `__init__(project_root: Path, prefix: str)` — worktree 베이스 디렉토리: `{project_root}/../.worktrees/{prefix}/`
  - `create_or_reuse(branch_name: str, issue_num: str) → Path` — `git worktree add` 또는 기존 재사용
  - `remove(issue_num: str)` — `git worktree remove --force`
  - `worktree_path(issue_num: str) → Path`
- worktree 경로: `{base_dir}/issue-{N}/`

### 2. `harness/core.py` — `create_feature_branch()` 시그니처 변경
- **현재**: `(branch_type, issue_num) → str`
- **변경**: `(branch_type, issue_num, worktree_mgr=None) → tuple[str, Path | None]`
- worktree_mgr가 있으면 `git worktree add`, 없으면 기존 `git checkout -b`
- **호출부 전부 수정 필요**: `impl_loop.py`의 `run_simple`, `_run_std_deep`

### 3. `harness/core.py` — `StateDir.__init__` 이슈별 플래그 디렉토리
- **현재**: `StateDir(project_root, prefix)`
- **변경**: `StateDir(project_root, prefix, issue_num="")`
- `issue_num`이 있으면 `.flags/{prefix}_{issue_num}/` 서브디렉토리 사용
- `_flag_path`에서 이슈 서브디렉토리 내에서는 `{name}`만 사용 (prefix 이미 디렉토리에 포함)

### 4. `harness/executor.py` — PID 잠금 이슈별 변경
- **현재**: `lock_file = state_dir.path / f"{prefix}_harness_active"`
- **변경**: `lock_file = state_dir.path / f"{prefix}_{issue}_harness_active"` (이슈 있을 때)
- `StateDir(Path.cwd(), prefix, issue_num=args.issue_num)` 으로 초기화
- cleanup()도 이슈별 플래그 디렉토리 정리

### 5. `harness/core.py` — `agent_call()` cwd 파라미터 추가
- **현재**: `subprocess.Popen(cmd, ..., env=env, text=True)` (cwd 없음)
- **변경**: `cwd` 파라미터 추가, Popen에 `cwd=str(cwd) if cwd else None` 전달
- env에 `HARNESS_ISSUE_NUM={issue_num}` 추가 → hooks가 이슈별 플래그 디렉토리 자동 참조
- **주의**: active 플래그 생성 로직 (라인 689-705)에서 `os.getcwd()` 재호출하는 부분도 cwd 기준으로 변경하거나, state_dir를 파라미터로 받도록 수정

### 6. `harness/core.py` — `_git()` 헬퍼 cwd 지원
- **현재**: `subprocess.run(["git"] + args, capture_output=True, ...)`
- **변경**: `cwd` 파라미터 추가

### 7. `harness/impl_loop.py` — `run_simple()`, `_run_std_deep()` 수정
- `create_feature_branch` 호출부에 `worktree_mgr` 전달
- 반환값 `(branch_name, wt_path)` 언패킹
- 이후 모든 `agent_call`에 `cwd=wt_path` 전달
- `config.isolation == "worktree"`일 때만 WorktreeManager 생성

### 8. `harness/core.py` — `merge_to_main()` 후 worktree 정리
- `worktree_manager` 파라미터 추가
- squash merge 성공 후 `worktree_manager.remove(issue_num)` 호출

### 9. `hooks/harness_common.py` — `get_flags_dir()` 이슈 인식
- **변경**: `HARNESS_ISSUE_NUM` env var가 있으면 이슈별 서브디렉토리 반환
```python
def get_flags_dir(issue_num=""):
    if not issue_num:
        issue_num = os.environ.get("HARNESS_ISSUE_NUM", "")
    if issue_num:
        prefix = get_prefix()
        flags_dir = os.path.join(get_state_dir(), ".flags", f"{prefix}_{issue_num}")
    else:
        flags_dir = os.path.join(get_state_dir(), ".flags")
    os.makedirs(flags_dir, exist_ok=True)
    return flags_dir
```

### 10. `hooks/harness-router.py` — 이슈별 플래그 디렉토리 탐색
- 프롬프트에서 이슈 번호 추출 후 해당 이슈의 플래그 디렉토리 탐색
- 이슈별 서브디렉토리 없으면 루트 `.flags/` fallback

### 11. `orchestration-rules.md` — 문서 업데이트
- worktree 격리 섹션 추가
- 이슈별 플래그 디렉토리 구조 설명

### 12. `harness/tests/test_parity.py` — TC 추가
- `WorktreeManager.create_or_reuse` / `remove` 동작 검증 (mock git)
- `StateDir(issue_num="42")` 시 `.flags/{prefix}_42/` 디렉토리 생성 검증
- `get_flags_dir()` 이슈별 분기 검증

## 호환성 보장
- `config.isolation`이 비어있거나 `"worktree"`가 아니면 기존 동작 100% 유지
- `issue_num`이 없으면 worktree 생성 스킵, 기존 `git checkout -b` 사용
- `StateDir.__init__`에 `issue_num=""` 기본값으로 기존 호출부 변경 불필요

## 위험 요소
1. **worktree 고아**: executor 비정상 종료 시 → atexit + `/harness-kill`에 worktree 강제 정리 추가
2. **git lock 충돌**: `git fetch/gc` 시 → 재시도 로직 (3회, 1초 간격)
3. **impl 파일 경로**: git-tracked이므로 worktree에 동일 상대경로로 존재. architect가 생성한 파일도 commit되면 worktree에 반영됨

## 검증 방법
1. `python3 -m pytest harness/tests/test_parity.py` 전체 통과
2. 세션 2개로 다른 이슈 동시 실행 → 각각 독립 merge 확인
3. 단일 세션 (기존 방식) 동작 변경 없음 확인
4. executor 비정상 종료 후 worktree 정리 확인

## 범위 외 자율 수정
명시된 파일 외에도 목표 달성에 필요하다고 판단되면 자율적으로 수정한다.
단, Phase 1에서 완료한 env var 판별 로직을 되돌리지 않는다.
