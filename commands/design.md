---
description: UI 디자인 워크플로우를 실행한다. DEFAULT(기본): Pencil MCP로 1개 variant 생성 → 유저 직접 확인. CHOICE(--choice): 3개 variant 생성 → design-critic PASS/REJECT → 유저 PICK.
argument-hint: "[대상 화면/컴포넌트] [--choice (3 variant + 크리틱)] [--ux-redesign (UX 전면 개편)]"
---

# /design

UI 디자인 워크플로우 실행 (Pencil MCP 기반 v3).

**요청 내용:** $ARGUMENTS

---

## 실행 순서

### Step 1 — 모드 결정

`$ARGUMENTS`에서 모드를 결정한다:

| 플래그 | 모드 | 동작 |
|---|---|---|
| (없음) | **DEFAULT** | 1 variant 생성 → 유저 직접 확인 |
| `--choice` | **CHOICE** | 3 variants 생성 → design-critic PASS/REJECT → 유저 PICK |
| `--ux-redesign` | **UX_REDESIGN** | 5→3 선별 → CHOICE 흐름 |

Pencil MCP 연결 확인:
- MCP 도구 `get_editor_state`가 응답하면 → Pencil 모드 진행
- 연결 실패 시 → ASCII 와이어프레임 + React 코드 폴백 제안:
  ```
  Pencil MCP 연결에 실패했습니다.
  Pencil.dev 설치 및 MCP 서버 활성화를 확인해주세요.
  ASCII 와이어프레임 모드로 대신 진행할까요? (y/n)
  ```

### Step 2 — designer 에이전트 실행

`~/.claude/agents/designer.md` 기반 designer 에이전트를 실행한다.

에이전트에 전달할 컨텍스트:
- 대상 화면/컴포넌트: `$ARGUMENTS`에서 추출
- 실행 모드: Step 1에서 결정한 모드
  - DEFAULT → `@MODE:DESIGNER:DEFAULT`
  - CHOICE → `@MODE:DESIGNER:CHOICE`
  - UX_REDESIGN → `@MODE:DESIGNER:UX_REDESIGN`
- 이전 피드백: 있으면 포함

designer 에이전트 수행:
- Phase 0: 컨텍스트 수집 + Pencil 캔버스 준비
- Phase 1: variant 생성 (DEFAULT: 1개 / CHOICE: 3개)
- `DESIGN_READY_FOR_REVIEW` 마커와 함께 variant 요약 출력

### Step 3 — DEFAULT vs CHOICE 분기

#### DEFAULT 모드 (--choice 없음)
design-critic을 호출하지 않는다. 유저에게 직접 확인을 요청한다:

```
✅ variant-A가 Pencil 캔버스에 준비됐습니다.
Pencil에서 확인 후 APPROVE / REJECT를 입력해주세요.
```

유저 응답:
- `APPROVE` → Step 4 진행
- `REJECT` / `다시` / `마음에 안 들어` → Step 2 재실행 (최대 3회, 초과 시 에스컬레이션)
- `취소` → 워크플로우 종료

#### CHOICE 모드 (--choice)
design-critic에 3 variants를 전달해 PASS/REJECT 판정을 받는다.

- `VARIANTS_APPROVED` (1개 이상 PASS) → Step 4 유저 PICK
- `VARIANTS_ALL_REJECTED` → Step 2 재실행 (최대 3회, 피드백 누적)
- 3라운드 후에도 VARIANTS_ALL_REJECTED → 에스컬레이션

### Step 4 — 유저 확인/선택 대기

**DEFAULT 모드**: 유저가 APPROVE 입력 → Step 5 진행.

**CHOICE 모드**: Pencil 캔버스에서 PASS된 variant 확인 후 선택 입력.

```
✅ PASS된 variant가 있습니다.
Pencil에서 확인 후 선택할 variant를 입력하세요 (A/B/C):
```

유저 응답 패턴 (CHOICE):
- `"A"` / `"B"` / `"C"` → 해당 variant 선택, Step 5 진행
- `"A, 버튼 색상 수정해서"` → A 기반 수정 후 Step 5 진행
- `"다시"` / `"마음에 안 들어"` → Step 2 재실행 (3회 초과 시 에스컬레이션)
- `"취소"` → 워크플로우 종료

> ⚠️ 유저 승인 없이 절대 Step 5로 넘어가지 않는다.

### Step 5 — Phase 4 코드 생성 (DESIGN_HANDOFF)

designer Phase 4를 실행해 DESIGN_HANDOFF 패키지 생성:
- Pencil에서 확정 프레임 요소 추출 (`batch_get`)
- 디자인 토큰 테이블 + 컴포넌트 구조 + 애니메이션 구현 스펙
- 코드 생성 → `design-variants/` 디렉토리에 저장 (src/ 직접 수정 금지)

패키지 출력 후:
```
impl 에이전트로 바로 적용할까요?
- y: architect → engineer 루프 실행 (Step 6)
- n: Handoff 패키지만 저장하고 종료
```

### Step 6 — impl 에이전트 실행 (승인 시)

impl 영향 체크 → architect Module Plan (영향 있을 경우) → engineer 루프.

전달 내용:
- `DESIGN_HANDOFF` 패키지 전체
- 대상 파일 경로
- `design-variants/` 코드 파일 경로

---

## 오류 처리

- designer 3회 후 DESIGN_READY_FOR_REVIEW 없음 → 유저 에스컬레이션
- Pencil MCP 오류 → ASCII 와이어프레임 폴백 제안
- impl 에이전트 SPEC_GAP_FOUND → 유저에게 갭 보고 후 대응 확인
