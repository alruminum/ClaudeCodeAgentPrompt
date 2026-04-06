# 오케스트레이션 룰

모든 프로젝트에서 공통으로 적용되는 에이전트 워크플로우 규칙.
**룰 변경 시 이 파일만 수정** → 스크립트·에이전트 업데이트의 단일 기준점.

---

## 루프 진입 기준 (메인 Claude)

| 상황 | 호출 |
|------|------|
| 신규 프로젝트 / PRD 변경 | → **루프 A** |
| UI 변경 요청 (design_critic_passed 없음) | → **루프 B** |
| 구현 요청 + READY_FOR_IMPL 확정 | → **루프 C** (`harness-router.py`가 `harness-executor.sh impl` 자동 spawn — LLM Bash 직접 실행 금지) |
| 구현 요청 + plan_validation_passed ✅ | → **루프 C 단축** (`harness-router.py`가 `harness-executor.sh impl2` 자동 spawn — LLM Bash 직접 실행 금지) |
| 버그 보고 (bug 레이블 OR 유저 직접 보고) | → **루프 D** (`harness-router.py`가 `harness-executor.sh bugfix` 자동 spawn — LLM Bash 직접 실행 금지) |
| 기술 에픽 / 리팩 / 인프라 | → **루프 E** |
| **AMBIGUOUS** (의도 불명확, 진행 중 워크플로우 없음) | → **product-planner 자동 힌트 주입** (루프 진입 금지) |

---

## 루프 A — 기획 루프

```
product-planner
  │ Mode A (신규)                Mode B (변경)
  ↓                                   ↓
PRODUCT_PLAN_READY           PRODUCT_PLAN_UPDATED
  │                                   │
  │                          메인 Claude 판단:
  │                          전체 구조 변경?
  │                            YES → architect [System Design]
  │                            NO  → architect [Module Plan] → READY_FOR_IMPL
  │                                   ↓                            │
  └───────────────────────────────────┘                            │
                 ↓                                                  │
    architect [System Design]                                       │
                 │                                                  │
        SYSTEM_DESIGN_READY                                         │
                 │                                                  │
    validator [Design Validation]                                   │
          │               │                                         │
 DESIGN_REVIEW_FAIL  DESIGN_REVIEW_PASS                            │
          │                     │                                   │
    architect 재설계   DESIGN_REVIEW_SAVE_REQUIRED                  │
    (max 1회)          설계 문서 저장 확인 후 에픽 규모 판단        │
    재실패 →                 │                                      │
 DESIGN_REVIEW_ESCALATE  메인 Claude 판단:                          │
 → 메인 Claude 보고    Epic 전체 batch?                             │
                         YES ↓           NO ↓                      │
                     architect        architect                     │
                  [Task Decompose]  [Module Plan]                   │
                  impl 파일 ×N      impl 파일                       │
                          │                    │                   │
                          └─────────┬──────────┘                   │
                                    └──────────────────┬───────────┘
                                                       ↓
                                              ┌─ impl 진입 게이트 ─┐
                                              │ (공통 — 모든 루프)  │
                                              └────────┬───────────┘
                                                       ↓
                                        validator [Plan Validation]
                                          │               │
                                 PLAN_VALIDATION_FAIL  PLAN_VALIDATION_PASS
                                          │                     │
                                   architect 재보강        READY_FOR_IMPL
                                   (max 1회)                    │
                                   재실패 →               유저 승인 대기
                              PLAN_VALIDATION_ESCALATE          │
                              → 메인 Claude 보고          → 루프 C 진입
```

---

## 루프 B — 디자인 루프

```
진입 조건: impl 파일에 UI 키워드 감지 + design_critic_passed 없음

designer
  │
DESIGN_READY_FOR_REVIEW
  │
design-preview-{issue}.html 생성  ← designer가 Write로 직접 생성 (브라우저 시각 확인용)
  │
design-critic
  │           │            │
PICK       ITERATE      ESCALATE
  │           │            │
  │     designer 재시도   유저 직접 선택
  │     (max 3회)       DESIGN_LOOP_ESCALATE
  │     3회 초과 →
  │     DESIGN_LOOP_ESCALATE
  │
  └─────────────────────────────┐
                                ↓
                  유저 variant 선택
                                ↓
              메인 Claude → DESIGN_HANDOFF 발행
                                ↓
                  impl 파일 영향 있음?
                    YES → architect [Module Plan] → READY_FOR_IMPL
                    NO  → 기존 impl 파일 유지
                                ↓
              /tmp/{prefix}_design_critic_passed 플래그 생성
                                ↓
                          유저 승인 대기
                                ↓
                          → 루프 C 진입
```

---

## 루프 C — 구현 루프

```
READY_FOR_IMPL (impl 파일 경로 확정)
      │
      ┌─────────────── attempt loop (MAX 3회) ───────────────────┐
      ↓                                                          │
  engineer                                               FAIL → attempt++
      │
SPEC_GAP_FOUND?
  YES → architect [SPEC_GAP]
          │
    SPEC_GAP_RESOLVED
          │ counter 리셋 (SPEC_GAP 리셋 max 2회)
          │ 리셋 횟수 초과 → IMPLEMENTATION_ESCALATE
          └──→ engineer 재시도
      │
  (SPEC_GAP 없음)
      ↓
src/** 변경 있음?
  NO  ────────────────────────────────────────────────┐
  YES ↓                                                │
  test-engineer (테스트 작성)                          │
    TESTS_FAIL 분류:                                   │
      IMPLEMENTATION_BUG → engineer 재구현 ──────────→ FAIL
      TEST_CODE_BUG      → test-engineer 자체 수정     │
      FLAKY              → test-engineer 자체 수정     │
      (자체 수정 max 2회, attempt 불변)                 │
    TESTS_PASS                                         │
      ↓                                                │
  harness-loop.sh → vitest run  ← ground truth (LLM 주장과 독립)
    실패 ─────────────────────────────────────────── → FAIL
    통과                                               │
      ↓  ←─────────────────────────────────────────────┘
  validator [Code Validation]
    FAIL ────────────────────────────────────────── → FAIL
    PASS
      ↓
  [deep only]
  pr-reviewer
    CHANGES_REQUESTED ─────────────────────────────→ FAIL
    LGTM                                      3회 후 → IMPLEMENTATION_ESCALATE
      ↓                                                → 메인 Claude 보고
  security-reviewer                                     (architect SPEC_GAP 권장)
    VULNERABILITIES_FOUND (HIGH/MEDIUM) ───────────────→ FAIL
    SECURE (LOW만 있으면 SECURE 판정)
  [std: pr-reviewer·security-reviewer 스킵, 플래그 자동 생성]
      ↓
  git commit (PR body → /tmp/{prefix}_pr_body.txt 자동 생성)
      ↓
  HARNESS_DONE  ← pr_body 파일 경로 포함 출력
      ↓
  메인 Claude: stories.md 체크 + GitHub Issue 업데이트
      ↓
  유저 보고 후 대기 (PR 생성 시 pr_body 파일 내용 활용 권장)
      ↓
  유저 승인 → git push
      ↓
  이후 버그 발견 시 → 유저가 루프 D 트리거
```

### 루프 C — 실패 유형별 수정 전략

FAIL 시 모든 유형을 동일하게 처리하지 않는다. `fail_type`에 따라 engineer에게 다른 컨텍스트와 지시를 전달한다.

| fail_type | 컨텍스트 (engineer에게 전달) | 지시 |
|---|---|---|
| `test_fail` | vitest 출력 전체 + 실패 테스트 파일 소스 | "테스트 실패. 구현 코드를 수정. 테스트 자체 수정 금지." |
| `validator_fail` | validator 리포트 + impl 파일 | "스펙 불일치. impl의 해당 항목 재확인 후 누락 구현." |
| `pr_fail` | MUST FIX 항목 목록 | "코드 품질 이슈. MUST FIX 항목만 수정. 기능 변경 금지." |
| `security_fail` | 취약점 리포트 (HIGH/MEDIUM 행) | "보안 취약점. 수정 방안 컬럼대로 적용." |

---

## 루프 D — 버그픽스 루프

```
진입: bug 레이블 이슈 OR 유저 버그 직접 보고
      │
      ↓
  qa (원인 분석 + 라우팅 추천)
      │ 원인 특정 3회 실패 → KNOWN_ISSUE → 메인 Claude 보고 후 대기
      │
  ┌───┴──────────────────────────┐
  ↓                              ↓
architect 권장               product-planner 권장
architect [Module Plan]       product-planner
  "버그픽스 —" 명시              PRD 레벨 검토
      │                              │
READY_FOR_IMPL                  PLAN_NEEDED
      │                         (유저 결정)
→ 루프 C 진입                   YES → 루프 A 재진입
                                NO  → 이슈 종료
```

---

## 루프 E — 기술 에픽 루프

```
진입: 기술 부채 / 성능 / 인프라 개선 요청
      │
      ↓
architect [Technical Epic]
      │
SYSTEM_DESIGN_READY
      │
validator [Design Validation]  ← 루프 A와 동일 게이트
      │               │
DESIGN_REVIEW_FAIL  DESIGN_REVIEW_PASS
      │                     │
architect 재설계        Epic+Story 이슈 생성
(max 1회)              architect [Module Plan] ×N
재실패 →               READY_FOR_IMPL ×N
DESIGN_REVIEW_ESCALATE        │
→ 메인 Claude 보고       순차 실행 (×N)
                              │
                        → 루프 C 진입
```

---

## 에스컬레이션 마커 — 모두 "메인 Claude 보고 후 대기"

| 마커 | 발행 주체 | 처리 |
|------|-----------|------|
| `DESIGN_REVIEW_ESCALATE` | validator Mode A (재검 후 재FAIL) | 메인 Claude 보고 |
| `VALIDATION_ESCALATE` | validator Mode B (3회 초과) | 메인 Claude 보고 |
| `REVIEW_LOOP_ESCALATE` | pr-reviewer (3라운드 초과) | 메인 Claude 보고 |
| `KNOWN_ISSUE` | qa (원인 특정 3회 실패) | 메인 Claude 보고 |
| `SPEC_MISSING` | validator Mode B (impl 없음) | architect Module Plan 호출 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect Mode C | product-planner 에스컬레이션 |
| `IMPLEMENTATION_ESCALATE` | harness-loop.sh (3회 실패 or SPEC_GAP 리셋 초과) | architect SPEC_GAP 권장 |
| `DESIGN_LOOP_ESCALATE` | designer (3라운드 후에도 ITERATE) | 유저 직접 선택 |
| `TECH_CONSTRAINT_CONFLICT` | architect Mode C (기술 제약 충돌) | 메인 Claude 보고 |
| `PLAN_VALIDATION_ESCALATE` | validator Plan Validation (재검 후 재FAIL) | 메인 Claude 보고 |

---

## 전체 마커 레퍼런스

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `PRODUCT_PLAN_READY` | product-planner | architect System Design |
| `PRODUCT_PLAN_UPDATED` | product-planner | 메인 Claude 범위 판단 → System Design or Module Plan |
| `SYSTEM_DESIGN_READY` | architect | validator Design Validation |
| `DESIGN_REVIEW_PASS` | validator Mode A | 메인 Claude 판단 → Task Decompose or Module Plan |
| `DESIGN_REVIEW_FAIL` | validator Mode A | architect 재설계 (max 1회) |
| `DESIGN_REVIEW_ESCALATE` | validator Mode A | 메인 Claude 보고 후 대기 |
| `READY_FOR_IMPL` | validator Plan Validation (PASS 시) | 유저 승인 → 루프 C |
| `DESIGN_READY_FOR_REVIEW` | designer | HTML 생성 → design-critic |
| `DESIGN_HANDOFF` | 메인 Claude (유저 선택 후 발행) | architect Module Plan (영향 있을 때) → 루프 C |
| `DESIGN_LOOP_ESCALATE` | designer | 유저 직접 선택 |
| `SPEC_GAP_FOUND` | engineer / test-engineer | architect SPEC_GAP, counter 리셋 |
| `SPEC_GAP_RESOLVED` | architect Mode C | engineer 재시도 |
| `TESTS_PASS` / `TESTS_FAIL` | test-engineer | PASS → vitest / FAIL → retry |
| `PASS` / `FAIL` | validator Mode B | PASS → pr-reviewer / FAIL → retry |
| `LGTM` / `CHANGES_REQUESTED` | pr-reviewer | LGTM → security-reviewer / CR → retry |
| `SECURE` / `VULNERABILITIES_FOUND` | security-reviewer | SECURE → commit / VF (HIGH/MEDIUM) → retry |
| `HARNESS_DONE` | harness-loop.sh | 메인 Claude: stories 체크 → 유저 보고 |
| `HARNESS_KILLED` | harness-loop.sh (킬 스위치) | 루프 즉시 종료. 메인 Claude 보고 후 대기 |
| `HARNESS_BUDGET_EXCEEDED` | harness-loop.sh (비용 상한) | 루프 즉시 종료. 메인 Claude 보고 후 대기 |
| `IMPLEMENTATION_ESCALATE` | harness-loop.sh | 메인 Claude 보고 후 architect SPEC_GAP 권장 |
| `KNOWN_ISSUE` | qa | 메인 Claude 보고 후 대기 |
| `PLAN_NEEDED` | harness-executor.sh | 유저 결정 → 루프 A or 이슈 종료 |
| `PLAN_VALIDATION_PASS` | validator Plan Validation | 유저 게이트 → 루프 C |
| `PLAN_VALIDATION_FAIL` | validator Plan Validation | architect 재보강 (max 1회) |
| `PLAN_VALIDATION_ESCALATE` | validator Plan Validation | 메인 Claude 보고 후 대기 |
| `UI_DESIGN_REQUIRED` | harness-executor.sh | 루프 B 선행 필요 안내 |
| `DESIGN_DONE` | harness-executor.sh | 유저 시안 확인 대기 |
| `PLAN_DONE` | harness-executor.sh | 유저 결정 대기 |
| `SPEC_GAP_ESCALATE` | harness-executor.sh | 메인 Claude 보고 |
| `TECH_CONSTRAINT_CONFLICT` | architect Mode C | 메인 Claude 보고 후 대기 |

---

## 정책 (절대 원칙)

**1. 메인 Claude — src/** 직접 Edit/Write 절대 금지**
이유 불문. 규모 불문. 상황 불문.
반드시 `bash .claude/harness-executor.sh`를 통해서만 구현.

**2. 구현 루프 예외 없음**
`src/**` 변경이 발생하는 모든 작업은 루프 C를 반드시 거친다.
"줄 수가 적다", "간단한 수정", "빨리 해달라" — 어느 것도 루프 자체를 건너뛰는 근거가 되지 않는다.
단, `--depth=fast` 플래그로 루프 깊이를 줄이는 것은 허용된다:

| depth | 실행 단계 | 사용 조건 |
|---|---|---|
| `fast` | engineer → commit (테스트·리뷰·보안 스킵) | impl에 `(MANUAL)` 태그만 있을 때 / 변수명·설정값 등 단순 변경 |
| `std` | engineer → test-engineer → vitest → validator → commit (LLM 3회) | 일반 구현 (기본값) |
| `deep` | engineer → test-engineer → vitest → validator → pr-reviewer → security-reviewer → commit (LLM 5회) | impl에 `(BROWSER:DOM)` 태그 있을 때, 또는 보안·품질 게이트 필요 시 |

자동 선택 규칙 (`--depth` 미지정 시):
- impl 파일에 `(MANUAL)` 태그만 있고 `(TEST)` `(BROWSER:DOM)` 없음 → `fast` 자동
- impl 파일에 `(BROWSER:DOM)` 태그 있음 → `deep` 자동
- 그 외 → `std`

**3. 유저 게이트 — 자동 진행 절대 금지**

| 게이트 | 금지 행동 |
|--------|-----------|
| `READY_FOR_IMPL` | 유저 명시 승인 전 루프 C 자동 진입 금지 |
| `DESIGN_HANDOFF` | 유저 선택 전 루프 C 자동 진입 금지 |
| `HARNESS_DONE` | 유저 보고 후 대기. 다음 모듈 자동 진입 금지 |
| `PLAN_DONE` | 유저 결정 전 다음 단계 진입 금지 |
| `PLAN_VALIDATION_PASS` | 유저 확인 전 impl2 자동 호출 금지 |

**4. 하네스 에이전트 포어그라운드 순차 실행**
`harness-loop.sh` 내 에이전트(engineer/validator 등) 호출은 포어그라운드 순차 실행. 에이전트 간 백그라운드 스폰 금지.
단, `harness-executor.sh` 자체는 `harness-router.py` 훅이 Popen 백그라운드 spawn (S16) — LLM이 Bash 도구로 직접 실행 금지 (이중 실행·좀비 방지).
spawn 안전 메커니즘: Atomic O_CREAT|O_EXCL lock + TTL 120s stale 해제 + heartbeat 15s JSON lease 갱신 + EXIT trap 정리 + timeout per agent call.
킬 스위치 (S31): `touch /tmp/{PREFIX}_harness_kill` → 다음 에이전트 호출 전 감지 → 즉시 `HARNESS_KILLED` 출력 + 루프 종료. harness-executor EXIT trap에서도 kill 파일 정리.
에이전트별 예산 상한 (S30): 모든 `_agent_call`에 `--max-budget-usd 2.00` 적용. 개별 에이전트 폭주 방지.
전체 루프 비용 상한 (S32): stream-json result 이벤트에서 `total_cost_usd` 추출 → `TOTAL_COST` 누적 → $10 초과 시 즉시 `HARNESS_BUDGET_EXCEEDED` 출력 + 루프 종료. `hlog`에 에이전트별·누적 비용 기록.
pre-evaluator: engineer 완료 직후 sh 레벨 사전 검사 (has_changes / no_new_deps / file_unchanged) → LLM 호출 없이 즉시 attempt++ (S17-2).
HARNESS_INTERNAL 재귀 방지: `_agent_call`이 `claude --agent xxx -p "..."` 실행 시 UserPromptSubmit 훅도 트리거됨. `HARNESS_INTERNAL=1` env var로 내부 호출 감지 → 라우터 즉시 통과 (재귀 spawn 방지).
is_bug LLM 분류 스킵: `is_bug=True` 확정 시 `classify_intent_llm()` 호출 금지 — 불필요한 curl 호출이 10s 훅 타임아웃 초과 유발.
이중 방어선: ① 내부 프롬프트 패턴 감지(^bug:.*issue: 등) → 즉시 통과. ② spawn rate limiter — 60초 내 3회 초과 시 하드 블록. HARNESS_INTERNAL 실패해도 차단.
붙여넣기 콘텐츠 감지(3차 방어): 유저가 로그/대화 기록을 붙여넣으면 라우터가 내용 속 키워드를 실제 명령으로 오인해 하네스 스폰. `[HH:MM:SS] [prefix]` 타임스탬프 패턴, Claude Code UI 마커(❯+⎿, ✶) 감지 시 즉시 통과.
LLM PRIMARY 분류(S19+): regex 키워드 분류 제거 → Haiku `extract_intent()`가 GREETING/QUESTION/IMPLEMENTATION/BUG/AMBIGUOUS/GENERIC 6카테고리 직접 반환. ≤2자 표현은 API 절약 위해 즉시 GREETING 처리. 안전 방어선(1~3차)은 LLM 호출 전 유지.
인터뷰 질문 주입 포맷: `additionalContext`에 "[HARNESS ROUTER] 지금 즉시 유저에게 아래 질문을 한국어로 물어보라" 형식으로 directive하게 주입 → 메인 Claude가 질문을 유저에게 전달.

**5. 에스컬레이션 → 메인 Claude 보고 후 대기**
에스컬레이션 마커 수신 시 자동 복구 시도 금지.
반드시 유저에게 보고 후 지시를 기다린다.

**6. 단일 소스 원칙 — orchestration-rules.md 선행 수정 강제**
워크플로우 변경(에이전트 추가/삭제, 루프 순서 변경, 마커 추가, 플래그 추가)이 필요할 때:
1. **먼저** 이 파일(`orchestration-rules.md`)에 변경 사항을 반영한다.
2. **그 다음** 스크립트(`harness-executor.sh`, `harness-loop.sh`, `setup-harness.sh` 등)를 업데이트한다.
3. 스크립트를 먼저 수정하고 이 파일을 나중에 수정하는 것은 **절대 금지**.
위반 시 PreToolUse 훅이 차단한다 (`orch_rules_first` 게이트).

**7. 실패 패턴 자동 프로모션**
`harness-memory.md`에 같은 파일+유형 조합의 실패가 3회 이상 누적되면:
1. 해당 패턴을 `## Auto-Promoted Rules` 섹션으로 이동
2. 이후 CONSTRAINTS 로드 시 Auto-Promoted Rules를 최우선 포함
3. 프로모션된 규칙은 수동 삭제 전까지 영구 적용

**8. 수용 기준 메타데이터 없는 태스크 = 구현 진입 불가**
impl 파일의 모든 요구사항 항목은 `## 수용 기준` 섹션에 검증 방법 태그가 있어야 한다.

**impl 파일 필수 포맷 요구사항**:
- `## 수용 기준` 섹션 필수 (섹션 자체가 없으면 PLAN_VALIDATION_FAIL)
- 각 요구사항 행에 `(TEST)` / `(BROWSER:DOM)` / `(MANUAL)` 중 하나 필수

**검증 방법 태그 의미**:
| 태그 | 의미 | 사용 조건 |
|---|---|---|
| `(TEST)` | vitest 자동 테스트 | 기본값 — 로직·상태·훅 검증 |
| `(BROWSER:DOM)` | Playwright DOM 쿼리 | UI 렌더링·DOM 상태 검증이 필요한 경우 |
| `(MANUAL)` | curl/bash 수동 절차 | 자동화가 불가능한 경우에만 (이유 명시 필수) |

impl 진입 게이트 상세:
```
validator [Plan Validation]
  ↓ PASS (기존 A/B 체크)
validator [수용 기준 메타데이터 감사]  ← 정책 8 게이트
  태그 없는 요구사항 발견 → PLAN_VALIDATION_FAIL (architect 재보강)
  ↓ PASS
READY_FOR_IMPL
```

**9. 하네스 관련 수정 순서**
`harness-executor.sh` / `harness-loop.sh` / `hooks/*.py` / `settings.json(hooks 섹션)` / 에이전트 파일 변경 시:
1. **먼저** `docs/harness-backlog.md` — 해당 항목 상태 업데이트 또는 신규 항목 추가
2. **그 다음** 실제 파일 수정
3. **마지막** `docs/harness-state.md` 관련 섹션 현행화 (완료 기능 / 플래그 / 파일 인벤토리)
순서 위반(backlog 없이 수정, state 나중에 안 하는 것) 금지.
물리적 강제: 현재는 written policy. 향후 `orch-rules-first.py` 확장으로 물리적 차단 예정.

---

## 에이전트 역할 경계

| 에이전트 | 담당 | 절대 금지 |
|----------|------|-----------|
| architect | 설계 문서 · impl 파일 작성 | src/** 수정 |
| engineer | 소스 코드 구현 | 설계 문서 수정 |
| validator | PASS/FAIL 판정 리포트 | 파일 수정 |
| designer | variant 3개 생성 | src/** 수정 |
| design-critic | PICK/ITERATE/ESCALATE 판정 | 파일 수정 |
| qa | 원인 분석 + 라우팅 추천 | 코드·문서 수정 |
| product-planner | PRD/TRD 작성 | 코드·설계 문서 수정 |
| test-engineer | 테스트 코드 작성 | 소스 수정 |
| pr-reviewer | 코드 품질 리뷰 | 파일 수정 |
| security-reviewer | OWASP+WebView 보안 감사 | 파일 수정 |

### 에이전트별 Write/Edit 허용 경로 매트릭스 (물리적 강제)

PreToolUse 훅 `agent-boundary.py`가 아래 매트릭스를 물리적으로 차단한다.
`{agent}_active` 플래그가 활성화된 상태에서 허용 경로 외 파일을 Write/Edit하면 deny.

| 에이전트 | 허용 경로 | 비고 |
|----------|-----------|------|
| engineer | `src/**` | 테스트 포함 |
| architect | `docs/**`, `backlog.md` | impl 파일 포함 |
| designer | `design-preview-*.html`, `docs/ui-spec*` | architecture 계열 금지 |
| test-engineer | `src/__tests__/**` | src 본체 수정 금지 |
| product-planner | `prd.md`, `trd.md` | 설계 문서 금지 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit deny |

---

## 이 파일 변경 시 함께 업데이트할 대상

| 변경 내용 | 업데이트 대상 |
|-----------|---------------|
| 루프 순서 / 조건 변경 | `harness-executor.sh`, `harness-loop.sh`, `docs/harness-state.md` |
| 마커 추가 / 변경 | 해당 에이전트 md 파일 |
| 에이전트 역할 경계 변경 | 해당 에이전트 md 파일 |
| 에이전트 추가 / 삭제 | 역할 경계 표 + 해당 루프 다이어그램 + 마커 표 + 스크립트 |
| 하네스 기능 추가 / 변경 | `docs/harness-state.md` (완료/한계 섹션) + `docs/harness-backlog.md` (항목 상태) |
| architect Mode 추가/변경 | `CLAUDE.md` (프로젝트) architect 호출 규칙 표 |
