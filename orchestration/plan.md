# 기획 루프 (Plan)

진입 조건: 신규 프로젝트 / PRD 변경

---

```
product-planner
  │ Mode A (신규)                Mode B (변경)
  ↓                                   ↓
PRODUCT_PLAN_READY           PRODUCT_PLAN_UPDATED
  │                                   │
  │                          메인 Claude 판단:
  │                          전체 구조 변경?
  │                            YES → architect [System Design]
  │                            NO  → architect [Module Plan] → READY_FOR_IMPL
  │                                   ↓                            │
  └───────────────────────────────────┘                            │
                 ↓                                                  │
    architect [System Design]                                       │
                 │                                                  │
        SYSTEM_DESIGN_READY                                         │
                 │                                                  │
    validator [Design Validation]                                   │
          │               │                                         │
 DESIGN_REVIEW_FAIL  DESIGN_REVIEW_PASS                            │
          │                     │                                   │
    architect 재설계   DESIGN_REVIEW_SAVE_REQUIRED                  │
    (max 1회)          설계 문서 저장 확인 후 에픽 규모 판단        │
    재실패 →                 │                                      │
 DESIGN_REVIEW_ESCALATE  메인 Claude 판단:                          │
 → 메인 Claude 보고    Epic 전체 batch?                             │
                         YES ↓           NO ↓                      │
                     architect        architect                     │
                  [Task Decompose]  [Module Plan]                   │
                  impl 파일 ×N      impl 파일                       │
                          │                    │                   │
                          └─────────┬──────────┘                   │
                                    └──────────────────┬───────────┘
                                                       ↓
                                              ┌─ impl 진입 게이트 ─┐
                                              │ (공통 — 모든 루프)  │
                                              └────────┬───────────┘
                                                       ↓
                                        validator [Plan Validation]
                                          │               │
                                 PLAN_VALIDATION_FAIL  PLAN_VALIDATION_PASS
                                          │                     │
                                   architect 재보강        READY_FOR_IMPL
                                   (max 1회)                    │
                                   재실패 →               유저 승인 대기
                              PLAN_VALIDATION_ESCALATE          │
                              → 메인 Claude 보고          → 구현 루프 진입
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
| `SYSTEM_DESIGN_READY` | architect | validator Design Validation |
| `DESIGN_REVIEW_PASS` | validator | 에픽 규모 판단 → Task Decompose or Module Plan |
| `DESIGN_REVIEW_FAIL` | validator | architect 재설계 (max 1회) |
| `DESIGN_REVIEW_ESCALATE` | validator | 메인 Claude 보고 후 대기 |
| `READY_FOR_IMPL` | architect | impl 진입 게이트 → validator Plan Validation |
| `PLAN_VALIDATION_PASS` | validator | 유저 승인 → 구현 루프 진입 |
| `PLAN_VALIDATION_FAIL` | validator | architect 재보강 (max 1회) |
| `PLAN_VALIDATION_ESCALATE` | validator | 메인 Claude 보고 후 대기 |
