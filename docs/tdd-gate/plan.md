# TDD 게이트 — 구현 계획

> impl 루프에서 test-engineer를 engineer 앞으로 이동하고, engineer가 테스트 통과를 자체 검증한 뒤 commit하도록 변경.
> 적용 대상: std / deep depth만. simple은 변경 없음.

---

## 배경

현재 std/deep 루프:
```
engineer 구현 → commit → test-engineer 테스트 작성 → harness vitest → FAIL → attempt++ → engineer 재시도
```

문제:
- 테스트 FAIL이 바깥 attempt를 소진함 (3회 실패 → ESCALATE)
- engineer가 "테스트가 뭔지 모르고" 구현하니까 스펙 해석 여지가 큼
- 테스트 코드가 구현 후에 작성되어 구현에 끌려감 (구현 확인용이 되어버림)

### 변경 후 (TDD 방식):
```
attempt 0:
  test-engineer (TDD) → vitest RED 확인 → engineer 구현 + 자체 vitest → commit → vitest GREEN 확인

attempt 1+:
  (테스트 이미 있음) → engineer 재시도 + 자체 vitest → commit → vitest GREEN 확인
```

### 핵심 이점:
- 테스트가 스펙의 가장 비모호한 형태 → engineer 해석 여지 제거
- engineer 내부 재시도로 attempt 낭비 감소
- architect가 이미 impl에 인터페이스 정의 + 수용 기준을 쓰고 있으므로 architect 부담 추가 없음
- attempt 1+에서 test-engineer 호출 불필요 → 에이전트 호출 1회 절약

---

## 변경 범위

### 적용 depth
- **std**: 적용 (로직 변경 = 테스트 필수)
- **deep**: 적용 (보안 민감 = 더더욱 테스트 필수)
- **simple**: 미적용 (behavior 불변, 테스트 불필요)

### 영향 파일

| 파일 | 변경 | 비고 |
|------|------|------|
| `harness/impl_loop.py` | std/deep 루프 TDD 순서 변경, attempt 0/1+ 분기, RED/GREEN 확인 | **핵심 변경** |
| `agents/test-engineer.md` | 기존 TEST 모드 → TDD 모드로 교체 (impl 기반, 코드 없이) | 모드 1개로 단순화 |
| `agents/engineer.md` | "commit 전 자체 vitest 실행" 지침 추가 | 기존 지침에 추가 |
| `orchestration/impl_std.md` | 흐름도 업데이트 (test-engineer → engineer 순서) | 다이어그램 |
| `orchestration/impl_deep.md` | 동일 | 다이어그램 |
| `orchestration-rules.md` | 구현 루프 내부 기능에 TDD 설명 추가 | 부수 문서 |
| `orchestration/changelog.md` | 변경 이력 | 부수 문서 |
| `harness/core.py` | TESTS_WRITTEN 마커 추가 | 마커 |
| `harness/tests/test_parity.py` | TDD 순서 테스트 추가 | 테스트 |

---

## Phase 1 — 문서 + 에이전트 정의

### 1-1. test-engineer.md — TDD 모드로 교체

기존 `@MODE:TEST_ENGINEER:TEST` 제거, `@MODE:TEST_ENGINEER:TDD`로 교체.

- [ ] 모드 정의:
  - `@MODE:TEST_ENGINEER:TDD`
  - 입력: `impl_path` (코드 없음, impl 파일만)
  - 동작: impl의 `## 인터페이스 정의` + `## 수용 기준` + `## 핵심 로직`에서 테스트 케이스 도출
  - 출력: 테스트 파일 생성 + `TESTS_WRITTEN` 마커 (실행 결과가 아닌 "작성 완료")
  - 기존 `@MODE:TEST_ENGINEER:TEST` 제거 — retry 시 test-engineer를 호출하지 않으므로 불필요
- [ ] @PARAMS 스키마:
  ```
  @MODE:TEST_ENGINEER:TDD
  @PARAMS: { "impl_path": "impl 계획 파일 경로" }
  @OUTPUT: { "marker": "TESTS_WRITTEN", "test_files": "생성된 테스트 파일 경로 목록" }
  ```
- [ ] TDD 모드 읽기 규칙:
  - impl 파일의 `## 인터페이스 정의` — 함수 시그니처, 타입, Props
  - impl 파일의 `## 수용 기준` — `(TEST)` 태그 항목만 테스트 케이스로 변환
  - impl 파일의 `## 핵심 로직` — 의사코드에서 엣지 케이스 추출
  - src/ 기존 파일 읽기 허용 (의존 모듈 import 경로 확인용)
  - **구현 파일은 아직 없으므로 읽기 불가** → import 경로를 impl의 `## 생성/수정 파일`에서 추론
- [ ] 테스트 파일 작성 규칙:
  - import 경로: impl의 `## 생성/수정 파일` 목록에서 추출
  - 아직 없는 모듈 import → 테스트 실행 시 import error로 RED 확인 (정상)
  - `describe` 블록명: impl의 REQ-NNN ID 포함 (추적 가능)
  - 각 수용 기준 `(TEST)` 항목 → 최소 1개 `it` 블록
- [ ] 역할 정의 변경:
  - 기존: "impl 파일과 **구현 코드를 기반으로** 테스트 코드를 작성"
  - 변경: "impl 파일의 **인터페이스와 수용 기준을 기반으로** 테스트 코드를 작성 (구현 코드 없이)"
  - "코드 수정 금지" 원칙 유지
  - "테스트 실행" 역할 제거 — 하네스가 직접 vitest 실행

### 1-2. engineer.md — 자체 테스트 지침 추가

- [ ] Phase 2 (구현) 마지막에 추가:
  ```
  ## 자체 테스트 검증 (TDD 모드)
  
  테스트 파일이 이미 존재하면 (test-engineer가 선작성):
  1. 구현 완료 후 commit 전에 Bash로 테스트 실행
  2. FAIL → 실패한 테스트 읽고 코드 수정 → 재실행 (최대 3회)
  3. 3회 내 PASS → commit 진행
  4. 3회 후에도 FAIL → commit 없이 종료 (TESTS_FAIL 보고)
  
  테스트 파일이 없으면 이 단계 스킵.
  ```
- [ ] 기존 "계획 파일을 유일한 기준으로 삼는다" 원칙 유지 + "테스트 파일도 참조"로 확장

### 1-3. orchestration/impl_std.md 흐름 업데이트

- [ ] TDD 흐름으로 재작성:
  ```
  attempt 0:
    test-engineer (TDD) → vitest RED → engineer (구현 + 자체 vitest) → commit → vitest GREEN → validator → pr-reviewer

  attempt 1+:
    (test-engineer 스킵) → engineer (재시도 + 자체 vitest) → commit → vitest GREEN → validator → pr-reviewer
  ```
- [ ] Mermaid 다이어그램 재작성
- [ ] engineer 내부 재시도 루프 표시 (attempt 미소진, max 3)

### 1-4. orchestration/impl_deep.md 흐름 업데이트

- [ ] impl_std.md와 동일한 TDD 순서 적용
- [ ] security-reviewer 위치는 변경 없음 (TDD와 무관)

### 1-5. orchestration-rules.md 업데이트

- [ ] "구현 루프 내부 기능"에 TDD 설명 추가:
  ```
  ### TDD 게이트 (std/deep — test-engineer 선행)
  - attempt 0: test-engineer TDD 모드 → RED 확인 → engineer 구현 + 자체 vitest → GREEN 확인
  - attempt 1+: test-engineer 스킵 (테스트 이미 존재) → engineer 재시도 + 자체 vitest → GREEN 확인
  - test_command 미설정 시 TDD 스킵 — 기존 순서(engineer → test-engineer) 폴백
  ```
- [ ] HUD DEPTH_AGENTS 순서 반영 (test-engineer가 engineer 앞)
- [ ] 마커 테이블에 `TESTS_WRITTEN` 추가

### 1-6. 부수 문서

- [ ] `orchestration/changelog.md` — TDD 게이트 변경 이력
- [ ] `docs/harness-state.md` — impl_loop.py 설명 업데이트
- [ ] `docs/harness-backlog.md` — TDD 항목 추가

### 1-7. 모순 검수

- [ ] test-engineer.md @MODE ↔ orchestration-rules.md 마커 테이블 일치
- [ ] impl_std.md / impl_deep.md 다이어그램 ↔ orchestration-rules.md TDD 설명 일치
- [ ] engineer.md 자체 테스트 지침 ↔ impl_loop.py 설계 일치
- [ ] 기존 simple 경로에 영향 없음 확인
- [ ] TESTS_WRITTEN 마커가 모든 관련 문서에 일관 사용

### Phase 1 완료 기준

- test-engineer.md: 기존 TEST 모드 제거, TDD 모드 단일 정의
- engineer.md: 자체 테스트 지침 추가
- impl_std.md / impl_deep.md: TDD 순서 다이어그램
- orchestration-rules.md: TDD 게이트 설명 + 마커
- simple 경로 영향 없음

---

## Phase 2 — Python 구현 + 테스트

### 2-1. core.py 마커 추가

- [ ] `TESTS_WRITTEN = "TESTS_WRITTEN"` 마커 상수 추가
- [ ] parse_marker에서 인식 가능 확인

### 2-2. impl_loop.py — std/deep 루프 TDD 순서 변경

#### attempt 0 흐름:

```python
# 1. test-engineer TDD (테스트 선작성)
if attempt == 0 and config.test_command:
    hud.agent_start("test-engineer")
    te_prompt = (
        f"@MODE:TEST_ENGINEER:TDD\n"
        f'@PARAMS: {{ "impl_path": "{impl_file}" }}\n\n'
        f"[지시] impl의 인터페이스 정의 + 수용 기준(TEST)에서 테스트 작성. 코드 없이 impl만 참조.\n"
        f"issue: #{issue_num}"
    )
    agent_call("test-engineer", 600, te_prompt, te_out, ...)
    te_marker = parse_marker(te_out, "TESTS_WRITTEN")
    # TESTS_WRITTEN이 아니면 경고 후 계속 (테스트 없이 engineer 진행)

    # 2. RED 확인
    red_result = subprocess.run(test_command, ...)
    if red_result.returncode == 0:
        print("[HARNESS] 경고: 테스트가 코드 없이 통과 — trivially true 의심")
    # RED 확인은 attempt 소진 안 함 (정보성)

    # 3. handoff: test-engineer → engineer (테스트 파일 경로 포함)
    test_files = collect_test_files(te_out)  # test-engineer 출력에서 추출
    handoff 생성

# 4. engineer 구현 (테스트 파일 경로 포함)
eng_prompt += f"\n테스트 파일: {test_files}\n[지시] 이 테스트를 통과시켜라. commit 전 자체 vitest 실행."
agent_call("engineer", 600, eng_prompt, ...)

# 5. commit

# 6. GREEN 확인 (기존 vitest 단계)
green_result = subprocess.run(test_command, ...)
if green_result.returncode != 0:
    # FAIL → attempt++
```

#### attempt 1+ 흐름:

```python
# test-engineer 스킵 (테스트 이미 존재)
hud.agent_skip("test-engineer", "attempt 1+ — 테스트 이미 작성됨")

# engineer 재시도 (기존 테스트 기반)
eng_prompt += f"\n기존 테스트 파일 사용. commit 전 자체 vitest 실행."
agent_call("engineer", 600, eng_prompt, ...)

# commit → GREEN 확인
```

#### test_command 미설정 시 폴백:

```python
if not config.test_command:
    # TDD 불가 — 기존 순서 유지 (engineer 먼저, test-engineer 나중)
    print("[HARNESS] test_command 미설정 — TDD 스킵, 기존 순서")
    # ... 기존 코드 그대로
```

구체적 변경:

- [ ] attempt 0 + test_command 있음 → TDD 순서 (test-engineer 먼저)
- [ ] attempt 0 + test_command 없음 → 기존 순서 (engineer 먼저, test-engineer 나중)
- [ ] attempt 1+ → test-engineer 스킵, engineer 재시도만
- [ ] RED 확인 단계 추가 (test_command 실행, exit ≠ 0 기대)
- [ ] GREEN 확인 단계 (기존 vitest 단계 유지)
- [ ] handoff 방향 변경: test-engineer → engineer
- [ ] engineer 프롬프트에 test_files 추가
- [ ] 기존 engineer → test-engineer handoff 코드 제거 (attempt 0 경로)
- [ ] 기존 test-engineer retry 프롬프트 제거 (attempt 1+ 경로)

### 2-3. HUD 에이전트 순서 변경

- [ ] core.py `DEPTH_AGENTS`:
  ```python
  "std": ["test-engineer", "engineer", "validator", "pr-reviewer", "merge"],
  "deep": ["test-engineer", "engineer", "validator", "security-reviewer", "pr-reviewer", "merge"],
  ```

### 2-4. 테스트 추가

- [ ] `test_parity.py` — TDD 순서 테스트:
  - attempt 0 + test_command 설정: test-engineer가 engineer 전에 호출
  - attempt 0 + test_command 미설정: 기존 순서 (engineer 먼저)
  - attempt 1+: test-engineer 스킵, engineer만 호출
  - TESTS_WRITTEN 마커 파싱
  - RED 확인 동작 (exit ≠ 0)
  - HUD 에이전트 순서: test-engineer가 engineer 앞

- [ ] 기존 테스트 regression:
  - simple 루프 테스트 영향 없음
  - plan 루프 테스트 영향 없음

### Phase 2 완료 기준

- std/deep attempt 0: test-engineer(TDD) → RED → engineer → GREEN
- std/deep attempt 1+: test-engineer 스킵 → engineer → GREEN
- test_command 미설정: 기존 순서 폴백
- HUD 에이전트 순서 반영
- simple/plan 경로 영향 없음
- 모든 테스트 PASS

---

## 설계 결정 기록

### Q: architect impl 변경 필요?
A: 없음. architect가 이미 `## 인터페이스 정의` + `## 수용 기준` + `## 핵심 로직`을 필수로 쓰고 있음 (module-plan.md 체크리스트). test-engineer TDD 모드가 이걸 읽고 테스트 작성.

### Q: test-engineer가 코드 없이 테스트를 잘 쓸 수 있나?
A: impl의 인터페이스 정의가 TypeScript 타입으로 명시되어 있으므로 import 경로 + 함수 시그니처가 명확. 수용 기준 `(TEST)` 태그가 테스트 케이스 1:1 매핑. 코드 없이도 가능.

### Q: RED 확인에서 import error나면?
A: 정상. 아직 코드가 없으니까 import error = RED의 한 형태. 전부 FAIL이 기대 상태.

### Q: engineer 내부 재시도를 하네스가 관리하나?
A: 아니요. engineer에게 "Bash로 vitest 돌리고 실패하면 고쳐라 (max 3)"라고 지시. 600s timeout 안에서 에이전트가 자율적으로 처리. 하네스는 engineer 완료 후 vitest 1회만 실행 (GREEN 확인).

### Q: 기존 TEST 모드를 왜 제거하나?
A: TDD로 바뀌면 test-engineer는 attempt 0에서만 호출됨 (테스트 선작성). attempt 1+에서는 테스트 파일이 이미 존재하고 vitest는 하네스가 직접 실행하므로 test-engineer 호출 자체가 불필요. TEST 모드의 두 역할(테스트 작성 + 테스트 실행)이 각각 TDD 모드와 하네스 vitest로 대체됨.

### Q: test_command 미설정 시 왜 기존 순서?
A: TDD의 핵심은 "테스트 먼저 실행 → RED 확인 → 구현 → GREEN 확인". vitest를 돌릴 수 없으면 RED/GREEN 확인이 불가능. 이 경우 테스트를 먼저 쓰는 의미가 없으므로 기존 순서가 합리적.
