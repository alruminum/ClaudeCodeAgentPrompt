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
