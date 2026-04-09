# Bugfix Loop (버그픽스 루프) 상세 리뷰

> 작성일: 2026-04-09
> 대상: `orchestration/bugfix.md` + 연관 에이전트·정책 파일
> 방법: 루프 명세 교차 검증 + Google/Meta 엔지니어링 프랙티스 비교 분석

---

## 요약

버그픽스 루프는 qa 에이전트의 4-way 분류(FUNCTIONAL_BUG, SPEC_ISSUE, DESIGN_ISSUE, KNOWN_ISSUE)를 기반으로 라우팅하는 구조로, 기본 골격은 건전하다. 그러나 교차 검증 결과 **7건의 갭/불일치**, **4건의 비효율/과잉**, **8건의 빅테크 벤치마크 기반 개선안**을 확인했다. 가장 심각한 문제는 ENG_RETRY 한도 초과 시 에스컬레이션 경로 부재(무한루프 가능)와 merge 단계 누락(브랜치 전략과 불일치)이다.

---

## 갭/불일치 분석

### G-1. [GAP] ENG_RETRY 한도 초과 시 에스컬레이션 경로 없음 (GAP_AUDIT B-4 대응)

**현황**: `ENG_RETRY["engineer 재시도 (max 2회)"]` -> ENG로 재연결만 있고, 2회 초과 후 종착점이 없다.

**impl.md와의 차이**: impl 루프에는 `FAIL_ROUTE --> |"attempt >= 3"| IMPL_ESC`가 명시적으로 있다.

**영향**: 이론적 무한 루프. 실제 하네스 스크립트에서 카운터를 관리하더라도, 명세에 빠져 있으면 스크립트 구현자가 누락할 위험이 있다.

**수정안**: ENG_RETRY 노드 뒤에 `{attempt >= 3}` 분기를 추가하고 `BUGFIX_ESCALATE` (또는 기존 `IMPLEMENTATION_ESCALATE`) 마커로 연결. 마커 테이블에도 해당 항목 추가.

---

### G-2. [GAP] merge 단계 누락 (GAP_AUDIT B-6 대응)

**현황**: `COMMIT --> HD` (직결). impl.md는 `COMMIT --> MERGE --> 충돌 시 MCE / 성공 시 HD`.

**정책 충돌**: orchestration-rules.md 브랜치 전략에 "bugfix도 feature branch 사용"이 명시되어 있고, 머지 조건 테이블에 `bugfix | validator_b_passed`가 있다. 브랜치에서 커밋만 하고 main에 머지하지 않으면 feature branch에 변경이 갇힌다.

**수정안**: COMMIT와 HD 사이에 `MERGE["merge_to_main (--no-ff)"]`와 `MCE["MERGE_CONFLICT_ESCALATE"]` 노드를 추가. impl.md와 동일 패턴.

---

### G-3. [GAP] SPEC_ISSUE 경로의 VAL_PV 실패 분기 없음 (GAP_AUDIT B-5 대응)

**현황**: `ARC_MP --> VAL_PV --> IMPL_ENTRY` 직결. VAL_PV에서 PLAN_VALIDATION_FAIL이 발생할 경우의 경로가 없다.

**plan.md와의 차이**: plan.md에는 `PVF --> ARC_RE (재보강 max 1회) --> PVE (에스컬레이션)` 경로가 있다.

**수정안**: VAL_PV 뒤에 `{PASS/FAIL}` 분기를 추가. FAIL 시 architect 재보강(max 1회) 또는 `PLAN_VALIDATION_ESCALATE` 연결.

---

### G-4. [INCONSISTENCY] KNOWN_ISSUE 발동 임계값 불일치 (GAP_AUDIT A-2 대응)

**현황**:
- bugfix.md 다이어그램 KI 노드 (line 31): `"1회 분석 원인 불가"` (현재 버전에서는 이미 "1회"로 수정됨)
- orchestration-rules.md 에스컬레이션 테이블 (line 36): `"1회 분석으로 원인 특정 불가"`
- GAP_AUDIT_REPORT A-2는 "원인 특정 3회 실패"라고 기재했는데, 현재 bugfix.md에는 3회라는 표현이 없다.

**분석**: 현재 bugfix.md와 orchestration-rules.md는 모두 "1회"로 일치한다. GAP_AUDIT가 이전 버전을 기준으로 작성되었을 가능성이 있다. 단, qa.md의 KNOWN_ISSUE 판정 기준은 "3가지 조건을 모두 만족"하는 별도 판별 로직이다. 여기서 혼동이 발생할 수 있다.

**수정안**: bugfix.md의 KI 노드 텍스트를 `"KNOWN_ISSUE\n(qa 3가지 판정 조건 충족)"` 등으로 qa.md의 판정 기준을 참조하게 변경. "1회 분석 원인 불가"라는 표현은 재시도 횟수처럼 오해될 수 있다.

---

### G-5. [GAP] BUGFIX_PLAN_READY 마커 다이어그램 미반영 (GAP_AUDIT A-3 대응)

**현황**: 마커 테이블에 `BUGFIX_PLAN_READY | architect | engineer 코드 수정`이 있으나, Mermaid 다이어그램에서는 `ARC_BF -->|"qa_report, issue"| ENG` 직결이다. 중간 마커 노드가 없다.

**architect/bugfix-plan.md와의 확인**: bugfix-plan.md 출력 형식에 `BUGFIX_PLAN_READY` 마커가 명시되어 있다. 다이어그램만 누락.

**수정안**: `ARC_BF --> BFPR["BUGFIX_PLAN_READY"] --> ENG` 형태로 중간 마커 노드 추가. 하네스 스크립트에서 이 마커를 파싱해 impl_path를 engineer에게 전달하는 구간이 필요하다.

---

### G-6. [INCONSISTENCY] Plan Validation 적용 불일치 (GAP_AUDIT C-1 대응)

**현황**: bugfix.md의 SPEC_ISSUE 경로에서는 `ARC_MP --> VAL_PV --> IMPL_ENTRY`로 Plan Validation을 수행한다. 그러나 다른 루프(tech-epic.md, design.md)에서는 같은 MODULE_PLAN인데 VAL_PV를 스킵한다.

**bugfix 관점 영향**: bugfix SPEC_ISSUE는 Plan Validation을 수행하는 것이 올바르다 (구현 누락 = 코드 결함이므로 impl 품질이 중요). 문제는 다른 루프와의 일관성이며, bugfix 자체의 수정은 불필요하다. 단, VAL_PV FAIL 분기가 없는 점(G-3)은 수정 필요.

---

### G-7. [GAP] test-engineer 부재 — 회귀 테스트 작성 주체 불명 (GAP_AUDIT C-3 대응)

**현황**:
- impl.md: test-engineer 에이전트가 테스트 작성 -> vitest (ground truth)
- bugfix.md: test-engineer 없음 -> vitest "직접 실행"

**질문**: 누가 새 회귀 테스트를 작성하는가?
- architect/bugfix-plan.md의 수용 기준에 `(TEST)` 태그가 있다면, 그에 대응하는 테스트는 누가 만드는가?
- engineer가 코드 수정 + 테스트까지 작성한다면, engineer.md에 그 지시가 있는가? -> 없다. engineer.md Phase 2는 "계획 파일을 유일한 기준으로" 구현한다고만 되어 있고, 테스트 작성 책임은 별도 언급이 없다.

**수정안**: 두 가지 선택지가 있다.
1. **경량 옵션**: engineer에게 bugfix 시 regression test 작성을 명시적으로 위임. bugfix-plan.md의 수용 기준 `(TEST)` 항목에 대한 테스트 파일을 engineer가 작성한다고 bugfix.md에 명시.
2. **완전 옵션**: bugfix에도 test-engineer 단계를 추가. 단, LLM 호출이 1회 증가하므로 경량성과 트레이드오프.

**권장**: 선택지 1 (경량 옵션). 버그 수정 테스트는 대체로 단순(입력-출력 쌍)하므로 engineer가 함께 작성하는 것이 효율적이다. 단, bugfix.md와 engineer.md 양쪽에 이 책임 명시가 필요하다.

---

## 비효율/과잉 분석

### I-1. [INEFFICIENCY] 모든 FUNCTIONAL_BUG에 architect 경유 — 단순 버그에 과잉

**현황**: FUNCTIONAL_BUG는 무조건 `architect BUGFIX_PLAN -> engineer -> vitest -> validator` 4단계를 거친다.

**문제**: 단순 오타, off-by-one 에러, 조건문 반전 등 원인이 명백하고 수정이 1-2줄인 버그에도 architect가 계획 파일을 작성하고 validator가 6항목 체크리스트를 수행한다. LLM 3회 호출(architect + engineer + validator)이 최소.

**빅테크 비교**: Google에서 P3/P4 단순 버그는 CL(changelist) 작성 -> 리뷰어 1명 -> submit. 별도 계획 문서 없음.

**수정안**: qa의 `AFFECTED_FILES`와 `SEVERITY`를 조합한 경량 분기 추가.

```
AFFECTED_FILES = 1 AND SEVERITY = LOW → architect 스킵, engineer 직접 수정 → vitest → validator
AFFECTED_FILES >= 2 OR SEVERITY >= MEDIUM → 현행 유지 (architect 경유)
```

또는 기존 depth 체계를 활용: `SEVERITY:LOW + AFFECTED_FILES:1 -> depth=fast (architect 스킵)`.

---

### I-2. [INEFFICIENCY] qa에서 vitest "직접 실행" vs impl 루프의 test-engineer + vitest

**현황**: bugfix 루프에서는 engineer 후 vitest를 "직접 실행"하고, impl 루프에서는 test-engineer가 테스트를 작성한 후 vitest를 실행한다.

**차이가 발생하는 이유**: bugfix는 "기존 테스트가 있다"는 가정하에 vitest만 돌리는 것. impl은 "새 기능이므로 테스트도 새로 작성"해야 하는 것.

**문제**: 이 가정이 맞지 않는 경우가 있다. 기존 테스트가 없는 코드의 버그를 수정하면, vitest 직접 실행은 해당 모듈에 대한 테스트 없이 전체 suite만 돌리게 된다. 이 경우 회귀 테스트가 부재하다. G-7과 연결.

---

### I-3. [INEFFICIENCY] DESIGN_ISSUE의 불필요한 중복 라우팅

**현황**: bugfix.md에 `QA_ROUTE -->|DESIGN_ISSUE| SE`로 SCOPE_ESCALATE로 보내면서, 동시에 분류 테이블에는 "DESIGN_ISSUE | 관련 파일 >= 1 | -> 디자인 루프 | designer -> design-critic -> engineer"라고 되어 있다.

**분석**: 다이어그램에서는 DESIGN_ISSUE가 SE(SCOPE_ESCALATE)로 가는데, 테이블에서는 디자인 루프로 가는 것으로 기재. 다이어그램과 테이블이 불일치한다. 다이어그램이 정확하다면 DESIGN_ISSUE는 항상 에스컬레이션이고, 테이블이 정확하다면 별도 디자인 루프 진입점이 다이어그램에 필요하다.

**수정안**: 의도를 확정 후 다이어그램 또는 테이블 중 하나를 수정. 현실적으로 UI 결함(폰트, 문구, 레이아웃)은 디자인 루프로 라우팅하는 것이 맞으므로 다이어그램에 `QA_ROUTE -->|DESIGN_ISSUE| DESIGN_LOOP["-> 디자인 루프 진입"]` 노드를 추가하는 것이 적절하다.

---

### I-4. [INEFFICIENCY] severity -> depth 연동이 HIGH만 정의

**현황**: severity 테이블에 `HIGH -> std 강제 (fast 금지)`, `MEDIUM/LOW -> 기존 로직`만 있다.

**문제**: "기존 로직 (TYPE + AFFECTED_FILES 기반)"이라고 되어 있지만, bugfix 루프에는 depth 자동 선택 규칙이 없다 (impl.md에만 있음). bugfix에서 fast/std/deep 중 어떤 것을 사용하는지, bugfix에도 depth 개념이 적용되는지 불명확.

**수정안**: bugfix의 depth 적용 방식을 명시. 예: "bugfix는 기본 std. SEVERITY:HIGH는 std 강제(이미 기본이므로 실질적으로 fast 금지). SEVERITY:LOW + AFFECTED_FILES=1이면 I-1의 경량 분기 적용 가능."

---

## 빅테크 벤치마크 기반 개선안

### BT-1. [IMPROVEMENT] 심각도 기반 라우팅 (Severity-Based Routing)

**Google P0-P4 / Meta SEV 시스템 비교**:
- Google P0 (서비스 다운): 자동 페이저 -> oncall 직접 핫픽스 -> 사후 postmortem
- Google P1 (주요 기능 장애): 1일 이내 수정 -> 간소화된 리뷰
- Google P3-P4 (UI 결함, 미관 이슈): 정상 CL 프로세스, 계획 문서 없음
- Meta SEV-1: 자동 에스컬레이션 -> VPe 통보 -> war room
- Meta SEV-4: 일반 태스크로 처리

**현재 bugfix 루프**: severity(LOW/MEDIUM/HIGH)가 있지만, 라우팅 경로에 영향을 주는 곳이 `HIGH -> std 강제` 하나뿐. 모든 FUNCTIONAL_BUG가 동일 파이프라인.

**제안**: 3단 라우팅

| Severity | 경로 | 근거 |
|---|---|---|
| HIGH | architect -> engineer -> vitest -> validator (현행 유지) | 영향 범위가 넓으므로 계획 필수 |
| MEDIUM | engineer 직접 -> vitest -> validator (architect 스킵) | 원인이 특정되어 있으므로 계획 과잉 |
| LOW (AFFECTED_FILES=1) | engineer 직접 -> vitest (validator 스킵) | 1파일 수정에 LLM 3회는 과잉 |

**리스크**: LOW에서 validator 스킵 시 회귀 버그를 놓칠 수 있다. 단, vitest가 ground truth 역할을 하므로 테스트 커버리지가 있는 모듈은 vitest로 충분. 테스트 미존재 모듈은 MEDIUM으로 격상 규칙 추가.

---

### BT-2. [IMPROVEMENT] 회귀 테스트 필수화 (Mandatory Regression Test for Bugfix)

**Google 프랙티스**: "Every bugfix CL must include a test that would have caught the bug." Google의 코드 리뷰에서 테스트 없는 버그픽스 CL은 거의 무조건 LGTM 거부.

**Meta 프랙티스**: 유사하게, diff에 테스트가 포함되지 않으면 "test plan?" 코멘트가 자동 생성.

**현재**: bugfix 루프에 테스트 작성 주체가 불명확(G-7). vitest "직접 실행"은 기존 테스트만 돌리는 것.

**제안**:
1. bugfix-plan.md의 수용 기준에 `(TEST)` 태그가 있으면 engineer가 해당 테스트를 반드시 작성
2. validator BUGFIX_VALIDATION의 체크리스트에 "새 regression test 존재 여부" 항목 추가
3. 기존 테스트가 없는 모듈의 버그 수정 시, 최소 1개의 regression test 작성을 강제

**리스크**: 낮음. engineer의 작업량이 소폭 증가하지만, 회귀 방지 효과가 크다.

---

### BT-3. [IMPROVEMENT] 근본 원인 분석 (Root Cause Analysis) 단계 추가

**Google postmortem / Meta SEV review**: 버그 수정 후 "왜 이 버그가 발생했는가?"를 체계적으로 분석.
- 코드 리뷰에서 왜 잡지 못했나?
- 테스트가 왜 없었나?
- 설계 단계에서 예방할 수 있었나?

**현재**: 버그 수정 후 COMMIT -> HARNESS_DONE. 재발 방지 분석이 없다.

**제안**: SEVERITY:HIGH 버그에 대해서만 commit 후 간단한 RCA 메타데이터 기록.

```
## RCA (commit 직후, engineer 또는 qa가 작성)
- root_cause_category: logic_error | missing_validation | race_condition | spec_ambiguity | ...
- prevention: test_added | spec_clarified | design_updated | ...
- affected_module: src/path/to/module
```

이 데이터가 `harness-memory.md`에 축적되면 정책 7(실패 패턴 자동 프로모션)과 결합해 반복 패턴을 조기 차단할 수 있다.

**리스크**: 중간. 모든 버그에 적용하면 과잉이므로 HIGH만 권장. 메타데이터 구조를 단순하게 유지해야 한다.

---

### BT-4. [IMPROVEMENT] 롤백 전략 (Rollback Strategy) 부재

**Google**: 핫픽스 CL에 문제가 발견되면 즉시 롤백 CL을 submit. "roll forward or roll back" 의사결정이 명시적.

**Meta**: SEV 대응 시 첫 번째 옵션은 항상 "can we revert?" 롤백이 불가능할 때만 forward fix.

**현재**: 버그 수정이 새 버그를 도입할 경우의 경로가 없다.
- BUGFIX_PASS 후 merge -> 새 버그 발견 -> ?
- 다시 bugfix 루프에 진입? 하지만 이미 merge된 상태에서의 롤백 절차가 없다.

**제안**: bugfix.md에 롤백 정책 섹션 추가.

```
## 롤백 정책
- merge 후 24시간 이내 동일 모듈에서 새 버그 발견 시: git revert (force push 금지)로 즉시 롤백
- 롤백 후 원본 버그 + 새 버그를 함께 분석하는 새 bugfix 루프 진입
- SEVERITY:HIGH 버그의 수정은 merge 후 "관찰 기간"을 유저에게 알림
```

**리스크**: 낮음. 정책 추가 수준이며 하네스 스크립트 변경은 최소.

---

### BT-5. [IMPROVEMENT] 멀티모듈 버그 대응 (Cross-Module Bug)

**현재**: bugfix 루프는 단일 모듈 스코프를 가정한다. architect/bugfix-plan.md의 구조도 단일 파일/함수 원인 특정을 전제로 한다.

**문제**: 실제 빅테크에서 가장 어려운 버그는 모듈 경계에서 발생한다. A 모듈의 상태 변경이 B 모듈에 예상치 못한 영향을 미치는 경우.

**현재 동작 추정**: qa가 AFFECTED_FILES >= 2로 보고 -> architect가 여러 파일을 bugfix-plan에 포함 -> engineer가 수정. 하지만 bugfix-plan.md의 구조는 "원인: 파일 1개, 함수 1개"로 되어 있다.

**제안**:
1. bugfix-plan.md 템플릿에 멀티파일 원인을 기술할 수 있는 구조 추가 (원인 파일 목록)
2. AFFECTED_FILES >= 3이면 architect BUGFIX_PLAN 대신 MODULE_PLAN으로 격상 (아키텍처 수준 분석 필요)
3. 이 격상 기준을 bugfix.md 분류 테이블에 명시

**리스크**: 중간. 격상 기준이 너무 낮으면(2파일) 과잉이 되고, 너무 높으면(5파일) 놓치게 된다. 3파일이 합리적 시작점.

---

### BT-6. [IMPROVEMENT] bugfix에도 depth 개념 공식화

**현재**: bugfix.md에 severity -> depth 매핑이 있지만, depth가 실질적으로 어떤 단계를 스킵하는지 불명확(I-4 연결).

**제안**: impl.md의 depth 체계를 bugfix에도 공식 적용.

| bugfix depth | 실행 단계 | 조건 |
|---|---|---|
| fast | engineer -> vitest -> commit -> merge | SEVERITY:LOW, AFFECTED_FILES=1 |
| std | architect -> engineer -> vitest -> validator -> commit -> merge | 기본값 |
| deep | architect -> engineer -> vitest -> validator -> pr-reviewer -> commit -> merge | SEVERITY:HIGH 또는 보안 관련 버그 |

이렇게 하면 BT-1(심각도 기반 라우팅)이 depth 체계 안에 자연스럽게 흡수된다.

---

### BT-7. [IMPROVEMENT] FUNCTIONAL_BUG 외 분류 확장 가능성

**현재 4-way**: FUNCTIONAL_BUG, SPEC_ISSUE, DESIGN_ISSUE, KNOWN_ISSUE

**누락 가능 분류**:

| 분류 | 현재 처리 | 문제 |
|---|---|---|
| PERFORMANCE_BUG | 분류 없음 -> FUNCTIONAL_BUG로 처리? | 성능 버그는 프로파일링이 필요하며, 단순 코드 수정과 접근이 다름 |
| REGRESSION | architect/bugfix-plan.md 진입 조건에 REGRESSION이 있으나 qa 분류에는 없음 | qa가 REGRESSION을 판별하지 못하면 bugfix-plan.md의 진입 조건이 작동하지 않음 |
| SECURITY_BUG | 분류 없음 | 보안 버그는 공개 이슈 생성이 부적절할 수 있고, security-reviewer 경유가 필요 |
| INTEGRATION_ISSUE | architect/bugfix-plan.md 진입 조건에 있으나 qa 분류에 없음 | REGRESSION과 동일 문제 |

**가장 중요한 불일치**: architect/bugfix-plan.md의 진입 조건에 `REGRESSION (모든 심각도)`, `INTEGRATION_ISSUE (모든 심각도)`가 있으나, qa.md의 출력 마커에 이 두 분류가 없다. qa는 FUNCTIONAL_BUG / SPEC_ISSUE / DESIGN_ISSUE / KNOWN_ISSUE 4가지만 출력한다.

**수정안**:
- 최소: architect/bugfix-plan.md의 진입 조건에서 REGRESSION과 INTEGRATION_ISSUE를 제거하고 FUNCTIONAL_BUG에 통합
- 확장: qa.md에 REGRESSION, SECURITY_BUG 분류를 추가하고 라우팅 경로 정의

**리스크**: 확장 시 qa 분류 로직이 복잡해짐. 현재 구조의 단순성이 장점이므로 최소 옵션 권장.

---

### BT-8. [IMPROVEMENT] bugfix.md의 design_doc 파라미터 출처 불명

**현황**: SPEC_ISSUE 경로에서 `ARC_MP -->|"design_doc, module"| VAL_PV`로 되어 있다. architect MODULE_PLAN의 @PARAMS에 `"design_doc": "SYSTEM_DESIGN_READY 문서 경로"`가 필수이다.

**문제**: bugfix 컨텍스트에서 design_doc은 어디서 오는가? bugfix는 qa 리포트에서 시작되므로 SYSTEM_DESIGN_READY 문서 경로가 당연히 존재하지 않는다.

**추정**: 하네스가 프로젝트의 기존 `docs/architecture.md` 경로를 자동으로 주입하는 것으로 보이나, bugfix.md에 이 동작이 명시되어 있지 않다.

**수정안**: bugfix.md의 SPEC_ISSUE 경로에 "design_doc = 프로젝트 기존 설계 문서 경로 (하네스가 자동 주입)" 주석 추가. 또는 ARC_MP 호출 시 파라미터 매핑을 명시.

---

## 구체적 수정 제안

아래는 우선순위 순 수정 제안. 각 항목에 what/why/risk를 명시한다.

### 1순위: 안전성 (무한루프·데이터 손실 방지)

| # | What | Why | Risk | 난이도 | 관련 항목 |
|---|---|---|---|---|---|
| P1 | ENG_RETRY 한도 초과 시 `IMPLEMENTATION_ESCALATE` 또는 `BUGFIX_ESCALATE` 연결 | 무한 루프 방지 | 없음 | 낮음 | G-1 |
| P2 | COMMIT-HD 사이에 MERGE + MERGE_CONFLICT_ESCALATE 추가 | 브랜치 전략 정합성. 없으면 코드가 feature branch에 갇힘 | 없음 | 낮음 | G-2 |
| P3 | VAL_PV FAIL 분기 추가 (재보강 max 1회 -> PLAN_VALIDATION_ESCALATE) | SPEC_ISSUE 경로의 데드엔드 방지 | 없음 | 낮음 | G-3 |

### 2순위: 정합성 (명세 간 불일치 해소)

| # | What | Why | Risk | 난이도 | 관련 항목 |
|---|---|---|---|---|---|
| P4 | BUGFIX_PLAN_READY 마커 노드를 다이어그램에 추가 | 마커 테이블-다이어그램 일치 | 없음 | 낮음 | G-5 |
| P5 | DESIGN_ISSUE 다이어그램 경로를 디자인 루프 진입으로 수정 (SE가 아닌 별도 노드) | 다이어그램-테이블 불일치 해소 | 다이어그램 구조 변경 | 낮음 | I-3 |
| P6 | architect/bugfix-plan.md 진입 조건에서 REGRESSION/INTEGRATION_ISSUE 제거 또는 qa에 해당 분류 추가 | qa 출력 마커에 없는 분류가 architect 진입 조건에 있으면 데드코드 | 분류 확장 시 qa 복잡도 증가 | 중간 | BT-7 |
| P7 | SPEC_ISSUE 경로의 design_doc 파라미터 출처 명시 | 하네스 구현자가 어떤 값을 주입해야 하는지 불명확 | 없음 | 낮음 | BT-8 |

### 3순위: 효율성 (불필요한 LLM 호출 감소)

| # | What | Why | Risk | 난이도 | 관련 항목 |
|---|---|---|---|---|---|
| P8 | severity+AFFECTED_FILES 기반 경량 분기 추가 (LOW+1파일 -> architect 스킵) | 단순 버그에 LLM 3회 -> 2회 절감 | 간단한 버그를 잘못 판정하면 품질 저하 | 중간 | I-1, BT-1 |
| P9 | bugfix depth 체계 공식화 (fast/std/deep 매핑 테이블) | depth 개념이 impl에만 있고 bugfix에 없어 혼란 | 다이어그램 복잡도 증가 | 중간 | I-4, BT-6 |

### 4순위: 프랙티스 강화 (빅테크 수준)

| # | What | Why | Risk | 난이도 | 관련 항목 |
|---|---|---|---|---|---|
| P10 | engineer의 bugfix 시 regression test 작성 의무화 | Google "every bugfix must include a test" | engineer 작업량 소폭 증가 | 낮음 | G-7, BT-2 |
| P11 | validator BUGFIX_VALIDATION에 "새 regression test 존재 여부" 항목 추가 | P10의 게이트 역할 | 없음 | 낮음 | BT-2 |
| P12 | SEVERITY:HIGH에 대해 RCA 메타데이터 기록 단계 추가 | 재발 방지. harness-memory.md와 결합 시 패턴 탐지 가능 | 과잉 적용 시 오버헤드 | 중간 | BT-3 |
| P13 | 롤백 정책 섹션 추가 (git revert 기반, force push 금지) | merge 후 새 버그 발견 시 대응 절차 부재 | 정책 수준이므로 실질 리스크 없음 | 낮음 | BT-4 |
| P14 | 멀티모듈 버그 격상 기준 추가 (AFFECTED_FILES >= 3 -> MODULE_PLAN 격상) | 크로스모듈 버그는 단일 파일 bugfix-plan 구조로 부족 | 격상 기준이 부정확할 수 있음 | 중간 | BT-5 |
