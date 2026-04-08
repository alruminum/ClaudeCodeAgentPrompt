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
