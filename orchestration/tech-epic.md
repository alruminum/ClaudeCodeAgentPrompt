# 기술 에픽 루프 (Tech Epic)

진입 조건: 기술 에픽 / 리팩 / 인프라

---

```
진입: 기술 부채 / 성능 / 인프라 개선 요청
      │
      ↓
architect [Technical Epic]
      │
SYSTEM_DESIGN_READY
      │
validator [Design Validation]  ← 기획 루프와 동일 게이트
      │               │
DESIGN_REVIEW_FAIL  DESIGN_REVIEW_PASS
      │                     │
architect 재설계        Epic+Story 이슈 생성
(max 1회)              architect [Module Plan] ×N
재실패 →               READY_FOR_IMPL ×N
DESIGN_REVIEW_ESCALATE        │
→ 메인 Claude 보고       순차 실행 (×N)
                              │
                        → 구현 루프 진입
```
