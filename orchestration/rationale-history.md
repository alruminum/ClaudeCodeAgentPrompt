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

### HARNESS-CHG-20260426-05 — Anti-AI-Smell 강화 (구조 패턴 + 자기 정당화 + 라이트 우선 사고)

**Rationale**: HARNESS-CHG-20260426-04에서 "다크 네이비+골드 단톤" 명시 금지 + 라이트/다크 둘 다 강제 박았는데, jajang ux-architect 재실행 산출물이 **골드만 민트로 swap**하고 동일 구조 그대로 반환 (dark navy + 단일 채도 엑센트 + outline 카드 + 플랫 글리프). 라이트 모드는 여전히 미정의. 유저 reject "이건 좀 너무하지 않냐". 룰이 "특정 색"을 막으니 색만 바꿔서 우회됨이 명확.

진짜 문제는 색이 아니라 **구조 패턴**: 다크 단색 + 단일 엑센트 + outline 카드 + 플랫 글리프 = "Spotify/Apple Music 다크모드" 구조 cl 자체가 슬립·명상·오디오 류에서 ux-architect의 디폴트 출력. 색을 바꿔도 같은 구조면 같은 클리셰.

**Alternatives**:
- A) 색 금지 목록 더 확장 (민트·코랄·세이지 등) — 무한 추가될 거고 다음 색 swap으로 또 우회됨
- B) 구조 패턴 5가지 정의 + 3개 이상 만족 시 reject — 색 무관, 구조 자체로 차단
- C) 디자이너 외부 발주 강제 — 비용·일정 폭발
- D) 자유도 풀고 design-critic만 신뢰 — design-critic은 디자인 단계, ux-architect 단계에선 못 잡음

**Decision**: B + 추가 강제 3개:
1. **구조 패턴 5가지 자가 점검** (단색 다크 / 단일 엑센트 / outline 카드 / 플랫 글리프 / Spotify-like 인상)
2. **자기 정당화 블록 필수**: 경쟁 앱 3개 명시 + 그들의 공통 패턴 + 우리의 **구조적** 차별점 + 자가 점검 결과
3. **라이트 우선 사고**: "밤에 쓰니까 다크" 사고가 클리셰 출발점이라 명시. 슬립/명상/오디오 카테고리는 "라이트 베이스 + 텍스처/일러스트 정체성" 권장
4. **표현 매체 1개 이상 채택**: 플랫 미니멀 단독은 클리셰 함정. 일러스트·사진·텍스처·그라디언트·손글씨·픽토그램·3D·콜라주 중 정체성 매체 명시

**Follow-Up**:
- jajang 재실행 시 검증 — 자가 정당화 블록 채워서 나오는지, 구조 자가 점검에서 통과하는지
- 만약 ux-architect가 자가 정당화에서도 거짓말(경쟁 앱 가짜 차별점)하면 design-critic UX_SHORTLIST 모드로 2차 게이트 필요
- 다른 카테고리 클리셰 누적 (핀테크 = 그린+화이트+숫자 모노 / SaaS = 인디고 그라디언트 + 카드 그리드 / 게임 = ...)

**Related**: 유저 발언 "야 ai클리세 쓰지말라니까 이건 좀 너무하지 않냐" + jajang 민트 톤 재시안 캡처 (2026-04-26 세션). HARNESS-CHG-20260426-04의 후속 강화 — 같은 세션 내 룰 약점 발견.

---

### HARNESS-CHG-20260426-04 — Anti-AI-Smell에 "다크 네이비+골드 단톤" 추가 + 라이트/다크 모드 둘 다 강제

**Rationale**: jajang ux-architect 산출물이 "딥 미드나잇 네이비 + 골드/앰버 엑센트 + 카드 outline" 톤으로 나옴. 유저 캡처 검토 결과 "Claude 브랜딩 톤(=AI 클리셰)"에 가까워 reject. 슬립·명상·오디오 류 앱에서 ux-architect가 자동으로 발현시키는 판박이 패턴으로 보임 — 한 번 막아두지 않으면 같은 카테고리 프로젝트마다 반복 사고 발생. 추가로, 가이드가 한 모드만(다크) 정의돼있어 라이트 모드 추가 시 토큰 갈아엎기 비용 발생 우려.

**Alternatives**:
- A) 케이스별 reject만 하고 일반화 안 함 — 같은 패턴 반복 발생
- B) Anti-AI-Smell에 명시적 추가 + 라이트/다크 둘 다 강제 — 사전 차단 + 토큰 시스템과 호환
- C) 아예 "다크 우선 금지, 라이트가 베이스" 강제 — 너무 경직, 진짜 다크 우선이 맞는 카테고리(영상·게임) 제약

**Decision**: B. Anti-AI-Smell 섹션에 "다크 네이비+골드/오렌지/앰버 단톤" 항목 추가 + Step 5에 컬러 팔레트 표를 라이트/다크 두 컬럼으로 강제. 두 모드 무드 일관성·WCAG AA·다크는 단순 반전 아닌 톤다운 등 가이드라인 추가.

**Follow-Up**:
- jajang은 이미 PR 진행 중 — 새 reject 처리는 ux-architect 재호출 시 자동 적용
- 추후 다른 카테고리에서 자주 발현되는 클리셰 발견 시 동일 방식으로 누적 (예: 핀테크 = 그린+화이트+숫자 모노)
- 토큰 시스템(HARNESS-CHG-20260426-02)과 결합되어 시너지 — 두 모드 토큰 모두 `theme.colors.<token>.{day,night}` 구조로 짜면 런타임 모드 전환 가능

**Related**: 유저 발언 "ux 아키텍쳐놈한테 ... 앞으로 다시는 이런 블랙+클로드 오렌지톤으로 디자인하지말라고 박아둬 추가로 나이트모드 데이모드 나눠서 색 지정하라고 하고" + jajang 디자인 시안 캡처 (2026-04-26 세션)

---

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
