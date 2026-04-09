# Plan Loop (기획 루프) 상세 리뷰

> 작성일: 2026-04-09
> 리뷰어: Claude Opus 4.6
> 대상: `orchestration/plan.md` + 관련 에이전트 정의 + orchestration-rules.md
> 방법: 다이어그램/마커/에이전트 교차 검증 + Meta Phabricator / Google CL 워크플로우 벤치마크

---

## 요약

Plan Loop는 product-planner → architect → validator → impl 진입이라는 단방향 파이프라인으로 설계되어 있다. 전체적으로 견실한 구조이나, 아래 5개 카테고리에서 총 17건의 이슈를 발견했다.

| 카테고리 | 건수 | 심각도 |
|----------|------|--------|
| GAP (누락) | 6 | 높음 |
| INCONSISTENCY (불일치) | 5 | 높음 |
| INEFFICIENCY (비효율) | 3 | 중간 |
| IMPROVEMENT (개선제안) | 3 | 중간 |
| **합계** | **17** | |

**Top 3 우선 수정 권장:**
1. ARC_MP_SKIP → RFI 경로에서 Plan Validation 바이패스 (보안 허점)
2. PLAN_DONE 마커가 규칙에 정의되어 있으나 루프 어디에도 사용되지 않음
3. SCOPE / EPIC 결정 다이아몬드에 판단 기준 명세 부재

---

## 갭/불일치 분석

### G-1. [GAP] ARC_MP_SKIP 경로 Plan Validation 바이패스 — 보안 허점

**현상**: `SCOPE=NO` 분기에서 `ARC_MP_SKIP → RFI`로 직결. Plan Validation(VAL_PV)을 완전히 건너뛴다.

**다이어그램 근거** (plan.md line 57):
```
ARC_MP_SKIP -->|"design_doc, module"| RFI
```

**반면** 정상 경로(EPIC=YES/NO)는 모두 `IMPL_GATE → VAL_PV`를 거친다.

**GAP_AUDIT_REPORT 교차**: C-1에서 동일하게 지적. "같은 MODULE_PLAN 호출인데 Plan Validation 적용 여부가 루프마다 다름."

**빅테크 벤치마크**: Meta Phabricator에서는 모든 CL이 `arc diff` 전에 lint + unit test를 통과해야 한다. "소규모 변경이라 리뷰 스킵"은 존재하지 않으며, 규모에 따라 리뷰 강도(lightweight vs. full)를 조절할 뿐 게이트 자체를 제거하지 않는다. Google CL도 마찬가지로 readability reviewer를 스킵하는 경로가 없다.

**판단**: "구조 변경 없음"이 "검증 불필요"를 의미하지 않는다. Module Plan은 동일한 architect @MODE:ARCHITECT:MODULE_PLAN이며, 동일한 impl 파일을 생성한다. impl 파일의 수용 기준 메타데이터(정책 8) 감사도 이 경로에서 누락된다.

**의도적 fast-path 가능성**: 단순한 설정 변경이나 모듈 내부 수정의 경우 Plan Validation이 과잉일 수 있다. 하지만 현재 SCOPE=NO의 정의가 "전체 구조 변경이 아님"이지 "검증이 불필요할 정도로 사소함"이 아니다.

**수정 제안**:
- ARC_MP_SKIP 경로에도 VAL_PV를 추가한다 (IMPL_GATE 경유).
- 만약 fast-path를 유지하려면, SCOPE 다이아몬드를 3-way 분기로 변경:
  - YES → SYSTEM_DESIGN (현재 그대로)
  - NO (non-trivial) → MODULE_PLAN → VAL_PV → RFI
  - NO (trivial: 설정값, 상수, 타입 수정) → MODULE_PLAN → RFI (VAL_PV 스킵, 단 정책 8 메타데이터 감사만 수행)
- 미수정 시 리스크: 수용 기준 태그 없는 impl이 검증 없이 구현 루프에 진입. 정책 8 위반.

---

### G-2. [GAP] PLAN_DONE 마커 미사용

**현상**: orchestration-rules.md 정책 3 (line 66)에 유저 게이트로 `PLAN_DONE`이 등록되어 있으나, plan.md 다이어그램에 해당 마커가 어디에도 등장하지 않는다.

**GAP_AUDIT_REPORT 교차**: A-6에서 동일하게 지적.

**분석**: plan.md의 흐름에서 기획 완료 시점은 두 군데:
1. `PRODUCT_PLAN_READY` — product-planner가 발행
2. `READY_FOR_IMPL` — architect/validator 체인 후 도달

PLAN_DONE의 의도가 (1) 직후라면 PPR → ARC_SD 사이에 유저 게이트가 필요하다.
PLAN_DONE의 의도가 (2)와 동일하다면 READY_FOR_IMPL과 중복이므로 제거해야 한다.

**수정 제안**:
- PLAN_DONE의 의도를 명확히 결정:
  - (a) PPR 직후 유저 게이트: PPR → PLAN_DONE(유저 승인) → ARC_SD. product-planner 결과를 유저가 확인 후 설계 단계 진행.
  - (b) 불필요: READY_FOR_IMPL + USER_APPROVE가 이미 같은 역할을 하므로 정책 3에서 PLAN_DONE 행을 삭제.
- 권장: (a). Meta에서도 PRD sign-off 후 design doc 작성이 별도 단계. product-planner 결과를 유저가 확인하지 않고 architect가 바로 설계를 시작하면, 잘못된 요구사항 위에 설계가 올라가는 리스크가 있다.
- 미수정 시 리스크: 정책과 다이어그램 불일치. 정책을 읽고 PLAN_DONE을 기다리는 구현이 있으면 데드락.

---

### G-3. [GAP] SCOPE 결정 다이아몬드 판단 기준 부재

**현상**: `SCOPE{{"메인 Claude 판단:\n전체 구조 변경?"}}`에 YES/NO를 결정하는 구체적 기준이 없다.

**다이어그램**: 단순히 "전체 구조 변경?"이라는 텍스트만 있음.

**문제점**:
- "전체 구조 변경"의 정의가 없다. 새 모듈 추가는? 기존 모듈 인터페이스 변경은? DB 스키마 변경은?
- 메인 Claude가 매번 다르게 판단할 수 있다 (비결정적).
- product-planner의 `PRODUCT_PLAN_UPDATED` 출력에 `affected_areas`가 있는데, 이것이 SCOPE 판단 입력으로 사용되는지 명시되어 있지 않다.

**빅테크 벤치마크**: Google Design Doc에서는 변경 규모를 "new system / major change / minor change"로 분류하되, 각 분류에 명시적 기준이 있다 (예: "3개 이상 팀의 API에 영향" → major).

**수정 제안**:
SCOPE 판단 기준을 plan.md에 명시:

| 조건 | 판단 | 근거 |
|------|------|------|
| `affected_areas`에 architecture.md 변경 포함 | YES | 시스템 구조 재설계 필요 |
| 새 모듈 추가 (기존에 없는 디렉토리/패키지) | YES | 모듈 경계 재정의 필요 |
| DB 스키마에 테이블 추가/삭제 | YES | 데이터 모델 변경 |
| 기존 모듈 내부 로직만 변경 | NO | 기존 설계 유지 |
| 설정값/상수/타입 수정 | NO | 구조 무관 |

입력 데이터: `PRODUCT_PLAN_UPDATED`의 `affected_areas` 필드를 명시적으로 SCOPE 판단에 사용한다고 기재.

---

### G-4. [GAP] EPIC 결정 다이아몬드 판단 기준 부재 + 자동화 가능성

**현상**: `EPIC{{"메인 Claude 판단:\nEpic 전체 batch?"}}`에 YES/NO 판단 기준이 없다.

**질문에 대한 답**: "이 다이아몬드는 필요한가, 자동화 가능한가?"

**분석**:
- `DESIGN_REVIEW_PASS` 이후 도달. 이 시점에서 architect의 SYSTEM_DESIGN_READY 문서에 모듈 목록과 구현 순서가 이미 존재한다.
- 모듈이 1개면 EPIC=NO (단일 MODULE_PLAN), 2개 이상이면 EPIC=YES (TASK_DECOMPOSE).
- 이 판단은 설계 문서의 모듈 수로 자동 결정 가능하다.

**수정 제안**:
- 자동화 규칙: `SYSTEM_DESIGN_READY 문서의 구현 순서 항목 수 >= 2 → TASK_DECOMPOSE, == 1 → MODULE_PLAN`
- 예외: 유저가 명시적으로 "이 모듈만 먼저" 요청한 경우 → MODULE_PLAN 강제 (override).
- 다이어그램에서 "메인 Claude 판단" 대신 "자동 분기 (모듈 수 기준, 유저 override 가능)"으로 변경.
- 미수정 시 리스크: 낮음. 현재도 동작하지만, 불필요한 사람(Claude) 판단이 병목.

---

### G-5. [GAP] product-planner → architect 핸드오프 정보 손실

**현상**: PP_NEW → PPR → ARC_SD 흐름에서 전달되는 파라미터:
- architect SYSTEM_DESIGN의 @PARAMS: `{ "plan_doc": "경로", "selected_option": "옵션" }`
- product-planner PRODUCT_PLAN의 @OUTPUT: `{ "marker": "PRODUCT_PLAN_READY", "plan_doc": "prd.md 경로" }`

**손실되는 정보**:
1. **NFR(비기능 요구사항)**: product-planner가 수집한 NFR(성능, 보안, 접근성, 오프라인)이 plan_doc 본문에는 있지만, architect @PARAMS에 별도 필드로 전달되지 않는다. architect가 plan_doc을 읽으면 되지만, 구조화된 핸드오프가 아니라 "문서를 읽고 알아서 찾아라" 방식이다.
2. **우선순위 기준**: product-planner Phase 3에서 결정된 "빠른 출시 vs 완성도 vs 확장성" 트레이드오프가 architect의 기술 스택 선정에 직접 영향을 미쳐야 하는데, 이 연결이 명시적이지 않다.
3. **기능 의존 관계**: product-planner가 작성한 기능 간 의존 관계 + 구현 순서 권고가 architect의 모듈 구현 순서와 일치해야 하는데, 교차 검증 지점이 없다.

**빅테크 벤치마크**: Google에서 PRD → Design Doc 핸드오프 시 PRD의 "Non-Goals" 섹션과 "Requirements" 섹션을 Design Doc이 명시적으로 참조(link)하고, 리뷰어가 불일치를 체크한다.

**수정 제안**:
- architect SYSTEM_DESIGN @PARAMS에 `nfr_summary`, `priority_axis`, `feature_dependencies` 필드를 추가하거나,
- validator DESIGN_VALIDATION 체크리스트에 "PRD NFR/우선순위와 설계의 정합성" 항목을 추가.
- 미수정 시 리스크: architect가 PRD의 NFR을 누락하고 설계를 진행할 수 있다. validator가 잡을 수도 있지만, DESIGN_VALIDATION 체크리스트에 PRD 정합성 항목이 없으므로 보장되지 않는다.

---

### G-6. [GAP] PRODUCT_PLAN_UPDATED → SCOPE 경로의 affected_areas 미활용

**현상**: product-planner PRODUCT_PLAN_CHANGE의 @OUTPUT에 `affected_areas`가 있으나, plan.md 다이어그램의 PPU → SCOPE 엣지에서 이 데이터가 SCOPE 판단의 입력으로 명시되지 않았다.

**다이어그램** (line 49):
```
PP_CHG -->|"plan_doc, change_request"| PPU
```

Output에 `affected_areas`가 있지만 다이어그램 엣지 라벨에 없다.

**수정 제안**: PPU → SCOPE 엣지 라벨에 `affected_areas` 추가. SCOPE 판단 기준(G-3 제안)에서 이 필드를 입력으로 사용.

---

### I-1. [INCONSISTENCY] READY_FOR_IMPL 발행 주체 혼재

**현상**: 마커 테이블(plan.md line 115)에서 `READY_FOR_IMPL | architect`로 기재. 그러나:
- ARC_MP_SKIP 경로: architect가 직접 발행 (일치)
- IMPL_GATE 경로: `PVP → RFI` 체인. validator가 PLAN_VALIDATION_PASS를 발행하고, 그 결과로 RFI에 도달. 실질 발행 주체는 validator 또는 메인 Claude.

**GAP_AUDIT_REPORT 교차**: C-4와 동일.

**수정 제안**:
- RFI는 "상태"이지 "마커"로 보는 것이 정확. 발행 주체를 "이전 단계 완료 시 메인 Claude가 설정"으로 통일.
- 또는 RFI를 두 가지로 분리: `READY_FOR_IMPL_VALIDATED` (VAL_PV 통과) vs `READY_FOR_IMPL_FAST` (스킵). 이렇게 하면 impl 루프 재진입 감지에서도 어떤 경로로 왔는지 알 수 있다.

---

### I-2. [INCONSISTENCY] 정책 8 수용 기준 메타데이터 감사 — 다이어그램 미반영

**현상**: orchestration-rules.md 정책 8 (line 107-113)에서 Plan Validation이 2단계로 정의:
```
validator [Plan Validation]
  ↓ PASS
validator [수용 기준 메타데이터 감사]  ← 정책 8 게이트
  ↓ PASS
READY_FOR_IMPL
```

하지만 plan.md 다이어그램에서는 단일 `VAL_PV` 노드만 존재.

**GAP_AUDIT_REPORT 교차**: C-2와 동일.

**분석**: validator/plan-validation.md 상세를 보면, 체크리스트 C 섹션이 "수용 기준 메타데이터 감사"를 포함하고 있다. 즉 validator 내부에서 1회 호출로 A+B+C를 모두 수행한다. 정책 8의 2단계 표현은 논리적 단계이지 물리적 호출 분리가 아닌 것으로 보인다.

**수정 제안**:
- 정책 8의 의사코드를 validator 내부 논리적 단계임을 명시하는 주석 추가. 또는
- plan.md 다이어그램에 VAL_PV 노드 내부 설명으로 "(A+B+C 포함, 정책 8 메타데이터 감사 포함)" 주석 추가.
- 미수정 시 리스크: 낮음 (실제 동작은 일치). 하지만 정책 문서와 다이어그램을 각각 읽는 사람이 다르게 해석할 수 있다.

---

### I-3. [INCONSISTENCY] ARC_REDO / ARC_RE 재시도 카운터 범위 불명확

**현상**:
- `ARC_REDO["architect 재설계\n(max 1회)"]` → 재FAIL 시 DRE (DESIGN_REVIEW_ESCALATE)
- `ARC_RE["architect 재보강\n(max 1회)"]` → 재FAIL 시 PVE (PLAN_VALIDATION_ESCALATE)

**질문에 대한 답**: "재시도 한도 max 1회는 충분한가?"

**분석**:
- max 1회 = 초회 + 재시도 1회 = 총 2회 시도.
- Design Validation 실패 후 architect가 재설계하는 것은 비용이 크다 (LLM 전체 호출). 1회 재시도는 합리적.
- Plan Validation 실패 후 재보강은 비교적 가볍다 (수용 기준 태그 추가 등). 2회까지 허용해도 비용 대비 효과가 있을 수 있다.

**빅테크 벤치마크**: Google CL 리뷰에서는 reviewer comment → author fix → re-review의 루프에 횟수 제한이 없다 (실무적으로는 3라운드 이상이면 미팅으로 전환). Meta Phabricator도 Request Changes → Update Diff에 횟수 제한은 없지만, 3라운드 이상은 드물다.

**수정 제안**:
- Design Validation 재시도 max 1회는 적절. 유지.
- Plan Validation 재시도를 max 2회로 상향 검토. 수용 기준 태그 누락 같은 단순 보강은 1회 더 기회를 주는 것이 합리적.
- 미수정 시 리스크: 낮음. 현재도 에스컬레이션으로 유저가 개입하므로 데드락은 없다.

---

### I-4. [INCONSISTENCY] ARC_MP_SKIP 입력 파라미터 불일치

**현상**: plan.md 다이어그램에서 ARC_MP_SKIP의 출력 엣지:
```
ARC_MP_SKIP -->|"design_doc, module"| RFI
```

그러나 SCOPE=NO 경로에서 ARC_MP_SKIP은 `PRODUCT_PLAN_UPDATED` 직후 호출된다. 이 시점에서 `design_doc`이 아직 존재하지 않는다 (SYSTEM_DESIGN을 거치지 않았으므로). 기존 설계 문서를 참조해야 하는데, 어떤 문서인지 명시되어 있지 않다.

architect MODULE_PLAN @PARAMS: `{ "design_doc": "SYSTEM_DESIGN_READY 문서 경로", "module": "대상 모듈명" }`
→ SYSTEM_DESIGN_READY를 거치지 않은 경로에서 design_doc에 무엇을 전달하는가?

**수정 제안**:
- ARC_MP_SKIP 호출 시 `design_doc`은 "기존 docs/architecture.md (변경 전 버전)"임을 명시.
- 또는 SCOPE=NO일 때 architect MODULE_PLAN의 @PARAMS를 `{ "design_doc": "기존 architecture.md", "module": "변경 대상", "change_context": "PRODUCT_PLAN_UPDATED 변경 요약" }` 형태로 확장.

---

### I-5. [INCONSISTENCY] 다이어그램 엣지 라벨과 @PARAMS 불일치

**현상**: 여러 엣지의 라벨이 실제 @PARAMS 스키마와 일치하지 않는다.

| 다이어그램 엣지 | 라벨 | 실제 @PARAMS |
|---|---|---|
| PP_NEW → PPR | `"idea, constraints?"` | `{ "idea": "...", "constraints?": "..." }` | 일치 |
| ARC_SD → SDR | `"plan_doc, selected_option"` | `{ "plan_doc": "...", "selected_option": "..." }` | 일치 |
| ARC_TD → IMPL_GATE | `"stories_doc, design_doc"` | 입력 파라미터가 아닌 출력이 라벨에 적혀 있음 | 불일치 |
| VAL_PV → PVF/PVP | `"impl_path"` | 출력인데 입력 라벨 위치에 적혀 있음 | 혼재 |

엣지 라벨이 "이 단계의 입력"인지 "이 단계의 출력"인지 일관성이 없다.

**수정 제안**: 엣지 라벨 규칙을 통일. 권장: `노드 → 마커` 엣지에는 출력(output) 표기, `마커 → 노드` 엣지에는 입력(input) 표기.

---

## 비효율/과잉 분석

### E-1. [INEFFICIENCY] PRODUCT_PLAN_READY 후 유저 확인 없이 architect 직행

**현상**: PP_NEW → PPR → ARC_SD 경로에서 product-planner가 PRODUCT_PLAN_READY를 발행하면 곧바로 architect SYSTEM_DESIGN으로 진입한다. 유저 확인 게이트가 없다.

**분석**: product-planner 내부에서 Phase 3 Step 8까지 유저 확인을 거치지만, 이것은 서브에이전트 내부 인터랙션이다. 서브에이전트가 완료된 후 메인 Claude 레벨에서 "이 PRD를 확정하고 설계를 시작할까요?"라는 게이트가 없다.

G-2(PLAN_DONE)와 관련. PLAN_DONE이 이 게이트여야 하지만 미사용.

**수정 제안**: PPR → USER_CONFIRM_PRD → ARC_SD 노드 추가. PLAN_DONE 마커를 이 위치에 배치.

---

### E-2. [INEFFICIENCY] 신규 기획(PP_NEW)과 변경(PP_CHG)의 합류 지점이 다름

**현상**:
- PP_NEW → PPR → ARC_SD (무조건 시스템 설계)
- PP_CHG → PPU → SCOPE → YES/NO 분기

신규 기획이라도 규모가 작을 수 있다 (예: 단일 기능 추가). 이 경우에도 무조건 SYSTEM_DESIGN을 거쳐야 하는 것은 과잉.

**빅테크 벤치마크**: 신규 프로젝트라도 규모에 따라 경량 설계(mini design doc)로 처리하는 것이 Google의 관행. Full design doc은 cross-team impact가 있을 때만.

**수정 제안**:
- PP_NEW → PPR 이후에도 SCOPE 판단을 추가. 규모가 작으면 MODULE_PLAN으로 직행.
- 또는 현재 구조 유지하되 "신규 프로젝트는 항상 시스템 설계가 필요하다"는 전제를 plan.md에 명시. 의도적 선택이라면 문서화.

---

### E-3. [INEFFICIENCY] TASK_DECOMPOSE와 MODULE_PLAN의 중복 호출 가능성

**현상**: EPIC=YES → ARC_TD (Task Decompose). ARC_TD의 출력은 `READY_FOR_IMPL ×N` (impl 파일 N개).

그런데 ARC_TD 내부에서 각 스토리에 대해 impl 파일을 작성하는 것은 사실상 MODULE_PLAN을 N번 수행하는 것과 동일하다. task-decompose.md의 작업 순서 Step 6: "각 태스크에 대응하는 impl 파일 작성".

**비효율**: 하나의 architect 세션에서 N개 impl을 모두 작성하면 컨텍스트 윈도우가 부족할 수 있다. 대규모 에픽에서 품질 저하 가능.

**수정 제안**:
- TASK_DECOMPOSE의 역할을 "태스크 분해 + 순서 결정"으로 한정하고, 각 impl 작성은 별도 MODULE_PLAN 호출로 분리.
- ARC_TD → stories + 순서 → ARC_MP ×N → RFI ×N
- 이렇게 하면 각 impl이 fresh context에서 작성되어 품질이 균일해진다.
- 미수정 시 리스크: 중간. 대규모 에픽에서 마지막 impl의 품질이 처음보다 떨어질 수 있다.

---

## 빅테크 벤치마크 기반 개선안

### B-1. [IMPROVEMENT] Design Doc Approval 게이트 추가

**빅테크 관행**: Google에서는 Design Doc이 "Approved" 상태가 되어야 구현을 시작할 수 있다. Approval은 TL + 관련 팀 리드가 한다. Meta에서도 Design Review는 별도 미팅으로 진행하는 경우가 많다.

**현재 plan.md**: DESIGN_REVIEW_PASS 후 유저 확인 없이 EPIC 분기로 진행.

**제안**: DRP → USER_APPROVE_DESIGN → EPIC 게이트 추가. 유저가 설계 리뷰 결과를 확인하고 "설계 확정"을 명시적으로 승인한 후 태스크 분해로 진행.

현재는 `READY_FOR_IMPL → USER_APPROVE`가 유일한 유저 게이트인데, 이 시점은 이미 모든 impl 파일이 작성된 후이다. 설계에 문제가 있으면 impl 작성 비용이 낭비된다.

---

### B-2. [IMPROVEMENT] Incremental Plan Review (점진적 기획 리뷰)

**빅테크 관행**: Google에서는 Design Doc 작성 중에도 "Early feedback" 단계를 둔다. 완성된 문서를 한 번에 리뷰하는 것보다, 핵심 결정(기술 스택, 데이터 모델)을 먼저 리뷰하고, 상세 설계를 나중에 리뷰하는 것이 효율적이다.

**현재 plan.md**: architect가 전체 SYSTEM_DESIGN을 완성한 후 validator가 한 번에 검증. 만약 기술 스택 선택이 잘못되었으면 전체 재작성.

**제안**: SYSTEM_DESIGN을 2단계로 분리하는 것을 고려.
1. Phase A — 기술 스택 + 모듈 구조 (경량 리뷰)
2. Phase B — 상세 인터페이스 + 데이터 흐름 (전체 리뷰)

현재 구조에서 구현하려면 architect에 새로운 @MODE(ARCHITECTURE_OUTLINE)을 추가하고, validator에 경량 검증 모드를 추가해야 하므로 복잡도가 높다. 현 시점에서는 trade-off를 고려해 "향후 개선" 항목으로 분류.

---

### B-3. [IMPROVEMENT] 에스컬레이션 후 복귀 경로 명시

**빅테크 관행**: 에스컬레이션은 "멈춤"이 아니라 "판단 후 재개"이다. Google에서는 에스컬레이션 후 "decision: proceed / redesign / cancel" 3-way 분기가 명시되어 있다.

**현재 plan.md**: DRE, PVE 모두 `:::escalation` 스타일만 적용되어 있고, 에스컬레이션 후 어떤 경로로 복귀하는지 다이어그램에 없다.

**수정 제안**: 각 에스컬레이션 노드에 복귀 분기 추가:
```
DRE → USER_DECIDE
  → "재설계 지시" → ARC_SD (SCOPE 판단 포함)
  → "현재 설계 강행" → DRP
  → "기획 단계로 롤백" → PP_CHG
  → "프로젝트 중단" → END

PVE → USER_DECIDE
  → "재보강 지시" → ARC_RE (카운터 리셋)
  → "현재 계획 강행" → PVP
  → "설계 단계로 롤백" → ARC_SD
```

---

## 구체적 수정 제안

아래 표에 모든 발견 사항을 우선순위순으로 정리한다.

| # | ID | 유형 | 제목 | 수정 대상 파일 | 우선순위 | 미수정 리스크 |
|---|---|---|---|---|---|---|
| 1 | G-1 | GAP | ARC_MP_SKIP Plan Validation 바이패스 | plan.md 다이어그램 + orchestration-rules.md C-1 해소 | P0 | 정책 8 위반 impl이 검증 없이 구현 진입 |
| 2 | G-2 | GAP | PLAN_DONE 마커 미사용 | plan.md 다이어그램 + orchestration-rules.md 정책 3 | P0 | 정책-다이어그램 불일치, 데드락 가능 |
| 3 | G-3 | GAP | SCOPE 판단 기준 부재 | plan.md (기준 표 추가) | P1 | 비결정적 분기, 일관성 없는 경로 선택 |
| 4 | G-5 | GAP | product-planner → architect 핸드오프 정보 손실 | architect.md @PARAMS 또는 validator design-validation 체크리스트 | P1 | NFR/우선순위 누락된 설계 |
| 5 | I-1 | INCONSISTENCY | READY_FOR_IMPL 발행 주체 혼재 | plan.md 마커 테이블 | P1 | 다이어그램 해석 혼란 |
| 6 | I-2 | INCONSISTENCY | 정책 8 메타데이터 감사 다이어그램 미반영 | plan.md 또는 orchestration-rules.md | P2 | 문서 해석 불일치 (실동작은 정상) |
| 7 | E-1 | INEFFICIENCY | PPR 후 유저 확인 없이 architect 직행 | plan.md 다이어그램 (G-2와 연계) | P1 | 잘못된 PRD 위에 설계 진행 |
| 8 | G-4 | GAP | EPIC 판단 기준 부재 + 자동화 가능 | plan.md (자동 분기 규칙 추가) | P2 | 불필요한 수동 판단 |
| 9 | I-4 | INCONSISTENCY | ARC_MP_SKIP 입력 design_doc 미존재 | plan.md 엣지 라벨 + architect 호출 명세 | P1 | 호출 시 파라미터 오류 |
| 10 | B-1 | IMPROVEMENT | Design Doc Approval 유저 게이트 | plan.md 다이어그램 | P2 | 불필요한 impl 작성 비용 |
| 11 | B-3 | IMPROVEMENT | 에스컬레이션 후 복귀 경로 | plan.md 다이어그램 | P2 | 에스컬레이션이 사실상 종착점 |
| 12 | E-3 | INEFFICIENCY | TASK_DECOMPOSE 내부 impl 일괄 작성 | architect/task-decompose.md | P3 | 대규모 에픽 시 마지막 impl 품질 저하 |
| 13 | G-6 | GAP | affected_areas 미활용 | plan.md 엣지 라벨 | P3 | SCOPE 판단의 입력 데이터 불명확 |
| 14 | I-5 | INCONSISTENCY | 엣지 라벨 입출력 혼재 | plan.md 다이어그램 전체 | P3 | 가독성 저하 |
| 15 | E-2 | INEFFICIENCY | 신규 기획도 무조건 SYSTEM_DESIGN | plan.md 다이어그램 | P3 | 소규모 신규 기능에 과잉 설계 |
| 16 | I-3 | INCONSISTENCY | Plan Validation 재시도 한도 | plan.md + validator/plan-validation.md | P3 | 낮음 (에스컬레이션으로 보완) |
| 17 | B-2 | IMPROVEMENT | Incremental Plan Review | 구조 변경 필요 | P4 | 향후 개선 항목 |

### P0 수정안 상세

#### G-1 수정 (ARC_MP_SKIP Plan Validation 바이패스)

변경 전:
```mermaid
ARC_MP_SKIP -->|"design_doc, module"| RFI
```

변경 후:
```mermaid
ARC_MP_SKIP -->|"design_doc, module"| IMPL_GATE_SKIP
IMPL_GATE_SKIP["impl 진입 게이트\n(공통)"] --> VAL_PV
VAL_PV -->|PASS| RFI
VAL_PV -->|FAIL| ARC_RE_SKIP["architect 재보강\n(max 1회)"]
ARC_RE_SKIP -->|재FAIL| PVE
ARC_RE_SKIP -->|PASS| RFI
```

또는 기존 IMPL_GATE 노드를 공유하도록 ARC_MP_SKIP → IMPL_GATE로 연결.

#### G-2 수정 (PLAN_DONE 마커)

변경 전:
```mermaid
PPR --> ARC_SD
```

변경 후:
```mermaid
PPR --> PLAN_DONE{{"PLAN_DONE\n유저 PRD 확인"}}
PLAN_DONE -->|승인| ARC_SD
PLAN_DONE -->|수정 요청| PP_CHG
```

orchestration-rules.md 정책 3의 PLAN_DONE 행에 "PPR/PPU 직후, architect 호출 전" 위치를 명시.

---

## 부록: GAP_AUDIT_REPORT 지적 사항 대응 현황

| GAP_AUDIT ID | 본 리뷰 대응 | 상태 |
|---|---|---|
| A-6 (PLAN_DONE 미사용) | G-2에서 상세 분석 + 수정안 제시 | 대응 완료 |
| C-1 (ARC_MP_SKIP Plan Validation 스킵) | G-1에서 상세 분석 + 수정안 제시 | 대응 완료 |
| C-2 (정책 8 메타데이터 감사 미반영) | I-2에서 분석. validator 내부에서 통합 처리됨 확인. 주석 추가 권장. | 대응 완료 |
| C-4 (READY_FOR_IMPL 발행 주체) | I-1에서 상세 분석 + 통일안 제시 | 대응 완료 |
