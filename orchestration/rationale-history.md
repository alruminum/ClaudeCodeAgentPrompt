# Change Rationale History (WHY)

각 Task-ID의 결정 근거·검토 대안·Follow-Up.
**WHAT**(변경 파일·날짜)는 [`update-record.md`](update-record.md)에서 같은 Task-ID로 추적.

중요하지 않은 사소 변경(오타 수정, 포맷팅)은 여기에 쓰지 않는다. **판단이 섞인 변경**만 기록.

---

## 엔트리 템플릿

```markdown
### HARNESS-CHG-YYYYMMDD-NN — <한 줄 요약>

**Rationale**: 왜 이 변경이 필요했나 (배경 문제·제약·트리거)
**Alternatives**:
- A) <대안 1> — <장단점>
- B) <대안 2> — <장단점>
- C) <대안 3> — <장단점>
**Decision**: 선택한 안 + 근거
**Follow-Up**: 남은 TODO / 검증 필요 항목 / 회귀 관찰 포인트
**Related**: 관련 PR/이슈/유저 발언

---
```

---

## 엔트리

### HARNESS-CHG-20260426-02 — 듀얼 모드 디자인 토큰 우선 가드레일

**Rationale**: jajang에서 ux-flow.md만 작성된 상태(Pencil 시안 미도착)로 구현이 시작됨. 유저 질문: "구현+디자인 듀얼이 빠를까, 디자인 다 받고 한번에가 빠를까?" 단순 듀얼은 시안 도착 시 화면 단위 컴포넌트 갈아엎기 비용이 폭발 — 색·폰트·간격·레이아웃 직접 박혀있으면 시안 적용 = 사실상 재작업.

**Alternatives**:
- A) 듀얼 그대로 (가드레일 없음) — wall-clock 짧지만 시안 도착 시 재작업 폭발
- B) 디자인 도착 후 구현 (B 모드) — 재작업 0이나 디자인이 critical path가 됨, 1인 개발 정체
- C) 듀얼 + **디자인 토큰 우선** 가드레일 — 시안 도착 시 토큰값만 patch, 컴포넌트 갈아엎기 0

**Decision**: C. ux-flow.md §0 디자인 가이드가 토큰 수준(컬러·타이포·UI 패턴)까지 내려와있으면 토큰 시스템 미리 깔 수 있음. jajang 가이드는 "딥 미드나잇 네이비 + 골드 엑센트, Playfair Display, breathing room" 등 충분히 구체적. 가드레일 3개 레이어로 강제: (1) architect TASK_DECOMPOSE 1번 impl을 `01-theme-tokens.md`로 박음 (2) MODULE_PLAN UI impl에 theme 의존성 + 리터럴 금지 수용 기준 (3) engineer가 hex/rem/font-name 직접 박기 금지.

**Follow-Up**:
- jajang에서 적용 결과 관찰 — 시안 도착 시 토큰 patch 비용 실측
- 가드레일 판정 자동화 검토 (현재는 architect/engineer 본문에 명시한 자가 검사)
- React Native에서 토큰 시스템 표준 패턴(StyleSheet.create + theme provider) 권고 사항 추가 여부

**Related**: 유저 발언 "지금 자장프로젝트에 ux flow만 하고 실제 디자인은 없이 그냥 구현시작했던데 너생각에는 구현 + 디자인 듀얼로 돌리고 나중에 디자인만 바꾸는게 빠를까?" (2026-04-26 세션)

---

### HARNESS-CHG-20260425-02 — 거버넌스 프레임워크 도입 (Task-ID + WHAT/WHY 로그 + 경로 기반 drift-check)

**Rationale**: changelog.md 하나에 WHAT과 WHY가 섞여서 장기적으로 "왜 이 코드가 이렇게 됐냐"를 추적하기 어렵다. 이번 세션에서만도 plan-reviewer 위치 이동·세션 훅 버그·fallback 제거 같은 결정들이 changelog 한 줄로 압축돼 맥락이 유실됨. 친구 프로젝트(TDM)의 거버넌스 시스템을 벤치마크해서 3개 개선점 도입.

**Alternatives**:
- A) 현상 유지 (changelog.md 한 곳) — 가볍지만 WHY 증발
- B) Task-ID 도입 + WHAT/WHY 분리 2개 로그 — 친구 구조 차용, 추적성 높음
- C) 티켓팅 시스템(GitHub Issues)으로 대체 — 오프라인·에이전트 자율 작업에 약함

**Decision**: B. 다만 친구의 3중 pre-commit 강제(git hook + CC hook + AGENTS.md)는 개발 인프라인 하네스에 과잉이라 pass. drift-check를 **경로 패턴 기반**으로 정교화하고 Document-Exception은 **diff 추가 라인만** 파싱하도록 구현 (과거 예외 재활용 방지).

**Follow-Up**:
- 신규 Task-ID 강제 적용은 새 엔트리부터. 과거 changelog는 그대로.
- drift-check가 경로 정규식 매칭하므로 새 디렉토리 구조 생길 때 PATH_RULES 업데이트 필요.
- rationale-history는 "판단이 섞인 변경"만 기록 (오타·포맷팅 등 제외).

**Related**: 유저 발언 "친구의 하네스야 좋은거 없니 결국 모델이 발전할수록 이게 맞는 방향인거같아서" (2026-04-25 세션)

---

### HARNESS-CHG-20260425-01 — plan-reviewer 위치 변경 (ux-architect 뒤 → 앞)

**Rationale**: jajang 실전(2026-04-24)에서 reviewer가 UX Flow 생성 후 FAIL하면 planner + ux-architect 둘 다 재작업해야 해서 "고칠 게 너무 많다"는 문제. reviewer의 8개 차원 중 7개(현실성·MVP·제약·숨은 가정·경쟁·과금·기술 실현성)는 PRD만으로 판정 가능하므로 ux-architect 호출 **전에** 배치하는 게 재작업 비용 측면에서 훨씬 유리.

**Alternatives**:
- A) 현 위치 유지 (validator(UX) 뒤) — UX 저니를 상세 와이어프레임으로 판정 가능하지만 재작업 비용 높음
- B) planner 직후로 이동 — PRD 기반 판정으로 후반 차원은 약간 약해지나 재작업 비용 0
- C) 2단 리뷰 (planner 후 + UX 후 2회) — 철저하지만 비용·복잡도 2배

**Decision**: B 선택. UX 저니 차원(4번)은 PRD의 "화면 인벤토리 + 대략적 플로우"로 고수준 판정 가능. 상세 UX 형식 체크(화면 커버리지·상태 정의·수용 기준)는 validator(UX)가 전담하므로 역할 분리도 자연스러움.

**Follow-Up**: jajang 재시도로 실전 검증. UX 저니 고수준 판정이 실제로 유의미한 지적을 내는지 관찰.

**Related**: PR #62

---

### HARNESS-CHG-20260424-04 — 세션 훅이 `_plan_metadata.json` 삭제 버그 + fallback 제거

**Rationale**: PR #58(plan-reviewer) 직후 jajang에서 reviewer CHANGES_REQUESTED → 유저 "수정 반영" 선택 → metadata.json 리셋했는데도 다음 세션에서 planner 스킵되는 회귀 발견. 원인 2개 조합: (1) session-start.py가 metadata.json을 지움 (2) plan_loop에 넣어둔 "metadata 없고 prd.md 있으면 스킵" 폴백이 이걸 "기존 프로젝트 첫 리뷰"로 오판.

**Alternatives**:
- A) session-start.py PRESERVE에 `_plan_metadata.json` 추가만 — 리셋 시나리오는 해결되나 fallback이 여전히 오탐 가능
- B) fallback만 제거 — metadata는 계속 삭제되지만 오판 경로 차단
- C) 둘 다 — 이중 안전장치

**Decision**: C. fallback은 원래 "기존 프로젝트 첫 리뷰" 편의 목적이었는데 오히려 버그 원인이 됨. planner가 자체 체크포인트로 prd.md 있으면 빠르게 READY 리턴하므로 fallback 불필요. PRESERVE 확장으로 의도된 체크포인트도 보존.

**Follow-Up**: 관련 테스트 `test_checkpoint_fallback_existing_project_reviewer_only` 폐기, `test_no_fallback_when_metadata_missing`·`test_checkpoint_skip_ux_flow_via_metadata`로 대체.

**Related**: PR #61, 유저 "얌마" 지적 (2026-04-24 세션)

---

### HARNESS-CHG-20260424-01 — plan-reviewer 에이전트 신설 + 4개 전문성 + 8개 차원

**Rationale**: validator(UX)는 형식 체크리스트(화면 커버리지·상태 정의·수용 기준)만 검사. PRD/UX Flow의 **판단 레벨** 문제(현실성·MVP 과적재·UX 저니 어색함·숨은 가정·경쟁 맥락·BM 구조 리스크·기술 실현성)는 유저 승인 ① 이전 게이트가 없었음.

**Alternatives**:
- A) validator(UX)에 판단 차원 추가 — 단일 에이전트 과부하, 형식/판단 경계 모호해짐
- B) 신규 에이전트 `plan-reviewer` 신설 — 역할 분리 명확, 페르소나 차별화 가능
- C) product-planner 내부에 self-review 단계 — 자기 평가는 약함

**Decision**: B. 페르소나 4개 전문성 겸비 (기획팀장 + 경쟁분석가 + 과금설계 + 기술실현성 판단자). 차원 8개로 세분화. ReadOnly(src/**, docs/impl/**, trd.md 금지 — architect 내부 결정 오염 방지).

**Follow-Up**: HARNESS-CHG-20260425-01에서 위치 이동 결정됨 (jajang 실전 피드백).

**Related**: PR #58, PR #60 (전문성 확장)
