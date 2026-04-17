# 디자인 게이트 인프라 설계 — 구현 계획

> 기획 루프에 UX 단계를 추가하고, 설계/구현 루프와 연결하는 인프라 변경.
> 각 Phase는 Ralph Loop로 실행 예정.

---

## 배경

기획 루프(plan loop)에 디자인 단계가 없어서, UI 변경이 포함된 기능도 designer 호출 없이 engineer가 추측 구현하는 구조적 빈 구간 존재.

### 핵심 변경

1. **ux-architect 에이전트 신설** — 화면 플로우 + 와이어프레임 + 인터랙션 정의
2. **plan loop → 3개 루프 분리** — 기획-UX / 설계 / 구현
3. **설계 루프에서 architect(SD) + designer 병렬 실행**
4. **메인 Claude가 PM 역할로 라우팅 판단**

### TO-BE 전체 흐름

```
[기획-UX 루프] 하네스 자동
  planner (PRD + 화면 인벤토리 + 대략적 플로우)
  → ux-architect (UX Flow Doc 상세화)
  → validator (UX Validation)
  → 메인 Claude에 리턴

🧑 유저 승인 ① (PRD + UX Flow + 와이어프레임)

[설계 루프] 메인 Claude 오케스트레이션
  ├── architect(SD) via 하네스    ── 병렬
  └── designer ONE_WAY 순차 생성  ── 병렬 (하네스 밖)
  → validator(DV)
  → 🧑 디자인 승인 (Pencil 확인)

[구현 루프] 하네스 자동
  architect(MP/TD) → validator(PV) → 🧑 유저 승인 ② → engineer
```

---

## Phase 1 — 문서 + 에이전트 정의

> 목표: 오케스트레이션 룰 문서 수정, 에이전트 파일 생성, 기존 문서와의 모순 제거

### 1-1. ux-architect 에이전트 생성

- [ ] `~/.claude/agents/ux-architect.md` 생성
  - @MODE 2개: `UX_FLOW` (정방향), `UX_SYNC` (역방향/현행화)
  - 마커: `UX_FLOW_READY`, `UX_FLOW_ESCALATE`
  - 도구: Read, Write, Glob, Grep
  - UX Flow Doc 포맷 정의 (화면 인벤토리, 플로우, 와이어프레임, 인터랙션, 상태, 애니메이션, 디자인 테이블)
  - UX_SYNC 모드: PRD + src/ 코드 → ux-flow.md 역생성

### 1-2. orchestration-rules.md 수정

- [ ] 루프 진입 기준 테이블에 기획-UX 루프 추가
- [ ] 마커 테이블에 UX_FLOW_READY, UX_REVIEW_PASS/FAIL/ESCALATE 추가
- [ ] 유저 승인 게이트 라우팅 규칙 추가 (수정 요청 시 planner/ux-architect 분기 기준)
- [ ] PRODUCT_PLAN_CHANGE 경로에 ux-architect 재호출 조건 추가
- [ ] SPEC_GAP에서 화면 구조 변경 시 에스컬레이션 경로 추가
- [ ] "이 파일 변경 시 함께 업데이트할 대상" 테이블에 ux-architect 관련 항목 추가

### 1-3. orchestration/plan.md 재작성

- [ ] 3개 루프 분리 반영 (기획-UX / 설계 / 구현)
- [ ] Mermaid 다이어그램 재작성
- [ ] 마커 레퍼런스 테이블 업데이트
- [ ] 병렬 실행 구간 명시 (architect SD + designer)
- [ ] 유저 승인 게이트 ① ② 위치 명시
- [ ] 체크포인트/재시작 로직 명시

### 1-4. orchestration/design.md 수정

- [ ] plan loop 경유 경로 추가 (기존 ux 스킬 독립 경로 보존)
- [ ] designer 파라미터 추가: `skip_issue_creation`, `save_handoff_to`
- [ ] DESIGN_HANDOFF 파일 저장 경로 명시 (`docs/design-handoff.md`)

### 1-5. 기존 에이전트 문서 수정

- [ ] `agents/product-planner.md` — PRD에 화면 인벤토리 + 대략적 플로우 섹션 추가
- [ ] `agents/architect.md` — SD 모드에 ux-flow.md 참조 규칙 추가, MP 모드에 design-handoff.md 참조 + Design Ref 섹션 규칙 추가
- [ ] `agents/designer.md` — plan loop 경유 모드 파라미터 (`skip_issue_creation`, `save_handoff_to`)
- [ ] `agents/validator.md` — UX_VALIDATION 모드 추가 + `validator/ux-validation.md` 생성

### 1-6. 부수 문서 수정

- [ ] `orchestration/agent-boundaries.md` — ux-architect 행 추가 (Write 권한: docs/ux-flow.md만)
- [ ] `orchestration/impl.md` — impl에 Design Ref 섹션 포맷 명시
- [ ] `orchestration/changelog.md` — 변경 이력 추가
- [ ] `commands/ux.md` — designer 스킬로 rename 예정 표기 (당장은 기존 유지, 향후 변경)

### 1-7. 모순 검수 체크리스트

- [ ] orchestration-rules.md의 마커 테이블 ↔ 각 에이전트 md의 마커 일치
- [ ] plan.md 다이어그램 ↔ orchestration-rules.md 루프 진입 기준 일치
- [ ] agent-boundaries.md ↔ 각 에이전트 도구 목록 일치
- [ ] design.md의 두 경로 (ux 스킬 독립 / plan loop 경유) 충돌 없음
- [ ] CLAUDE.md "문서/코드 직접 수정 금지" 테이블에 ux-architect 행 추가

### Phase 1 완료 기준

- 모든 문서가 3개 루프 구조를 일관되게 반영
- ux-architect 에이전트 파일이 존재하고 2개 모드 정의 완료
- 기존 문서와 마커/경로 모순 0개
- 기존 ux 스킬 독립 경로에 영향 없음

---

## Phase 2 — Python 구현 + 훅

> 목표: 오케스트레이션 룰에 맞게 하네스 코드 수정, 실제 동작하도록 구현

### 2-1. plan_loop.py 분리

- [ ] 기존 `run_plan()` → Phase 1 (기획-UX 루프)만 실행하고 리턴
  - planner → ux-architect → validator(UX) → 메인 Claude에 결과 반환
  - ux-architect `agent_call()` 추가 (타임아웃, 마커 파싱, 체크포인트)
  - UX_FLOW_READY / UX_FLOW_ESCALATE 마커 처리
  - UX_REVIEW_PASS / UX_REVIEW_FAIL 마커 처리 (재시도 max 1회)
  - UI 없는 기능 감지: planner PRD 화면 인벤토리 비어있으면 ux-architect 스킵
- [ ] 체크포인트 확장: ux-flow.md 존재 시 ux-architect 스킵
- [ ] UX_SYNC 모드 분기: src/ 코드 존재 + ux-flow.md 없음 → UX_SYNC 모드로 호출

### 2-2. 설계 루프 오케스트레이션 (메인 Claude 규칙)

- [ ] plan loop Phase 1 리턴 후 메인 Claude가 유저 승인 ① 처리하는 흐름 정의
- [ ] 승인 후 architect(SD) + designer 병렬 호출 패턴 구현
  - architect(SD): `executor.py` 경유 (기존 패턴)
  - designer: Agent 도구 직접 호출 (하네스 밖)
  - designer에 UX Flow Doc 디자인 테이블에서 대상 화면 추출 → 화면별 ONE_WAY 순차 호출
- [ ] designer 결과물 `docs/design-handoff.md`로 저장하는 로직
- [ ] 병렬 완료 후 validator(DV) + 디자인 승인 처리

### 2-3. executor.py / impl_router.py 수정

- [ ] architect(SD) 호출 시 ux-flow.md 경로 파라미터 추가
- [ ] architect(MP/TD) 호출 시 design-handoff.md 경로 파라미터 추가
- [ ] impl frontmatter에서 `ui_change` 필드 읽기 (ux-flow.md 디자인 테이블 기반으로 architect가 마킹)
- [ ] 체크포인트 파일 추가: design-handoff.md 존재 여부 감지

### 2-4. designer 에이전트 파라미터 확장

- [ ] `skip_issue_creation: true` 시 Phase 0-0 (이슈 생성) 스킵
- [ ] `save_handoff_to: <path>` 시 DESIGN_HANDOFF를 해당 파일에 저장
- [ ] plan loop 경유 시 UX Flow Doc 와이어프레임을 디자인 가이드로 참조

### 2-5. product-plan 스킬 수정

- [ ] `commands/product-plan.md` — 3개 루프 분리 반영
- [ ] Phase 1 (기획-UX) 완료 후 유저 승인 ① 안내 메시지
- [ ] 승인 후 설계 루프(병렬) 트리거 로직
- [ ] 설계 루프 완료 후 구현 루프 트리거 로직

### 2-6. 유저 승인 게이트 라우팅 구현

- [ ] 유저 수정 요청 시 라우팅 판단 로직 (orchestration-rules 기준)
  - 화면 추가/삭제 → planner + ux-architect
  - 기존 화면 내 변경 → ux-architect만
  - 비기능 변경 → planner만
- [ ] PRODUCT_PLAN_CHANGE 경유 시 ux-architect 재호출 조건 분기
- [ ] validator(UX) 재실행 트리거

### 2-7. HUD / 이벤트 로그 확장

- [ ] 기획-UX 루프 HUD 에이전트 목록에 ux-architect 추가
- [ ] 설계 루프 HUD (병렬 표시)
- [ ] 이벤트 로그에 ux-architect agent_start/agent_done 기록

### Phase 2 완료 기준

- plan_loop.py가 Phase 1 (기획-UX)만 실행하고 정상 리턴
- 메인 Claude가 승인 ① 후 architect(SD) + designer 병렬 호출 가능
- designer가 plan loop 경유 시 이슈 생성 스킵 + 파일 저장 동작
- 체크포인트로 중간 재시작 가능
- 기존 ux 스킬 독립 경로 영향 없음

---

## Phase 3 — 테스트 + 검증 + 빈틈 찾기

> 목표: 실제 동작 확인, 기존 구현과 모순 없음 검증, 빈틈 발견 및 수정

### 3-1. 단위 테스트 추가

- [ ] plan_loop.py 테스트: Phase 1 분리 동작, 체크포인트 스킵, UX_SYNC 모드 분기
- [ ] impl_router.py 테스트: ux-flow.md 파라미터 전달, design-handoff.md 감지
- [ ] designer 파라미터 테스트: skip_issue_creation, save_handoff_to 분기
- [ ] 마커 파싱 테스트: UX_FLOW_READY, UX_REVIEW_PASS/FAIL 등 신규 마커

### 3-2. 기존 테스트 parity 검증

- [ ] `harness/tests/test_parity.py` — 기존 테스트가 깨지지 않는지 확인
- [ ] 기존 plan loop 경로 (UI 변경 없는 기능) 정상 동작 확인
- [ ] 기존 ux 스킬 독립 경로 정상 동작 확인
- [ ] 기존 QA → DESIGN_ISSUE → ux 스킬 경로 정상 동작 확인

### 3-3. Dry-run 시나리오

- [ ] **시나리오 A: UI 포함 신규 기능** — planner → ux-architect → validator(UX) → 승인 → architect(SD) + designer 병렬 → impl
  - 각 단계 마커 정상 발행 확인
  - 산출물 파일 정상 생성 확인 (prd.md, ux-flow.md, architecture.md, design-handoff.md, impl)
  - 체크포인트 파일 존재 확인
- [ ] **시나리오 B: UI 없는 순수 로직 기능** — planner → ux-architect 스킵 → architect(SD) → impl
  - ux-architect 스킵 정상 동작 확인
  - designer 호출 안 됨 확인
- [ ] **시나리오 C: 기존 프로젝트 현행화** — UX_SYNC 모드로 ux-flow.md 역생성
  - src/ 코드에서 화면 구조 추출 확인
  - 생성된 ux-flow.md 포맷 검증
- [ ] **시나리오 D: 중간 재시작** — Phase 1 완료 후 ESC → 재실행 시 ux-architect 스킵 확인
- [ ] **시나리오 E: 유저 수정 요청** — 승인 ①에서 화면 추가 요청 → 라우팅 정상 동작

### 3-4. 전체 정합성 검수

- [ ] orchestration-rules.md 마커 테이블 ↔ 실제 코드의 마커 문자열 grep 일치
- [ ] 에이전트 md 파일의 도구 목록 ↔ agent-boundaries.md 일치
- [ ] plan.md 다이어그램의 모든 분기 ↔ plan_loop.py 코드 경로 일치
- [ ] design.md 두 경로 ↔ 실제 호출 코드 일치
- [ ] CLAUDE.md "문서/코드 직접 수정 금지" 테이블 ↔ 실제 에이전트 권한 일치

### 3-5. 빈틈 탐색

- [ ] 에이전트 간 handoff 데이터 누락 점검 (ux-architect → architect 전달 파라미터)
- [ ] 에러 경로 점검: 각 에이전트 FAIL/ESCALATE 시 복구 흐름 실제 동작
- [ ] 병렬 실행 구간: 한쪽 실패 시 다른 쪽 결과물 보존 확인
- [ ] 타임아웃 정책: ux-architect 타임아웃 값 결정 (planner와 유사 600s?)
- [ ] 비용 영향: ux-architect 추가로 plan loop 전체 비용 증가량 추정

### Phase 3 완료 기준

- 모든 단위 테스트 PASS
- 기존 테스트 regression 0
- 5개 dry-run 시나리오 전부 정상 통과
- 문서 ↔ 코드 정합성 불일치 0
- 발견된 빈틈 목록화 + 수정 완료

---

## 참고: 영향받는 파일 인벤토리

### 신규 생성
| 파일 | 내용 |
|------|------|
| `~/.claude/agents/ux-architect.md` | ux-architect 에이전트 정의 |
| `~/.claude/agents/validator/ux-validation.md` | UX Validation 모드 상세 |
| `docs/design-gate/plan.md` | 이 문서 |

### 수정
| 파일 | 변경 |
|------|------|
| `~/.claude/orchestration-rules.md` | 루프 진입 기준, 마커 테이블, 라우팅 규칙, 동기화 대상 |
| `~/.claude/orchestration/plan.md` | 3개 루프 분리, Mermaid, 마커 레퍼런스 |
| `~/.claude/orchestration/design.md` | plan loop 경유 경로 추가 |
| `~/.claude/orchestration/impl.md` | Design Ref 섹션 포맷 |
| `~/.claude/orchestration/agent-boundaries.md` | ux-architect 행 추가 |
| `~/.claude/orchestration/changelog.md` | 변경 이력 |
| `~/.claude/agents/product-planner.md` | PRD 화면 인벤토리 + 플로우 섹션 |
| `~/.claude/agents/architect.md` | ux-flow.md 참조, Design Ref 규칙 |
| `~/.claude/agents/designer.md` | plan loop 경유 파라미터 |
| `~/.claude/agents/validator.md` | UX_VALIDATION 모드 |
| `~/.claude/commands/ux.md` | designer 스킬 rename 예정 표기 |
| `~/.claude/commands/product-plan.md` | 3개 루프 분리 반영 |
| `~/.claude/harness/plan_loop.py` | Phase 1 분리, ux-architect 호출, 체크포인트 |
| `~/.claude/harness/executor.py` | ux-flow.md / design-handoff.md 파라미터 |
| `~/.claude/harness/impl_router.py` | design-handoff 감지, 파라미터 추가 |
| `~/.claude/harness/core.py` | 신규 마커 상수 |
| `~/.claude/CLAUDE.md` | 수정 금지 테이블에 ux-architect 추가 |
