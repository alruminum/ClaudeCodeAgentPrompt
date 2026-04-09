---
description: UI 디자인 워크플로우를 실행한다. Pencil MCP로 3개 variant 생성 → 유저 심사 → impl 에이전트로 적용.
argument-hint: "[대상 화면/컴포넌트] [--ux-redesign (UX 전면 개편)]"
---

# /design

UI 디자인 워크플로우 실행 (Pencil MCP 기반 v2).

**요청 내용:** $ARGUMENTS

---

## 실행 순서

### Step 1 — 모드 결정

`$ARGUMENTS`에 `--ux-redesign`이 포함되어 있으면 **UX_REDESIGN 모드**, 아니면 **DEFAULT 모드**로 실행한다.

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
- 실행 모드: Step 1에서 결정한 모드 (`@MODE:DESIGNER:DEFAULT` 또는 `@MODE:DESIGNER:UX_REDESIGN`)
- 이전 design-critic 피드백: 있으면 포함

designer 에이전트는 다음을 수행한다:
- Phase 0: 컨텍스트 수집 + Pencil 캔버스 준비
- Phase 1: 3개 variant 생성 (Pencil 프레임 + 스크린샷 + 애니메이션 스펙)
- `DESIGN_READY_FOR_REVIEW` 마커와 함께 variant 요약 출력

### Step 3 — design-critic 실행

designer 출력(스크린샷 + 차별화 테이블 + 애니메이션 스펙)을 design-critic에 전달한다.

- PICK → Step 4 유저 선택
- ITERATE → Step 2 재실행 (최대 3회, 피드백 누적)
- ESCALATE → Step 4 유저 직접 선택 강제

### Step 4 — 유저 선택 대기

Pencil 캔버스에서 3개 variant(A/B/C) 확인 후 선택 입력.

```
✅ 3개 variant가 Pencil 캔버스에 준비됐습니다.
Pencil에서 확인 후 선택할 variant를 입력하세요 (A/B/C):
```

유저 응답 패턴:
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
