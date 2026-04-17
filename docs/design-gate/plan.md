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

## Phase 1 — 문서 + 에이전트 정의 ✅ 완료

> 목표: 오케스트레이션 룰 문서 수정, 에이전트 파일 생성, 기존 문서와의 모순 제거

### 1-1. ux-architect 에이전트 생성 ✅

- [x] `~/.claude/agents/ux-architect.md` 생성
  - @MODE 2개: `UX_FLOW` (정방향), `UX_SYNC` (역방향/현행화)
  - 마커: `UX_FLOW_READY`, `UX_FLOW_ESCALATE`
  - 도구: Read, Write, Glob, Grep
  - UX Flow Doc 포맷 정의 (화면 인벤토리, 플로우, 와이어프레임, 인터랙션, 상태, 애니메이션, 디자인 테이블)
  - UX_SYNC 모드: PRD + src/ 코드 → ux-flow.md 역생성

### 1-2. orchestration-rules.md 수정 ✅

- [x] 루프 진입 기준 테이블 — 기획-UX + 설계 + 구현 3개 루프 체인 반영
- [x] 마커 테이블에 UX_FLOW_READY, UX_REVIEW_PASS/FAIL/ESCALATE 추가
- [x] 유저 승인 게이트 라우팅 규칙 추가 (화면 추가→planner+ux / 기존 변경→ux만 / 비기능→planner만)
- [x] PRODUCT_PLAN_CHANGE 경로에 ux-architect 재호출 조건 추가
- [x] SPEC_GAP에서 화면 구조 변경 시 UX_FLOW_ESCALATE 에스컬레이션 경로 추가
- [x] "이 파일 변경 시 함께 업데이트할 대상" 테이블에 ux-architect 관련 항목 추가
- [x] 데이터 전달 규칙에 planner→ux-architect, ux-architect→architect 경로 추가
- [x] 체크포인트에 ux-flow.md 존재 여부 추가
- [x] 에이전트별 타임아웃에 ux-architect 600s 추가

### 1-3. orchestration 루프 문서 분리 ✅

- [x] `orchestration/plan.md` — 기획-UX 루프 전용으로 재작성 (Mermaid + 마커 레퍼런스 + 체크포인트)
- [x] `orchestration/system-design.md` — 설계 루프 신규 생성 (병렬 실행 + 한쪽 실패 처리 + 체크포인트)
- [x] `orchestration/impl.md` — Design Ref 섹션 포맷 추가

### 1-4. orchestration/design.md 수정 ✅

- [x] plan loop 경유 경로 참고 노트 추가 (기존 ux 스킬 독립 경로 보존)
- [x] system-design.md 크로스 레퍼런스 추가

### 1-5. 기존 에이전트 문서 수정 ✅

- [x] `agents/product-planner.md` — PRD에 화면 인벤토리 + 대략적 플로우 섹션 추가
- [x] `agents/architect.md` — SD 모드에 ux-flow.md 참조 규칙, MP 모드에 design-handoff.md 참조 + Design Ref 섹션 규칙
- [x] `agents/designer.md` — plan loop 경유 파라미터 (`skip_issue_creation`, `save_handoff_to`)
- [x] `agents/validator.md` — UX_VALIDATION 모드 + @PARAMS 추가
- [x] `agents/validator/ux-validation.md` — UX Validation 5점 체크리스트 생성

### 1-6. 부수 문서 수정 ✅

- [x] `orchestration/agent-boundaries.md` — ux-architect 행 + Write 경로 (docs/ux-flow.md만)
- [x] `orchestration/changelog.md` — 디자인 게이트 Phase 1 변경 이력 추가
- [x] `CLAUDE.md` — 수정 금지 테이블 + 에이전트 관리 테이블에 ux-architect 추가

### 1-7. 검수 결과

**정합성 PASS:**
- orchestration-rules.md 마커 테이블 ↔ 에이전트 md 마커 일치 ✅
- plan.md 다이어그램 ↔ orchestration-rules.md 루프 진입 기준 일치 ✅
- agent-boundaries.md ↔ 에이전트 도구 목록 일치 ✅
- design.md 두 경로 (ux 스킬 독립 / plan loop 경유) 충돌 없음 ✅
- system-design.md ↔ orchestration-rules.md 상세 문서 테이블 일치 ✅

**잔여 이슈:** 없음 (2건 모두 Phase 1 내에서 해결 완료)
- `commands/product-plan.md` 5~8단계 추가 ✅
- `orchestration-rules.md` HUD 에이전트 목록 3개 루프 분리 반영 ✅

---

## Phase 2 — Python 구현

> 목표: 오케스트레이션 룰에 맞게 하네스 코드 수정, 실제 동작하도록 구현

### 2-1. plan_loop.py 분리

- [ ] 기존 `run_plan()` → 기획-UX 루프만 실행하고 리턴
  - planner → ux-architect → validator(UX) → 메인 Claude에 결과 반환
  - ux-architect `agent_call()` 추가 (타임아웃 600s, 마커 파싱, 체크포인트)
  - `UX_FLOW_READY` / `UX_FLOW_ESCALATE` 마커 처리
  - `UX_REVIEW_PASS` / `UX_REVIEW_FAIL` 마커 처리 (재시도 max 1회 → 재FAIL시 `UX_REVIEW_ESCALATE`)
  - UI 없는 기능 감지: planner PRD 화면 인벤토리 비어있으면 ux-architect 스킵
- [ ] 체크포인트 확장: ux-flow.md 존재 시 ux-architect 스킵
- [ ] UX_SYNC 모드 분기: src/ 코드 존재 + ux-flow.md 없음 → UX_SYNC 모드로 호출
- [ ] architect(SD) / validator(DV) / architect(MP/TD) / validator(PV) 단계를 plan_loop에서 제거 (설계 루프는 메인 Claude 오케스트레이션으로 이동)

### 2-2. core.py 마커 상수 추가

- [ ] `UX_FLOW_READY`, `UX_FLOW_ESCALATE` 마커 상수
- [ ] `UX_REVIEW_PASS`, `UX_REVIEW_FAIL`, `UX_REVIEW_ESCALATE` 마커 상수
- [ ] `parse_marker()`에 신규 마커 패턴 등록

### 2-3. executor.py 파라미터 확장

- [ ] `plan` 서브커맨드: 기획-UX 루프만 실행 후 리턴 (설계 루프 분리 반영)
- [ ] architect(SD) 호출 시 `--ux-flow` 파라미터 추가 (ux-flow.md 경로)
- [ ] architect(MP/TD) 호출 시 `--design-handoff` 파라미터 추가 (design-handoff.md 경로)
- [ ] 체크포인트: design-handoff.md 존재 여부 감지

### 2-4. impl_router.py 수정

- [ ] architect(SD) 호출 시 ux-flow.md 경로 전달
- [ ] architect(MP/TD) 호출 시 design-handoff.md 경로 전달
- [ ] impl Design Ref 섹션 유무로 디자인 시안 연결 여부 판단

### 2-5. product-plan 스킬 — Python 연동 확인

`commands/product-plan.md` 5~8단계는 Phase 1에서 문서 추가 완료. Phase 2에서는:

- [ ] 스킬의 executor.py plan 호출이 축소된 plan_loop(기획-UX만)과 정상 연동되는지 확인
- [ ] 5단계(유저 승인 ①) 후 6단계(설계 루프 병렬 호출) Agent 도구 2개 동시 호출 패턴이 실제 동작하는지 확인
- [ ] 8단계 구현 루프 트리거 시 design-handoff.md 경로가 executor.sh에 정상 전달되는지 확인

### 2-6. 유저 승인 게이트 라우팅 구현

- [ ] orchestration-rules.md의 라우팅 기준을 product-plan 스킬에 반영
- [ ] PRODUCT_PLAN_CHANGE 경유 시 ux-architect 재호출 조건 분기
- [ ] validator(UX) 재실행 트리거

### 2-7. HUD / 이벤트 로그 수정

- [ ] plan_loop.py HUD 에이전트 목록을 기획-UX만으로 축소 (문서는 Phase 1에서 반영 완료, 코드 반영)
- [ ] 설계 루프용 HUD 패턴 정의 (메인 Claude 오케스트레이션이므로 별도 HUD 또는 로그 방식)
- [ ] 이벤트 로그에 ux-architect agent_start/agent_done 기록

### Phase 2 완료 기준

- plan_loop.py가 기획-UX 루프만 실행하고 정상 리턴
- core.py에 신규 마커 상수 등록 + parse_marker 동작
- product-plan 스킬이 기획-UX → 유저 승인 ① → 설계 루프(병렬) → 디자인 승인 → 구현 루프 전체 체인 실행 가능
- designer가 plan loop 경유 시 이슈 생성 스킵 + 파일 저장 동작
- 체크포인트로 중간 재시작 가능 (ux-flow.md / architecture.md / design-handoff.md 각각 독립)
- 기존 ux 스킬 독립 경로 영향 없음
- HUD 에이전트 목록이 3개 루프 분리와 일치

---

## Phase 3 — 테스트 + 검증 + 빈틈 찾기

> 목표: 실제 동작 확인, 기존 구현과 모순 없음 검증, 빈틈 발견 및 수정

### 3-1. 단위 테스트 추가

- [ ] plan_loop.py: 기획-UX 루프 분리 동작, 체크포인트 스킵, UX_SYNC 모드 분기, UI 없는 기능 스킵
- [ ] core.py: 신규 마커 파싱 (UX_FLOW_READY, UX_REVIEW_PASS/FAIL 등)
- [ ] executor.py: `--ux-flow`, `--design-handoff` 파라미터 전달
- [ ] impl_router.py: design-handoff.md 감지, ux-flow.md 파라미터 전달

### 3-2. 기존 테스트 parity 검증

- [ ] `harness/tests/test_parity.py` — 기존 테스트가 깨지지 않는지 확인
- [ ] 기존 plan loop 경로 (UI 변경 없는 기능) 정상 동작 확인
- [ ] 기존 ux 스킬 독립 경로 정상 동작 확인
- [ ] 기존 QA → DESIGN_ISSUE → ux 스킬 경로 정상 동작 확인

### 3-3. Dry-run 시나리오

- [ ] **시나리오 A: UI 포함 신규 기능**
  - 기획-UX 루프: planner → ux-architect → validator(UX) → 리턴
  - 유저 승인 ①
  - 설계 루프: architect(SD) + designer 병렬 → validator(DV) → 디자인 승인
  - 구현 루프: architect(MP) → validator(PV) → engineer
  - 검증: 각 단계 마커 정상 발행, 산출물 파일 생성 (prd.md, ux-flow.md, architecture.md, design-handoff.md, impl)
- [ ] **시나리오 B: UI 없는 순수 로직 기능**
  - 기획-UX 루프: planner → ux-architect 스킵 → 리턴
  - 설계 루프: architect(SD)만 (designer 호출 없음) → validator(DV)
  - 검증: ux-architect 스킵, designer 미호출
- [ ] **시나리오 C: 기존 프로젝트 현행화 (UX_SYNC)**
  - src/ 코드 존재 + ux-flow.md 없음 → UX_SYNC 모드
  - 검증: 코드에서 화면 구조 추출, 생성된 ux-flow.md 포맷 정합
- [ ] **시나리오 D: 중간 재시작 (ESC 복구)**
  - Case 1: 기획-UX 루프 도중 끊김 → ux-flow.md 없음 → ux-architect부터 재시작
  - Case 2: 설계 루프 도중 끊김 → architecture.md 있고 design-handoff.md 없음 → designer만 재시작
  - Case 3: 구현 루프 도중 끊김 → 기존 재진입 로직 동작
- [ ] **시나리오 E: 유저 수정 요청 라우팅**
  - 승인 ①에서 화면 추가 → planner + ux-architect 재호출
  - 승인 ①에서 기존 화면 내 변경 → ux-architect만 재호출
  - 승인 ①에서 비기능 변경 → planner만 재호출

### 3-4. 전체 정합성 검수

- [ ] orchestration-rules.md 마커 테이블 ↔ core.py 마커 상수 grep 일치
- [ ] orchestration-rules.md 에이전트 타임아웃 ↔ plan_loop.py 실제 타임아웃 값 일치
- [ ] plan.md 다이어그램 분기 ↔ plan_loop.py 코드 경로 일치
- [ ] system-design.md 흐름 ↔ product-plan 스킬 6단계 실제 호출 일치
- [ ] design.md 두 경로 (ux 스킬 독립 / system-design.md 경유) ↔ 실제 호출 코드 일치
- [ ] agent-boundaries.md Write 경로 ↔ hooks/agent-boundary.py 매트릭스 일치
- [ ] CLAUDE.md 수정 금지 테이블 ↔ 실제 에이전트 Write 권한 일치
- [ ] impl.md Design Ref 포맷 ↔ architect.md MP 모드 규칙 일치

### 3-5. 빈틈 탐색

- [ ] 에이전트 간 handoff 데이터 누락: ux-architect → architect 전달 파라미터 체인
- [ ] 에러 경로: 각 에이전트 FAIL/ESCALATE 시 복구 흐름이 실제 동작하는지
- [ ] 병렬 실행: architect(SD) 성공 + designer 실패 시 architecture.md 보존 + designer 재시도만 동작하는지
- [ ] 타임아웃: ux-architect 600s가 충분한지 (큰 프로젝트에서 화면 20개+ 와이어프레임)
- [ ] 비용: ux-architect(sonnet) + validator(UX)(sonnet) 추가로 plan loop 비용 증가량 추정
- [ ] product-plan 스킬의 설계 루프 병렬 호출이 Agent 도구 2개 동시 호출로 정상 동작하는지

### Phase 3 완료 기준

- 모든 단위 테스트 PASS
- 기존 테스트 regression 0
- 5개 dry-run 시나리오 전부 정상 통과 (시나리오 D는 4개 케이스 포함)
- 문서 ↔ 코드 정합성 불일치 0
- 발견된 빈틈 목록화 + 수정 완료

---

## 참고: 영향받는 파일 인벤토리

### 신규 생성 (Phase 1 ✅)

| 파일 | 내용 | Phase |
|------|------|-------|
| `~/.claude/agents/ux-architect.md` | ux-architect 에이전트 정의 (UX_FLOW + UX_SYNC) | P1 ✅ |
| `~/.claude/agents/validator/ux-validation.md` | UX Validation 5점 체크리스트 | P1 ✅ |
| `~/.claude/orchestration/system-design.md` | 설계 루프 (plan.md에서 분리) | P1 ✅ |
| `docs/design-gate/plan.md` | 이 문서 | P1 ✅ |

### 수정 (Phase 1 ✅)

| 파일 | 변경 | Phase |
|------|------|-------|
| `~/.claude/orchestration-rules.md` | 루프 진입 기준, 마커 테이블, 라우팅 규칙, 데이터 전달, 체크포인트, 타임아웃, 동기화 대상 | P1 ✅ |
| `~/.claude/orchestration/plan.md` | 기획-UX 루프 전용 재작성 (Mermaid, 마커, 체크포인트) | P1 ✅ |
| `~/.claude/orchestration/design.md` | plan loop 경유 참고 노트 + system-design.md 크로스 레퍼런스 | P1 ✅ |
| `~/.claude/orchestration/impl.md` | Design Ref 섹션 포맷 | P1 ✅ |
| `~/.claude/orchestration/agent-boundaries.md` | ux-architect 행 + Write 경로 | P1 ✅ |
| `~/.claude/orchestration/changelog.md` | 디자인 게이트 Phase 1 변경 이력 | P1 ✅ |
| `~/.claude/agents/product-planner.md` | PRD 화면 인벤토리 + 대략적 플로우 섹션 | P1 ✅ |
| `~/.claude/agents/architect.md` | ux-flow.md 참조, Design Ref 규칙, design-handoff.md 참조 | P1 ✅ |
| `~/.claude/agents/designer.md` | plan loop 경유 파라미터 (skip_issue_creation, save_handoff_to) | P1 ✅ |
| `~/.claude/agents/validator.md` | UX_VALIDATION 모드 + @PARAMS | P1 ✅ |
| `~/.claude/CLAUDE.md` | 수정 금지 테이블 + 에이전트 관리 테이블에 ux-architect | P1 ✅ |

### 수정 예정 (Phase 2)

| 파일 | 변경 | Phase |
|------|------|-------|
| `~/.claude/harness/plan_loop.py` | 기획-UX 루프만 실행, ux-architect agent_call, 체크포인트, architect 단계 제거 | P2 |
| `~/.claude/harness/core.py` | 신규 마커 상수 + parse_marker 패턴 | P2 |
| `~/.claude/harness/executor.py` | --ux-flow / --design-handoff 파라미터, plan 서브커맨드 축소 | P2 |
| `~/.claude/harness/impl_router.py` | ux-flow.md / design-handoff.md 경로 전달 | P2 |
