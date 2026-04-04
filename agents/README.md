# Claude Code 에이전트 시스템

AI 보조 소프트웨어 개발 워크플로를 위한 에이전트 모음.
각 에이전트는 `## 공통 지침` + `## 프로젝트 특화 지침` 2-섹션 구조로 관리된다. `/agent-downSync`로 공통 지침을 로컬에 내려받고, `/agent-upSync`로 다시 올린다.

> **오케스트레이션 방식**: 메인 Claude가 `~/.claude/orchestration-rules.md`를 직접 읽고 에이전트를 순서대로 호출한다. 오케스트레이터 에이전트 없음.
> 워크플로 강제는 `.claude/settings.json`의 PreToolUse/PostToolUse 훅으로 처리한다 (validator PASS 전 engineer 차단, architect Mode 명시 강제 등).

---

## 에이전트 목록

| 에이전트 | 파일 | 역할 | 입력 | 출력 마커 | 파일 수정 |
|---|---|---|---|---|---|
| **product-planner** | `product-planner.md` | 요구사항 수집 → 기능 스펙(AC/UX흐름) → 스코프 결정 | 유저 대화 | `PRODUCT_PLAN_READY` / `PRODUCT_PLAN_UPDATED` | O |
| **architect** | `architect.md` | Mode A: 시스템 설계 / Mode B: 모듈 계획 / Mode C: SPEC_GAP 처리 / Mode D: Epic 태스크 분해 / Mode E: 기술 에픽 작성 | `PRODUCT_PLAN_READY` + 옵션 | `SYSTEM_DESIGN_READY` / `READY_FOR_IMPL` | O |
| **validator** | `validator.md` | Mode A: 설계 검증 / Mode B: 코드 검증 (A.스펙일치 B.의존성 C.코드품질 3계층) | `SYSTEM_DESIGN_READY` 또는 구현 파일 | `DESIGN_REVIEW_PASS/FAIL` / `PASS/FAIL` | X |
| **engineer** | `engineer.md` | Phase1 스펙검토(SPEC_GAP 체크) → Phase2 구현 → Phase3 자가검증. DESIGN_HANDOFF 수신 시 Design Tokens → CSS 변환 후 통합 | `READY_FOR_IMPL` (계획 파일) | 완료 리포트 | O |
| **designer** | `designer.md` | Mode A: ASCII 와이어프레임 + React 구현체 생성 (컴포넌트 수준 3 variant / UX 개편 5 variant). Mode B: Figma 렌더링. 출력: `DESIGN_HANDOFF` 패키지 | 화면 스펙 / 피드백 | `DESIGN_READY_FOR_REVIEW` / `DESIGN_HANDOFF` | O |
| **design-critic** | `design-critic.md` | 컴포넌트 수준: 3 variant 점수화·판정. UX 개편: 5개 중 3개 선별 후 유저 제시 | 3개 또는 5개 variant | `PICK` / `ITERATE` / `ESCALATE` | X |
| **pr-reviewer** | `pr-reviewer.md` | validator PASS 이후 코드 품질 리뷰. 패턴·컨벤션·가독성·기술부채 검토. MUST FIX / NICE TO HAVE 분류. 파일 수정 금지 | 구현 파일 | `LGTM` / `CHANGES_REQUESTED` | X |
| **test-engineer** | `test-engineer.md` | engineer 완료 후 테스트 코드 작성 + 실행. TESTS_FAIL 시 engineer 재구현 요청. 구현 파일 수정 금지 | `READY_FOR_IMPL` + 구현 파일 | `TESTS_PASS` / `TESTS_FAIL` | O (테스트 파일만) |
| **qa** | `qa.md` | 이슈 접수 → 증거 확보 → 경량 RCA → 타입×심각도 2축 분류(SPEC_VIOLATION/FUNCTIONAL_BUG/REGRESSION/DESIGN_ISSUE/ARCH_ISSUE/INTEGRATION_ISSUE × CRITICAL/HIGH/MEDIUM/LOW) → 라우팅 추천. 재검증 루프 지원(최대 3회 → KNOWN_ISSUE). 코드 수정·에이전트 직접 호출 금지 | 이슈 보고 | `QA_REPORT` (BLOCKED/FAIL/PASS) | X |

---

## 전체 흐름도

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PRODUCT-PLANNER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   유저 아이디어
        │
        ▼
   ┌──────────────────────────────────────────┐
   │ Phase 1 — 요구사항 수집                  │
   │ 역질문 (서비스 본질 / 기능 / BM / 환경)  │
   └──────────────────────────────────────────┘
        │
        ▼
   ◆ 유저 확인?
  Y│         │N
   │         └──► 수정 후 재제시 ──┐
   │                               │(loop)
   ▼◄──────────────────────────────┘
   ┌──────────────────────────────────────────┐
   │ Phase 2 — 기능 스펙 작성                 │
   │ 동작 명세 / 유저 시나리오 / AC(G/W/T)   │
   │ + UX 흐름 (화면 목록 · 이동 조건)        │
   └──────────────────────────────────────────┘
        │
        ▼
   ◆ 유저 확인?
  Y│         │N
   │         └──► 수정 후 재제시 ──┐
   │                               │(loop)
   ▼◄──────────────────────────────┘
   ┌──────────────────────────────────────────┐
   │ Phase 3 — 스코프 결정                    │
   │ A Expansion / B Selective                │
   │ C Hold Scope / D Reduction               │
   │ (BM · 타임라인 · 리스크 트레이드오프)    │
   └──────────────────────────────────────────┘
        │
        ▼
   ◆ 유저 옵션 선택?
  Y│         │N
   │         └──► [대기]
   │
   ▼
PRODUCT_PLAN_READY
(요구사항 + 기능 스펙 + AC + UX 흐름 + 스코프 결정)
        │
        ├──────────────────────────────────────────────────────┐
        ▼                                                      ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MAIN CLAUDE — Phase 1                       UI 디자인 루프  ← 병렬
 (orchestration-rules.md 따름)              ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │                                                      │
        ▼                                                      ▼
   ◆ 전제조건 통과?                            ◆ UX 전체 개편?
   (스펙·AC·스코프 포함?)                     Y│              │N (컴포넌트 수준)
  Y│         │N                               ▼               ▼
   │         └──► product-planner 재요청  designer: ASCII×5  designer: variant×3  loop=0
   │                                          │               │
   ▼                                          ▼               ▼
architect (Mode A) 호출           design-critic: 5→3 선별  ◆ design-critic ◄────┐
        │                                     │             ◆ 판정?              │
        ▼                              유저 확인 (3개)    PICK──► 유저 승인?     │
   ◆ DESIGN_REVIEW_PASS? ◄─┐                  │           Y│          │N        │
  Y│         │N             │                 ▼            │          └──► [대기]│
   │         ▼              │     designer: Stitch 렌더링  ▼    ITERATE──► loop<3?│
   │   ◆ loop < 3?          │                 │          [보류]  Y│         │N   │
   │  Y│         │N         │                 ▼                  └──► designer   │
   │   │         └──► [ESCALATE]         유저 1개 선택               재호출 loop+1┘
   │   └──► architect 재호출│                 │          ESCALATE──► 유저 직접 선택
   │         loop+1 ────────┘                 │                      │
   │                                          └──────────────────────┤
   │                                                                  ▼
   │                                                           DESIGN_PICKED
   ▼                                          │
   ◆ 체크리스트 6개? ◄──────┐                 └──────────────────────────────┐
  Y│         │N             │                                               │
   │         └──► architect  │  (최대 2회, 초과 시 ESCALATE)               │
   │              보강 ──────┘                                              │
   ▼                                                                        │
   ◆ 유저 승인?                                                             │
  Y│         │N                                                             │
   │         └──► [대기]                                                    │
   │                                                                        │
   ├────────────────── 둘 다 완료 후 ◄─────────────────────────────────────┘
   ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MAIN CLAUDE — Phase 2  (Implementation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
architect (Mode B) → 계획 파일 생성
        │
        ▼
   [DESIGN_HANDOFF 수신 시]
   Design Tokens → CSS 변환
   Mode A(Code): 구현체 기반 통합
   Mode B(Figma): Figma MCP 스펙 추출
   View 레이어만 교체 (Model 변경 금지)
        │
        ▼
engineer 호출 (Phase 1: 스펙 검토)
        │
        ▼
   ◆ SPEC_GAP_FOUND?
  Y│         │N
   │         ▼
   │    ◆ 완료 조건 3개?
   │    (tsc · 파일목록 · import)
   │   Y│         │N
   │    │         └──► engineer 재작업
   └──► architect (Mode C) 보강
        → 갭 해소 후 engineer 재시작
   │
   ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MAIN CLAUDE — Phase 3  (Review)         loop=0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
test-engineer 호출
        │
        ▼
   ◆ TESTS_PASS? ◄───────────────────────────────────────┐
  Y│         │N                                           │
   │         ▼                                            │
   │   리포트 출력                                        │
   │   ◆ loop < 3?                                        │
   │  Y│         │N                                       │
   │   │         └──► [ESCALATE → 유저]                   │
   │   └──► engineer 재구현, loop+1 ──────────────────────┘
   │
   ▼
validator (Mode B) 호출  ⛔ TESTS_PASS 없으면 훅 차단
        │
        ▼
   ◆ PASS?
  Y│         │N
   │         ▼
   │   ◆ FIXABLE?                                         ┐
   │  Y│         │N                                        │
   │   │         └──► [INVESTIGATE → 유저 판단]            │
   │   ▼                                                   │
   │   ◆ loop < 3?                                         │
   │  Y│         │N                                        │ (공유 loop)
   │   │         └──► [ESCALATE → 유저]                    │
   │   └──► engineer 재구현, loop+1 ─────────────────────┐ │
   │                                                      │ │
   ▼                                                      │ │
pr-reviewer 호출                                          │ │
        │                                                 │ │
        ▼                                                 │ │
   ◆ LGTM? ◄───────────────────────────────────┐         │ │
  Y│         │N (CHANGES_REQUESTED)             │         │ │
   │         ▼                                  │         │ │
   │   ◆ loop < 3?                              │         │ │
   │  Y│         │N                             │         │ │
   │   │         └──► [ESCALATE → 유저]         │         │ │
   │   └──► engineer 재구현, loop+1 ────────────┘         │ │
   │         (test-engineer → validator 재실행)            │ │
   ▼                                                      │ │
validator + pr-reviewer 리포트 전문 출력                  │ │
        │                                                 │ │
        ▼                                                 │ │
git commit  ⛔ LGTM 없으면 훅 차단 ◄─────────────────────┘ │
        │                                                   │
        ▼                                                   │
[유저 대기] ⛔ 자동 진행 금지 ◄──────────────────────────────┘
   │
   ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MAIN CLAUDE — Phase 4  (Done)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
   [DONE ✓]
   파일 목록 / 기능 요약 / 결정 로그 / 다음 단계


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 요구사항 변경 인터럽트  (언제든 발생)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   유저 명시적 변경 요청 (자동 감지 아님)
        │
        ▼
   product-planner (Mode B)
   → 영향 분석 → PRODUCT_PLAN_UPDATED
        │
        ▼
   ◆ Phase 1 진입 전?
  Y│         │N
   │         ▼
   │   ◆ Phase 1 진행 중?
   │  Y│         │N (Phase 2 이후)
   │   │         ▼
   │   │   ◆ 구현 코드 충돌?
   │   │  Y│         │N
   │   │   ▼         ▼
   │   │  유저 보고  계획 파일만 수정
   │   │  롤백/추가
   │   ▼
   │  영향 모듈만 architect 재작성
   ▼
   product-planner 스코프 재선택
   → 새 PRODUCT_PLAN_READY → Phase 1 재시작


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 루프 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  위치                   조건                최대    초과 시
  ──────────────────────────────────────────────────────────
  product-planner        유저 미확인         무제한  대기
  Orch. Phase 1 설계     DESIGN_REVIEW_FAIL  3회     ESCALATE
  Orch. Phase 1 체크     체크리스트 미통과   최대 2회  ESCALATE
  Orch. Phase 3 테스트   TESTS_FAIL          3회 공유 ESCALATE
  Orch. Phase 3 리뷰     FAIL (FIXABLE)      3회 공유 ESCALATE
  Orch. Phase 3 PR리뷰   CHANGES_REQUESTED   3회 공유 ESCALATE
  UI 디자인 루프         ITERATE             3회     ESCALATE
```

---

## 마커 흐름

```
PRODUCT_PLAN_READY
  └→ SYSTEM_DESIGN_READY
       ├→ DESIGN_REVIEW_PASS
       └→ READY_FOR_IMPL
            └→ (구현 완료)
                 └→ TESTS_PASS (test-engineer)
                      └→ PASS (validator Mode B)
                           └→ LGTM (pr-reviewer)
                                └→ git commit → [유저 대기] → DONE ✓
                           FAIL / CHANGES_REQUESTED → engineer 재구현 → loop (최대 3회 공유)
```

---

## validator 검증 기준

### Mode A — 설계 검증 (`DESIGN_REVIEW_PASS/FAIL`)

| 항목 | 내용 |
|---|---|
| 구현 가능성 | 기술 스택·의존성 현실성 |
| 스펙 완결성 | 인터페이스·엣지케이스·에러처리 정의 여부 |
| 리스크 평가 | 모듈 경계 충돌, 누락 항목, 롤백 전략 |

### Mode B — 코드 검증 (`PASS/FAIL`)

| 계층 | 항목 | FAIL 조건 |
|---|---|---|
| **A. 스펙 일치** | 생성 파일·Props 타입·함수 시그니처·핵심 로직·에러 처리·ui-spec 일치 | 하나라도 불일치 |
| **B. 의존성 규칙** | 래퍼 함수 사용·외부 패키지·모듈 경계·공유 상태·DB 스키마 계약 | 하나라도 위반 |
| **C. 코드 품질** | 경쟁조건·메모리 누수·불필요한 리렌더·에러 전파·타입 안전성·매직 넘버·적대적 시나리오 | 프로덕션 위험 항목 발견 |

> PASS 조건: A/B 모두 통과 + C에서 치명적 문제 없음

---

## 설계 원칙

- **역할 분리**: 기획(product-planner) · 조율(메인 Claude) · 설계(architect) · 구현(engineer) · 검증(validator) · 디자인(designer+design-critic)
- **읽기 전용**: validator, design-critic은 파일을 수정하지 않는다
- **게이트 강제**: 각 Phase 출구는 반드시 유저 명시적 승인 후 진입
- **루프 상한**: 자동 루프는 최대 3회, 초과 시 ESCALATE
- **병렬 허용**: UI 디자인 루프는 Phase 1 Architecture와 병렬 실행 가능 (engineer 적용은 Phase 1 승인 후)
- **훅 강제**: PreToolUse 훅으로 validator Mode A PASS 전 engineer 호출 차단, architect 호출 시 Mode 명시 강제 (`.claude/settings.json`)
- **서브에이전트 중첩 금지**: 메인 Claude가 에이전트를 직접 호출. 서브에이전트가 다른 서브에이전트를 스폰하면 훅이 우회된다
