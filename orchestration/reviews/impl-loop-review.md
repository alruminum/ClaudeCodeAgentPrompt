# Impl Loop (구현 루프) 상세 리뷰

> 작성일: 2026-04-09
> 대상: `orchestration/impl.md` + 관련 에이전트 6종 + `orchestration-rules.md` + `GAP_AUDIT_REPORT.md`
> 벤치마크: Google CL Review / Presubmit / TAP, Meta Diff Review / Sandcastle / Land Queue
> 분류: GAP (누락), INCONSISTENCY (불일치), INEFFICIENCY (비효율), IMPROVEMENT (개선제안)

---

## 요약

구현 루프는 depth 3단계(fast/std/deep), SPEC_GAP 분기, TE_SELF 자체수정, 실패유형별 라우팅 등 상당히 정교한 설계다. 그러나 교차 검증 결과 **다이어그램-테이블 모순 3건, 미정의 종착점 2건, 카운터 설계 결함 2건, 빅테크 대비 부재 단계 3건**이 식별되었다. GAP_AUDIT_REPORT에서 지적된 impl 관련 항목(A-1, A-4, A-5, B-2, B-3, C-2, D-3) 중 해결된 것은 없으며 일부는 실행 시 무한루프 또는 데드락을 유발할 수 있다.

가장 심각한 구조적 문제는 **(1) 단일 attempt 카운터가 이질적 실패유형을 동일 취급하는 것**, **(2) SPEC_GAP 리셋이 무한 오실레이션 가능성을 열어두는 것**, **(3) TE_SELF max 2회 초과 시 종착점 부재**다.

---

## 갭/불일치 분석

### G-1. [GAP] fast depth 다이어그램에 테스트 스킵 분기 노드 부재 (GAP_AUDIT B-2)

**현상**: 다이어그램의 SRC_CHK --> YES는 무조건 TE(test-engineer) 진입. depth에 따른 분기가 없다. fast depth는 "테스트/보안 스킵"이라 명시하지만, 실제 다이어그램에는 depth 분기가 SRC_CHK와 TE 사이에 존재하지 않는다. DEPTH_CHK 노드는 validator 이후에만 존재한다.

**영향**: 하네스 스크립트가 다이어그램을 따르면 fast에서도 test-engineer를 호출하게 되거나, 스크립트 구현자가 다이어그램 외 로직을 암묵적으로 추가해야 한다. 명세와 구현의 괴리.

**수정안**: SRC_CHK --> YES 이후에 `DEPTH_CHK_TE{{"depth?"}}` 분기 노드 추가. fast --> VAL_CV 직결, std/deep --> TE 진입.

### G-2. [GAP] TE_SELF max 2회 초과 시 종착점 미정의 (GAP_AUDIT B-3)

**현상**: `TE_SELF["test-engineer 자체 수정\n(max 2회, attempt 불변)"]` --> TE로만 재연결. test-engineer.md 제약 섹션에는 "2회 초과 시 SPEC_GAP_FOUND로 메인 Claude에 에스컬레이션"이라 기재되어 있으나, 다이어그램에 이 경로가 없다. FLAKY 2회 수정 후 재현 시 IMPLEMENTATION_BUG로 재분류한다는 정책도 다이어그램 미반영.

**영향**: 하네스 스크립트가 TE_SELF 2회 초과 후 무한루프에 빠지거나, 에이전트가 자체 판단으로 중단해야 하는 비구조적 상황 발생.

**수정안**: TE_SELF --> `TE_LIMIT{{"TE_SELF 횟수 > 2?"}}` 분기 추가.
- YES + FLAKY --> IMPLEMENTATION_BUG로 재분류 --> FAIL_ROUTE
- YES + TEST_CODE_BUG --> FAIL_ROUTE (fail_type: test_infra_fail 신규)
- NO --> TE 재시도

### G-3. [GAP] fast depth 테이블에 pr-reviewer 포함 (GAP_AUDIT A-1)

**현상**: depth 테이블 line 11: `fast: engineer --> validator --> pr-reviewer --> commit --> merge`. 그러나 다이어그램 DEPTH_CHK는 `std/fast --> COMMIT` (pr-reviewer 스킵). 머지 조건도 fast = "없음".

**영향**: fast depth의 정의가 3곳(depth 테이블, 다이어그램, 머지 조건)에서 2:1로 불일치. depth 테이블이 틀렸을 가능성이 높지만 명시적 정정이 필요.

**수정안**: depth 테이블의 fast 시퀀스를 `engineer --> validator --> commit --> merge (LLM 2회)` 로 정정. pr-reviewer 제거.

### G-4. [GAP] VALIDATION_ESCALATE 마커 미사용 (GAP_AUDIT A-4)

**현상**: orchestration-rules.md 에스컬레이션 테이블에 `VALIDATION_ESCALATE | validator Code Validation (3회 초과)` 정의됨. validator/code-validation.md에도 "재검증 최대 3회, 초과 시 VALIDATION_ESCALATE" 명시. 그러나 impl.md 다이어그램에서 validator FAIL은 FAIL_ROUTE --> attempt++ 경로만 존재. validator 자체의 3회 카운터는 attempt 카운터에 병합되어 VALIDATION_ESCALATE는 발행되지 않는다.

**영향**: 에이전트 정의와 루프 다이어그램의 모순. validator가 VALIDATION_ESCALATE를 발행해도 하네스가 처리하지 않거나, validator가 자체 카운터를 관리하지 않고 항상 단일 PASS/FAIL만 반환할 가능성.

**수정안**: 두 가지 선택지:
- (A) validator 자체 3회 카운터를 폐기하고, 루프의 attempt 카운터에 통합. VALIDATION_ESCALATE를 에스컬레이션 테이블에서 제거. validator/code-validation.md에서 재시도 한도 섹션 삭제.
- (B) validator 내부 루프를 다이어그램에 명시. VAL_CV --> VAL_RESULT 사이에 `VAL_RETRY{{"val_attempt < 3?"}}` 분기 추가. 3회 초과 시 VALIDATION_ESCALATE 직결 (FAIL_ROUTE 우회).
- 권장: **(A)**. 이유: 현재 구조에서 attempt 카운터가 이미 3회 제한을 걸고 있어, validator 내부에 별도 3회 카운터를 두면 최악의 경우 9회(3 validator x 3 attempt) 반복이 가능하며 이는 과도하다.

### G-5. [GAP] REVIEW_LOOP_ESCALATE 마커 미사용 (GAP_AUDIT A-5)

**현상**: orchestration-rules.md에 `REVIEW_LOOP_ESCALATE | pr-reviewer (3라운드 초과)` 정의됨. pr-reviewer.md에도 "최대 3라운드, 초과 시 REVIEW_LOOP_ESCALATE" 명시. 그러나 impl.md에서 pr-reviewer CHANGES_REQUESTED는 FAIL_ROUTE --> attempt++ 경로만 존재. pr-reviewer 자체 라운드 카운터가 다이어그램에 없다.

**영향**: G-4와 동일 구조. pr-reviewer가 내부적으로 3라운드를 세더라도 하네스가 REVIEW_LOOP_ESCALATE를 처리하는 경로가 없다.

**수정안**: G-4와 동일 논리. pr-reviewer 내부 라운드 카운터를 폐기하고 attempt 카운터에 통합하거나, deep mode 전용으로 pr-reviewer 내부 루프를 다이어그램에 명시. 권장: 폐기 후 통합.

### G-6. [GAP] 정책 8 수용 기준 메타데이터 감사 2단계 미반영 (GAP_AUDIT C-2)

**현상**: orchestration-rules.md 정책 8은 Plan Validation 후 별도의 "수용 기준 메타데이터 감사" 단계를 명시한다:
```
validator [Plan Validation]
  ↓ PASS
validator [수용 기준 메타데이터 감사]  ← 정책 8 게이트
  ↓ PASS
READY_FOR_IMPL
```
그러나 validator/plan-validation.md에서는 체크리스트 C가 "수용 기준 메타데이터 감사"를 Plan Validation 내부에 통합하고 있다. impl.md 다이어그램에도 이 2단계가 반영되지 않았다.

**영향**: 실질적으로 Plan Validation 체크리스트 C가 메타데이터 감사를 수행하므로 기능적 갭은 없을 수 있다. 그러나 orchestration-rules.md의 정책 8 도해와 validator 구현이 불일치하여 어느 것이 정본인지 혼동.

**수정안**: orchestration-rules.md 정책 8의 도해를 Plan Validation 내부 체크리스트 C로 통합된 것을 반영하도록 수정. "별도 호출이 아닌 Plan Validation 체크리스트 C로 수행됨" 주석 추가.

### G-7. [GAP] vitest 실패 시 fail_type 자동 지정 불명확 (GAP_AUDIT D-3)

**현상**: 실패 유형별 수정 전략 테이블에 `test_fail`이 있으나, VITEST --> 실패 --> FAIL_ROUTE 경로에서 이 fail_type이 자동 지정되는지 불명확. test-engineer IMPLEMENTATION_BUG와 vitest 직접 실패가 동일 `test_fail`인지도 미정의.

**영향**: engineer 재시도 시 컨텍스트가 부정확할 수 있다. test-engineer가 분류한 IMPLEMENTATION_BUG는 "구현 로직 문제"이고, vitest ground truth 실패는 "LLM 테스트가 아닌 실제 테스트 실패"인데 같은 fail_type으로 처리하면 engineer에게 전달되는 지시가 동일해진다.

**수정안**: fail_type을 세분화:
- `test_fail_te`: test-engineer 판정 IMPLEMENTATION_BUG --> 테스트 코드 소스 포함 전달
- `test_fail_vitest`: vitest ground truth 실패 --> vitest 출력 전체 전달
또는 최소한 다이어그램 VITEST --> 실패 경로에 `fail_type = "test_fail"` 라벨 명시.

---

## 비효율/과잉 분석

### I-1. [INEFFICIENCY] 단일 attempt 카운터가 이질적 실패유형을 동일 취급

**현상**: test_fail, validator_fail, pr_fail, security_fail 모두 같은 attempt 카운터를 공유한다. 3회 제한에서:
- attempt 1: test_fail (구현 버그)
- attempt 2: validator_fail (스펙 누락)
- attempt 3: pr_fail (코드 품질)
이 경우 3가지 **완전히 다른 문제**가 각 1회씩 발생했을 뿐인데 IMPLEMENTATION_ESCALATE로 에스컬레이션된다.

**빅테크 비교**:
- Google CL: 프리서밋 실패(빌드, 테스트, 린트)와 코드 리뷰 라운드는 별개 카운터. 프리서밋은 무제한 재시도, 코드 리뷰는 사실상 무제한 라운드.
- Meta Diff: Sandcastle CI 실패와 diff 리뷰는 독립. land queue 진입 조건만 충족하면 됨.

**수정안**: 실패 유형별 독립 카운터 도입:
| 카운터 | 제한 | 초과 시 |
|---|---|---|
| `test_attempt` | 3 | IMPLEMENTATION_ESCALATE |
| `validator_attempt` | 2 | SPEC_GAP 자동 트리거 (architect에게 넘기기) |
| `pr_attempt` | 3 | REVIEW_LOOP_ESCALATE |
| `security_attempt` | 2 | IMPLEMENTATION_ESCALATE |

총 attempt는 safety cap으로 별도 유지 (예: 총 6회). 이렇게 하면 각 유형별로 충분한 재시도를 허용하면서도 무한 루프를 방지한다.

### I-2. [INEFFICIENCY] SPEC_GAP 리셋이 무한 오실레이션 허용

**현상**: SPEC_GAP_FOUND --> architect --> SPEC_GAP_RESOLVED --> attempt 카운터 리셋 (max 2회). 그러나:
- 리셋 2회 = attempt 카운터가 최대 2번 0으로 돌아감
- 리셋 1회당 3 attempt = 최대 9회 시도 (3 + reset + 3 + reset + 3)
- engineer가 매번 다른 항목에서 SPEC_GAP를 발견하면 오실레이션 형태

더 근본적으로, SPEC_GAP_FOUND가 "실제 스펙 갭"이 아니라 "engineer가 구현을 못하겠다"는 회피 수단으로 사용될 수 있다. LLM 에이전트는 인간과 달리 "모르겠으면 갭이라고 하자"는 패턴을 학습할 수 있다.

**수정안**:
- (A) 리셋 대신 "SPEC_GAP는 attempt를 소비하지 않되, 별도 spec_gap_count 카운터(max 2)로 관리"
- (B) SPEC_GAP 후 architect가 impl을 보강하면 attempt는 리셋하되, **총 리셋 포함 attempt 상한 (total_attempt <= 6)** 을 별도로 건다
- 권장: **(A)**. 리셋이라는 개념 자체를 제거하면 로직이 단순해진다.

### I-3. [INEFFICIENCY] SRC_CHK 노드의 존재 의의

**현상**: SRC_CHK{{"src/** 변경 있음?"}} --> NO --> VAL_CV. 질문: engineer가 src/를 변경하지 않는 경우가 언제인가?

가능한 시나리오:
- engineer가 SPEC_GAP_FOUND만 반환하고 코드 변경 없이 종료 --> 그러나 이 경우 SPEC_CHK에서 이미 분기됨
- engineer가 docs/ 또는 config만 변경 --> 그러나 engineer의 허용 경로는 `src/**`만
- engineer가 "변경 불필요" 판단 --> 이 경우 PASS로 빠져야 하는데, 다이어그램상 VAL_CV를 거치게 됨

**수정안**: SRC_CHK가 커버하는 시나리오를 주석으로 명시하거나, 실제 발생하지 않는 분기라면 제거. 가능성이 있다면 (예: 설정 파일만 변경), engineer 허용 경로 매트릭스와 일관성 확인 필요.

### I-4. [INEFFICIENCY] validator --> pr-reviewer --> security-reviewer 순서 (deep)

**현상**: deep mode: validator(스펙 일치) --> pr-reviewer(코드 품질) --> security-reviewer(보안).

**빅테크 비교**:
- Google: presubmit(빌드+테스트+린트) --> 코드 리뷰(인간) --> 보안 리뷰(필요 시). 린트가 리뷰 전에 실행됨.
- Meta: Sandcastle(CI) --> diff 리뷰(인간) --> security review(필요 시).

현재 순서에서 pr-reviewer가 네이밍/복잡도 이슈를 발견하면 engineer가 수정하고, security-reviewer는 수정된 코드를 본다. 이 순서는 합리적이다. **그러나** pr-reviewer와 security-reviewer 사이에 의존 관계가 없으므로 병렬 실행이 가능하다.

**수정안**: deep mode에서 pr-reviewer와 security-reviewer를 병렬 실행. LLM 호출 5회 --> 4회로 감소. 단, 둘 다 FAIL이면 engineer에게 합산 피드백 전달. 위험: 병렬 실행이 "정책 4 순차 실행"과 충돌. 정책 변경이 필요하므로 현 단계에서는 정보 제공용.

---

## 빅테크 벤치마크 기반 개선안

### B-1. [IMPROVEMENT] Lint/Format 단계 부재 (Google presubmit 대비)

**현상**: Google의 presubmit은 빌드 --> 린트 --> 포맷 --> 테스트 순서로 자동 실행된다. 현재 impl 루프에는 lint/format 단계가 없다. engineer 완료 게이트에 `npx tsc --noEmit`만 있고, ESLint/Prettier 같은 정적 분석이 없다.

정책 13에 post-commit-scan(console.log, any 타입, TODO 잔류)이 언급되지만 settings.json에 미등록이고 커밋 *후*에 실행된다. 문제 발견이 너무 늦다.

**수정안**: engineer 완료 게이트에 lint 단계 추가:
```
Phase 2.5 — 정적 분석 (커밋 전)
1. npx tsc --noEmit (이미 존재)
2. npx eslint --max-warnings=0 [변경 파일] (존재 시)
3. npx prettier --check [변경 파일] (존재 시)
```
이를 통해 pr-reviewer가 "console.log 남아있음", "포매팅 불일치" 같은 기계적 피드백으로 attempt를 소비하는 것을 방지.

### B-2. [IMPROVEMENT] 3회 attempt 제한의 합리성 (Google CL 무제한 대비)

**현상**: 현재 max 3 attempt. Google CL은 프리서밋 재시도 무제한, 코드 리뷰 라운드도 무제한이다.

**그러나** 이는 인간 엔지니어 기준이다. LLM 에이전트는:
- 같은 실수를 반복할 확률이 인간보다 높다 (hallucination)
- 무제한 재시도는 토큰 비용 폭증으로 이어진다
- 3회 실패 후 인간 개입이 비용 대비 효율적일 수 있다

**결론**: 3회 제한 자체는 LLM 에이전트 맥락에서 합리적이다. 다만 I-1에서 제안한 대로 유형별 카운터로 세분화하는 것이 더 효과적이다.

### B-3. [IMPROVEMENT] fast depth 존재 가치 평가 (Google presubmit 무조건 실행 대비)

**현상**: fast depth는 테스트와 보안 리뷰를 스킵한다. 사용 조건: impl에 `(MANUAL)` 태그만 있을 때, 변수명/설정값 단순 변경.

**빅테크 비교**:
- Google: 모든 CL에 presubmit 필수. 테스트 스킵은 `TEST=none` 명시적 태그 + 리뷰어 승인 필요. 사실상 테스트가 없는 CL은 존재하지만 presubmit 자체를 스킵하지는 않음.
- Meta: Sandcastle CI는 모든 diff에 실행. 작은 diff도 CI 필수.

**위험**:
- "단순 변경"의 경계가 모호. 변수명 변경이 다른 모듈의 import를 깨뜨릴 수 있다.
- `(MANUAL)` 태그는 자동화 불가능한 항목에 사용되므로, 테스트 자체가 없다는 의미가 아니라 "이 특정 수용 기준은 수동 검증"이라는 의미다.
- tsc --noEmit으로 타입 에러는 잡히지만, 런타임 동작 변경은 감지 못함.

**수정안**: fast depth를 완전 폐기하기보다, 최소 게이트를 추가:
- fast에서도 `npx tsc --noEmit` + `vitest run --related [변경 파일]` (영향받는 테스트만 실행)은 필수
- 이를 `fast-with-related-tests` depth로 재정의
- 순수하게 docs/config 변경으로 src/ 변경이 없는 경우에만 현재 fast 유지
- 이 접근은 Google의 "affected tests only" 전략과 유사

### B-4. [IMPROVEMENT] 포스트머지 flow의 수동성

**현상**: MERGE --> HARNESS_DONE --> stories.md 체크 --> USER_REPORT --> git push. 머지 후 stories 체크는 메인 Claude가 수동 수행, push는 유저 승인 대기.

**빅테크 비교**:
- Google: CL이 submit되면 TAP이 post-submit 테스트를 자동 실행. 실패 시 자동 rollback.
- Meta: land queue에서 머지 후 자동 canary deploy + 메트릭 모니터링.

**수정안**: 현 단계에서는 유저 게이트(정책 3)가 의도된 설계이므로 push 자동화는 불필요. 그러나 stories.md 체크는 자동화 가능:
- HARNESS_DONE 수신 시 하네스가 impl_path에서 관련 stories.md를 역추적하여 해당 태스크를 자동 체크 (`[x]`)
- 실패 시에만 메인 Claude에게 보고
이렇게 하면 메인 Claude의 수동 작업 1단계가 제거된다.

### B-5. [IMPROVEMENT] 코드 리뷰 단계의 선택적 활성화 (deep mode)

**현상**: pr-reviewer와 security-reviewer는 deep mode에서만 실행된다. std mode에서는 validator만 통과하면 커밋된다.

**빅테크 비교**:
- Google: 모든 CL에 코드 리뷰 필수 (인간 리뷰어). 보안 리뷰는 LGTM + security tag일 때만.
- Meta: 모든 diff에 코드 리뷰 필수. security review는 특정 디렉토리 변경 시 자동 태그.

**수정안**: std mode에도 pr-reviewer 경량 버전을 추가하는 것을 검토. 예:
- std: pr-reviewer가 MUST FIX만 체크 (NICE TO HAVE 스킵). 1라운드 한정.
- deep: pr-reviewer 전체 체크 + security-reviewer.
이렇게 하면 std에서도 매직 넘버, console.log, 하드코딩 비밀값 같은 치명적 품질 이슈를 잡을 수 있다. 단 LLM 호출이 3회 --> 4회로 증가하므로 비용 트레이드오프.

---

## 구체적 수정 제안

### 수정 1: 다이어그램에 fast depth 테스트 스킵 분기 추가 (G-1)

**대상**: `orchestration/impl.md` Mermaid 다이어그램
**내용**: SRC_CHK --> YES 이후에 depth 분기 노드 삽입

```mermaid
SRC_CHK -->|YES| DEPTH_CHK_TE{{"depth?"}}
DEPTH_CHK_TE -->|fast| VAL_CV
DEPTH_CHK_TE -->|"std/deep"| TE
```

**위험**: 낮음. 다이어그램 수정만으로 기존 동작에 영향 없음.

### 수정 2: TE_SELF 초과 종착점 추가 (G-2)

**대상**: `orchestration/impl.md` Mermaid 다이어그램 + `agents/test-engineer.md`
**내용**:

```mermaid
TE_SELF --> TE_LIMIT{{"TE_SELF > 2?"}}
TE_LIMIT -->|NO| TE
TE_LIMIT -->|"YES + FLAKY"| RECLASS["재분류: IMPLEMENTATION_BUG"]
TE_LIMIT -->|"YES + TEST_CODE_BUG"| FAIL_ROUTE
RECLASS --> FAIL_ROUTE
```

**위험**: 낮음. test-engineer.md에 이미 정책이 기술되어 있으며 다이어그램만 보강.

### 수정 3: depth 테이블 fast 시퀀스 정정 (G-3)

**대상**: `orchestration/impl.md` depth 테이블
**내용**: fast 행을 `engineer --> validator --> commit --> merge (테스트·보안·PR리뷰 스킵)` 로 수정. LLM 호출 횟수를 2회로 명시.

**위험**: 없음. 다이어그램과 머지 조건에 이미 일치하는 방향으로 정정.

### 수정 4: VALIDATION_ESCALATE / REVIEW_LOOP_ESCALATE 처리 명확화 (G-4, G-5)

**대상**: `orchestration/impl.md`, `agents/validator/code-validation.md`, `agents/pr-reviewer.md`, `orchestration-rules.md`
**내용**: 에이전트 자체 재시도 카운터를 폐기하고 루프 attempt 카운터에 통합. 에스컬레이션 테이블에서 VALIDATION_ESCALATE와 REVIEW_LOOP_ESCALATE를 삭제하거나 "reserved for future use"로 변경.

대안으로, 에이전트 내부 카운터를 유지하되 다이어그램에 명시하는 방법도 있으나 복잡도 대비 이점이 적다.

**위험**: 중간. 에이전트 파일과 규칙 파일 동시 수정 필요. 마커 동기화 정책(정책 15)에 따라 에이전트 --> 루프 --> 스크립트 순서로 진행해야 함.

### 수정 5: 실패 유형별 독립 카운터 도입 (I-1)

**대상**: `orchestration/impl.md` 다이어그램 + 하네스 스크립트
**내용**: FAIL_ROUTE 노드를 확장:

```mermaid
FAIL_ROUTE --> FAIL_TYPE_CHK{{"fail_type?"}}
FAIL_TYPE_CHK -->|test_fail| TEST_CTR{{"test_attempt < 3?"}}
FAIL_TYPE_CHK -->|validator_fail| VAL_CTR{{"val_attempt < 2?"}}
FAIL_TYPE_CHK -->|pr_fail| PR_CTR{{"pr_attempt < 3?"}}
FAIL_TYPE_CHK -->|security_fail| SEC_CTR{{"sec_attempt < 2?"}}

TEST_CTR -->|YES| ENG
TEST_CTR -->|NO| IMPL_ESC

VAL_CTR -->|YES| ENG
VAL_CTR -->|NO| SPEC_GAP_AUTO["자동 SPEC_GAP 트리거"]

PR_CTR -->|YES| ENG
PR_CTR -->|NO| REVIEW_ESC["REVIEW_LOOP_ESCALATE"]

SEC_CTR -->|YES| ENG
SEC_CTR -->|NO| IMPL_ESC

TOTAL_CHK{{"총 attempt < 6?"}}
```

추가로 총 attempt safety cap (6회)을 두어 개별 카운터 합산 무한 루프 방지.

**위험**: 높음. 다이어그램 복잡도 증가, 하네스 스크립트 대폭 수정 필요. 단계적 도입 권장: 먼저 test_fail과 나머지를 분리하고, 효과 검증 후 전체 세분화.

### 수정 6: SPEC_GAP 카운터 리셋 폐지 (I-2)

**대상**: `orchestration/impl.md`, `agents/engineer.md`
**내용**: "SPEC_GAP 발생 시 attempt 리셋" 정책을 폐지. 대신:
- SPEC_GAP_FOUND --> architect --> SPEC_GAP_RESOLVED는 attempt를 소비하지 않음 (카운터 동결)
- spec_gap_count 별도 카운터 (max 2) 유지
- 총 attempt (SPEC_GAP 제외)가 3회 도달 시 IMPLEMENTATION_ESCALATE
- spec_gap_count가 2회 도달 시 IMPLEMENTATION_ESCALATE

이렇게 하면:
- 정당한 SPEC_GAP는 attempt를 소비하지 않아 engineer에게 불이익 없음
- 리셋이 없으므로 최대 시도 횟수가 예측 가능 (attempt 3 + spec_gap 2 = 최대 5 라운드)
- 오실레이션 방지

**위험**: 중간. 기존 "리셋" 개념 제거로 하네스 스크립트 수정 필요. 그러나 로직은 단순해진다.

### 수정 7: vitest 실패 fail_type 명시 (G-7)

**대상**: `orchestration/impl.md` 다이어그램 + 실패 유형 테이블
**내용**: `VITEST -->|실패| FAIL_ROUTE` 라벨을 `VITEST -->|"실패 (fail_type=test_fail)"| FAIL_ROUTE` 로 변경. 실패 유형 테이블에 주석 추가: "test-engineer IMPLEMENTATION_BUG와 vitest ground truth 실패 모두 test_fail로 분류. vitest 출력이 fail_context로 전달됨."

**위험**: 없음. 라벨 명시 수준.

### 수정 8: fast depth 최소 테스트 게이트 추가 (B-3)

**대상**: `orchestration/impl.md` depth 테이블 + 다이어그램
**내용**: fast depth 정의를 변경:
- 기존: 테스트 완전 스킵
- 변경: `vitest run --related [변경 파일]` (영향받는 테스트만 실행). test-engineer 호출은 여전히 스킵.

시퀀스: `engineer --> vitest --related --> validator --> commit --> merge`

이렇게 하면:
- 기존 테스트가 깨지는 변경을 감지
- 새 테스트 작성 비용(test-engineer)은 회피
- tsc만으로는 잡히지 않는 런타임 회귀 방지

**위험**: 낮음. vitest --related가 변경 파일 기준으로 최소 테스트만 실행하므로 비용 미미.

---

## 부록: GAP_AUDIT_REPORT impl 관련 항목 처리 상태

| GAP_AUDIT ID | 항목 | 이 리뷰에서의 처리 | 상태 |
|---|---|---|---|
| A-1 | fast depth pr-reviewer 모순 | G-3에서 수정안 제시 | 수정 필요 |
| A-4 | VALIDATION_ESCALATE 미사용 | G-4에서 폐기 또는 명시화 제안 | 수정 필요 |
| A-5 | REVIEW_LOOP_ESCALATE 미사용 | G-5에서 폐기 또는 명시화 제안 | 수정 필요 |
| B-2 | fast depth 테스트 스킵 분기 미반영 | G-1에서 분기 노드 추가 제안 | 수정 필요 |
| B-3 | TE_SELF 종착점 없음 | G-2에서 종착점 추가 제안 | 수정 필요 |
| C-2 | 정책 8 다이어그램 미반영 | G-6에서 주석 추가 제안 | 수정 필요 |
| D-3 | vitest fail_type 미지정 | G-7에서 라벨 명시 제안 | 수정 필요 |

---

## 우선순위 요약 (수정 난이도 x 영향도)

| 순위 | 수정 | 난이도 | 영향도 | 이유 |
|---|---|---|---|---|
| 1 | 수정 2 (TE_SELF 종착점) | 낮음 | 높음 | 미정의 시 무한루프 |
| 2 | 수정 1 (fast 분기 노드) | 낮음 | 높음 | 명세-구현 괴리 원인 |
| 3 | 수정 3 (fast 테이블 정정) | 낮음 | 중간 | 3곳 불일치 해소 |
| 4 | 수정 7 (vitest fail_type) | 낮음 | 중간 | 라벨 명시만으로 해결 |
| 5 | 수정 6 (SPEC_GAP 리셋 폐지) | 중간 | 높음 | 오실레이션 방지 |
| 6 | 수정 4 (에스컬레이션 정리) | 중간 | 중간 | 마커 일관성 확보 |
| 7 | 수정 5 (유형별 카운터) | 높음 | 높음 | 근본 개선이나 복잡도 증가 |
| 8 | 수정 8 (fast 최소 테스트) | 낮음 | 중간 | 안전망 보강 |
