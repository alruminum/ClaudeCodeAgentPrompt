# 기획 루프 (Plan)

진입 조건: 신규 프로젝트 / PRD 변경

---

```mermaid
flowchart TD
    PP_NEW["product-planner\n@MODE:PLANNER:PRODUCT_PLAN"]
    PP_CHG["product-planner\n@MODE:PLANNER:PRODUCT_PLAN_CHANGE"]

    PPR{"PRODUCT_PLAN_READY"}
    PPU{"PRODUCT_PLAN_UPDATED"}
    CI["CLARITY_INSUFFICIENT\n(마커 누락 포함)"]:::escalation

    SCOPE{{"메인 Claude 판단:\n전체 구조 변경?"}}

    ARC_SD["architect\n@MODE:ARCHITECT:SYSTEM_DESIGN"]
    ARC_MP_SKIP["architect\n@MODE:ARCHITECT:MODULE_PLAN"]

    SDR{"SYSTEM_DESIGN_READY"}

    VAL_DV["validator\n@MODE:VALIDATOR:DESIGN_VALIDATION"]

    DRF{"DESIGN_REVIEW_FAIL"}
    DRP{"DESIGN_REVIEW_PASS"}

    ARC_REDO["architect 재설계\n(max 1회)"]
    DRE["DESIGN_REVIEW_ESCALATE"]:::escalation

    EPIC{{"메인 Claude 판단:\nEpic 전체 batch?"}}

    ARC_TD["architect\n@MODE:ARCHITECT:TASK_DECOMPOSE"]
    ARC_MP["architect\n@MODE:ARCHITECT:MODULE_PLAN"]

    IMPL_GATE["impl 진입 게이트\n(공통 — 모든 루프)"]
    VAL_PV["validator\n@MODE:VALIDATOR:PLAN_VALIDATION"]

    PVF{"PLAN_VALIDATION_FAIL"}
    PVP{"PLAN_VALIDATION_PASS"}

    ARC_RE["architect 재보강\n(max 1회)"]
    PVE["PLAN_VALIDATION_ESCALATE"]:::escalation

    RFI{"READY_FOR_IMPL"}
    USER_APPROVE{{"유저 승인 대기"}}
    IMPL_ENTRY["→ 구현 루프 진입"]

    PP_NEW -->|"PRODUCT_PLAN_READY"| PPR
    PP_NEW -->|"CLARITY_INSUFFICIENT\n또는 마커 없음"| CI
    PP_CHG -->|"PRODUCT_PLAN_UPDATED"| PPU

    CI -->|"유저 답변 후 재실행"| PP_NEW

    PPR -->|"prd.md 경로 전달\n(전문 X)"| ARC_SD
    PPU --> SCOPE
    SCOPE -->|YES| ARC_SD
    SCOPE -->|NO| ARC_MP_SKIP

    ARC_SD -->|"SYSTEM_DESIGN_READY"| SDR
    ARC_SD -->|"마커 없음"| SGE_SD["SPEC_GAP_ESCALATE"]:::escalation
    ARC_MP_SKIP -->|"design_doc, module"| IMPL_GATE

    SDR --> VAL_DV
    VAL_DV -->|"design_doc"| DRF
    VAL_DV -->|"design_doc"| DRP

    DRF --> ARC_REDO
    ARC_REDO -->|재FAIL| DRE
    ARC_REDO -->|PASS| DRP

    DRP --> EPIC
    EPIC -->|YES| ARC_TD
    EPIC -->|NO| ARC_MP

    ARC_TD -->|"READY_FOR_IMPL"| IMPL_GATE
    ARC_MP -->|"READY_FOR_IMPL"| IMPL_GATE
    ARC_MP -->|"마커 없음"| SGE_MP["SPEC_GAP_ESCALATE"]:::escalation

    IMPL_GATE --> VAL_PV
    VAL_PV -->|"impl_path"| PVF
    VAL_PV -->|"impl_path"| PVP

    PVF --> ARC_RE
    ARC_RE -->|재FAIL| PVE
    ARC_RE -->|PASS| PVP

    PVP --> RFI
    RFI --> USER_APPROVE
    USER_APPROVE --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:PLANNER:PRODUCT_PLAN` | product-planner | 신규 기획 시작 |
| `@MODE:PLANNER:PRODUCT_PLAN_CHANGE` | product-planner | 기존 PRD 변경 |
| `@MODE:ARCHITECT:SYSTEM_DESIGN` | architect | PRODUCT_PLAN_READY 후 전체 구조 설계 |
| `@MODE:ARCHITECT:MODULE_PLAN` | architect | 단일 모듈 impl 작성 (구조 변경 불필요 시) |
| `@MODE:ARCHITECT:TASK_DECOMPOSE` | architect | Epic 전체 batch 분해 |
| `@MODE:VALIDATOR:DESIGN_VALIDATION` | validator | SYSTEM_DESIGN_READY 후 설계 검증 |
| `@MODE:VALIDATOR:PLAN_VALIDATION` | validator | impl 계획 검증 (impl 진입 게이트) |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `PRODUCT_PLAN_READY` | product-planner | architect System Design |
| `PRODUCT_PLAN_UPDATED` | product-planner | 메인 Claude 범위 판단 → System Design or Module Plan |
| `CLARITY_INSUFFICIENT` | product-planner (또는 마커 누락 시 자동) | 유저에게 부족 항목 질문 → 답변 후 plan 루프 재실행 |
| `SYSTEM_DESIGN_READY` | architect | validator Design Validation |
| `SPEC_GAP_ESCALATE` | plan_loop (architect 마커 누락 시 자동) | 메인 Claude 보고 후 대기 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect | product-planner 에스컬레이션 |
| `DESIGN_REVIEW_PASS` | validator | 에픽 규모 판단 → Task Decompose or Module Plan |
| `DESIGN_REVIEW_FAIL` | validator | architect 재설계 (max 1회) |
| `DESIGN_REVIEW_ESCALATE` | validator | 메인 Claude 보고 후 대기 |
| `READY_FOR_IMPL` | architect | impl 진입 게이트 → validator Plan Validation |
| `PLAN_VALIDATION_PASS` | validator | 유저 승인 → 구현 루프 진입 |
| `PLAN_VALIDATION_FAIL` | validator | architect 재보강 (max 1회) |
| `PLAN_VALIDATION_ESCALATE` | validator | 메인 Claude 보고 후 대기 |
