# 디자인 루프 (Design)

진입 조건: impl 파일에 UI 키워드 감지 + design_critic_passed 없음

---

```mermaid
flowchart TD
    DES["designer\n@MODE:DESIGNER:DEFAULT\n/ FIGMA / UX_REDESIGN"]
    DRR{"DESIGN_READY_FOR_REVIEW"}
    HTML["design-preview-{issue}.html 생성"]

    CRITIC["design-critic\n@MODE:CRITIC:REVIEW"]

    PICK{"PICK"}
    ITERATE{"ITERATE"}
    ESC_CRITIC{"ESCALATE"}

    DES_RETRY["designer 재시도\n(max 3회)"]
    DLE["DESIGN_LOOP_ESCALATE"]:::escalation
    USER_PICK{{"유저 직접 선택"}}

    USER_SELECT{{"유저 variant 선택"}}
    HANDOFF{"DESIGN_HANDOFF"}

    IMPL_CHK{{"impl 파일 영향 있음?"}}
    ARC_MP["architect\n@MODE:ARCHITECT:MODULE_PLAN"]
    RFI{"READY_FOR_IMPL"}
    KEEP["기존 impl 파일 유지"]

    FLAG["/tmp/{prefix}_design_critic_passed\n플래그 생성"]
    USER_APPROVE{{"유저 승인 대기"}}
    IMPL_ENTRY["→ 구현 루프 진입"]

    DES -->|"screen, ui_spec?, impl_path?"| DRR
    DRR --> HTML
    HTML --> CRITIC
    CRITIC -->|"variants, ui_spec?"| PICK
    CRITIC -->|"variants, ui_spec?"| ITERATE
    CRITIC -->|"variants, ui_spec?"| ESC_CRITIC

    PICK --> USER_SELECT
    ITERATE -->|feedback| DES_RETRY
    DES_RETRY -->|"3회 초과"| DLE
    DES_RETRY -->|"3회 이내"| DES
    ESC_CRITIC --> USER_PICK
    DLE --> USER_PICK
    USER_PICK --> USER_SELECT

    USER_SELECT --> HANDOFF
    HANDOFF --> IMPL_CHK
    IMPL_CHK -->|YES| ARC_MP
    ARC_MP -->|"design_doc, module"| RFI
    IMPL_CHK -->|NO| KEEP
    RFI --> FLAG
    KEEP --> FLAG
    FLAG --> USER_APPROVE
    USER_APPROVE --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
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
