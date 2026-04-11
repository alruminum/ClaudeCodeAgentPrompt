---
name: ux
description: 디자인/UX 변경 요청을 2×2 포맷 매트릭스(SCREEN/COMPONENT × ONE_WAY/THREE_WAY)로 정의한 뒤 designer 에이전트를 직접 호출하는 스킬. harness 루프 없음. 유저가 "디자인 바꾸고 싶어", "시안 뽑아줘", "화면 개선하고 싶어", "디자인 이터레이션", "UX 이상해", "디자이너야", "디자인팀", "모양 바꿔", "디자인이 구려", "디자인이 심플해", "디자인 별로야", "@designer" 등의 표현을 쓸 때 반드시 이 스킬을 사용한다.
---

# UX Loop Skill

유저의 디자인/UX 변경 요청을 구조화된 컨텍스트로 만들고, 부족한 정보는 역질문으로 채운 뒤 designer 에이전트를 직접 호출한다.

## 정보 추출

유저 메시지에서 다음을 추출한다:

| 항목 | 설명 | 예시 |
|------|------|------|
| **대상** (WHERE) | 어느 화면 또는 컴포넌트인가 | "게임 메인 화면", "랭킹 리스트 카드" |
| **대상 유형** (TYPE) | 전체 화면인가, 개별 컴포넌트인가 | SCREEN / COMPONENT |
| **문제/요청** (WHAT) | 무엇이 이상하거나 어떻게 바꾸고 싶은가 | "너무 심심해", "칸이 안 맞아", "더 임팩트 있게" |
| **참고** (REF) | 스크린샷, 기준 시안, 원하는 방향 | 이미지 첨부, "레트로 아케이드 느낌" |

## 역질문 규칙

**대상(WHERE)이 없으면** 반드시 물어본다.
**문제/요청(WHAT)이 없으면** 반드시 물어본다.
TYPE이 불명확하면 물어본다 ("전체 화면인가요, 아니면 특정 컴포넌트인가요?").
참고(REF)는 없어도 진행한다.

질문은 **한 번에 최대 2개**. 이미 말한 건 다시 묻지 않는다.

## 2×2 모드 선택

정보가 충분하면 아래 형식으로 제시한다:

```
---
**UX Loop 설정**

[대상] <화면/컴포넌트명>
[유형] SCREEN (전체 화면) | COMPONENT (개별 컴포넌트)  ← 해당 항목 강조
[요청] <무엇을 어떻게 바꾸고 싶은가>
[참고] <있으면>

**시안 수 선택:**
- ONE_WAY: 시안 1개 → 유저 직접 확인 (APPROVE/REJECT)
- THREE_WAY: 시안 3개 → design-critic 심사 → 유저 PICK

어떤 모드로 실행할까요? (기본값: ONE_WAY)
---
```

## 유저 응답 해석

- 긍정/모드 미언급 ("응", "ㅇㅇ", "ok", "고", "그래", "ㅇ") → ONE_WAY로 진행
- "3개", "three", "골라볼게", "비교", "여러 개" 등 → THREE_WAY로 진행
- 수정 요청 → 수정 후 2×2 모드 선택 화면 재출력
- 취소 → 종료

## designer 직접 호출 및 critic 루프

유저 확인 후 Agent 도구로 에이전트를 직접 호출한다.
**executor.sh design은 사용하지 않는다. 오케스트레이션은 이 스킬이 담당한다.**

### 모드별 @MODE 매핑

| TYPE | 시안 수 | @MODE |
|------|---------|-------|
| SCREEN | ONE_WAY | `@MODE:DESIGNER:SCREEN_ONE_WAY` |
| SCREEN | THREE_WAY | `@MODE:DESIGNER:SCREEN_THREE_WAY` |
| COMPONENT | ONE_WAY | `@MODE:DESIGNER:COMPONENT_ONE_WAY` |
| COMPONENT | THREE_WAY | `@MODE:DESIGNER:COMPONENT_THREE_WAY` |

### 호출 프롬프트 형식

```
@MODE:DESIGNER:[SCREEN|COMPONENT]_[ONE_WAY|THREE_WAY]
@PARAMS: {
  "target": "<대상 화면/컴포넌트명>",
  "ux_goal": "<UX 목표/문제점>",
  "parent_screen?": "<COMPONENT일 때 속한 화면>",
  "ui_spec?": "<docs/ui-spec.md 경로 — 존재하면>"
}
```

### ONE_WAY 실행 절차

1. designer 에이전트 호출 (Agent 도구)
2. `DESIGN_READY_FOR_REVIEW` 수신 → 유저에게 Pencil 캔버스 확인 안내
3. 유저 APPROVE → DESIGN_HANDOFF 대기 / REJECT → designer 재호출 (max 3회)

### THREE_WAY 실행 절차

attempt = 0, max = 3

1. designer 에이전트 호출 (Agent 도구) — `DESIGN_READY_FOR_REVIEW` 수신 대기
2. `DESIGN_READY_FOR_REVIEW` 수신 후 **design-critic 에이전트 호출** (Agent 도구):
   ```
   @MODE:CRITIC:REVIEW
   designer 출력: <DESIGN_READY_FOR_REVIEW 전문>
   variant A/B/C 각각 PASS/REJECT 판정하라.
   ```
3. critic 결과 판정:
   - `VARIANTS_APPROVED` → 유저에게 PASS된 variant 안내 + PICK 요청, 종료
   - `VARIANTS_ALL_REJECTED` → attempt += 1
     - attempt < max → critic 피드백을 포함해 designer 재호출 (1번으로)
     - attempt == max → `DESIGN_LOOP_ESCALATE` 출력, 유저에게 직접 선택 요청, 종료

> **주의**: designer → critic → (재시도 시) designer 순서는 반드시 순차 실행.
> 이전 단계 결과를 받은 후 다음 에이전트를 호출한다. 병렬 호출 금지.

## 구현 연결

유저가 Pencil 캔버스에서 디자인을 확인하고 구현 요청 시:

### 1. GitHub 이슈 처리 (designer가 담당)

designer 에이전트가 Phase 0-0에서 GitHub 이슈를 직접 생성한다.
(QA 경로로 유입된 경우 기존 이슈 번호 재사용)

DESIGN_HANDOFF 후 이슈 본문에 스펙이 업데이트되어 있다.

### 2. executor.sh impl 호출

```bash
# PREFIX: .claude/harness.config.json 있으면 읽고, 없으면 생략
PREFIX=$(python3 -c "import json,sys; d=json.load(open('.claude/harness.config.json')); print(d.get('prefix',''))" 2>/dev/null || echo "")
PREFIX_FLAG=${PREFIX:+--prefix "$PREFIX"}
bash ~/.claude/harness/executor.sh impl \
  --issue <생성된 이슈 번호> \
  $PREFIX_FLAG
```

engineer가 GitHub 이슈에서 DESIGN_HANDOFF 패키지를 읽고 `batch_get`으로 Pencil 프레임을 참조해 `src/`에 구현한다.
