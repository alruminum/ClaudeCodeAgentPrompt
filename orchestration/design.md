# 디자인 루프 (Design)

진입 조건: impl 파일에 UI 키워드 감지 + design_critic_passed 없음

---

```
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
                          → 구현 루프 진입
```

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:DESIGNER:DEFAULT` | designer | ASCII+Code 3 variant 생성 (기본) |
| `@MODE:DESIGNER:FIGMA` | designer | Figma MCP 연동 시 |
| `@MODE:DESIGNER:UX_REDESIGN` | designer | UX 전면 개편 요청 시 |
| `@MODE:CRITIC:REVIEW` | design-critic | 3 variant 심사 |
| `@MODE:CRITIC:UX_SHORTLIST` | design-critic | UX 개편 5→3 선별 |
| `@MODE:ARCHITECT:MODULE_PLAN` | architect | DESIGN_HANDOFF 후 impl 영향 있을 때 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `DESIGN_READY_FOR_REVIEW` | designer | HTML 생성 → design-critic 호출 |
| `PICK` | design-critic | 유저 variant 선택 대기 |
| `ITERATE` | design-critic | designer 재시도 (max 3회) |
| `ESCALATE` | design-critic | DESIGN_LOOP_ESCALATE |
| `UX_REDESIGN_SHORTLIST` | design-critic | 3개 선별 → designer Stitch 렌더링 |
| `DESIGN_LOOP_ESCALATE` | designer (3회 초과) | 유저 직접 선택 |
| `DESIGN_HANDOFF` | 메인 Claude (유저 선택 후) | architect Module Plan (영향 시) → 구현 루프 |
