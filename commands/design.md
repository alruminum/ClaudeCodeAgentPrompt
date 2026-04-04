---
description: UI 디자인 워크플로우를 실행한다. designer 에이전트로 3개 variant 생성 → 유저 심사 → impl 에이전트로 적용.
argument-hint: "[대상 화면/컴포넌트] [--figma (Figma 모드)]"
---

# /design

UI 디자인 워크플로우 오케스트레이터.

**요청 내용:** $ARGUMENTS

---

## 실행 순서

### Step 1 — 모드 결정

`$ARGUMENTS`에 `--figma`가 포함되어 있으면 **Figma 모드**, 아니면 **ASCII+Code 모드**로 실행한다.

Figma 모드 선택 시 MCP 연결 확인:
- `/mcp` 에서 figma가 목록에 있으면 → Figma 모드 진행
- 없으면 → 사용자에게 안내:
  ```
  Figma MCP가 설정되지 않았습니다.
  설정 방법: claude mcp add --transport http figma https://mcp.figma.com/mcp
  ASCII+Code 모드로 대신 진행할까요? (y/n)
  ```

### Step 2 — designer 에이전트 실행

`~/.claude/agents/designer-base.md` 기반 designer 에이전트(또는 프로젝트의 `.claude/agents/designer.md`)를 실행한다.

에이전트에 전달할 컨텍스트:
- 대상 화면/컴포넌트: `$ARGUMENTS`에서 추출
- 실행 모드: Step 1에서 결정한 모드
- 이전 design-review 피드백: 있으면 포함

designer 에이전트는 `DESIGN_READY_FOR_REVIEW` 마커와 함께 3개 variant 요약을 출력한다.

### Step 3 — 유저 심사 대기

`DESIGN_READY_FOR_REVIEW` 출력 후 **반드시 멈추고** 유저 입력을 기다린다.

유저 응답 패턴:
- `"1번"` / `"1번으로"` → Variant 1 선택, Step 4 진행
- `"2번, ~~ 수정해서"` → Variant 2 기반으로 수정 사항 반영, Step 4 진행
- `"다시"` / `"마음에 안 들어"` → designer 에이전트 재실행 (최대 3회)
- `"취소"` → 워크플로우 종료

> ⚠️ 유저 승인 없이 절대 Step 4로 넘어가지 않는다.

### Step 4 — Design Handoff Package 생성

유저가 선택한 variant의 `DESIGN_HANDOFF` 패키지를 출력한다.

Mode A (ASCII+Code): 선택된 variant의 React 코드 + 토큰 정보
Mode B (Figma): Figma 링크 + 토큰 + 스펙

패키지 출력 후 물어본다:
```
impl 에이전트로 바로 적용할까요?
- y: impl 에이전트 실행 (Step 5)
- n: Handoff 패키지만 저장하고 종료
```

### Step 5 — impl 에이전트 실행 (승인 시)

`~/.claude/agents/engineer-base.md` 기반 engineer/impl 에이전트를 실행한다.

전달 내용:
- `DESIGN_HANDOFF` 패키지 전체
- 대상 파일 경로
- 모드 (Code 직접 통합 / Figma MCP 읽기)

impl 에이전트 완료 후 → reviewer 에이전트 호출 권장 메시지 출력.

---

## 오류 처리

- designer가 3회 후에도 DESIGN_READY_FOR_REVIEW를 못 내면 → 유저에게 에스컬레이션
- Figma MCP 오류 → ASCII+Code 모드로 자동 폴백 제안
- impl 에이전트 SPEC_GAP_FOUND → 유저에게 갭 내용 보고, 대응 방법 확인 후 재진행
